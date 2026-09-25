"""Review bagging and Clear/Purge job routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile

from librarian.web.deps import WebDeps
from librarian.web.route_imports import *  # noqa: F403


def register_review_routes(app: FastAPI, deps: WebDeps) -> None:
    """Register review routes on the composition-root app."""
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

    @app.get("/api/review")
    def review_list(request: Request):
        require_role(request.state.user, "owner", "op")
        cfg = settings()
        from librarian.llm_providers import resolve_llm_connection

        llm_ok = bool(resolve_llm_connection(cfg).get("api_key"))
        works = public_works(db.list_works(review_state="needs_review", limit=80))
        jobs_by_work: Dict[str, Any] = {}
        for job in db.list_jobs(limit=200):
            work_id = job.get("work_id")
            if work_id and work_id not in jobs_by_work:
                jobs_by_work[work_id] = job
        for work in works:
            job = jobs_by_work.get(work["id"]) if work else None
            storage = str((job or {}).get("storage_path") or "")
            work["storage_path"] = storage or None
            if not work.get("folder_path") and storage:
                work["folder_path"] = storage
            folder_raw = str(work.get("folder_path") or storage or "")
            diagnosis = diagnose_review_folder(Path(folder_raw), cfg.complete_root)
            work["folder_diagnosis"] = diagnosis
            problem = diagnosis.get("problem")
            stored = str(work.get("review_reason") or "")
            # Response overlay only — SQLite soft-repair runs in the poller.
            if problem == REVIEW_UNPACK_STUCK and stored in {"", REVIEW_NO_PAYLOAD}:
                work["review_reason"] = REVIEW_UNPACK_STUCK
            shelf = shelf_work_for_collision(db, work)
            work["shelf_work"] = shelf
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
        extra_files_count = db.count_works(review_state="needs_review", review_reason=REVIEW_EXTRA)
        needs_review_count = db.count_works(review_state="needs_review")
        return {
            "works": works,
            "llm_configured": llm_ok,
            "extra_files_count": extra_files_count,
            "needs_review_count": needs_review_count,
        }

    @app.post("/api/review/reprocess-extra-files")
    def review_reprocess_extra_files(request: Request, limit: int = 0):
        """Owner bulk: kick off background clear for extra_files slips (poll status)."""
        require_role(request.state.user, "owner", "op")
        user = request.state.user
        requested_by = str(user.get("id") or user.get("display_name") or "owner")
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

        kicked = extra_files_reprocess_job.start_if_idle(
            is_running=lambda: is_extra_files_reprocess_running(root),
            begin=lambda: begin_extra_files_reprocess_run(root, total=0, phase="starting"),
            target=run_reprocess,
            name="librarian-extra-files-reprocess",
        )
        payload = read_extra_files_reprocess_progress(root)
        payload["extra_files_remaining"] = db.count_works(
            review_state="needs_review", review_reason=REVIEW_EXTRA
        )
        return {**payload, "kicked_off": kicked}

    @app.get("/api/review/reprocess-extra-files/status")
    def review_reprocess_extra_files_status(request: Request):
        """Poll Clear extra-files slips progress (survives refresh via DATA_DIR JSON)."""
        require_role(request.state.user, "owner", "op")
        progress = read_extra_files_reprocess_progress(root)
        if str(progress.get("status") or "") != "running":
            progress["extra_files_remaining"] = db.count_works(
                review_state="needs_review", review_reason=REVIEW_EXTRA
            )
            return progress
        alive = extra_files_reprocess_job.alive()
        if alive and not is_extra_files_reprocess_stale(progress):
            progress["extra_files_remaining"] = db.count_works(
                review_state="needs_review", review_reason=REVIEW_EXTRA
            )
            return progress
        if alive:
            error = (
                "Clear extra-files stalled (no progress heartbeat). "
                "Try Clear again — large author folders now queue instead of blocking."
            )
        else:
            error = "Clear extra-files stopped — the lamp was restarted. Try again."
        finished = finish_extra_files_reprocess_run(root, error=error)
        finished["extra_files_remaining"] = db.count_works(
            review_state="needs_review", review_reason=REVIEW_EXTRA
        )
        return finished

    @app.post("/api/review/purge-duplicates")
    def review_purge_duplicates(request: Request, limit: int = 0):
        """Owner bulk: dismiss safely redundant Review slips (poll status)."""
        require_role(request.state.user, "owner", "op")
        run_limit = max(0, int(limit or 0))

        def run_purge() -> None:
            reporter = PurgeDuplicatesProgressReporter(root)
            try:
                purge_duplicate_reviews(
                    db,
                    settings(),
                    limit=run_limit,
                    progress=reporter,
                )
            except Exception as error:
                logger.exception("Purge duplicates failed")
                reporter.fail(str(error) or "Purge duplicates failed")

        kicked = purge_duplicates_job.start_if_idle(
            is_running=lambda: is_purge_duplicates_running(root),
            begin=lambda: begin_purge_duplicates_run(root, total=0, phase="starting"),
            target=run_purge,
            name="librarian-purge-duplicates",
        )
        payload = read_purge_duplicates_progress(root)
        payload["needs_review_remaining"] = db.count_works(review_state="needs_review")
        return {**payload, "kicked_off": kicked}

    @app.get("/api/review/purge-duplicates/status")
    def review_purge_duplicates_status(request: Request):
        """Poll Purge duplicates progress (survives refresh via DATA_DIR JSON)."""
        require_role(request.state.user, "owner", "op")
        progress = read_purge_duplicates_progress(root)
        if str(progress.get("status") or "") != "running":
            progress["needs_review_remaining"] = db.count_works(review_state="needs_review")
            return progress
        alive = purge_duplicates_job.alive()
        if alive and not is_purge_duplicates_stale(progress):
            progress["needs_review_remaining"] = db.count_works(review_state="needs_review")
            return progress
        if alive:
            error = (
                "Purge duplicates stalled (no progress heartbeat). "
                "Try Purge again."
            )
        else:
            error = "Purge duplicates stopped — the lamp was restarted. Try again."
        finished = finish_purge_duplicates_run(root, error=error)
        finished["needs_review_remaining"] = db.count_works(review_state="needs_review")
        return finished

    @app.post("/api/review/{work_id}/suggest")
    def review_suggest(work_id: str, request: Request):
        """BYO LLM title/author suggest for a Review slip. Pre-fills only — never Apply."""
        require_role(request.state.user, "owner", "op")
        if db.get_work(work_id) is None:
            raise HTTPException(status_code=404, detail="Work not found")
        job = None
        for row in db.list_jobs(limit=200):
            if row.get("work_id") == work_id:
                job = row
                break
        try:
            return suggest_review_identity(db, settings(), work_id=work_id, job=job)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/review/{work_id}/apply")
    def review_apply(work_id: str, payload: ReviewApplyPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        raw = str(payload.folder or work.get("folder_path") or "").strip()
        folder = Path(raw) if raw else Path()
        overrides = payload.model_dump(exclude_none=True)
        overrides.pop("folder", None)
        try:
            result = apply_review(db, settings(), work_id=work_id, folder=folder, identity_overrides=overrides)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return result

    @app.post("/api/review/{work_id}/repair")
    def review_repair(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        if db.get_work(work_id) is None:
            raise HTTPException(status_code=404, detail="Work not found")
        try:
            return repair_review(db, settings(), work_id=work_id)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/review/{work_id}/regrab")
    def review_regrab_candidates(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        fails = int(work.get("repair_fail_count") or 0)
        if fails < 2:
            return {"candidates": [], "repair_fail_count": fails, "ready": False}
        q = " ".join(
            part
            for part in [str(work.get("title") or "").strip(), str(work.get("author") or "").strip()]
            if part
        )
        failed_guid = str(work.get("indexer_guid") or "").strip()
        failed_ctx: Dict[str, Any] = {
            "guid": failed_guid,
            "title": str(work.get("title") or "").strip(),
            "host": "",
            "size": None,
        }
        file_sizes = [
            int(row["size"])
            for row in db.files_for_work(work_id)
            if row.get("size") is not None
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
                    selected.get("host_name")
                    or selected.get("host")
                    or selected.get("indexer")
                    or ""
                ).strip()
                if isinstance(payload.get("candidates"), list):
                    remembered = remember_candidates(payload["candidates"])
        exclude = db.tried_indexer_guids_for_work(work)
        beyond_error = None
        hits: List[Dict[str, Any]] = []
        search_trace = None
        rank_method = ""
        rank_reason = ""
        ranked_candidates: List[Dict[str, Any]] = []
        if remembered:
            hits = [row for row in remembered if str(row.get("guid") or "").strip() not in set(exclude)]
        if len(hits) < 3:
            ranked = search_and_rank(
                settings(),
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
            fresh = list(ranked.get("hits") or [])
            seen = {str(row.get("guid") or "") for row in hits}
            for row in fresh:
                guid = str(row.get("guid") or "").strip()
                if not guid or guid in seen or guid in set(exclude):
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

    @app.post("/api/review/{work_id}/retry")
    def review_retry(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        if db.get_work(work_id) is None:
            raise HTTPException(status_code=404, detail="Work not found")
        try:
            return retry_review(db, settings(), work_id=work_id)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/review/{work_id}/skip")
    def review_skip(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        updated = db.delete_work(work_id)
        if not updated:
            raise HTTPException(status_code=404, detail="Work not found")
        return {"deleted": True, "work_id": work_id}

    @app.post("/api/review/{work_id}/reprocess-extra-files")
    def review_reprocess_extra_files_one(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        user = request.state.user
        try:
            return reprocess_extra_files_work(
                db,
                settings(),
                work_id=work_id,
                requested_by=str(user.get("id") or user.get("display_name") or "owner"),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

