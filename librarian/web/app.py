"""FastAPI app: household API + Vite SPA from frontend/dist."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from librarian import __version__
from librarian.auth import (
    clear_session_cookie,
    has_real_owner,
    is_public_handshake,
    public_user,
    require_role,
    seed_env_owner,
    set_session_cookie,
    user_from_request,
    verify_password,
)
from librarian.config import load_merged_settings, mask_settings, merge_secret_fields, save_settings
from librarian.db import Database
from librarian.gaps import gap_cards, local_gaps
from librarian.invites import (
    create_household_invite,
    lookup_pending_invite,
    public_invite_view,
    redeem_local_invite,
)
from librarian.jobs import confirm_asked_job, enqueue_indexer_item, poll_active_jobs, poll_job
from librarian.nzbfinder import NZBFinderClient, NZBFinderError
from librarian.organize import apply_review, organize_identified, promote_music
from librarian.sabnzbd import SABError
from librarian.sessions import (
    ensure_session_secret,
    has_usable_session_secret,
    is_dev_session_secret,
)

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


class LoginPayload(BaseModel):
    username: str
    password: str


class RedeemPayload(BaseModel):
    token: str
    username: str
    password: str


class InvitePayload(BaseModel):
    role: str
    expires_in_seconds: int = 7 * 24 * 3600


class RequestPayload(BaseModel):
    title: str
    guid: str = ""
    kind: Optional[str] = None
    download_url: str = ""
    category: Optional[str] = None
    author: str = ""
    isbn: str = ""


class ReviewApplyPayload(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    kind: Optional[str] = None
    series_name: Optional[str] = None
    series_index: Optional[str] = None
    year: Optional[int] = None
    isbn: Optional[str] = None
    folder: Optional[str] = None


class SettingsPayload(BaseModel):
    sabnzbd_url: Optional[str] = None
    sabnzbd_api_key: Optional[str] = None
    nzbfinder_url: Optional[str] = None
    nzbfinder_api_token: Optional[str] = None
    books_root: Optional[str] = None
    magazines_root: Optional[str] = None
    comics_root: Optional[str] = None
    audiobooks_root: Optional[str] = None
    incoming_music_root: Optional[str] = None
    music_root: Optional[str] = None
    audiobook_target: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    household_name: Optional[str] = None


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/config"))


def create_app(data_dir: Optional[Path] = None) -> FastAPI:
    root = Path(data_dir) if data_dir is not None else _data_dir()
    root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DATA_DIR", str(root))

    if is_dev_session_secret(os.environ.get("LIBRARIAN_SESSION_SECRET") or ""):
        raise RuntimeError("Refuse to start with the public LIBRARIAN_SESSION_SECRET default")
    ensure_session_secret(root)

    db = Database(root / "librarian.db")
    seed_env_owner(db)

    app = FastAPI(title="Librarian", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.data_dir = root
    app.state.db = db

    def settings():
        return load_merged_settings(root)

    def current_user(request: Request) -> Optional[Dict[str, Any]]:
        return user_from_request(request, db)

    @app.middleware("http")
    async def auth_gate(request: Request, call_next):
        path = request.url.path
        method = request.method.upper()
        if not path.startswith("/api/"):
            return await call_next(request)
        if is_public_handshake(method, path):
            return await call_next(request)
        if path == "/api/health" or path == "/api/features":
            return await call_next(request)
        if not has_real_owner(db) and path.startswith("/api/"):
            return JSONResponse({"detail": "Owner has not been seeded"}, status_code=503)
        user = current_user(request)
        if user is None:
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
        request.state.user = user
        return await call_next(request)

    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        return {"status": "ok", "ok": True, "version": __version__}

    @app.get("/api/features")
    def features() -> Dict[str, Any]:
        cfg = settings()
        return {
            "household_name": cfg.household_name,
            "owner_ready": has_real_owner(db),
            "session_secret_ok": has_usable_session_secret(root),
            "auth_methods": ["local"],
            "version": __version__,
        }

    @app.post("/api/auth/local/login")
    def login(payload: LoginPayload, request: Request):
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
            secure=request.url.scheme == "https",
            session_epoch=int(user.get("session_epoch") or 0),
        )
        return response

    @app.post("/api/auth/logout")
    def logout():
        response = JSONResponse({"ok": True})
        clear_session_cookie(response)
        return response

    @app.get("/api/auth/me")
    def me(request: Request):
        user = getattr(request.state, "user", None) or current_user(request)
        require_role(user, "owner", "op", "reader")
        assert user is not None
        return {"user": public_user(user)}

    @app.get("/api/invites/validate")
    def validate_invite(token: str = ""):
        try:
            invite = lookup_pending_invite(db, token)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"invite": public_invite_view(invite)}

    @app.post("/api/invites/redeem/local")
    def redeem(payload: RedeemPayload, request: Request):
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
            secure=request.url.scheme == "https",
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

    @app.get("/api/hall")
    def hall(request: Request):
        user = request.state.user
        recent = db.list_works(limit=18)
        favorites = db.favorite_works(user["id"], limit=18)
        areas = {
            "books": db.list_works(kind="book", limit=12),
            "magazines": db.list_works(kind="magazine", limit=12),
            "comics": db.list_works(kind="comic", limit=12),
            "audiobooks": db.list_works(kind="audiobook", limit=12),
            "incoming_music": db.list_works(kind="music", music_state="incoming", limit=12),
        }
        gaps = []
        if user["role"] in ("owner", "op"):
            gaps = gap_cards(local_gaps(db))
        return {
            "whats_new": recent,
            "favorites": favorites,
            "areas": areas,
            "gaps": gaps,
            "continue": [],
            "owner_ready": True,
            "empty": not recent and not any(areas.values()),
        }

    @app.get("/api/search")
    def search(request: Request, q: str = "", beyond: int = 0, kind: str = ""):
        user = request.state.user
        local = db.search_works(q, limit=24) if q.strip() else []
        indexer = []
        if beyond and q.strip():
            cfg = settings()
            if cfg.nzbfinder_api_token:
                try:
                    client = NZBFinderClient(cfg.nzbfinder_url, cfg.nzbfinder_api_token)
                    if kind in ("book", "magazine") or not kind:
                        indexer = client.books(query=q, title=q)
                    else:
                        indexer = client.search(q, kind=kind or None)
                    if kind == "comic":
                        indexer = client.search(q, kind="comic")
                except NZBFinderError as error:
                    raise HTTPException(status_code=502, detail=str(error)) from error
        return {"q": q, "local": local, "beyond": indexer, "can_request": user["role"] in ("owner", "op", "reader")}

    @app.get("/api/works/{work_id}")
    def work_detail(work_id: str, request: Request):
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        files = db.files_for_work(work_id)
        return {
            "work": work,
            "files": files,
            "favorite": db.is_favorite(request.state.user["id"], work_id),
        }

    @app.post("/api/works/{work_id}/favorite")
    def favorite(work_id: str, request: Request):
        if db.get_work(work_id) is None:
            raise HTTPException(status_code=404, detail="Work not found")
        on = db.toggle_favorite(request.state.user["id"], work_id)
        return {"favorite": on}

    @app.post("/api/request")
    def request_item(payload: RequestPayload, request: Request):
        user = request.state.user
        require_role(user, "owner", "op", "reader")
        item = payload.model_dump()
        try:
            job = enqueue_indexer_item(
                db, settings(), item=item, requested_by=user["id"], role=user["role"]
            )
        except (SABError, NZBFinderError) as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        return {"job": job}

    @app.get("/api/queue")
    def queue(request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            poll_active_jobs(db, settings())
        except SABError:
            pass
        return {"jobs": db.list_jobs()}

    @app.post("/api/queue/{job_id}/poll")
    def queue_poll(job_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            job = poll_job(db, settings(), job_id)
        except (ValueError, SABError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"job": job}

    @app.post("/api/queue/{job_id}/confirm")
    def queue_confirm(job_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            job = confirm_asked_job(db, settings(), job_id)
        except (ValueError, SABError, NZBFinderError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"job": job}

    @app.get("/api/review")
    def review_list(request: Request):
        require_role(request.state.user, "owner", "op")
        return {"works": db.list_works(review_state="needs_review", limit=80)}

    @app.post("/api/review/{work_id}/apply")
    def review_apply(work_id: str, payload: ReviewApplyPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        folder = Path(payload.folder or work.get("folder_path") or "")
        overrides = payload.model_dump(exclude_none=True)
        overrides.pop("folder", None)
        try:
            result = apply_review(db, settings(), work_id=work_id, folder=folder, identity_overrides=overrides)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return result

    @app.post("/api/review/{work_id}/skip")
    def review_skip(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        updated = db.upsert_work({**work, "review_state": "resolved"})
        return {"work": updated}

    @app.get("/api/gaps")
    def gaps(request: Request):
        require_role(request.state.user, "owner", "op")
        rows = local_gaps(db)
        return {"series": rows, "cards": gap_cards(rows)}

    @app.post("/api/gaps/confirm")
    def gaps_confirm(payload: RequestPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        return request_item(payload, request)

    @app.post("/api/music/{work_id}/promote")
    def music_promote(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            work = promote_music(db, settings(), work_id)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"work": work}

    @app.get("/api/settings")
    def get_settings(request: Request):
        require_role(request.state.user, "owner")
        return {"settings": mask_settings(settings())}

    @app.put("/api/settings")
    def put_settings(payload: SettingsPayload, request: Request):
        require_role(request.state.user, "owner")
        incoming = {key: value for key, value in payload.model_dump().items() if value is not None}
        merged = merge_secret_fields(incoming, settings())
        from librarian.config import Settings

        saved = Settings.from_mapping(merged)
        save_settings(root, saved)
        return {"settings": mask_settings(saved)}

    @app.post("/api/organize/preview")
    def organize_preview(folder: str, request: Request, guid: str = "", title: str = ""):
        require_role(request.state.user, "owner", "op")
        result = organize_identified(
            db,
            settings(),
            folder=Path(folder),
            indexer_item={"guid": guid, "title": title} if title or guid else None,
            apply=False,
        )
        return result

    if FRONTEND_DIST.is_dir():
        assets = FRONTEND_DIST / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}")
        def spa(full_path: str):
            candidate = FRONTEND_DIST / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            index = FRONTEND_DIST / "index.html"
            if index.is_file():
                return FileResponse(index)
            return JSONResponse({"detail": "SPA is not built"}, status_code=404)

    return app


if os.environ.get("LIBRARIAN_SKIP_APP_BOOT") == "1":
    app = FastAPI(title="Librarian", version=__version__)
else:
    app = create_app()
