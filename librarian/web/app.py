"""FastAPI app: household API + Vite SPA from frontend/dist."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from librarian import __version__
from librarian.auth import has_real_owner, is_public_handshake, seed_env_owner, user_from_request
from librarian.config import load_merged_settings
from librarian.db import Database
from librarian.indexers.sync import sync_nzbfinder
from librarian.poller import JobPoller
from librarian.progress_job import BackgroundJobSlot
from librarian.sessions import (
    ensure_session_secret,
    is_dev_session_secret,
)
from librarian.web.build_info import FRONTEND_DIST
from librarian.web.deps import WebDeps
from librarian.web.routers import (
    register_auth_routes,
    register_catalog_routes,
    register_ingest_routes,
    register_maintain_routes,
    register_review_routes,
    register_settings_routes,
)


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
    sync_nzbfinder(db, load_merged_settings(root))

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        poller = JobPoller(db, lambda: load_merged_settings(root), data_dir=root)
        poller.start()
        application.state.poller = poller
        try:
            yield
        finally:
            poller.stop()
            db.close()

    app = FastAPI(
        title="Librarian",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.data_dir = root
    app.state.db = db
    enrich_job = BackgroundJobSlot()
    scan_job = BackgroundJobSlot()
    ingest_job = BackgroundJobSlot()
    extra_files_reprocess_job = BackgroundJobSlot()
    purge_duplicates_job = BackgroundJobSlot()
    purge_shells_job = BackgroundJobSlot()
    split_mixed_kinds_job = BackgroundJobSlot()

    def settings():
        return load_merged_settings(root)

    deps = WebDeps(
        root=root,
        db=db,
        settings=settings,
        enrich_job=enrich_job,
        scan_job=scan_job,
        ingest_job=ingest_job,
        extra_files_reprocess_job=extra_files_reprocess_job,
        purge_duplicates_job=purge_duplicates_job,
        purge_shells_job=purge_shells_job,
        split_mixed_kinds_job=split_mixed_kinds_job,
    )

    @app.middleware("http")
    async def auth_gate(request: Request, call_next):
        path = request.url.path
        method = request.method.upper()
        if not path.startswith("/api/"):
            return await call_next(request)
        if is_public_handshake(method, path):
            return await call_next(request)
        if not has_real_owner(db) and path.startswith("/api/"):
            return JSONResponse({"detail": "Owner has not been seeded"}, status_code=503)
        user = user_from_request(request, db)
        if user is None:
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
        request.state.user = user
        return await call_next(request)

    register_auth_routes(app, deps)
    register_catalog_routes(app, deps)
    register_review_routes(app, deps)
    register_ingest_routes(app, deps)
    register_maintain_routes(app, deps)
    register_settings_routes(app, deps)

    @app.get("/release-notes.json")
    def release_notes():
        from librarian.web.build_info import frontend_public_file

        path = frontend_public_file("release-notes.json")
        if path is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Release notes not found")
        return FileResponse(
            path,
            media_type="application/json",
            headers={"Cache-Control": "public, max-age=60"},
        )

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
