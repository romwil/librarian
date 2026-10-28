"""Holds desk and Clear/Purge job routes."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, Request

from librarian import review_suggest_batch as review_suggest_batch_mod
from librarian.auth import require_role
from librarian.progress_job import BackgroundJobSlot
from librarian.services import review as review_service
from librarian.web.deps import WebDeps
from librarian.web.schemas import ReviewApplyPayload, ReviewRetrievePayload
from librarian.web.service_errors import http_errors


def _requested_by(user: Dict[str, Any]) -> str:
    return str(user.get("id") or user.get("display_name") or "owner")


def register_review_routes(app: FastAPI, deps: WebDeps) -> None:
    """Register review routes on the composition-root app."""
    root = deps.root
    db = deps.db
    settings = deps.settings
    extra_files_reprocess_job = deps.extra_files_reprocess_job
    purge_duplicates_job = deps.purge_duplicates_job
    suggest_batch_job = BackgroundJobSlot()

    @app.get("/api/review")
    def review_list(request: Request, work: str = ""):
        require_role(request.state.user, "owner", "op")
        return review_service.review_desk(db, settings(), root=root, focus=work)

    @app.get("/api/review/bad-release-migration/status")
    def review_bad_release_migration_status(request: Request):
        """One-time return of no-payload / convert-failed slips to Wanted (boot migration)."""
        require_role(request.state.user, "owner", "op")
        return review_service.bad_release_migration_status(db, root)

    @app.post("/api/review/bulk-by-reason")
    def review_bulk_by_reason(request: Request, body: Optional[Dict[str, Any]] = Body(default=None)):
        """One group action on a pile, by the server's effective reason. Never deletes files."""
        require_role(request.state.user, "owner", "op")
        with http_errors():
            return review_service.bulk_motion(db, settings(), root=root, payload=body or {})

    @app.post("/api/review/suggest-batch")
    def review_suggest_batch(request: Request, limit: int = 0):
        """Kick off model triage for low-confidence slips (poll status; each answer persists)."""
        require_role(request.state.user, "owner", "op")
        return review_service.start_suggest_batch(
            db, settings, root=root, slot=suggest_batch_job, limit=limit
        )

    @app.get("/api/review/suggest-batch/status")
    def review_suggest_batch_status(request: Request):
        require_role(request.state.user, "owner", "op")
        return review_service.suggest_batch_status(root=root, slot=suggest_batch_job)

    @app.post("/api/review/apply-trusted")
    def review_apply_trusted(request: Request):
        """File slips whose persisted model answer is trusted, through the normal Apply path."""
        require_role(request.state.user, "owner", "op")
        return review_suggest_batch_mod.apply_trusted_matches(db, settings(), data_dir=root)

    @app.post("/api/review/reprocess-extra-files")
    def review_reprocess_extra_files(request: Request, limit: int = 0):
        """Owner bulk: kick off background clear for extra_files slips (poll status)."""
        require_role(request.state.user, "owner", "op")
        return review_service.start_extra_files_reprocess(
            db,
            settings,
            root=root,
            slot=extra_files_reprocess_job,
            requested_by=_requested_by(request.state.user),
            limit=limit,
        )

    @app.get("/api/review/reprocess-extra-files/status")
    def review_reprocess_extra_files_status(request: Request):
        """Poll Clear extra-files slips progress (survives refresh via DATA_DIR JSON)."""
        require_role(request.state.user, "owner", "op")
        return review_service.extra_files_reprocess_status(
            db, root=root, slot=extra_files_reprocess_job
        )

    @app.post("/api/review/accept-clear")
    def review_accept_clear(request: Request, body: Optional[Dict[str, Any]] = Body(default=None)):
        """Shelve path-clear slips in one reason group. Does not delete files."""
        require_role(request.state.user, "owner", "op")
        from librarian.slip_gate import accept_path_clear_slips

        reason = str((body or {}).get("reason") or "")
        return accept_path_clear_slips(db, reason=reason)

    @app.post("/api/review/purge-duplicates")
    def review_purge_duplicates(request: Request, limit: int = 0):
        """Owner bulk: dismiss safely redundant Review slips (poll status)."""
        require_role(request.state.user, "owner", "op")
        return review_service.start_purge_duplicates(
            db, settings, root=root, slot=purge_duplicates_job, limit=limit
        )

    @app.get("/api/review/purge-duplicates/status")
    def review_purge_duplicates_status(request: Request):
        """Poll Purge duplicates progress (survives refresh via DATA_DIR JSON)."""
        require_role(request.state.user, "owner", "op")
        return review_service.purge_duplicates_status(db, root=root, slot=purge_duplicates_job)

    @app.post("/api/review/{work_id}/suggest")
    def review_suggest(work_id: str, request: Request):
        """BYO LLM title/author suggest for a Review slip. Pre-fills only — never Apply."""
        require_role(request.state.user, "owner", "op")
        with http_errors():
            return review_service.suggest_slip(db, settings(), work_id=work_id)

    @app.post("/api/review/{work_id}/apply")
    def review_apply(work_id: str, payload: ReviewApplyPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        overrides = payload.model_dump(exclude_none=True)
        overrides.pop("folder", None)
        with http_errors():
            return review_service.apply_slip(
                db,
                settings(),
                work_id=work_id,
                folder=payload.folder,
                identity_overrides=overrides,
            )

    @app.post("/api/review/{work_id}/repair")
    def review_repair(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        with http_errors():
            return review_service.repair_slip(db, settings(), work_id=work_id)

    @app.post("/api/review/{work_id}/retrieve")
    def review_retrieve(work_id: str, payload: ReviewRetrievePayload, request: Request):
        """Search and queue another release on this slip. Does not send the household to Find."""
        require_role(request.state.user, "owner", "op")
        user = request.state.user
        with http_errors():
            return review_service.retrieve_slip(
                db,
                settings(),
                root=root,
                work_id=work_id,
                intent=payload.intent,
                role=str(user.get("role") or ""),
                requested_by=str(user.get("id") or ""),
            )

    @app.get("/api/review/{work_id}/regrab")
    def review_regrab_candidates(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        with http_errors():
            return review_service.regrab_candidates(db, settings, root=root, work_id=work_id)

    @app.post("/api/review/{work_id}/retry")
    def review_retry(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        with http_errors():
            return review_service.retry_slip(db, settings(), work_id=work_id)

    @app.post("/api/review/{work_id}/skip")
    def review_skip(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        with http_errors():
            return review_service.skip_slip(db, root=root, work_id=work_id)

    @app.post("/api/review/{work_id}/reprocess-extra-files")
    def review_reprocess_extra_files_one(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        with http_errors():
            return review_service.reprocess_extra_files_slip(
                db,
                settings(),
                work_id=work_id,
                requested_by=_requested_by(request.state.user),
            )
