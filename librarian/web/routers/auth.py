"""Auth, health, features, invites, and people routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from librarian import __version__
from librarian.auth import (
    INVITE_ROLES,
    change_own_password,
    clear_session_cookie,
    has_real_owner,
    public_user,
    require_role,
    set_session_cookie,
    sign_out_everywhere,
    verify_password,
)
from librarian.invites import (
    create_household_invite,
    list_pending_invites,
    lookup_pending_invite,
    public_invite_view,
    redeem_local_invite,
    resolve_invite_base_url,
    revoke_household_invite,
)
from librarian.privacy import household_privacy_notice, member_export_payload
from librarian.rate_limit import (
    auth_local_login_limit,
    clear_login_failures,
    enforce_account_backoff,
    enforce_rate_limit,
    record_login_failure,
)
from librarian.resets import issue_password_reset, lookup_pending_reset, redeem_password_reset
from librarian.sessions import (
    SESSION_COOKIE_NAME,
    has_usable_session_secret,
    invalidate_session_cache,
    parse_session_token,
)
from librarian.web.deps import WebDeps
from librarian.web.schemas import (
    DisablePayload,
    InvitePayload,
    LoginPayload,
    PasswordChangePayload,
    RedeemPayload,
    ResetRedeemPayload,
    RoleChangePayload,
)
from librarian.web.status import is_ready, owner_status


def register_auth_routes(app: FastAPI, deps: WebDeps) -> None:
    """Register auth routes on the composition-root app."""
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

    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        """Public liveness — process is up. No version, rev, notes, or build."""
        return {"status": "ok"}

    @app.get("/api/health/ready")
    def health_ready(request: Request):
        """Public readiness: 200 or 503 only. No booleans or ages in the body."""
        poller = getattr(request.app.state, "poller", None)
        if not is_ready(db=db, poller=poller):
            return JSONResponse({}, status_code=503)
        return JSONResponse({}, status_code=200)

    @app.get("/api/status")
    def status(request: Request) -> Dict[str, Any]:
        """Owner deploy truth: version, rev, notes lockstep, poller, last backup."""
        user = getattr(request.state, "user", None) or current_user(request)
        require_role(user, "owner")
        poller = getattr(request.app.state, "poller", None)
        return owner_status(db=db, poller=poller, data_dir=root)

    @app.get("/api/features")
    def features() -> Dict[str, Any]:
        """Foyer-minimal handshake — no ops posture for anonymous LAN recon (P4-MED-01)."""
        cfg = settings()
        return {
            "household_name": cfg.household_name,
            "owner_ready": has_real_owner(db),
            "auth_methods": ["local"],
            "version": __version__,
        }

    @app.get("/api/features/ops")
    def features_ops(request: Request) -> Dict[str, Any]:
        """Authenticated ops posture (session secret, notification channels)."""
        user = getattr(request.state, "user", None) or current_user(request)
        require_role(user, "owner", "op", "reader")
        cfg = settings()
        from librarian.mail import mail_configured
        from librarian.notifications import notification_channel_offerings

        return {
            "session_secret_ok": has_usable_session_secret(root),
            "notifications": {
                "channels": notification_channel_offerings(cfg),
                "mail_configured": mail_configured(cfg),
            },
        }

    def _invite_origin(request: Request) -> str:
        return resolve_invite_base_url(settings(), request)

    @app.post("/api/auth/local/login")
    def login(payload: LoginPayload, request: Request):
        enforce_rate_limit(
            request,
            bucket="auth_local_login",
            limit=auth_local_login_limit(),
            window_seconds=60,
        )
        enforce_account_backoff(payload.username)
        if not has_real_owner(db):
            raise HTTPException(status_code=503, detail="Owner has not been seeded")
        user = db.get_user_by_display_name(payload.username)
        stored = str((user or {}).get("password_hash") or "")
        if user is None or not verify_password(payload.password, stored):
            record_login_failure(payload.username)
            db.add_security_event(kind="login_fail", detail={"name_len": len(payload.username or "")})
            raise HTTPException(status_code=401, detail="Invalid username or password")
        if bool(int(user.get("disabled") or 0)):
            raise HTTPException(status_code=403, detail="This library card is paused")
        clear_login_failures(payload.username)
        db.touch_login(user["id"])
        db.add_security_event(kind="login_success", user_id=user["id"], actor_id=user["id"])
        response = JSONResponse({"authenticated": True, "user": public_user(user)})
        set_session_cookie(
            response,
            user["id"],
            request=request,
            session_epoch=int(user.get("session_epoch") or 0),
            db=db,
        )
        return response

    @app.post("/api/auth/logout")
    def logout(request: Request):
        token = request.cookies.get(SESSION_COOKIE_NAME)
        payload = parse_session_token(token or "")
        if payload and payload.get("jti"):
            db.revoke_session(str(payload["jti"]))
            invalidate_session_cache(jti=str(payload["jti"]))
            db.add_security_event(
                kind="logout",
                user_id=str(payload.get("uid") or "") or None,
                actor_id=str(payload.get("uid") or "") or None,
            )
        response = JSONResponse({"ok": True})
        clear_session_cookie(response, request=request)
        return response

    @app.get("/api/auth/me")
    def me(request: Request):
        user = getattr(request.state, "user", None) or current_user(request)
        require_role(user, "owner", "op", "reader")
        assert user is not None
        payload = {
            "user": public_user(user),
            "review_count": 0,
            "inbox_unread": db.count_unread_notifications(user["id"]),
        }
        if user["role"] in ("owner", "op"):
            payload["review_count"] = db.count_works(review_state="needs_review")
        return payload

    @app.post("/api/auth/password")
    def change_password(payload: PasswordChangePayload, request: Request):
        user = request.state.user
        require_role(user, "owner", "op", "reader")
        try:
            change_own_password(
                db, user, current=payload.current_password, new_password=payload.new_password
            )
        except ValueError as error:
            status = 401 if "match" in str(error).lower() else 400
            raise HTTPException(status_code=status, detail=str(error)) from error
        response = JSONResponse({"ok": True})
        clear_session_cookie(response, request=request)
        fresh = db.get_user(user["id"])
        assert fresh is not None
        set_session_cookie(
            response,
            fresh["id"],
            request=request,
            session_epoch=int(fresh.get("session_epoch") or 0),
            db=db,
        )
        return response

    @app.post("/api/auth/sessions/revoke-all")
    def revoke_all_sessions(request: Request):
        user = request.state.user
        require_role(user, "owner", "op", "reader")
        sign_out_everywhere(db, user["id"])
        response = JSONResponse({"ok": True})
        clear_session_cookie(response, request=request)
        return response

    @app.get("/api/auth/export")
    def export_self(request: Request):
        user = request.state.user
        require_role(user, "owner", "op", "reader")
        db.add_security_event(kind="export", user_id=user["id"], actor_id=user["id"])
        return member_export_payload(db, user["id"])

    @app.get("/api/privacy")
    def privacy_notice(request: Request):
        user = request.state.user
        require_role(user, "owner", "op", "reader")
        return household_privacy_notice(settings())

    @app.get("/api/auth/reset/validate")
    def validate_reset(request: Request, token: str = ""):
        enforce_rate_limit(request, bucket="reset_validate", limit=30, window_seconds=60)
        try:
            row = lookup_pending_reset(db, token)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        user = db.get_user(str(row["user_id"]))
        return {
            "reset": {"expires_at": row["expires_at"]},
            "display_name": (user or {}).get("display_name") or "",
        }

    @app.post("/api/auth/reset/redeem")
    def redeem_reset(payload: ResetRedeemPayload, request: Request):
        enforce_rate_limit(request, bucket="reset_redeem", limit=10, window_seconds=60)
        try:
            result = redeem_password_reset(db, raw_token=payload.token, password=payload.password)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        user = db.get_user(result["user"]["id"])
        assert user is not None
        response = JSONResponse({"authenticated": True, **result, "user": public_user(user)})
        set_session_cookie(
            response,
            user["id"],
            request=request,
            session_epoch=int(user.get("session_epoch") or 0),
            db=db,
        )
        return response

    @app.get("/api/invites/validate")
    def validate_invite(request: Request, token: str = ""):
        enforce_rate_limit(request, bucket="invite_validate", limit=30, window_seconds=60)
        try:
            invite = lookup_pending_invite(db, token)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"invite": public_invite_view(invite)}

    @app.post("/api/invites/redeem/local")
    def redeem(payload: RedeemPayload, request: Request):
        enforce_rate_limit(request, bucket="invite_redeem_local", limit=10, window_seconds=60)
        try:
            result = redeem_local_invite(
                db, raw_token=payload.token, username=payload.username, password=payload.password
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        user = db.get_user(result["user"]["id"])
        assert user is not None
        db.add_security_event(kind="invite_redeem", user_id=user["id"], actor_id=user["id"])
        response = JSONResponse({"authenticated": True, **result})
        set_session_cookie(
            response,
            user["id"],
            request=request,
            session_epoch=int(user.get("session_epoch") or 0),
            db=db,
        )
        return response

    @app.post("/api/invites")
    def mint_invite(payload: InvitePayload, request: Request):
        user = request.state.user
        require_role(user, "owner", "op")
        try:
            minted = create_household_invite(
                db,
                created_by=user["id"],
                actor_role=user["role"],
                role=payload.role,
                expires_in_seconds=payload.expires_in_seconds,
                base_url=_invite_origin(request),
            )
        except ValueError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        db.add_security_event(
            kind="invite_mint",
            user_id=user["id"],
            actor_id=user["id"],
            detail={"role": payload.role, "invite_id": minted["invite"]["id"]},
        )
        return minted

    @app.get("/api/invites")
    def list_invites(request: Request):
        user = request.state.user
        require_role(user, "owner", "op")
        pending = list_pending_invites(db)
        if user["role"] == "op":
            pending = [row for row in pending if row.get("role") == "reader"]
        return {"invites": pending}

    @app.post("/api/invites/{invite_id}/revoke")
    def revoke_invite(invite_id: str, request: Request):
        user = request.state.user
        require_role(user, "owner", "op")
        try:
            invite = revoke_household_invite(db, invite_id=invite_id, actor_role=user["role"])
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        db.add_security_event(
            kind="invite_revoke",
            user_id=user["id"],
            actor_id=user["id"],
            detail={"invite_id": invite_id},
        )
        return {"invite": invite}

    @app.get("/api/people")
    def people(request: Request):
        user = request.state.user
        require_role(user, "owner", "op")
        rows = [public_user(row, include_activity=True) for row in db.list_users()]
        pending = list_pending_invites(db)
        if user["role"] == "op":
            pending = [row for row in pending if row.get("role") == "reader"]
        return {"users": rows, "invites": pending, "can_manage": user["role"] == "owner"}

    @app.post("/api/people/{user_id}/reset")
    def issue_reset(user_id: str, request: Request):
        actor = request.state.user
        require_role(actor, "owner")
        try:
            issued = issue_password_reset(
                db, user_id=user_id, created_by=actor["id"], base_url=_invite_origin(request)
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return issued

    @app.post("/api/people/{user_id}/role")
    def change_role(user_id: str, payload: RoleChangePayload, request: Request):
        actor = request.state.user
        require_role(actor, "owner")
        target = db.get_user(user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        if str(target.get("role")) == "owner" or actor["id"] == user_id:
            raise HTTPException(status_code=403, detail="Cannot change the owner")
        role = str(payload.role or "").strip().lower()
        if role not in INVITE_ROLES:
            raise HTTPException(status_code=400, detail="role must be op or reader")
        db.update_user_role(user_id, role)
        invalidate_session_cache(user_id=user_id)
        db.add_security_event(
            kind="role_change",
            user_id=user_id,
            actor_id=actor["id"],
            detail={"role": role},
        )
        fresh = db.get_user(user_id)
        assert fresh is not None
        return {"user": public_user(fresh, include_activity=True)}

    @app.post("/api/people/{user_id}/disable")
    def disable_user(user_id: str, payload: DisablePayload, request: Request):
        actor = request.state.user
        require_role(actor, "owner")
        target = db.get_user(user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        if str(target.get("role")) == "owner":
            raise HTTPException(status_code=403, detail="Cannot pause the owner")
        db.set_user_disabled(user_id, bool(payload.disabled))
        if payload.disabled:
            db.revoke_sessions_for_user(user_id)
            invalidate_session_cache(user_id=user_id)
        db.add_security_event(
            kind="user_disable" if payload.disabled else "user_enable",
            user_id=user_id,
            actor_id=actor["id"],
        )
        fresh = db.get_user(user_id)
        assert fresh is not None
        return {"user": public_user(fresh, include_activity=True)}

    @app.delete("/api/people/{user_id}")
    def delete_user(user_id: str, request: Request):
        actor = request.state.user
        require_role(actor, "owner")
        target = db.get_user(user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        if str(target.get("role")) == "owner":
            raise HTTPException(status_code=403, detail="Cannot delete the owner")
        if actor["id"] == user_id:
            raise HTTPException(status_code=403, detail="Cannot delete yourself")
        db.delete_user_cascade(user_id)
        invalidate_session_cache(user_id=user_id)
        db.add_security_event(kind="user_delete", actor_id=actor["id"], detail={"gone": True})
        return {"ok": True}
