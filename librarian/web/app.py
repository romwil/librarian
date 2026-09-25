"""FastAPI app: household API + Vite SPA from frontend/dist."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.background import BackgroundTask

from librarian import __version__
from librarian.audiobook_match import companion_audiobook_payload
from librarian.audiobookshelf import abs_match_counts, match_audiobooks
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
from librarian.convert import ALLOWED_EBOOK_FORMATS, convert_ebook, which_ebook_convert
from librarian.db import Database
from librarian.delight import (
    WHISPER_LIST_LIMIT,
    celebration_candidates,
    cover_story,
    estimate_finish_eta_minutes,
    finish_set_label,
    in_quiet_hours,
    normalize_ambient,
    normalize_ui_font_step,
    normalize_ui_theme,
    plexamp_handoff,
    rank_regrab_candidates,
    sanitize_whisper,
    series_ribbon,
    tonight_shelf,
)
from librarian.enrich import (
    apply_audnexus_match,
    apply_comicvine_match,
    apply_openlibrary_match,
    clear_enrichment,
    enrich_library,
    enrich_work,
    friendly_enrich_error,
    list_match_candidates,
    update_work_metadata,
)
from librarian.enrich_progress import (
    EnrichProgressReporter,
    begin_enrich_run,
    finish_enrich_run,
    is_enrich_running,
    read_enrich_progress,
)
from librarian.extra_files_reprocess_progress import (
    ExtraFilesReprocessProgressReporter,
    begin_extra_files_reprocess_run,
    finish_extra_files_reprocess_run,
    is_extra_files_reprocess_running,
    is_extra_files_reprocess_stale,
    read_extra_files_reprocess_progress,
)
from librarian.gaps import catalog_gaps, gap_cards, gaps_for_series
from librarian.goodreads import MAX_GOODREADS_BYTES, import_goodreads_csv
from librarian.identify import diagnose_review_folder
from librarian.indexers.discover import discover_beyond, resolve_feed_limit
from librarian.indexers.rank import remember_candidates, search_and_rank
from librarian.indexers.sync import ping_nzbfinder, sync_nzbfinder
from librarian.ingest import (
    PathDenied,
    confined_path,
    list_dir,
    poll_watch_folder,
    protected_path_refusal,
    run_ingest_paths,
    validate_watch_root,
)
from librarian.ingest_progress import (
    IngestProgressReporter,
    begin_ingest_run,
    finish_ingest_run,
    is_ingest_running,
    read_ingest_progress,
)
from librarian.invites import (
    create_household_invite,
    lookup_pending_invite,
    public_invite_view,
    redeem_local_invite,
)
from librarian.jobs import confirm_asked_job, enqueue_indexer_item, poll_active_jobs, poll_job
from librarian.kinds import ALL_KINDS, EXTRA_KINDS
from librarian.komga import komga_payload
from librarian.listen import extract_chapters, listen_payload, split_continue_rails
from librarian.lists import (
    chase_missing_items,
    curated_list_payload,
    list_presets,
)
from librarian.nyt_books import (
    NytBooksClient,
    NytBooksError,
    default_list_names,
    match_local_work,
    normalize_list_date,
    normalize_list_name,
)
from librarian.nzbfinder import NZBFinderError
from librarian.organize import (
    apply_review,
    organize_identified,
    promote_music,
    repair_review,
    reprocess_extra_files_reviews,
    reprocess_extra_files_work,
    retry_review,
    review_slip_actions,
    shelf_work_for_collision,
    suggest_review_identity,
)
from librarian.parts import build_part_set
from librarian.poller import JobPoller
from librarian.progress_job import BackgroundJobSlot
from librarian.purge_duplicates import purge_duplicate_reviews
from librarian.purge_duplicates_progress import (
    PurgeDuplicatesProgressReporter,
    begin_purge_duplicates_run,
    finish_purge_duplicates_run,
    is_purge_duplicates_running,
    is_purge_duplicates_stale,
    read_purge_duplicates_progress,
)
from librarian.purge_shells import purge_shell_works
from librarian.purge_shells_progress import (
    PurgeShellsProgressReporter,
    begin_purge_shells_run,
    finish_purge_shells_run,
    is_purge_shells_running,
    is_purge_shells_stale,
    read_purge_shells_progress,
)
from librarian.rate_limit import enforce_rate_limit
from librarian.rss import create_rss_feed, poll_rss_feeds, public_rss_feed, update_rss_feed
from librarian.sabnzbd import SABError
from librarian.scan import scan_library
from librarian.scan_progress import (
    ScanProgressReporter,
    begin_scan_run,
    finish_scan_run,
    is_scan_running,
    read_scan_progress,
)
from librarian.serve import (
    annotate_work_files,
    can_read_work,
    existing_file_paths,
    is_inline_media,
    is_reading_file,
    is_streamable_audio,
    media_type_for,
    primary_reading_path,
    resolve_catalog_file,
    safe_filename,
    zip_files,
)
from librarian.sessions import (
    ensure_session_secret,
    has_usable_session_secret,
    is_dev_session_secret,
)
from librarian.split_mixed_kinds import count_mixed_kind_works, split_mixed_kind_works
from librarian.split_mixed_kinds_progress import (
    SplitMixedKindsProgressReporter,
    begin_split_mixed_kinds_run,
    finish_split_mixed_kinds_run,
    is_split_mixed_kinds_running,
    is_split_mixed_kinds_stale,
    read_split_mixed_kinds_progress,
)
from librarian.suggest import SUGGEST_FIELDS, refresh_suggest_cache, suggest_items

logger = logging.getLogger(__name__)

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_build_info() -> str:
    """Docker image stamp from /app/.build-info, or empty when unset (local venv)."""
    for candidate in (Path("/app/.build-info"), _REPO_ROOT / ".build-info"):
        try:
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return ""


def _frontend_public_file(*parts: str) -> Path | None:
    """Resolve a Vite public asset from dist (prod) or public/ (local pre-build).

    When both exist (common after generate-release-notes without a rebuild),
    prefer the newer file so Settings stays current during local development.
    """
    candidates = [
        FRONTEND_DIST.joinpath(*parts),
        FRONTEND_DIST.parent.joinpath("public", *parts),
    ]
    existing = [candidate for candidate in candidates if candidate.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda item: item.stat().st_mtime)


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
    category: Optional[Any] = None
    author: str = ""
    isbn: str = ""
    q: str = ""
    series: str = ""
    issue: str = ""
    artist: str = ""
    album: str = ""
    year: str = ""
    size: Optional[int] = None
    cover: str = ""
    book_title: str = ""
    poster: str = ""
    category_name: str = ""
    sought: Optional[Dict[str, Any]] = None
    selected: Optional[Dict[str, Any]] = None
    retrieved: Optional[Dict[str, Any]] = None
    candidates: Optional[List[Dict[str, Any]]] = None
    rank_method: str = ""
    rank_reason: str = ""


class ReviewApplyPayload(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    kind: Optional[str] = None
    series_name: Optional[str] = None
    series_index: Optional[str] = None
    year: Optional[int] = None
    isbn: Optional[str] = None
    folder: Optional[str] = None


class ExtraIndexerPayload(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None
    api_token: Optional[str] = None
    enabled: Optional[bool] = True


class RssFeedPayload(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    kind: Optional[str] = None
    enabled: Optional[bool] = None


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
    complete_root: Optional[str] = None
    audiobook_target: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    llm_profiles: Optional[Dict[str, Any]] = None
    household_name: Optional[str] = None
    hardcover_api_token: Optional[str] = None
    nyt_books_api_key: Optional[str] = None
    comicvine_api_key: Optional[str] = None
    komga_url: Optional[str] = None
    komga_api_key: Optional[str] = None
    komga_library_id: Optional[str] = None
    watch_root: Optional[str] = None
    watch_enabled: Optional[bool] = None
    extra_indexers: Optional[List[ExtraIndexerPayload]] = None
    audiobookshelf_url: Optional[str] = None
    audiobookshelf_api_token: Optional[str] = None
    show_extra_categories: Optional[bool] = None
    radarr_url: Optional[str] = None
    radarr_api_key: Optional[str] = None
    sonarr_url: Optional[str] = None
    sonarr_api_key: Optional[str] = None
    sab_movie_category: Optional[str] = None
    sab_tv_category: Optional[str] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None


class IngestPayload(BaseModel):
    path: str


class ProgressPayload(BaseModel):
    position: str = ""
    fraction: Optional[float] = None
    finished: bool = False


class ConvertPayload(BaseModel):
    format: str = "epub"


class PrefsPayload(BaseModel):
    ambient: Optional[str] = None
    ui_theme: Optional[str] = None
    ui_font_step: Optional[int] = None


class WhisperPayload(BaseModel):
    body: str


class WorkMetadataPayload(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    year: Optional[int] = None
    description: Optional[str] = None
    genre: Optional[str] = None
    series_name: Optional[str] = None
    series_index: Optional[str] = None
    kind: Optional[str] = None
    synopsis_source: Optional[str] = None
    llm_blurb: Optional[str] = None
    cover_url: Optional[str] = None


class ApplyMatchPayload(BaseModel):
    match_key: str = ""


class CelebrationSeenPayload(BaseModel):
    key: str


class FinishSetEtaPayload(BaseModel):
    missing_count: int = 0
    kind: str = ""
    total_bytes: Optional[int] = None
    multipart: bool = False


class LlmListPayload(BaseModel):
    preset: str = "hardcover-fiction"
    date: str = "current"
    query: str = ""


class LlmListChaseItem(BaseModel):
    title: str
    author: str
    isbn: str = ""


class LlmListChasePayload(BaseModel):
    items: List[LlmListChaseItem] = []


def public_work(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    data = dict(row)
    data["has_cover"] = bool(data.get("cover_path"))
    story = cover_story(data)
    if story:
        data["cover_story"] = story
    return data


def public_works(rows: list) -> list:
    return [public_work(row) for row in rows if row]


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
        if not has_real_owner(db) and path.startswith("/api/"):
            return JSONResponse({"detail": "Owner has not been seeded"}, status_code=503)
        user = current_user(request)
        if user is None:
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
        request.state.user = user
        return await call_next(request)

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

    @app.get("/api/hall")
    def hall(request: Request):
        user = request.state.user
        recent = db.list_works(limit=18, require_files=True)
        favorites = db.favorite_works(user["id"], limit=18)
        areas = {
            "books": db.list_works(kind="book", limit=12, require_files=True),
            "magazines": db.list_works(kind="magazine", limit=12, require_files=True),
            "comics": db.list_works(kind="comic", limit=12, require_files=True),
            "audiobooks": db.list_works(kind="audiobook", limit=12, require_files=True),
            "incoming_music": db.list_works(kind="music", music_state="incoming", limit=12, require_files=True),
        }
        gaps = []
        if user["role"] in ("owner", "op"):
            gaps = gap_cards(catalog_gaps(db, settings()))
        continue_rows = db.continue_works(user["id"], limit=18)
        continue_split = split_continue_rails(continue_rows)
        surprise = None
        if recent:
            surprise = public_work(recent[0])
        elif favorites:
            surprise = public_work(favorites[0])
        counts = db.kind_counts()
        celebrations = db.unseen_celebrations(
            user["id"],
            celebration_candidates(
                kind_counts=counts,
                author_year_counts=db.author_year_counts(year=datetime.now().year),
            ),
        )
        tonight = tonight_shelf(
            continue_items=continue_rows,
            gaps=gaps,
            surprise=surprise,
        )
        return {
            "whats_new": public_works(recent),
            "favorites": public_works(favorites),
            "areas": {key: public_works(value) for key, value in areas.items()},
            "gaps": gaps,
            "continue": continue_split["reading"],
            "continue_listening": continue_split["listening"],
            "tonight": tonight,
            "celebrations": celebrations,
            "kind_counts": counts,
            "owner_ready": True,
            "empty": not recent and not any(areas.values()),
        }

    @app.get("/api/search")
    def search(
        request: Request,
        q: str = "",
        beyond: int = 0,
        kind: str = "",
        title: str = "",
        author: str = "",
        isbn: str = "",
        series: str = "",
        issue: str = "",
        artist: str = "",
        album: str = "",
        year: str = "",
    ):
        user = request.state.user
        local_kind = kind if kind in ALL_KINDS else None
        local_q = q.strip()
        local = public_works(db.search_works(local_q, limit=24, kind=local_kind) if local_q else [])
        indexer = []
        beyond_error = None
        sought = {
            "kind": kind,
            "q": q,
            "title": title,
            "author": author,
            "isbn": isbn,
            "series": series,
            "issue": issue,
            "artist": artist,
            "album": album,
            "year": year,
        }
        has_beyond_query = bool(beyond) and any(
            str(sought[key] or "").strip() for key in sought if key != "kind"
        )
        extra_on = bool(settings().show_extra_categories)
        search_trace = None
        pick = None
        candidates: List[Dict[str, Any]] = []
        rank_method = ""
        rank_reason = ""
        if kind in EXTRA_KINDS and not extra_on:
            indexer, beyond_error = [], None
        elif has_beyond_query:
            ranked = search_and_rank(settings(), **sought)
            indexer = list(ranked.get("hits") or [])
            beyond_error = ranked.get("error")
            if beyond_error:
                from librarian.llm import friendly_llm_error

                beyond_error = friendly_llm_error(RuntimeError(str(beyond_error)))
            pick = ranked.get("pick")
            candidates = list(ranked.get("candidates") or [])
            rank_method = str(ranked.get("rank_method") or "")
            rank_reason = str(ranked.get("rank_reason") or "")
            search_trace = {
                "conversation": list(ranked.get("conversation") or []),
                "steps": list(ranked.get("steps") or []),
                "results": list(ranked.get("results") or []),
                "plan": ranked.get("plan"),
                "raw_count": ranked.get("raw_count"),
                "rejected_count": ranked.get("rejected_count"),
                "rank_method": rank_method,
                "rank_reason": rank_reason,
            }
        return {
            "q": q,
            "local": local,
            "beyond": indexer,
            "beyond_error": beyond_error,
            "pick": pick,
            "candidates": candidates,
            "rank_method": rank_method,
            "rank_reason": rank_reason,
            "search_trace": search_trace,
            "can_request": user["role"] in ("owner", "op", "reader"),
        }

    @app.get("/api/browse")
    def browse(
        request: Request,
        kind: str = "",
        author: str = "",
        letter: str = "",
        series: str = "",
        genre: str = "",
        shelf: str = "",
        sort: str = "author",
        offset: int = 0,
        limit: int = 48,
    ):
        user = request.state.user
        kind_key = kind if kind in ALL_KINDS else None
        shelf_key = "favorites" if str(shelf or "").strip().lower() == "favorites" else None
        page = db.browse_works(
            kind=kind_key,
            author=author.strip() or None,
            letter=letter.strip() or None,
            series=series.strip() or None,
            genre=genre.strip() or None,
            shelf=shelf_key,
            user_id=user["id"] if shelf_key else None,
            sort=sort,
            offset=offset,
            limit=limit,
        )
        return {
            "items": public_works(page["items"]),
            "total": page["total"],
            "offset": page["offset"],
            "limit": page["limit"],
            "sort": page["sort"],
            "filters": {
                "kind": kind_key or "",
                "author": author.strip(),
                "letter": letter.strip().upper(),
                "series": series.strip(),
                "genre": genre.strip(),
                "shelf": shelf_key or "",
            },
        }

    @app.get("/api/browse/facets")
    def browse_facets_endpoint(
        request: Request,
        kind: str = "",
        shelf: str = "",
    ):
        user = request.state.user
        kind_key = kind if kind in ALL_KINDS else None
        shelf_key = "favorites" if str(shelf or "").strip().lower() == "favorites" else None
        facets = db.browse_facets(
            kind=kind_key,
            shelf=shelf_key,
            user_id=user["id"] if shelf_key else None,
        )
        return facets

    @app.get("/api/suggest")
    def suggest(
        request: Request,
        field: str = "",
        kind: str = "",
        q: str = "",
        limit: int = 12,
    ):
        enforce_rate_limit(request, bucket="suggest", limit=120, window_seconds=60)
        key = str(field or "").strip().lower()
        if key not in SUGGEST_FIELDS:
            raise HTTPException(status_code=400, detail="Unknown suggest field")
        items = suggest_items(db, root, field=key, kind=kind, q=q, limit=limit)
        return {"field": key, "kind": kind, "q": q, "items": items}

    @app.get("/api/discover")
    def discover(request: Request, kind: str = "", cat: str = "", limit: int = 0):
        cfg = settings()
        feed_limit = resolve_feed_limit(cat=cat, limit=limit if limit else None)
        items, categories, beyond_error = discover_beyond(cfg, kind=kind, cat=cat, limit=feed_limit)
        return {
            "kind": kind,
            "cat": cat,
            "limit": feed_limit,
            "items": items,
            "categories": categories,
            "beyond_error": beyond_error,
            "show_extra_categories": bool(cfg.show_extra_categories),
            "can_request": request.state.user["role"] in ("owner", "op", "reader"),
        }

    @app.get("/api/lists/presets")
    def curated_list_presets(request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        cfg = settings()
        from librarian.llm_providers import resolve_llm_connection

        llm_ok = bool(resolve_llm_connection(cfg).get("api_key"))
        return {
            "presets": list_presets(),
            "configured": llm_ok,
            "source": "llm",
            "empty_copy": (
                ""
                if llm_ok
                else "Add a BYO LLM in Settings to load curated bestseller lists."
            ),
        }

    @app.post("/api/lists/llm")
    def curated_llm_list(payload: LlmListPayload, request: Request):
        """BYO LLM curated list → match local shelves. Fail closed without LLM."""
        require_role(request.state.user, "owner", "op", "reader")
        when = normalize_list_date(payload.date)
        if not when:
            raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD or current")
        result = curated_list_payload(
            settings(),
            db,
            preset=payload.preset,
            date=when,
            query=payload.query,
            data_dir=root,
        )
        # Enrich shelved stubs with public_work cover flags.
        for entry in result.get("books") or []:
            for key in ("shelved", "shelved_audiobook"):
                stub = entry.get(key)
                if not stub or not stub.get("id"):
                    continue
                work = public_work(db.get_work(str(stub["id"])))
                if work:
                    entry[key] = {
                        "id": work.get("id"),
                        "title": work.get("title"),
                        "author": work.get("author"),
                        "kind": stub.get("kind") or work.get("kind"),
                        "has_cover": bool(work.get("has_cover") or work.get("cover_path")),
                    }
        result["can_request"] = request.state.user["role"] in ("owner", "op", "reader")
        result["can_confirm"] = request.state.user["role"] in ("owner", "op")
        return result

    @app.post("/api/lists/llm/chase")
    def curated_llm_chase(payload: LlmListChasePayload, request: Request):
        """Find beyond for missing list titles (book + audiobook). Never auto-queues."""
        require_role(request.state.user, "owner", "op", "reader")
        items = [row.model_dump() for row in (payload.items or [])]
        results = chase_missing_items(settings(), items)
        return {
            "results": results,
            "can_request": request.state.user["role"] in ("owner", "op", "reader"),
            "can_confirm": request.state.user["role"] in ("owner", "op"),
        }

    @app.get("/api/lists/nyt/names")
    def nyt_list_names(request: Request):
        """Optional NYT Books API names — soft-deprecated; prefer POST /api/lists/llm."""
        require_role(request.state.user, "owner", "op", "reader")
        cfg = settings()
        key = str(cfg.nyt_books_api_key or "").strip()
        if not key:
            return {
                "configured": False,
                "names": default_list_names(),
                "empty_reason": "missing_key",
                "empty_copy": "Add a BYO LLM in Settings for curated bestseller lists (NYT Books API key is optional fallback).",
                "deprecated": True,
            }
        client = NytBooksClient(key, data_dir=root)
        try:
            names = client.list_names()
        except NytBooksError as error:
            return {
                "configured": True,
                "names": default_list_names(),
                "empty_reason": "error",
                "empty_copy": str(error),
                "deprecated": True,
            }
        finally:
            client.close()
        return {
            "configured": True,
            "names": names or default_list_names(),
            "empty_reason": "",
            "empty_copy": "",
            "deprecated": True,
        }

    @app.get("/api/lists/nyt")
    def nyt_bestseller_list(
        request: Request,
        list: str = "hardcover-fiction",  # noqa: A002 — query param name matches NYT docs
        date: str = "current",
    ):
        require_role(request.state.user, "owner", "op", "reader")
        slug = normalize_list_name(list) or "hardcover-fiction"
        when = normalize_list_date(date)
        if not when:
            raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD or current")
        cfg = settings()
        key = str(cfg.nyt_books_api_key or "").strip()
        client = NytBooksClient(key, data_dir=root)
        try:
            payload = client.bestseller_list(slug, date=when)
        except NytBooksError as error:
            client.close()
            return {
                "configured": bool(key),
                "list_name": slug,
                "date": when,
                "published_date": "",
                "display_name": slug,
                "books": [],
                "empty_reason": "error",
                "empty_copy": str(error),
            }
        client.close()
        books = []
        for book in payload.get("books") or []:
            query = " ".join(
                part for part in (str(book.get("author") or "").strip(), str(book.get("title") or "").strip()) if part
            )
            candidates: List[Dict[str, Any]] = []
            isbn = str(book.get("isbn") or "").strip()
            if isbn:
                candidates.extend(db.search_works(isbn, limit=8, kind="book"))
            if query:
                candidates.extend(db.search_works(query, limit=12, kind="book"))
            # Deduplicate by id while preserving order.
            seen: set[str] = set()
            uniq: List[Dict[str, Any]] = []
            for row in candidates:
                wid = str(row.get("id") or "")
                if not wid or wid in seen:
                    continue
                seen.add(wid)
                uniq.append(row)
            local = match_local_work(book, uniq)
            entry = dict(book)
            if local:
                pub = public_work(local)
                entry["shelved"] = {
                    "id": pub.get("id") if pub else local.get("id"),
                    "title": (pub or local).get("title"),
                    "author": (pub or local).get("author"),
                    "has_cover": bool((pub or local).get("has_cover") or (pub or local).get("cover_path")),
                }
            else:
                entry["shelved"] = None
            books.append(entry)
        empty_reason = str(payload.get("empty_reason") or "")
        empty_copy = ""
        if empty_reason == "missing_key":
            empty_copy = "Add a BYO LLM in Settings for curated bestseller lists (NYT Books API key is optional fallback)."
        elif empty_reason == "empty_list":
            empty_copy = "That list came back empty for this date."
        elif not books and not empty_reason:
            empty_copy = "No titles on this list yet."
        return {
            **payload,
            "books": books,
            "empty_copy": empty_copy,
            "deprecated": True,
        }

    @app.get("/api/works/{work_id}")
    def work_detail(work_id: str, request: Request):
        work = public_work(db.get_work(work_id))
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        files = db.files_for_work(work_id)
        on_disk = existing_file_paths(files)
        part_set = build_part_set(work, files)
        if part_set:
            work["part_set"] = part_set
        related = []
        if work.get("author"):
            related = [
                row
                for row in public_works(db.search_works(str(work["author"]), limit=8))
                if row and row.get("id") != work_id
            ]
        progress = db.get_progress(request.state.user["id"], work_id)
        ribbon = []
        series_name = str(work.get("series_name") or "").strip()
        kind = str(work.get("kind") or "")
        if kind == "audiobook" and str(work.get("abs_item_id") or "").strip():
            try:
                from librarian.audiobookshelf import pull_abs_listen_progress

                pulled = pull_abs_listen_progress(
                    db,
                    settings(),
                    user_id=str(request.state.user["id"]),
                    work=work,
                    files=files,
                )
                if pulled:
                    progress = pulled
            except Exception:  # noqa: BLE001 — fail-soft ABS federation
                pass
        if series_name and kind in ALL_KINDS:
            card = gaps_for_series(db, kind=kind, series_name=series_name)
            owned = card.get("owned_indexes") or [
                str(row.get("series_index") or "")
                for row in db.works_for_series(kind=kind, series_name=series_name)
            ]
            missing = card.get("missing") or card.get("series_missing") or []
            ribbon = series_ribbon(
                owned_indexes=owned,
                missing_indexes=missing,
                current=work.get("series_index"),
            )
        whispers = db.list_whispers(work_id, limit=WHISPER_LIST_LIMIT)
        can_download = bool(on_disk)
        audiobook = companion_audiobook_payload(
            work,
            audiobooks=db.list_works(kind="audiobook", limit=500) if kind == "book" else [],
        )
        return {
            "work": work,
            "files": annotate_work_files(files, on_disk),
            "file_count": len(on_disk),
            "can_open": bool(on_disk),
            "can_download": can_download,
            "can_read": can_read_work(str(work.get("kind") or ""), on_disk),
            "listen": listen_payload(work, can_download=can_download, settings=settings()),
            "komga": komga_payload(work, settings()),
            "audiobook": audiobook,
            "favorite": db.is_favorite(request.state.user["id"], work_id),
            "related": related,
            "progress": progress,
            "ebook_convert": bool(which_ebook_convert()),
            "formats": list(ALLOWED_EBOOK_FORMATS),
            "series_ribbon": ribbon,
            "whispers": whispers,
        }

    @app.post("/api/works/{work_id}/favorite")
    def favorite(work_id: str, request: Request):
        if db.get_work(work_id) is None:
            raise HTTPException(status_code=404, detail="Work not found")
        on = db.toggle_favorite(request.state.user["id"], work_id)
        return {"favorite": on}

    @app.get("/api/works/{work_id}/whispers")
    def work_whispers(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        if db.get_work(work_id) is None:
            raise HTTPException(status_code=404, detail="Work not found")
        return {"whispers": db.list_whispers(work_id, limit=WHISPER_LIST_LIMIT)}

    @app.post("/api/works/{work_id}/whispers")
    def add_work_whisper(work_id: str, payload: WhisperPayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        if db.get_work(work_id) is None:
            raise HTTPException(status_code=404, detail="Work not found")
        body = sanitize_whisper(payload.body)
        if not body:
            raise HTTPException(status_code=400, detail="Whisper is empty")
        whisper = db.add_whisper(work_id=work_id, user_id=request.state.user["id"], body=body)
        return {"whisper": whisper, "whispers": db.list_whispers(work_id, limit=WHISPER_LIST_LIMIT)}

    def _public_prefs(row: Dict[str, Any]) -> Dict[str, Any]:
        nested = dict(row.get("prefs") or {})
        return {
            **row,
            "ui_theme": normalize_ui_theme(nested.get("ui_theme")),
            "ui_font_step": normalize_ui_font_step(nested.get("ui_font_step")),
        }

    @app.get("/api/prefs")
    def get_prefs(request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        return _public_prefs(db.get_user_prefs(request.state.user["id"]))

    @app.put("/api/prefs")
    def put_prefs(payload: PrefsPayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        ambient = normalize_ambient(payload.ambient) if payload.ambient is not None else None
        nested: Dict[str, Any] = {}
        if payload.ui_theme is not None:
            nested["ui_theme"] = normalize_ui_theme(payload.ui_theme)
        if payload.ui_font_step is not None:
            nested["ui_font_step"] = normalize_ui_font_step(payload.ui_font_step)
        return _public_prefs(
            db.set_user_prefs(
                request.state.user["id"],
                ambient=ambient,
                prefs=nested or None,
            )
        )

    @app.post("/api/celebrations/seen")
    def celebration_seen(payload: CelebrationSeenPayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        key = str(payload.key or "").strip()
        if not key:
            raise HTTPException(status_code=400, detail="Missing celebration key")
        db.mark_celebration_seen(request.state.user["id"], key)
        return {"ok": True}

    @app.post("/api/find/finish-eta")
    def finish_eta(payload: FinishSetEtaPayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        miss = int(payload.missing_count or 0)
        kind = str(payload.kind or "").strip()
        multipart = bool(payload.multipart)
        kind_samples = (
            db.recent_job_durations(kind=kind, multipart=True if multipart else None)
            if kind
            else []
        )
        pool_approximate = False
        if len(kind_samples) >= 2:
            samples = kind_samples
        else:
            global_samples = db.recent_job_durations(
                multipart=True if multipart else None
            )
            if len(global_samples) >= 2:
                samples = global_samples
                pool_approximate = bool(kind)
            elif kind_samples:
                samples = kind_samples
                pool_approximate = True
            else:
                samples = global_samples
                pool_approximate = True
        eta = estimate_finish_eta_minutes(
            missing_count=miss,
            recent_seconds=samples,
            total_bytes=payload.total_bytes,
        )
        minutes = eta.get("eta_minutes")
        approximate = bool(eta.get("approximate")) or (bool(minutes) and pool_approximate)
        return {
            "eta_minutes": minutes,
            "approximate": approximate if minutes else False,
            "label": finish_set_label(
                missing_count=miss,
                eta_minutes=minutes,
                approximate=approximate if minutes else False,
            ),
            "quiet_hours": in_quiet_hours(settings()),
        }

    @app.post("/api/works/{work_id}/progress")
    def touch_progress(work_id: str, payload: ProgressPayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        if db.get_work(work_id) is None:
            raise HTTPException(status_code=404, detail="Work not found")
        existing = db.get_progress(request.state.user["id"], work_id)
        if payload.finished:
            fraction = 1.0
        elif payload.fraction is not None:
            fraction = float(payload.fraction)
        elif existing:
            fraction = float(existing.get("fraction") or 0)
        else:
            fraction = 0.05
        position = payload.position or (existing or {}).get("position") or ""
        row = db.upsert_progress(
            user_id=request.state.user["id"],
            work_id=work_id,
            position=str(position),
            fraction=fraction,
        )
        work = db.get_work(work_id)
        if work and str(work.get("kind") or "") == "audiobook" and str(work.get("abs_item_id") or "").strip():
            try:
                from librarian.audiobookshelf import push_abs_listen_progress

                push_abs_listen_progress(
                    settings(),
                    work,
                    fraction=fraction,
                    position=str(position),
                    finished=bool(payload.finished),
                    force=bool(payload.finished),
                )
            except Exception:  # noqa: BLE001 — fail-soft ABS federation
                pass
        return {"progress": row}

    @app.get("/api/works/{work_id}/cover")
    def work_cover(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        path = Path(str(work.get("cover_path") or ""))
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Cover not found")
        return FileResponse(path, media_type="image/jpeg")

    def _files_on_disk(work_id: str) -> List[Path]:
        return existing_file_paths(db.files_for_work(work_id))

    def _canonical_file(work_id: str) -> Path:
        on_disk = _files_on_disk(work_id)
        if not on_disk:
            raise HTTPException(status_code=404, detail="File missing")
        return primary_reading_path(on_disk) or on_disk[0]

    def _unlink(path: str) -> None:
        try:
            os.unlink(path)
        except OSError:
            pass

    @app.get("/api/works/{work_id}/download")
    def work_download(
        work_id: str,
        request: Request,
        format: str = "",
        inline: int = 0,
        file: str = "",
    ):
        require_role(request.state.user, "owner", "op", "reader")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        rows = db.files_for_work(work_id)
        on_disk = existing_file_paths(rows)
        if not on_disk:
            raise HTTPException(status_code=404, detail="File missing")
        chosen = None
        if str(file or "").strip():
            chosen = resolve_catalog_file(rows, file)
            if chosen is None:
                raise HTTPException(status_code=404, detail="File not found")
        reading = primary_reading_path(on_disk)
        # Convert / Download may use Kindle; Reading Room never does.
        src = chosen or reading or on_disk[0]
        if format:
            fmt = format.lower()
            if f".{fmt}" != src.suffix.lower():
                cache = Path(root) / "conversions" / work_id
                try:
                    dest = convert_ebook(src, fmt, cache)
                except ValueError as error:
                    raise HTTPException(status_code=400, detail=str(error)) from error
                except FileNotFoundError as error:
                    raise HTTPException(status_code=422, detail=str(error)) from error
                except RuntimeError as error:
                    raise HTTPException(status_code=502, detail=str(error)) from error
                return FileResponse(dest, filename=dest.name)
        if inline:
            # Hard rule: Reading Room gets ONLY EPUB/CBZ/PDF — never Kindle, never a zip.
            if chosen is not None:
                if is_reading_file(chosen):
                    return FileResponse(
                        chosen,
                        filename=chosen.name,
                        media_type=media_type_for(chosen),
                        content_disposition_type="inline",
                    )
                if is_inline_media(chosen):
                    return FileResponse(
                        chosen,
                        filename=chosen.name,
                        media_type=media_type_for(chosen),
                        content_disposition_type="inline",
                    )
                raise HTTPException(
                    status_code=422,
                    detail="This volume isn’t a readable EPUB, CBZ, or PDF.",
                )
            if reading is not None:
                return FileResponse(
                    reading,
                    filename=reading.name,
                    media_type=media_type_for(reading),
                    content_disposition_type="inline",
                )
            inline_src = next((path for path in on_disk if is_inline_media(path)), None)
            if inline_src is not None:
                return FileResponse(
                    inline_src,
                    filename=inline_src.name,
                    media_type=media_type_for(inline_src),
                    content_disposition_type="inline",
                )
            raise HTTPException(
                status_code=422,
                detail="This volume isn’t a readable EPUB, CBZ, or PDF.",
            )
        if chosen is not None or len(on_disk) == 1:
            return FileResponse(
                src,
                filename=src.name,
                media_type=media_type_for(src),
                content_disposition_type="attachment",
            )
        zip_path = zip_files(on_disk)
        zip_name = f"{safe_filename(str(work.get('title') or 'volume'))}.zip"
        return FileResponse(
            zip_path,
            filename=zip_name,
            media_type="application/zip",
            background=BackgroundTask(_unlink, str(zip_path)),
        )

    @app.get("/api/works/{work_id}/stream")
    def work_stream(work_id: str, request: Request, file: str = ""):
        """Single-file audio stream for on-page album playback (household auth)."""
        require_role(request.state.user, "owner", "op", "reader")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        rows = db.files_for_work(work_id)
        chosen = resolve_catalog_file(rows, file)
        if chosen is None:
            raise HTTPException(status_code=404, detail="File not found")
        if not is_streamable_audio(chosen):
            raise HTTPException(status_code=422, detail="Not a streamable audio file")
        return FileResponse(
            chosen,
            filename=chosen.name,
            media_type=media_type_for(chosen),
            content_disposition_type="inline",
        )

    @app.get("/api/works/{work_id}/chapters")
    def work_chapters(work_id: str, request: Request, file: str = ""):
        """Mutagen chapter markers for an audiobook file (empty list when none)."""
        require_role(request.state.user, "owner", "op", "reader")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        rows = db.files_for_work(work_id)
        wanted = str(file or "").strip()
        if wanted:
            chosen = resolve_catalog_file(rows, wanted)
            if chosen is None:
                raise HTTPException(status_code=404, detail="File not found")
        else:
            on_disk = existing_file_paths(rows)
            streamable = [path for path in on_disk if is_streamable_audio(path)]
            if not streamable:
                raise HTTPException(status_code=404, detail="File not found")
            chosen = streamable[0]
        if not is_streamable_audio(chosen):
            raise HTTPException(status_code=422, detail="Not a streamable audio file")
        return {"chapters": extract_chapters(chosen), "file": wanted or chosen.name}

    @app.post("/api/works/{work_id}/convert")
    def work_convert(work_id: str, payload: ConvertPayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        if db.get_work(work_id) is None:
            raise HTTPException(status_code=404, detail="Work not found")
        src = _canonical_file(work_id)
        cache = Path(root) / "conversions" / work_id
        try:
            dest = convert_ebook(src, payload.format, cache)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except FileNotFoundError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        return {"path": str(dest), "format": payload.format, "filename": dest.name}

    @app.get("/api/indexers")
    def list_indexers(request: Request):
        require_role(request.state.user, "owner")
        return {"indexers": db.list_indexers()}

    @app.post("/api/indexers/ping")
    def indexer_ping(request: Request):
        require_role(request.state.user, "owner")
        return ping_nzbfinder(db, settings())

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
        return {"job": job}

    @app.get("/api/queue")
    def queue(request: Request):
        require_role(request.state.user, "owner", "op")
        cfg = settings()
        poll_watch_folder(db, cfg)
        try:
            poll_rss_feeds(db, cfg)
        except Exception:
            pass
        try:
            poll_active_jobs(db, cfg)
        except SABError:
            pass
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
        return {"jobs": jobs}

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
            if problem == "unpack_stuck" and stored in {"", "no_payload"}:
                work["review_reason"] = "unpack_stuck"
            shelf = shelf_work_for_collision(db, work)
            work["shelf_work"] = shelf
            work["actions"] = review_slip_actions(work, diagnosis, llm_configured=llm_ok)
            reason = str(work.get("review_reason") or "")
            if work.get("kind") == "comic" and reason in (
                "comicvine_ambiguous",
                "comicvine_unmatched",
                "low_confidence",
                "unknown_identity",
            ):
                try:
                    work["match_candidates"] = list_match_candidates(work, settings=cfg, limit=6)
                except Exception:
                    work["match_candidates"] = []
        extra_files_count = db.count_works(review_state="needs_review", review_reason="extra_files")
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
            already_running=is_extra_files_reprocess_running(root),
            begin=lambda: begin_extra_files_reprocess_run(root, total=0, phase="starting"),
            target=run_reprocess,
            name="librarian-extra-files-reprocess",
        )
        payload = read_extra_files_reprocess_progress(root)
        payload["extra_files_remaining"] = db.count_works(
            review_state="needs_review", review_reason="extra_files"
        )
        return {**payload, "kicked_off": kicked}

    @app.get("/api/review/reprocess-extra-files/status")
    def review_reprocess_extra_files_status(request: Request):
        """Poll Clear extra-files slips progress (survives refresh via DATA_DIR JSON)."""
        require_role(request.state.user, "owner", "op")
        progress = read_extra_files_reprocess_progress(root)
        if str(progress.get("status") or "") != "running":
            progress["extra_files_remaining"] = db.count_works(
                review_state="needs_review", review_reason="extra_files"
            )
            return progress
        alive = extra_files_reprocess_job.alive()
        if alive and not is_extra_files_reprocess_stale(progress):
            progress["extra_files_remaining"] = db.count_works(
                review_state="needs_review", review_reason="extra_files"
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
            review_state="needs_review", review_reason="extra_files"
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
            already_running=is_purge_duplicates_running(root),
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

    @app.post("/api/maintain/purge-shells")
    def maintain_purge_shells(request: Request, limit: int = 0):
        """Owner bulk: delete catalog shells with no media on disk (poll status)."""
        require_role(request.state.user, "owner", "op")
        run_limit = max(0, int(limit or 0))

        def run_purge() -> None:
            reporter = PurgeShellsProgressReporter(root)
            try:
                purge_shell_works(
                    db,
                    settings(),
                    limit=run_limit,
                    progress=reporter,
                )
            except Exception as error:
                logger.exception("Purge shells failed")
                reporter.fail(str(error) or "Purge shells failed")

        kicked = purge_shells_job.start_if_idle(
            already_running=is_purge_shells_running(root),
            begin=lambda: begin_purge_shells_run(root, total=0, phase="starting"),
            target=run_purge,
            name="librarian-purge-shells",
        )
        payload = read_purge_shells_progress(root)
        payload["shells_remaining"] = db.count_shell_works()
        return {**payload, "kicked_off": kicked}

    @app.get("/api/maintain/purge-shells/status")
    def maintain_purge_shells_status(request: Request):
        """Poll Purge shells progress (survives refresh via DATA_DIR JSON)."""
        require_role(request.state.user, "owner", "op")
        progress = read_purge_shells_progress(root)
        if str(progress.get("status") or "") != "running":
            progress["shells_remaining"] = db.count_shell_works()
            return progress
        alive = purge_shells_job.alive()
        if alive and not is_purge_shells_stale(progress):
            progress["shells_remaining"] = db.count_shell_works()
            return progress
        if alive:
            error = "Purge shells stalled (no progress heartbeat). Try Purge again."
        else:
            error = "Purge shells stopped — the lamp was restarted. Try again."
        finished = finish_purge_shells_run(root, error=error)
        finished["shells_remaining"] = db.count_shell_works()
        return finished

    @app.post("/api/maintain/split-mixed-kinds")
    def maintain_split_mixed_kinds(request: Request, limit: int = 0):
        """Owner bulk: split works that blend comic archives with ebook encodings."""
        require_role(request.state.user, "owner", "op")
        run_limit = max(0, int(limit or 0))

        def run_split() -> None:
            reporter = SplitMixedKindsProgressReporter(root)
            try:
                split_mixed_kind_works(
                    db,
                    settings(),
                    limit=run_limit,
                    progress=reporter,
                )
            except Exception as error:
                logger.exception("Split mixed kinds failed")
                reporter.fail(str(error) or "Split mixed kinds failed")

        kicked = split_mixed_kinds_job.start_if_idle(
            already_running=is_split_mixed_kinds_running(root),
            begin=lambda: begin_split_mixed_kinds_run(root, total=0, phase="starting"),
            target=run_split,
            name="librarian-split-mixed-kinds",
        )
        payload = read_split_mixed_kinds_progress(root)
        payload["mixed_remaining"] = count_mixed_kind_works(db)
        return {**payload, "kicked_off": kicked}

    @app.get("/api/maintain/split-mixed-kinds/status")
    def maintain_split_mixed_kinds_status(request: Request):
        """Poll split-mixed-kinds progress (survives refresh via DATA_DIR JSON)."""
        require_role(request.state.user, "owner", "op")
        progress = read_split_mixed_kinds_progress(root)
        if str(progress.get("status") or "") != "running":
            progress["mixed_remaining"] = count_mixed_kind_works(db)
            return progress
        alive = split_mixed_kinds_job.alive()
        if alive and not is_split_mixed_kinds_stale(progress):
            progress["mixed_remaining"] = count_mixed_kind_works(db)
            return progress
        if alive:
            error = "Split mixed kinds stalled (no progress heartbeat). Try again."
        else:
            error = "Split mixed kinds stopped — the lamp was restarted. Try again."
        finished = finish_split_mixed_kinds_run(root, error=error)
        finished["mixed_remaining"] = count_mixed_kind_works(db)
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

    @app.get("/api/gaps")
    def gaps(request: Request):
        require_role(request.state.user, "owner", "op")
        rows = catalog_gaps(db, settings())
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
        return {"work": work, "plexamp": plexamp_handoff(work)}

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
        merged = merge_secret_fields(incoming, settings())
        from librarian.config import Settings

        saved = Settings.from_mapping(merged)
        watch_error = validate_watch_root(str(saved.watch_root or ""), saved)
        if watch_error:
            raise HTTPException(status_code=400, detail=watch_error)
        save_settings(root, saved)
        sync_nzbfinder(db, saved)
        return {"settings": mask_settings(saved), "abs_match": abs_match_counts(db)}

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

    @app.post("/api/settings/abs-match")
    def abs_match_settings(request: Request):
        require_role(request.state.user, "owner")
        return match_audiobooks(db, settings(), force=True)

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

    @app.post("/api/settings/scan")
    def scan_settings(request: Request):
        require_role(request.state.user, "owner")

        def run_scan() -> None:
            reporter = ScanProgressReporter(root, source="manual")
            try:
                scan_library(db, settings(), progress=reporter)
            except Exception as error:
                logger.exception("Scan shelves failed")
                reporter.fail(str(error) or "Scan failed")

        kicked = scan_job.start_if_idle(
            already_running=is_scan_running(root),
            begin=lambda: begin_scan_run(root, source="manual", total=0, phase="starting"),
            target=run_scan,
            name="librarian-scan",
        )
        payload = read_scan_progress(root)
        return {**payload, "kicked_off": kicked}

    @app.get("/api/settings/scan/status")
    def scan_settings_status(request: Request):
        require_role(request.state.user, "owner")
        progress = read_scan_progress(root)
        if str(progress.get("status") or "") != "running":
            return progress
        if scan_job.alive():
            return progress
        return finish_scan_run(
            root,
            error="Scan stopped — the lamp was restarted. Try Scan again.",
        )

    @app.get("/api/fs")
    def fs_list(request: Request, path: str = ""):
        require_role(request.state.user, "owner", "op")
        try:
            return list_dir(path)
        except PathDenied as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/ingest")
    def ingest_path(payload: IngestPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            target = confined_path(payload.path, must_exist=True)
        except PathDenied as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        refusal = protected_path_refusal(target, settings())
        if refusal:
            raise HTTPException(status_code=400, detail=refusal)
        user_id = request.state.user["id"]
        source_path = str(target)

        def run_ingest() -> None:
            reporter = IngestProgressReporter(root, source_path=source_path)
            try:
                run_ingest_paths(
                    db,
                    settings(),
                    paths=[target],
                    requested_by=user_id,
                    source="ingest",
                    progress=reporter,
                )
            except Exception as error:
                logger.exception("Add to the shelves failed")
                reporter.fail(str(error) or "Ingest failed")

        # Expand recursively in the worker so the meter denominator is real.
        kicked = ingest_job.start_if_idle(
            already_running=is_ingest_running(root),
            begin=lambda: begin_ingest_run(root, source_path=source_path, total=0, phase="scanning"),
            target=run_ingest,
            name="librarian-ingest",
        )
        progress = read_ingest_progress(root)
        return {**progress, "kicked_off": kicked}

    @app.get("/api/ingest/status")
    def ingest_status(request: Request):
        require_role(request.state.user, "owner", "op")
        progress = read_ingest_progress(root)
        if str(progress.get("status") or "") != "running":
            return progress
        if ingest_job.alive():
            return progress
        # Rebuild / process restart left a stale "running" blob with no worker.
        return finish_ingest_run(
            root,
            error="Shelving stopped — the lamp was restarted. Try Add again.",
        )

    @app.post("/api/settings/enrich")
    def enrich_settings(request: Request):
        require_role(request.state.user, "owner")

        def run_enrich() -> None:
            reporter = EnrichProgressReporter(root, source="manual")
            try:
                enrich_library(db, settings(), data_dir=root, progress=reporter)
            except Exception as error:
                logger.exception("Enrich shelves failed")
                reporter.fail(friendly_enrich_error(error) or "Enrich failed")

        kicked = enrich_job.start_if_idle(
            already_running=is_enrich_running(root),
            begin=lambda: begin_enrich_run(root, source="manual", total=0, phase="starting"),
            target=run_enrich,
            name="librarian-enrich",
        )
        payload = read_enrich_progress(root)
        return {**payload, "kicked_off": kicked}

    @app.get("/api/settings/enrich/status")
    def enrich_settings_status(request: Request):
        require_role(request.state.user, "owner")
        progress = read_enrich_progress(root)
        if str(progress.get("status") or "") != "running":
            return progress
        if enrich_job.alive():
            return progress
        # Rebuild / process restart left a stale "running" blob with no worker.
        return finish_enrich_run(
            root,
            error="Enrich stopped — the lamp was restarted. Try Enrich again.",
        )

    @app.post("/api/settings/suggest-cache")
    def suggest_cache_settings(request: Request, external: int = 0):
        require_role(request.state.user, "owner")
        return refresh_suggest_cache(db, root, include_external=bool(external))

    @app.post("/api/works/{work_id}/enrich")
    def work_enrich(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            result = enrich_work(db, settings(), work_id, data_dir=root)
        except ValueError as error:
            detail = str(error)
            status = 404 if detail == "Work not found" else 400
            raise HTTPException(status_code=status, detail=detail) from error
        return result

    @app.patch("/api/works/{work_id}/metadata")
    def work_metadata(work_id: str, payload: WorkMetadataPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        fields = payload.model_dump(exclude_unset=True)
        if not fields:
            raise HTTPException(status_code=400, detail="No metadata fields to update")
        try:
            work = update_work_metadata(db, work_id, fields, data_dir=root)
        except ValueError as error:
            detail = str(error)
            status = 404 if detail == "Work not found" else 400
            raise HTTPException(status_code=status, detail=detail) from error
        return {"work": public_work(work)}

    @app.get("/api/works/{work_id}/match-candidates")
    def work_match_candidates(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        if str(work.get("kind") or "") not in ("book", "audiobook", "comic"):
            raise HTTPException(status_code=400, detail="Only books, audiobooks, and comics can be matched")
        candidates = list_match_candidates(work, settings=settings())
        return {"candidates": candidates, "title": work.get("title"), "author": work.get("author")}

    @app.post("/api/works/{work_id}/apply-match")
    def work_apply_match(work_id: str, payload: ApplyMatchPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        try:
            kind = str(work.get("kind") or "")
            if kind == "comic":
                result = apply_comicvine_match(
                    db,
                    settings(),
                    work_id,
                    payload.match_key,
                )
            elif kind == "audiobook":
                result = apply_audnexus_match(
                    db,
                    settings(),
                    work_id,
                    payload.match_key,
                    data_dir=root,
                )
            else:
                result = apply_openlibrary_match(
                    db,
                    settings(),
                    work_id,
                    payload.match_key,
                    data_dir=root,
                )
        except ValueError as error:
            detail = str(error)
            status = 404 if detail in (
                "Work not found",
                "Open Library match not found",
                "Comic Vine match not found",
                "Audnexus match not found",
            ) else 400
            raise HTTPException(status_code=status, detail=detail) from error
        result["work"] = public_work(result.get("work"))
        return result

    @app.post("/api/works/{work_id}/clear-enrich")
    def work_clear_enrich(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            work = clear_enrichment(db, work_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"work": public_work(work)}

    @app.post("/api/settings/goodreads")
    async def goodreads_settings(request: Request, file: UploadFile = File(...)):
        require_role(request.state.user, "owner")
        raw = await file.read()
        if len(raw) > MAX_GOODREADS_BYTES:
            raise HTTPException(status_code=400, detail="Goodreads CSV is too large")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise HTTPException(status_code=400, detail="Goodreads CSV must be UTF-8") from error
        return import_goodreads_csv(db, request.state.user["id"], text)

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

    @app.get("/release-notes.json")
    def release_notes_json() -> FileResponse:
        """Serve release notes copied into dist (Docker) or public/ (local generate)."""
        path = _frontend_public_file("release-notes.json")
        if path is None:
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
