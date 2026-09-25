"""Maintain grooming jobs, scan/enrich, and Shelf health."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile

from librarian.web.deps import WebDeps
from librarian.web.route_imports import *  # noqa: F403


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

    def current_user(request: Request) -> Optional[Dict[str, Any]]:
        return deps.current_user(request)


    @app.get("/api/maintain/shelf-health")
    def maintain_shelf_health(request: Request):
        require_role(current_user(request), "owner")
        return shelf_permission_report(settings())

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

