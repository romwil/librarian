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
    confirm_asked_job,
    enqueue_indexer_item,
    poll_active_jobs,
    poll_job,
)
from librarian.kinds import EXTRA_KINDS
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
        if kind in EXTRA_KINDS and not settings().show_extra_categories:
            raise HTTPException(status_code=400, detail="Show categories is off")
        try:
            job = enqueue_indexer_item(
                db, settings(), item=item, requested_by=user["id"], role=user["role"]
            )
        except (SABError, NZBFinderError) as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        return {"job": public_job(job)}

    @app.get("/api/queue")
    def queue(request: Request):
        """List jobs only — no watch/RSS/SAB side effects (P2-CRIT-01)."""
        require_role(request.state.user, "owner", "op")
        jobs = db.list_jobs()
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
        return {"jobs": public_jobs(jobs)}

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

    @app.post("/api/gaps/confirm")
    def gaps_confirm(payload: RequestPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        return request_item(payload, request)
