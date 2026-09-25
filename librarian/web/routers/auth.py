"""Auth, health, features, invites, and people routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile

from librarian.web.deps import WebDeps
from librarian.web.route_imports import *  # noqa: F403


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
        return {
            "status": "ok",
            "ok": True,
            "version": __version__,
            "build": _read_build_info(),
        }

    @app.get("/api/features")
    def features() -> Dict[str, Any]:
        cfg = settings()
        return {
            "household_name": cfg.household_name,
            "owner_ready": has_real_owner(db),
            "session_secret_ok": has_usable_session_secret(root),
            "auth_methods": ["local"],
            "version": __version__,
            "show_extra_categories": bool(cfg.show_extra_categories),
        }

    @app.post("/api/auth/local/login")
    def login(payload: LoginPayload, request: Request):
        enforce_rate_limit(request, bucket="auth_local_login", limit=10, window_seconds=60)
        if not has_real_owner(db):
            raise HTTPException(status_code=503, detail="Owner has not been seeded")
        user = db.get_user_by_display_name(payload.username)
        stored = str((user or {}).get("password_hash") or "")
        if user is None or not verify_password(payload.password, stored):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        db.touch_login(user["id"])
        response = JSONResponse({"authenticated": True, "user": public_user(user)})
        set_session_cookie(
            response,
            user["id"],
            request=request,
            session_epoch=int(user.get("session_epoch") or 0),
        )
        return response

    @app.post("/api/auth/logout")
    def logout(request: Request):
        response = JSONResponse({"ok": True})
        clear_session_cookie(response, request=request)
        return response

    @app.get("/api/auth/me")
    def me(request: Request):
        user = getattr(request.state, "user", None) or current_user(request)
        require_role(user, "owner", "op", "reader")
        assert user is not None
        payload = {"user": public_user(user), "review_count": 0}
        if user["role"] in ("owner", "op"):
            payload["review_count"] = len(db.list_works(review_state="needs_review", limit=80))
        return payload

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
        response = JSONResponse({"authenticated": True, **result})
        set_session_cookie(
            response,
            user["id"],
            request=request,
            session_epoch=int(user.get("session_epoch") or 0),
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
            )
        except ValueError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        return minted

    @app.get("/api/people")
    def people(request: Request):
        require_role(request.state.user, "owner")
        return {"users": [public_user(row) for row in db.list_users()]}

