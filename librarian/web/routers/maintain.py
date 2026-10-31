"""Maintain grooming jobs, scan/enrich, and Shelf health."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile

from librarian.audiobookshelf import match_audiobooks
from librarian.auth import require_role
from librarian.backup import backup_dir_for, backup_status
from librarian.calibre_renormalize import assemble_calibre_renormalize
from librarian.cleanup import cleanup_library, restore_quarantine
from librarian.cleanup import read_progress as read_cleanup_progress
from librarian.config import save_settings
from librarian.enrich import enrich_library, friendly_enrich_error
from librarian.enrich_progress import (
    EnrichProgressReporter,
    begin_enrich_run,
    finish_enrich_run,
    is_enrich_running,
    read_enrich_progress,
)
from librarian.extra_files_reprocess_progress import (
    finish_extra_files_reprocess_run,
    is_extra_files_reprocess_stale,
    read_extra_files_reprocess_progress,
)
from librarian.goodreads import MAX_GOODREADS_BYTES, import_goodreads_csv
from librarian.grooming_undo import assemble_grooming_undo, restore_grooming_batch
from librarian.indexer_scorecard import assemble_indexer_scorecard, mute_host
from librarian.ingest_progress import finish_ingest_run, read_ingest_progress
from librarian.morning_brief import assemble_morning_brief
from librarian.purge_shells import purge_shell_works
from librarian.purge_shells_progress import (
    PurgeShellsProgressReporter,
    begin_purge_shells_run,
    finish_purge_shells_run,
    is_purge_shells_running,
    is_purge_shells_stale,
    read_purge_shells_progress,
)
from librarian.review_reasons import REVIEW_EXTRA
from librarian.scan import scan_library
from librarian.scan_progress import (
    ScanProgressReporter,
    begin_scan_run,
    finish_scan_run,
    is_scan_running,
    read_scan_progress,
)
from librarian.screen_leftovers import screen_leftover_report
from librarian.shelf_health import shelf_permission_report
from librarian.shelf_health_score import assemble_shelf_health_score
from librarian.split_mixed_kinds import count_mixed_kind_works, split_mixed_kind_works
from librarian.split_mixed_kinds_progress import (
    SplitMixedKindsProgressReporter,
    begin_split_mixed_kinds_run,
    finish_split_mixed_kinds_run,
    is_split_mixed_kinds_running,
    is_split_mixed_kinds_stale,
    read_split_mixed_kinds_progress,
)
from librarian.suggest import refresh_suggest_cache
from librarian.web.deps import WebDeps

logger = logging.getLogger("librarian.web")


def _background_poller_status(app: FastAPI) -> Dict[str, Any]:
    """Last run and last error for each poller step."""
    poller = getattr(app.state, "poller", None)
    report = getattr(poller, "step_status", None)
    if not callable(report):
        return {"steps": []}
    payload = report()
    steps = payload.get("steps") if isinstance(payload, dict) else None
    if not isinstance(steps, list):
        return {"steps": []}
    return {"steps": steps}


def _backup_report(app: FastAPI, data_dir: Any) -> Dict[str, Any]:
    """Newest snapshot on disk plus the backup step's last error, if any."""
    report = backup_status(backup_dir_for(data_dir))
    error = None
    for step in _background_poller_status(app)["steps"]:
        if isinstance(step, dict) and step.get("id") == "backup":
            raw = step.get("last_error")
            error = raw.strip() if isinstance(raw, str) and raw.strip() else None
    return {**report, "last_error": error}


def register_maintain_routes(app: FastAPI, deps: WebDeps) -> None:
    """Register maintain routes on the composition-root app."""
    root = deps.root
    db = deps.db
    settings = deps.settings
    enrich_job = deps.enrich_job
    scan_job = deps.scan_job
    ingest_job = deps.ingest_job
    extra_files_reprocess_job = deps.extra_files_reprocess_job
    purge_duplicates_job = deps.purge_duplicates_job
    purge_shells_job = deps.purge_shells_job
    split_mixed_kinds_job = deps.split_mixed_kinds_job
    cleanup_job = deps.cleanup_job

    def current_user(request: Request) -> Optional[Dict[str, Any]]:
        return deps.current_user(request)

    @app.get("/api/maintain/shelf-health")
    def maintain_shelf_health(request: Request):
        """Permission roots plus living pulse + one tend (weather, not KPI)."""
        require_role(current_user(request), "owner")
        report = shelf_permission_report(settings())
        extra = db.count_works(review_state="needs_review", review_reason=REVIEW_EXTRA)
        shells = db.count_shell_works()
        blends = count_mixed_kind_works(db)
        score = assemble_shelf_health_score(
            shelf_health=report,
            extra_files=extra,
            unshelved_shells=shells,
            comic_book_blends=blends,
        )
        return {**report, "score": score}

    @app.get("/api/maintain/morning-brief")
    def maintain_morning_brief(request: Request):
        """Owner morning desk: at most three tend items, ranked softly."""
        require_role(current_user(request), "owner")
        health = shelf_permission_report(settings())
        stuck: List[Dict[str, Any]] = []
        for job_id, label, href, reader in (
            ("scan", "Scan is walking the shelves", "#maintain-scan", read_scan_progress),
            ("enrich", "Enrich is still naming volumes", "#maintain-enrich", read_enrich_progress),
            ("ingest", "Shelving is still at work", "#maintain-ingest", read_ingest_progress),
            (
                "extra_files",
                "Clear extra-files is still running",
                "#maintain-clear-extra-files",
                read_extra_files_reprocess_progress,
            ),
            ("shells", "Purge shells is still running", "#maintain-shells", read_purge_shells_progress),
            ("cleanup", "Catalog cleanup is still running", "#maintain-cleanup", read_cleanup_progress),
            (
                "mixed",
                "Split blends is still running",
                "#maintain-split-mixed",
                read_split_mixed_kinds_progress,
            ),
        ):
            progress = reader(root)
            if str(progress.get("status") or "") == "running":
                stuck.append(
                    {
                        "id": job_id,
                        "label": label,
                        "detail": str(progress.get("phase") or "Still breathing.").strip(),
                        "href": href,
                        "cta": "Watch the dock",
                    }
                )
        needs = db.count_works(review_state="needs_review")
        extra = db.count_works(review_state="needs_review", review_reason=REVIEW_EXTRA)
        # Holds desk = identity slips; extra-files are their own tend row.
        holds = max(0, int(needs) - int(extra))
        shells = db.count_shell_works()
        blends = count_mixed_kind_works(db)
        brief = assemble_morning_brief(
            shelf_health=health,
            stuck_jobs=stuck,
            holds_desk_slips=holds,
            extra_files=extra,
            unshelved_shells=shells,
            comic_book_blends=blends,
        )
        brief["screen_leftovers"] = screen_leftover_report(db)
        return brief

    @app.get("/api/maintain/jobs/status")
    def maintain_jobs_status(request: Request):
        """Dock telemetry plus each background poller step's last run and last error."""
        require_role(current_user(request), "owner")

        scan = read_scan_progress(root)
        if str(scan.get("status") or "") == "running" and not scan_job.alive():
            scan = finish_scan_run(
                root,
                error="Scan stopped — the lamp was restarted. Try Scan again.",
            )

        enrich = read_enrich_progress(root)
        if str(enrich.get("status") or "") == "running" and not enrich_job.alive():
            enrich = finish_enrich_run(
                root,
                error="Enrich stopped — the lamp was restarted. Try Enrich again.",
            )

        ingest = read_ingest_progress(root)
        if str(ingest.get("status") or "") == "running" and not ingest_job.alive():
            ingest = finish_ingest_run(
                root,
                error="Shelving stopped — the lamp was restarted. Try Add again.",
            )

        extra_files = read_extra_files_reprocess_progress(root)
        if str(extra_files.get("status") or "") == "running":
            alive = extra_files_reprocess_job.alive()
            if not alive or is_extra_files_reprocess_stale(extra_files):
                if alive:
                    error = (
                        "Clear extra-files stalled (no progress heartbeat). "
                        "Try Clear again — large author folders now queue instead of blocking."
                    )
                else:
                    error = "Clear extra-files stopped — the lamp was restarted. Try again."
                extra_files = finish_extra_files_reprocess_run(root, error=error)
        extra_files = {
            **extra_files,
            "extra_files_remaining": db.count_works(
                review_state="needs_review", review_reason=REVIEW_EXTRA
            ),
        }

        return {
            "scan": scan,
            "enrich": enrich,
            "ingest": ingest,
            "extra_files": extra_files,
            "cleanup": read_cleanup_progress(root),
            "poller": _background_poller_status(app),
            "backup": _backup_report(app, root),
        }

    @app.post("/api/maintain/cleanup")
    def maintain_cleanup(request: Request, approve: bool = False):
        """Preview canonical cleanup, then run only after owner approval."""
        require_role(request.state.user, "owner")

        def run_cleanup() -> None:
            try:
                cleanup_library(db, settings(), apply=approve, data_dir=root)
            except Exception as error:
                logger.exception("Catalog cleanup failed")
                from librarian.cleanup import PROGRESS

                PROGRESS.finish(root, error=str(error) or "Catalog cleanup failed")

        kicked = cleanup_job.start_if_idle(
            is_running=lambda: str(read_cleanup_progress(root).get("status") or "") == "running",
            begin=lambda: None,
            target=run_cleanup,
            name="librarian-cleanup",
        )
        return {**read_cleanup_progress(root), "kicked_off": kicked}

    @app.get("/api/maintain/cleanup/status")
    def maintain_cleanup_status(request: Request):
        require_role(request.state.user, "owner")
        return read_cleanup_progress(root)

    @app.post("/api/maintain/cleanup/restore")
    def maintain_cleanup_restore(request: Request):
        """Restore the most recently quarantined duplicate copies."""
        require_role(request.state.user, "owner")
        report = read_cleanup_progress(root).get("report") or {}
        manifest = Path(str(report.get("quarantine") or "")) / "manifest.json"
        if not manifest.is_file():
            raise HTTPException(status_code=404, detail="No cleanup quarantine is ready to restore")
        return {"restored": restore_quarantine(manifest)}

    @app.post("/api/maintain/cleanup/empty")
    def maintain_cleanup_empty(request: Request):
        """Permanently empty the owner-approved cleanup quarantine."""
        require_role(request.state.user, "owner")
        report = read_cleanup_progress(root).get("report") or {}
        quarantine = Path(str(report.get("quarantine") or ""))
        if not quarantine.is_dir():
            raise HTTPException(status_code=404, detail="No cleanup quarantine is ready to empty")
        shutil.rmtree(quarantine)
        return {"emptied": True}

    @app.get("/api/maintain/indexer-scorecard")
    def maintain_indexer_scorecard(request: Request):
        """Hosts as lanterns — weather + mute, never a latency KPI strip."""
        require_role(current_user(request), "owner")
        return assemble_indexer_scorecard(root, settings())

    @app.post("/api/maintain/indexer-scorecard/{host_id}/mute")
    def maintain_indexer_mute(host_id: str, request: Request):
        """Mute a sick host without deleting it — Find skips it until unmute."""
        require_role(current_user(request), "owner")
        current = settings()
        try:
            mute_host(current, host_id, muted=True)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Indexer not found") from error
        save_settings(root, current)
        return assemble_indexer_scorecard(root, current)

    @app.post("/api/maintain/indexer-scorecard/{host_id}/unmute")
    def maintain_indexer_unmute(host_id: str, request: Request):
        """Unmute a resting host so Find queries it again."""
        require_role(current_user(request), "owner")
        current = settings()
        try:
            mute_host(current, host_id, muted=False)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Indexer not found") from error
        save_settings(root, current)
        return assemble_indexer_scorecard(root, current)

    @app.get("/api/maintain/grooming-undo")
    def maintain_grooming_undo(request: Request):
        """Last Clear/Purge/Skip batch — recoverable for a short warm window."""
        require_role(current_user(request), "owner", "op")
        return assemble_grooming_undo(root)

    @app.post("/api/maintain/grooming-undo")
    def maintain_grooming_undo_restore(request: Request):
        """Restore the last metadata-only grooming batch when still in window."""
        require_role(current_user(request), "owner", "op")
        return restore_grooming_batch(db, root)

    @app.get("/api/maintain/calibre-renormalize")
    def maintain_calibre_renormalize_preview(request: Request):
        """Look first: dry-run Calibre dump → books_root map."""
        require_role(current_user(request), "owner")
        return assemble_calibre_renormalize(settings(), apply=False)

    @app.post("/api/maintain/calibre-renormalize")
    def maintain_calibre_renormalize_apply(request: Request):
        """One graceful ritual: copy Calibre dump into books_root (never move)."""
        require_role(current_user(request), "owner")
        return assemble_calibre_renormalize(settings(), apply=True, limit=None)

    @app.post("/api/maintain/purge-shells")
    def maintain_purge_shells(request: Request, limit: int = 0):
        """Owner bulk: delete catalog shells with no media on disk (poll status)."""
        require_role(request.state.user, "owner", "op")
        run_limit = max(0, int(limit or 0))

        def run_purge() -> None:
            reporter = PurgeShellsProgressReporter(root)
            try:
                purge_shell_works(
                    db,
                    settings(),
                    limit=run_limit,
                    progress=reporter,
                    data_dir=root,
                )
            except Exception as error:
                logger.exception("Purge shells failed")
                reporter.fail(str(error) or "Purge shells failed")

        kicked = purge_shells_job.start_if_idle(
            is_running=lambda: is_purge_shells_running(root),
            begin=lambda: begin_purge_shells_run(root, total=0, phase="starting"),
            target=run_purge,
            name="librarian-purge-shells",
        )
        payload = read_purge_shells_progress(root)
        payload["shells_remaining"] = db.count_shell_works()
        return {**payload, "kicked_off": kicked}

    @app.get("/api/maintain/purge-shells/status")
    def maintain_purge_shells_status(request: Request):
        """Poll Purge shells progress (survives refresh via DATA_DIR JSON)."""
        require_role(request.state.user, "owner", "op")
        progress = read_purge_shells_progress(root)
        if str(progress.get("status") or "") != "running":
            progress["shells_remaining"] = db.count_shell_works()
            return progress
        alive = purge_shells_job.alive()
        if alive and not is_purge_shells_stale(progress):
            progress["shells_remaining"] = db.count_shell_works()
            return progress
        if alive:
            error = "Purge shells stalled (no progress heartbeat). Try Purge again."
        else:
            error = "Purge shells stopped — the lamp was restarted. Try again."
        finished = finish_purge_shells_run(root, error=error)
        finished["shells_remaining"] = db.count_shell_works()
        return finished

    @app.post("/api/maintain/split-mixed-kinds")
    def maintain_split_mixed_kinds(request: Request, limit: int = 0):
        """Owner bulk: split works that blend comic archives with ebook encodings."""
        require_role(request.state.user, "owner", "op")
        run_limit = max(0, int(limit or 0))

        def run_split() -> None:
            reporter = SplitMixedKindsProgressReporter(root)
            try:
                split_mixed_kind_works(
                    db,
                    settings(),
                    limit=run_limit,
                    progress=reporter,
                )
            except Exception as error:
                logger.exception("Split mixed kinds failed")
                reporter.fail(str(error) or "Split mixed kinds failed")

        kicked = split_mixed_kinds_job.start_if_idle(
            is_running=lambda: is_split_mixed_kinds_running(root),
            begin=lambda: begin_split_mixed_kinds_run(root, total=0, phase="starting"),
            target=run_split,
            name="librarian-split-mixed-kinds",
        )
        payload = read_split_mixed_kinds_progress(root)
        payload["mixed_remaining"] = count_mixed_kind_works(db)
        return {**payload, "kicked_off": kicked}

    @app.get("/api/maintain/split-mixed-kinds/status")
    def maintain_split_mixed_kinds_status(request: Request):
        """Poll split-mixed-kinds progress (survives refresh via DATA_DIR JSON)."""
        require_role(request.state.user, "owner", "op")
        progress = read_split_mixed_kinds_progress(root)
        if str(progress.get("status") or "") != "running":
            progress["mixed_remaining"] = count_mixed_kind_works(db)
            return progress
        alive = split_mixed_kinds_job.alive()
        if alive and not is_split_mixed_kinds_stale(progress):
            progress["mixed_remaining"] = count_mixed_kind_works(db)
            return progress
        if alive:
            error = "Split mixed kinds stalled (no progress heartbeat). Try again."
        else:
            error = "Split mixed kinds stopped — the lamp was restarted. Try again."
        finished = finish_split_mixed_kinds_run(root, error=error)
        finished["mixed_remaining"] = count_mixed_kind_works(db)
        return finished

    @app.post("/api/settings/abs-match")
    def abs_match_settings(request: Request):
        require_role(request.state.user, "owner")
        return match_audiobooks(db, settings(), force=True)

    @app.post("/api/settings/scan")
    def scan_settings(request: Request):
        require_role(request.state.user, "owner")

        def run_scan() -> None:
            reporter = ScanProgressReporter(root, source="manual")
            try:
                scan_library(db, settings(), progress=reporter)
            except Exception as error:
                logger.exception("Scan shelves failed")
                reporter.fail(str(error) or "Scan failed")

        kicked = scan_job.start_if_idle(
            is_running=lambda: is_scan_running(root),
            begin=lambda: begin_scan_run(root, source="manual", total=0, phase="starting"),
            target=run_scan,
            name="librarian-scan",
        )
        payload = read_scan_progress(root)
        return {**payload, "kicked_off": kicked}

    @app.get("/api/settings/scan/status")
    def scan_settings_status(request: Request):
        require_role(request.state.user, "owner")
        progress = read_scan_progress(root)
        if str(progress.get("status") or "") != "running":
            return progress
        if scan_job.alive():
            return progress
        return finish_scan_run(
            root,
            error="Scan stopped — the lamp was restarted. Try Scan again.",
        )

    @app.post("/api/settings/enrich")
    def enrich_settings(request: Request):
        require_role(request.state.user, "owner")

        def run_enrich() -> None:
            reporter = EnrichProgressReporter(root, source="manual")
            try:
                enrich_library(db, settings(), data_dir=root, progress=reporter)
            except Exception as error:
                logger.exception("Enrich shelves failed")
                reporter.fail(friendly_enrich_error(error) or "Enrich failed")

        kicked = enrich_job.start_if_idle(
            is_running=lambda: is_enrich_running(root),
            begin=lambda: begin_enrich_run(root, source="manual", total=0, phase="starting"),
            target=run_enrich,
            name="librarian-enrich",
        )
        payload = read_enrich_progress(root)
        return {**payload, "kicked_off": kicked}

    @app.get("/api/settings/enrich/status")
    def enrich_settings_status(request: Request):
        require_role(request.state.user, "owner")
        progress = read_enrich_progress(root)
        if str(progress.get("status") or "") != "running":
            return progress
        if enrich_job.alive():
            return progress
        # Rebuild / process restart left a stale "running" blob with no worker.
        return finish_enrich_run(
            root,
            error="Enrich stopped — the lamp was restarted. Try Enrich again.",
        )

    @app.post("/api/settings/suggest-cache")
    def suggest_cache_settings(request: Request, external: int = 0):
        require_role(request.state.user, "owner")
        return refresh_suggest_cache(db, root, include_external=bool(external))

    @app.post("/api/settings/goodreads")
    async def goodreads_settings(request: Request, file: UploadFile = File(...)):
        require_role(request.state.user, "owner")
        raw = await file.read()
        if len(raw) > MAX_GOODREADS_BYTES:
            raise HTTPException(status_code=400, detail="Goodreads CSV is too large")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise HTTPException(status_code=400, detail="Goodreads CSV must be UTF-8") from error
        return import_goodreads_csv(db, request.state.user["id"], text)
