"""Settings, RSS, and indexer routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile

from librarian.web.deps import WebDeps
from librarian.web.route_imports import *  # noqa: F403


def register_settings_routes(app: FastAPI, deps: WebDeps) -> None:
    """Register settings routes on the composition-root app."""
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

    @app.get("/api/indexers")
    def list_indexers(request: Request):
        require_role(request.state.user, "owner")
        return {"indexers": db.list_indexers()}

    @app.post("/api/indexers/ping")
    def indexer_ping(request: Request):
        require_role(request.state.user, "owner")
        return ping_nzbfinder(db, settings())

    @app.get("/api/settings")
    def get_settings(request: Request):
        require_role(request.state.user, "owner")
        return {"settings": mask_settings(settings()), "abs_match": abs_match_counts(db)}

    @app.put("/api/settings")
    def put_settings(payload: SettingsPayload, request: Request):
        require_role(request.state.user, "owner")
        incoming = {key: value for key, value in payload.model_dump().items() if value is not None}
        if "extra_indexers" in incoming:
            incoming["extra_indexers"] = [
                row if isinstance(row, dict) else dict(row)
                for row in incoming["extra_indexers"]
            ]
        if "mail" in incoming and isinstance(incoming["mail"], dict):
            # Drop unset nested keys so retain-on-empty only sees explicit blanks.
            incoming["mail"] = {
                key: value for key, value in incoming["mail"].items() if value is not None
            }
        merged = merge_secret_fields(incoming, settings())
        from librarian.config import Settings

        saved = Settings.from_mapping(merged)
        watch_error = validate_watch_root(str(saved.watch_root or ""), saved)
        if watch_error:
            raise HTTPException(status_code=400, detail=watch_error)
        save_settings(root, saved)
        sync_nzbfinder(db, saved)
        return {"settings": mask_settings(saved), "abs_match": abs_match_counts(db)}

    @app.post("/api/settings/mail/test")
    def test_mail_send(payload: MailTestPayload, request: Request):
        """Send a test email using the configured SMTP or Resend transport."""
        require_role(request.state.user, "owner")
        from librarian.mail import MailSendError, mail_configured, send_mail

        cfg = settings()
        if not mail_configured(cfg):
            raise HTTPException(
                status_code=400,
                detail="Configure and enable SMTP or Resend under Settings → Mail first.",
            )
        to_email = str(payload.to_email or "").strip()
        if not to_email or "@" not in to_email:
            raise HTTPException(
                status_code=400,
                detail="Provide a to_email address for the test send.",
            )
        try:
            result = send_mail(
                cfg,
                to_email=to_email,
                subject="Librarian mail test",
                body_text=(
                    "This is a test message from Librarian.\n\n"
                    "If you received it, your mail settings are working."
                ),
            )
        except MailSendError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "ok": True,
            "provider": result.provider,
            "message_id": result.message_id,
            "to_email": to_email,
        }

    @app.get("/api/settings/quiet-hours")
    def get_quiet_hours(request: Request):
        require_role(request.state.user, "owner", "op")
        cfg = settings()
        return {
            "quiet_hours_enabled": bool(cfg.quiet_hours_enabled),
            "quiet_hours_start": cfg.quiet_hours_start,
            "quiet_hours_end": cfg.quiet_hours_end,
            "active_now": in_quiet_hours(cfg),
        }

    @app.put("/api/settings/quiet-hours")
    def put_quiet_hours(payload: SettingsPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        incoming = {
            key: value
            for key, value in payload.model_dump().items()
            if value is not None and key in {"quiet_hours_enabled", "quiet_hours_start", "quiet_hours_end"}
        }
        merged = merge_secret_fields(incoming, settings())
        from librarian.config import Settings

        saved = Settings.from_mapping(merged)
        save_settings(root, saved)
        return {
            "quiet_hours_enabled": bool(saved.quiet_hours_enabled),
            "quiet_hours_start": saved.quiet_hours_start,
            "quiet_hours_end": saved.quiet_hours_end,
            "active_now": in_quiet_hours(saved),
        }

    @app.get("/api/rss")
    def rss_list(request: Request):
        require_role(request.state.user, "owner", "op")
        return {"feeds": [public_rss_feed(row) for row in db.list_rss_feeds()]}

    @app.post("/api/rss")
    def rss_create(payload: RssFeedPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            feed = create_rss_feed(db, payload.model_dump())
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"feed": feed}

    @app.put("/api/rss/{feed_id}")
    def rss_update(feed_id: str, payload: RssFeedPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            feed = update_rss_feed(db, feed_id, payload.model_dump(exclude_unset=True))
        except ValueError as error:
            status = 404 if str(error) == "RSS feed not found" else 400
            raise HTTPException(status_code=status, detail=str(error)) from error
        return {"feed": feed}

    @app.delete("/api/rss/{feed_id}")
    def rss_delete(feed_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        if db.get_rss_feed(feed_id) is None:
            raise HTTPException(status_code=404, detail="RSS feed not found")
        db.delete_rss_feed(feed_id)
        return {"ok": True}

    @app.post("/api/rss/poll")
    def rss_poll(request: Request):
        require_role(request.state.user, "owner", "op")
        created = poll_rss_feeds(db, settings())
        return {"created": created, "feeds": [public_rss_feed(row) for row in db.list_rss_feeds()]}

