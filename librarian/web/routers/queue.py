"""Request enqueue and the household download queue."""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request

from librarian.auth import require_role
from librarian.indexers.scrub import (
    public_job,
    public_jobs,
)
from librarian.ingest import poll_watch_folder
from librarian.jobs import (
    QUEUE_VIEW_ACTIONABLE,
    QUEUE_VIEW_ACTIVE,
    QUEUE_VIEW_HISTORY,
    QUEUE_VIEWS,
    confirm_asked_job,
    dismiss_queue_job,
    enqueue_indexer_item,
    poll_active_jobs,
    poll_job,
    queue_view_statuses,
    retry_failed_job,
)
from librarian.nzbfinder import NZBFinderError
from librarian.rss import poll_rss_feeds
from librarian.sabnzbd import SABError
from librarian.web.deps import WebDeps
from librarian.web.schemas import (
    RequestPayload,
)

logger = logging.getLogger("librarian.web")


def register_queue_routes(app: FastAPI, deps: WebDeps) -> None:
    """Register request and queue routes on the composition-root app."""
    db = deps.db
    settings = deps.settings

    @app.post("/api/request")
    def request_item(payload: RequestPayload, request: Request):
        user = request.state.user
        require_role(user, "owner", "op", "reader")
        item = payload.model_dump()
        kind = str(item.get("kind") or (item.get("selected") or {}).get("kind") or "")
        if kind in {"movie", "tv", "xxx"}:
            raise HTTPException(status_code=400, detail="That kind is not on these shelves.")
        try:
            job = enqueue_indexer_item(
                db, settings(), item=item, requested_by=user["id"], role=user["role"]
            )
        except (SABError, NZBFinderError) as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        return {"job": public_job(job)}

    @app.get("/api/queue")
    def queue(request: Request, view: str = "actionable"):
        """List jobs only — no watch/RSS/SAB side effects (P2-CRIT-01).

        Default ``view=actionable`` (Asked / Failed / Needs you). Active, History
        (Arrived), and All are one tap away with accurate counts (PRD-011).
        """
        require_role(request.state.user, "owner", "op")
        key = str(view or "actionable").strip().lower() or "actionable"
        if key not in QUEUE_VIEWS:
            key = "actionable"
        jobs = [
            job
            for job in db.list_jobs(limit=200)
            if str(
                (
                    job.get("payload") if isinstance(job.get("payload"), dict) else {}
                ).get("source")
                or ""
            )
            != "ask"
            or str(job.get("indexer_guid") or "").strip()
        ]
        counts = {
            "actionable": 0,
            "active": 0,
            "history": 0,
            "all": len(jobs),
        }
        for job in jobs:
            status = str(job.get("status") or "")
            if status in QUEUE_VIEW_ACTIONABLE:
                counts["actionable"] += 1
            elif status in QUEUE_VIEW_ACTIVE:
                counts["active"] += 1
            elif status in QUEUE_VIEW_HISTORY:
                counts["history"] += 1
        allowed = queue_view_statuses(key)
        if allowed is not None:
            jobs = [job for job in jobs if str(job.get("status") or "") in allowed]
        for job in jobs:
            if job.get("status") != "review":
                continue
            work_id = str(job.get("work_id") or "").strip()
            if not work_id:
                continue
            work = db.get_work(work_id)
            if not work:
                continue
            job["review_reason"] = work.get("review_reason")
            job["review_state"] = work.get("review_state")
        rank = {"review": 0, "failed": 1, "skipped": 1, "asked": 2}
        jobs.sort(key=lambda row: (rank.get(str(row.get("status") or ""), 3), -float(row.get("updated_at") or 0)))
        return {"jobs": public_jobs(jobs), "view": key, "counts": counts}

    @app.post("/api/queue/tick")
    def queue_tick(request: Request):
        """Explicit poller kick — JobPoller remains the automatic driver."""
        require_role(request.state.user, "owner", "op")
        cfg = settings()
        poll_watch_folder(db, cfg)
        try:
            poll_rss_feeds(db, cfg)
        except Exception:
            logger.exception("RSS tick failed")
        try:
            poll_active_jobs(db, cfg)
        except SABError:
            pass
        return {"ok": True}

    @app.post("/api/queue/{job_id}/poll")
    def queue_poll(job_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            job = poll_job(db, settings(), job_id)
        except (ValueError, SABError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"job": public_job(job)}

    @app.post("/api/queue/{job_id}/confirm")
    def queue_confirm(job_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            job = confirm_asked_job(db, settings(), job_id)
        except (ValueError, SABError, NZBFinderError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"job": public_job(job)}

    @app.post("/api/queue/{job_id}/retry")
    def queue_retry(job_id: str, request: Request):
        """Failed/skipped → Asked. Confirm still sends SABnzbd."""
        require_role(request.state.user, "owner", "op")
        try:
            job = retry_failed_job(db, job_id)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"job": public_job(job)}

    @app.post("/api/queue/{job_id}/dismiss")
    def queue_dismiss(job_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            job = dismiss_queue_job(db, job_id)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"job": public_job(job)}

    @app.post("/api/gaps/confirm")
    def gaps_confirm(payload: RequestPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        return request_item(payload, request)
