"""In-app inbox and per-kind notification preference routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from librarian.notifications import (
    deliver_editions,
    deliver_notification,
    flush_email_digests,
    merge_notification_prefs,
    notification_channel_offerings,
    public_notification_prefs,
    resolve_push_user_ids,
)
from librarian.web.deps import WebDeps
from librarian.web.route_imports import *  # noqa: F403


class NotificationsSeenPayload(BaseModel):
    ids: Optional[List[str]] = None
    all_unread: bool = False


class NotificationPrefsPayload(BaseModel):
    notification_email: Optional[str] = Field(default=None, max_length=320)
    kinds: Optional[Dict[str, Any]] = None


class NotificationTestPayload(BaseModel):
    kind: str = "arrived"
    title: str = "Test notice from the library"
    body: Optional[str] = "If you see this in your inbox, notifications are working."


class NewsletterPushPayload(BaseModel):
    """Owner early push / self-test for library newsletter editions."""

    scope: str = "self"  # self | users | all
    user_ids: Optional[List[str]] = None
    force: bool = True  # skip cadence wait (still requires opt-in)


def register_notification_routes(app: FastAPI, deps: WebDeps) -> None:
    """Register notification inbox + prefs routes on the composition-root app."""
    db = deps.db
    settings = deps.settings

    @app.get("/api/notifications")
    def list_notifications(
        request: Request,
        unread_only: bool = Query(default=False),
        limit: int = Query(default=50, ge=1, le=100),
        kind: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        user = request.state.user
        require_role(user, "owner", "op", "reader")
        kinds = [kind] if kind else None
        items = db.list_notifications_for_user(
            user["id"],
            unread_only=unread_only,
            kinds=kinds,
            limit=limit,
        )
        return {
            "items": items,
            "unread_count": db.count_unread_notifications(user["id"]),
        }

    @app.post("/api/notifications/seen")
    def mark_seen(payload: NotificationsSeenPayload, request: Request) -> Dict[str, Any]:
        user = request.state.user
        require_role(user, "owner", "op", "reader")
        updated = db.mark_notifications_seen(
            user["id"],
            notification_ids=payload.ids or None,
            all_unread=bool(payload.all_unread),
        )
        return {
            "updated": updated,
            "unread_count": db.count_unread_notifications(user["id"]),
        }

    @app.get("/api/notifications/prefs")
    def get_notification_prefs(request: Request) -> Dict[str, Any]:
        user = request.state.user
        require_role(user, "owner", "op", "reader")
        cfg = settings()
        prefs = public_notification_prefs(db.get_user_prefs(user["id"]))
        return {
            **prefs,
            "channels": notification_channel_offerings(cfg),
            "mail_configured": any(
                c.get("id") == "email" and c.get("available") for c in notification_channel_offerings(cfg)
            ),
        }

    @app.put("/api/notifications/prefs")
    def put_notification_prefs(payload: NotificationPrefsPayload, request: Request) -> Dict[str, Any]:
        user = request.state.user
        require_role(user, "owner", "op", "reader")
        data = payload.model_dump(exclude_unset=True)
        try:
            nested = merge_notification_prefs(
                db.get_user_prefs(user["id"]),
                notification_email=data["notification_email"] if "notification_email" in data else ...,
                kinds=data.get("kinds") if "kinds" in data else None,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        saved = db.set_user_prefs(user["id"], prefs=nested)
        cfg = settings()
        prefs = public_notification_prefs(saved)
        return {
            **prefs,
            "channels": notification_channel_offerings(cfg),
            "mail_configured": any(
                c.get("id") == "email" and c.get("available") for c in notification_channel_offerings(cfg)
            ),
        }

    @app.post("/api/notifications/test")
    def test_notification(payload: NotificationTestPayload, request: Request) -> Dict[str, Any]:
        """Owner self-test: drop one inbox item (and email if that kind opts in)."""
        user = request.state.user
        require_role(user, "owner")
        try:
            result = deliver_notification(
                db,
                settings(),
                user_id=user["id"],
                kind=payload.kind,
                title=payload.title,
                body=payload.body,
                force_inbox=True,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "ok": True,
            "notification": result.get("notification"),
            "emailed": bool(result.get("emailed")),
            "email_error": result.get("email_error"),
            "unread_count": db.count_unread_notifications(user["id"]),
        }

    @app.post("/api/notifications/digest/flush")
    def flush_digests(
        request: Request,
        period: str = Query(default="daily"),
    ) -> Dict[str, Any]:
        """Owner flush of queued daily/weekly digest emails (scheduler seam)."""
        require_role(request.state.user, "owner")
        return flush_email_digests(db, settings(), period=period)

    @app.post("/api/newsletters/push")
    def push_newsletter(payload: NewsletterPushPayload, request: Request) -> Dict[str, Any]:
        """Owner: push personalized editions early (opt-in still required; never force-email)."""
        user = request.state.user
        require_role(user, "owner")
        scope = str(payload.scope or "self").strip().lower()
        if scope not in {"self", "me", "users", "selected", "all", "opted_in"}:
            raise HTTPException(status_code=400, detail="scope must be self, users, or all")
        if scope in {"users", "selected"} and not (payload.user_ids or []):
            raise HTTPException(status_code=400, detail="Select at least one member")
        targets = resolve_push_user_ids(
            db,
            scope=scope,
            actor_id=str(user["id"]),
            user_ids=payload.user_ids,
        )
        result = deliver_editions(
            db,
            settings(),
            user_ids=targets,
            force=bool(payload.force),
        )
        return {"ok": True, **result}

    @app.post("/api/newsletters/run")
    def run_due_newsletters(request: Request) -> Dict[str, Any]:
        """Owner: deliver editions that are due by cadence (scheduler seam)."""
        require_role(request.state.user, "owner")
        result = deliver_editions(db, settings(), force=False)
        return {"ok": True, **result}
