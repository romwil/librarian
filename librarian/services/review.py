"""Holds desk: slip listing, per-slip motions, regrab ranking, and bulk background jobs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from librarian import review_suggest_batch as review_suggest_batch_mod
from librarian.bad_releases import (
    BAD_RELEASE_REASONS,
    MIGRATION_NAME,
    NEEDS_OWNER_ACTION,
    NEEDS_OWNER_NOTE,
    read_migration_progress,
)
from librarian.delight import rank_regrab_candidates
from librarian.enrich import list_match_candidates
from librarian.extra_files_reprocess_progress import (
    ExtraFilesReprocessProgressReporter,
    begin_extra_files_reprocess_run,
    finish_extra_files_reprocess_run,
    is_extra_files_reprocess_running,
    is_extra_files_reprocess_stale,
    read_extra_files_reprocess_progress,
)
from librarian.identify import diagnose_review_folder
from librarian.indexers.rank import remember_candidates, search_and_rank
from librarian.organize import (
    apply_review,
    repair_review,
    reprocess_extra_files_reviews,
    reprocess_extra_files_work,
    retry_review,
    review_slip_actions,
    shelf_work_for_collision,
    suggest_review_identity,
)
from librarian.progress_job import BackgroundJobSlot
from librarian.purge_duplicates import purge_duplicate_reviews
from librarian.purge_duplicates_progress import (
    PurgeDuplicatesProgressReporter,
    begin_purge_duplicates_run,
    finish_purge_duplicates_run,
    is_purge_duplicates_running,
    is_purge_duplicates_stale,
    read_purge_duplicates_progress,
)
from librarian.review_bulk import BulkError, bulk_by_reason, effective_review_reason
from librarian.review_reasons import (
    REVIEW_COMICVINE_AMBIGUOUS,
    REVIEW_COMICVINE_UNMATCHED,
    REVIEW_EXTRA,
    REVIEW_LOW,
    REVIEW_NO_PAYLOAD,
    REVIEW_UNKNOWN,
    REVIEW_UNPACK_STUCK,
)
from librarian.review_retrieve import SlipDownError, retrieve_slip_release
from librarian.services import NotFoundError, ServiceError
from librarian.web.serializers import public_work_admin, public_works_admin

logger = logging.getLogger("librarian.web")

SettingsFn = Callable[[], Any]

TRIAGE_LABELS = {
    "trusted": "Ready to file",
    "ambiguous": "Needs a decision",
    "failed": "Model unavailable",
}


def shape_review_work_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    """Allowlist work objects on Review mutation responses (P4-HIGH-02)."""
    if not isinstance(result, dict):
        return result
    out = dict(result)
    if "work" in out:
        out["work"] = public_work_admin(out.get("work"))
    if "shelf_work" in out:
        out["shelf_work"] = public_work_admin(out.get("shelf_work"))
    return out


def public_triage(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Persisted model answer for one slip (no raw prompt or provider text)."""
    if not row:
        return None
    outcome = str(row.get("outcome") or "")
    suggestion = row.get("suggestion") if isinstance(row.get("suggestion"), dict) else None
    return {
        "outcome": outcome,
        "label": TRIAGE_LABELS.get(outcome, "Model unavailable"),
        "explanation": str(row.get("explanation") or ""),
        "suggestion": suggestion,
        "updated_at": row.get("updated_at"),
    }


def _require_work(db: Any, work_id: str) -> Dict[str, Any]:
    work = db.get_work(work_id)
    if work is None:
        raise NotFoundError("Work not found")
    return work


# --- desk listing ------------------------------------------------------------


def bad_release_migration_status(db: Any, root: Path) -> Dict[str, Any]:
    """One-time return of no-payload / convert-failed slips to Wanted (boot migration)."""
    progress = read_migration_progress(root)
    done = db.get_migration(MIGRATION_NAME)
    if done is not None and str(progress.get("status") or "") != "running":
        report = dict(done.get("report") or {})
        return {
            "status": "completed",
            "total": int(report.get("total") or 0),
            "done": int(report.get("total") or 0),
            "returned": int(report.get("returned") or 0),
            "dismissed": int(report.get("dismissed") or 0),
            "left_on_desk": int(report.get("left_on_desk") or 0),
            "failed": int(report.get("failed") or 0),
        }
    return {
        key: progress.get(key)
        for key in (
            "status",
            "total",
            "done",
            "returned",
            "dismissed",
            "left_on_desk",
            "failed",
            "current_title",
            "error",
        )
    }


def _annotate_slip(work: Dict[str, Any], job: Optional[Mapping[str, Any]], db: Any, cfg: Any, llm_ok: bool) -> None:
    from librarian.slip_gate import parse_library_volume

    storage = str((job or {}).get("storage_path") or "")
    work["storage_path"] = storage or None
    if not work.get("folder_path") and storage:
        work["folder_path"] = storage
    folder_raw = str(work.get("folder_path") or storage or "")
    diagnosis = diagnose_review_folder(Path(folder_raw), cfg.complete_root)
    work["folder_diagnosis"] = diagnosis
    if diagnosis.get("path_clear") and str(work.get("kind") or "") == "book":
        parsed = parse_library_volume(Path(folder_raw)) if folder_raw else None
        if parsed and str(work.get("review_reason") or "") in {REVIEW_LOW, REVIEW_UNKNOWN, ""}:
            work["author"] = parsed["author"]
            work["title"] = parsed["title"]
            if parsed.get("series_name"):
                work["series_name"] = parsed["series_name"]
    problem = diagnosis.get("problem")
    stored = str(work.get("review_reason") or "")
    # Response overlay only — SQLite soft-repair runs in the poller.
    if problem == REVIEW_UNPACK_STUCK and stored in {"", REVIEW_NO_PAYLOAD}:
        work["review_reason"] = REVIEW_UNPACK_STUCK
    shelf = shelf_work_for_collision(db, work)
    work["shelf_work"] = public_work_admin(shelf) if shelf else None
    work["actions"] = review_slip_actions(work, diagnosis, llm_configured=llm_ok)
    reason = str(work.get("review_reason") or "")
    if work.get("kind") == "comic" and reason in (
        REVIEW_COMICVINE_AMBIGUOUS,
        REVIEW_COMICVINE_UNMATCHED,
        REVIEW_LOW,
        REVIEW_UNKNOWN,
    ):
        try:
            work["match_candidates"] = list_match_candidates(work, settings=cfg, limit=6)
        except Exception:
            work["match_candidates"] = []


def _annotate_slip_from_cache(
    work: Dict[str, Any],
    job: Optional[Mapping[str, Any]],
    db: Any,
    llm_ok: bool,
    *,
    diagnosis: Optional[Mapping[str, Any]] = None,
    suggestion: Optional[Mapping[str, Any]] = None,
) -> None:
    """Shape one desk row from cached diagnosis. Does not walk the folder."""
    from librarian.organize import review_slip_actions, shelf_work_for_collision
    from librarian.slip_gate import parse_library_volume

    storage = str((job or {}).get("storage_path") or "")
    work["storage_path"] = storage or None
    if not work.get("folder_path") and storage:
        work["folder_path"] = storage
    folder_raw = str(work.get("folder_path") or storage or "")
    cached = dict(diagnosis or {})
    work["folder_diagnosis"] = cached
    if cached.get("path_clear") and str(work.get("kind") or "") == "book":
        parsed = parse_library_volume(Path(folder_raw)) if folder_raw else None
        if parsed and str(work.get("review_reason") or "") in {REVIEW_LOW, REVIEW_UNKNOWN, ""}:
            work["author"] = parsed["author"]
            work["title"] = parsed["title"]
            if parsed.get("series_name"):
                work["series_name"] = parsed["series_name"]
    problem = cached.get("problem")
    stored = str(work.get("review_reason") or "")
    if problem == REVIEW_UNPACK_STUCK and stored in {"", REVIEW_NO_PAYLOAD}:
        work["review_reason"] = REVIEW_UNPACK_STUCK
    shelf = shelf_work_for_collision(db, work)
    work["shelf_work"] = public_work_admin(shelf) if shelf else None
    work["actions"] = review_slip_actions(work, cached, llm_configured=llm_ok)
    work["match_candidates"] = []
    work["llm_triage"] = public_triage(suggestion)
    work["effective_reason"] = effective_review_reason(
        {**work, "review_reason": work.get("review_reason")},
        cached,
        suggestion,
    )


def review_desk(
    db: Any,
    cfg: Any,
    *,
    root: Path,
    focus: str = "",
    reason: str = "",
    cursor: str = "",
    limit: int = 25,
) -> Dict[str, Any]:
    """``GET /api/review``: paginated slips. Diagnosis comes from the table, not rglob."""
    from librarian.llm_providers import resolve_llm_connection
    from librarian.owned_slip import owned_slip_note
    from librarian.review_diagnosis import (
        PAGE_LIMIT_DEFAULT,
        PAGE_LIMIT_MAX,
        counts_by_effective_reason,
        diagnosis_from_row,
        list_review_page,
    )
    from librarian.sorting_undo import public_undo

    note = owned_slip_note(db)
    llm_ok = bool(resolve_llm_connection(cfg).get("api_key"))
    counts = counts_by_effective_reason(db)
    total = int(sum(counts.values()))
    page = list_review_page(
        db,
        reason=reason,
        cursor=cursor,
        limit=min(PAGE_LIMIT_MAX, max(1, int(limit or PAGE_LIMIT_DEFAULT))),
    )
    raw_rows = page["rows"]
    works = public_works_admin(raw_rows)
    by_id = {str(row.get("id") or ""): row for row in raw_rows}
    focus = str(focus or "").strip()
    if focus and all(str(row.get("id") or "") != focus for row in works):
        pinned = db.get_work(focus)
        if pinned and str(pinned.get("review_state") or "") == "needs_review":
            works.insert(0, public_work_admin(pinned))
            cached = db.get_review_diagnoses([focus]).get(focus) or {}
            by_id[focus] = {
                **pinned,
                "_diagnosis_json": cached.get("diagnosis_json"),
            }
    jobs_by_work: Dict[str, Any] = {}
    for job in db.list_jobs(limit=200):
        work_id = job.get("work_id")
        if work_id and work_id not in jobs_by_work:
            jobs_by_work[work_id] = job
    needs_owner = db.review_audit_work_ids(NEEDS_OWNER_ACTION)
    for work in works:
        source = by_id.get(str(work.get("id") or ""), {})
        suggestion = None
        if source.get("_suggestion_outcome"):
            suggestion = {
                "outcome": source.get("_suggestion_outcome"),
                "suggestion": source.get("_suggestion_json"),
                "explanation": source.get("_suggestion_explanation") or "",
                "updated_at": source.get("_suggestion_updated_at"),
            }
            if isinstance(suggestion["suggestion"], str):
                from librarian.repositories._base import _loads

                suggestion["suggestion"] = _loads(suggestion["suggestion"], None)
        _annotate_slip_from_cache(
            work,
            jobs_by_work.get(work["id"]) if work else None,
            db,
            llm_ok,
            diagnosis=diagnosis_from_row(source),
            suggestion=suggestion,
        )
        if (
            str(work.get("id") or "") in needs_owner
            and str(work.get("review_reason") or "") in BAD_RELEASE_REASONS
        ):
            work["owner_decision_note"] = NEEDS_OWNER_NOTE
    extra_files_count = int(counts.get(REVIEW_EXTRA) or 0)
    return {
        "items": works,
        "works": works,
        "next_cursor": page["next_cursor"],
        "counts_by_reason": counts,
        "total": total,
        "llm_configured": llm_ok,
        "extra_files_count": extra_files_count,
        "needs_review_count": total,
        "owned_slip_note": note,
        "bad_release_migration": bad_release_migration_status(db, root),
        "undo": public_undo(db),
    }


def review_candidates(db: Any, cfg: Any, *, work_id: str) -> Dict[str, Any]:
    """Lazy match candidates for the slip drawer. Not loaded on the desk GET."""
    from librarian.enrich import list_match_candidates

    work = _require_work(db, work_id)
    if str(work.get("review_state") or "") != "needs_review":
        return {"candidates": []}
    reason = str(work.get("review_reason") or "")
    if work.get("kind") != "comic" or reason not in (
        REVIEW_COMICVINE_AMBIGUOUS,
        REVIEW_COMICVINE_UNMATCHED,
        REVIEW_LOW,
        REVIEW_UNKNOWN,
    ):
        return {"candidates": []}
    try:
        return {"candidates": list_match_candidates(work, settings=cfg, limit=6)}
    except Exception:
        return {"candidates": []}


# --- bulk motions ------------------------------------------------------------


def bulk_motion(db: Any, cfg: Any, *, root: Path, payload: Mapping[str, Any]) -> Dict[str, Any]:
    """One group action on a pile, by the server's effective reason. Never deletes files."""
    raw_ids = payload.get("work_ids")
    work_ids = [str(item) for item in raw_ids] if isinstance(raw_ids, list) else None
    try:
        confirm = payload.get("confirm_count")
        confirm_count = int(confirm) if confirm is not None and str(confirm) != "" else None
        return bulk_by_reason(
            db,
            cfg,
            reason=str(payload.get("reason") or ""),
            action=str(payload.get("action") or ""),
            work_ids=work_ids,
            dry_run=bool(payload.get("dry_run")),
            data_dir=root,
            confirm_count=confirm_count,
        )
    except BulkError as error:
        raise ServiceError(str(error)) from error


def start_suggest_batch(
    db: Any, settings: SettingsFn, *, root: Path, slot: BackgroundJobSlot, limit: int = 0
) -> Dict[str, Any]:
    """Kick off model triage for low-confidence slips (poll status; each answer persists)."""
    size = int(limit or 0) or review_suggest_batch_mod.DEFAULT_BATCH_SIZE

    def run_batch() -> None:
        try:
            review_suggest_batch_mod.run_suggest_batch(db, settings(), data_dir=root, batch_size=size)
        except Exception as error:
            logger.exception("Suggest batch failed")
            review_suggest_batch_mod.finish(root, error=str(error) or "Suggest batch failed")

    kicked = slot.start_if_idle(
        is_running=lambda: review_suggest_batch_mod.is_running(root),
        begin=lambda: review_suggest_batch_mod.begin(root),
        target=run_batch,
        name="librarian-review-suggest-batch",
    )
    return {**review_suggest_batch_mod.read_progress(root), "kicked_off": kicked}


def suggest_batch_status(*, root: Path, slot: BackgroundJobSlot) -> Dict[str, Any]:
    progress = review_suggest_batch_mod.read_progress(root)
    if str(progress.get("status") or "") != "running":
        return progress
    alive = slot.alive()
    if alive and not review_suggest_batch_mod.is_stale(progress):
        return progress
    error = (
        "Model check stalled (no progress heartbeat). Start it again — finished slips are kept."
        if alive
        else "Model check stopped — the lamp was restarted. Start it again; finished slips are kept."
    )
    return review_suggest_batch_mod.finish(root, error=error)


def _extra_files_remaining(db: Any) -> int:
    return db.count_works(review_state="needs_review", review_reason=REVIEW_EXTRA)


def start_extra_files_reprocess(
    db: Any,
    settings: SettingsFn,
    *,
    root: Path,
    slot: BackgroundJobSlot,
    requested_by: str,
    limit: int = 0,
) -> Dict[str, Any]:
    """Owner bulk: kick off background clear for extra_files slips (poll status)."""
    run_limit = max(0, int(limit or 0))

    def run_reprocess() -> None:
        reporter = ExtraFilesReprocessProgressReporter(root)
        try:
            reprocess_extra_files_reviews(
                db,
                settings(),
                requested_by=requested_by,
                limit=run_limit,
                progress=reporter,
            )
        except Exception as error:
            logger.exception("Clear extra-files slips failed")
            reporter.fail(str(error) or "Clear extra-files failed")

    kicked = slot.start_if_idle(
        is_running=lambda: is_extra_files_reprocess_running(root),
        begin=lambda: begin_extra_files_reprocess_run(root, total=0, phase="starting"),
        target=run_reprocess,
        name="librarian-extra-files-reprocess",
    )
    payload = read_extra_files_reprocess_progress(root)
    payload["extra_files_remaining"] = _extra_files_remaining(db)
    return {**payload, "kicked_off": kicked}


def extra_files_reprocess_status(db: Any, *, root: Path, slot: BackgroundJobSlot) -> Dict[str, Any]:
    """Clear extra-files slips progress (survives refresh via DATA_DIR JSON)."""
    progress = read_extra_files_reprocess_progress(root)
    if str(progress.get("status") or "") != "running":
        progress["extra_files_remaining"] = _extra_files_remaining(db)
        return progress
    alive = slot.alive()
    if alive and not is_extra_files_reprocess_stale(progress):
        progress["extra_files_remaining"] = _extra_files_remaining(db)
        return progress
    if alive:
        error = (
            "Clear extra-files stalled (no progress heartbeat). "
            "Try Clear again — large author folders now queue instead of blocking."
        )
    else:
        error = "Clear extra-files stopped — the lamp was restarted. Try again."
    finished = finish_extra_files_reprocess_run(root, error=error)
    finished["extra_files_remaining"] = _extra_files_remaining(db)
    return finished


def start_purge_duplicates(
    db: Any, settings: SettingsFn, *, root: Path, slot: BackgroundJobSlot, limit: int = 0
) -> Dict[str, Any]:
    """Owner bulk: dismiss safely redundant Review slips (poll status)."""
    run_limit = max(0, int(limit or 0))

    def run_purge() -> None:
        reporter = PurgeDuplicatesProgressReporter(root)
        try:
            purge_duplicate_reviews(db, settings(), limit=run_limit, progress=reporter)
        except Exception as error:
            logger.exception("Purge duplicates failed")
            reporter.fail(str(error) or "Purge duplicates failed")

    kicked = slot.start_if_idle(
        is_running=lambda: is_purge_duplicates_running(root),
        begin=lambda: begin_purge_duplicates_run(root, total=0, phase="starting"),
        target=run_purge,
        name="librarian-purge-duplicates",
    )
    payload = read_purge_duplicates_progress(root)
    payload["needs_review_remaining"] = db.count_works(review_state="needs_review")
    return {**payload, "kicked_off": kicked}


def purge_duplicates_status(db: Any, *, root: Path, slot: BackgroundJobSlot) -> Dict[str, Any]:
    """Purge duplicates progress (survives refresh via DATA_DIR JSON)."""
    progress = read_purge_duplicates_progress(root)
    if str(progress.get("status") or "") != "running":
        progress["needs_review_remaining"] = db.count_works(review_state="needs_review")
        return progress
    alive = slot.alive()
    if alive and not is_purge_duplicates_stale(progress):
        progress["needs_review_remaining"] = db.count_works(review_state="needs_review")
        return progress
    if alive:
        error = "Purge duplicates stalled (no progress heartbeat). Try Purge again."
    else:
        error = "Purge duplicates stopped — the lamp was restarted. Try again."
    finished = finish_purge_duplicates_run(root, error=error)
    finished["needs_review_remaining"] = db.count_works(review_state="needs_review")
    return finished


# --- one slip ----------------------------------------------------------------


def suggest_slip(db: Any, cfg: Any, *, work_id: str) -> Dict[str, Any]:
    """BYO LLM title/author suggest for a Review slip. Pre-fills only — never Apply."""
    _require_work(db, work_id)
    job = None
    for row in db.list_jobs(limit=200):
        if row.get("work_id") == work_id:
            job = row
            break
    try:
        return suggest_review_identity(db, cfg, work_id=work_id, job=job)
    except ValueError as error:
        raise NotFoundError(str(error)) from error


def apply_slip(
    db: Any,
    cfg: Any,
    *,
    work_id: str,
    folder: Optional[str],
    identity_overrides: Dict[str, Any],
) -> Dict[str, Any]:
    work = _require_work(db, work_id)
    raw = str(folder or work.get("folder_path") or "").strip()
    path = Path(raw) if raw else Path()
    try:
        return shape_review_work_payload(
            apply_review(db, cfg, work_id=work_id, folder=path, identity_overrides=identity_overrides)
        )
    except ValueError as error:
        raise ServiceError(str(error)) from error


def repair_slip(db: Any, cfg: Any, *, work_id: str) -> Dict[str, Any]:
    _require_work(db, work_id)
    try:
        return shape_review_work_payload(repair_review(db, cfg, work_id=work_id))
    except ValueError as error:
        raise ServiceError(str(error)) from error


def retry_slip(db: Any, cfg: Any, *, work_id: str) -> Dict[str, Any]:
    _require_work(db, work_id)
    try:
        return shape_review_work_payload(retry_review(db, cfg, work_id=work_id))
    except ValueError as error:
        raise ServiceError(str(error)) from error


def reprocess_extra_files_slip(db: Any, cfg: Any, *, work_id: str, requested_by: str) -> Dict[str, Any]:
    try:
        return shape_review_work_payload(
            reprocess_extra_files_work(db, cfg, work_id=work_id, requested_by=requested_by)
        )
    except ValueError as error:
        raise ServiceError(str(error)) from error


def retrieve_slip(
    db: Any,
    cfg: Any,
    *,
    root: Path,
    work_id: str,
    intent: Any,
    role: str,
    requested_by: str,
) -> Dict[str, Any]:
    """Search and queue another release on this slip. Does not send the household to Find."""
    try:
        return retrieve_slip_release(
            db,
            cfg,
            work_id=work_id,
            intent=intent,
            role=role,
            requested_by=requested_by,
            data_dir=root,
        )
    except SlipDownError as error:
        raise ServiceError(error.message, status_code=502) from error
    except ValueError as error:
        status = 404 if "not found" in str(error).lower() else 400
        raise ServiceError(str(error), status_code=status) from error


def skip_slip(db: Any, *, root: Path, work_id: str) -> Dict[str, Any]:
    work = _require_work(db, work_id)
    try:
        from librarian.grooming_undo import record_grooming_batch

        record_grooming_batch(root, action="skip", works=[work])
    except Exception:  # noqa: BLE001 — undo must never block Skip
        pass
    if not db.delete_work(work_id):
        raise NotFoundError("Work not found")
    return {"deleted": True, "work_id": work_id}


def _failed_release_context(db: Any, work: Mapping[str, Any], work_id: str) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """What the failed release looked like, plus any candidates remembered from its job."""
    failed_guid = str(work.get("indexer_guid") or "").strip()
    failed_ctx: Dict[str, Any] = {
        "guid": failed_guid,
        "title": str(work.get("title") or "").strip(),
        "host": "",
        "size": None,
    }
    file_sizes = [
        int(row["size"]) for row in db.files_for_work(work_id) if row.get("size") is not None
    ]
    if file_sizes:
        failed_ctx["size"] = sum(file_sizes)
    remembered: List[Dict[str, Any]] = []
    if failed_guid:
        prior = db.get_job_by_indexer_guid(failed_guid)
        if prior:
            payload = prior.get("payload") if isinstance(prior.get("payload"), dict) else {}
            selected = payload.get("selected") if isinstance(payload.get("selected"), dict) else {}
            if selected.get("title"):
                failed_ctx["title"] = str(selected.get("title") or "")
            if selected.get("size") is not None:
                failed_ctx["size"] = selected.get("size")
            elif prior.get("bytes") is not None:
                failed_ctx["size"] = prior.get("bytes")
            failed_ctx["host"] = str(
                selected.get("host_name") or selected.get("host") or selected.get("indexer") or ""
            ).strip()
            if isinstance(payload.get("candidates"), list):
                remembered = remember_candidates(payload["candidates"])
    return failed_ctx, remembered


def regrab_candidates(db: Any, settings: SettingsFn, *, root: Path, work_id: str) -> Dict[str, Any]:
    """Top three replacement releases for a slip that failed repair twice."""
    work = _require_work(db, work_id)
    fails = int(work.get("repair_fail_count") or 0)
    if fails < 2:
        return {"candidates": [], "repair_fail_count": fails, "ready": False}
    q = " ".join(
        part
        for part in [
            str(work.get("title") or "").strip(),
            str(work.get("author") or "").strip(),
        ]
        if part
    )
    failed_ctx, remembered = _failed_release_context(db, work, work_id)
    failed_guid = failed_ctx["guid"]
    exclude = db.tried_indexer_guids_for_work(work)
    excluded = set(exclude)
    beyond_error = None
    hits: List[Dict[str, Any]] = []
    search_trace = None
    rank_method = ""
    rank_reason = ""
    ranked_candidates: List[Dict[str, Any]] = []
    if remembered:
        hits = [row for row in remembered if str(row.get("guid") or "").strip() not in excluded]
    if len(hits) < 3:
        ranked = search_and_rank(
            settings(),
            data_dir=root,
            q=q,
            kind=str(work.get("kind") or ""),
            title=str(work.get("title") or ""),
            author=str(work.get("author") or ""),
        )
        beyond_error = ranked.get("error")
        if beyond_error:
            from librarian.llm import friendly_llm_error

            beyond_error = friendly_llm_error(RuntimeError(str(beyond_error)))
        rank_method = str(ranked.get("rank_method") or "")
        rank_reason = str(ranked.get("rank_reason") or "")
        ranked_candidates = list(ranked.get("candidates") or [])
        search_trace = {
            "conversation": list(ranked.get("conversation") or []),
            "steps": list(ranked.get("steps") or []),
            "results": list(ranked.get("results") or []),
            "rank_method": rank_method,
            "rank_reason": rank_reason,
        }
        seen = {str(row.get("guid") or "") for row in hits}
        for row in list(ranked.get("hits") or []):
            guid = str(row.get("guid") or "").strip()
            if not guid or guid in seen or guid in excluded:
                continue
            hits.append(row)
            seen.add(guid)
    candidates = rank_regrab_candidates(
        hits or [],
        failed_guid=failed_guid,
        failed=failed_ctx,
        exclude_guids=exclude,
        limit=3,
    )
    # Prefer full ranked memory for dud-primary fallback on the next request.
    memory = ranked_candidates or remember_candidates(hits)
    return {
        "candidates": candidates,
        "remembered_candidates": memory,
        "repair_fail_count": fails,
        "ready": True,
        "beyond_error": beyond_error,
        "from_memory": bool(remembered),
        "rank_method": rank_method,
        "rank_reason": rank_reason,
        "search_trace": search_trace,
    }
