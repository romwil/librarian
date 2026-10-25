"""Find: search, browse, suggest, discover, and curated lists."""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Optional, Sequence

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from librarian.auth import require_role
from librarian.db import BROWSE_EXPORT_ROW_CAP, BROWSE_PAGE_MAX_LIMIT
from librarian.delight import (
    estimate_finish_eta_minutes,
    finish_set_label,
    in_quiet_hours,
)
from librarian.indexers.discover import discover_beyond, resolve_feed_limit
from librarian.indexers.rank import search_and_rank
from librarian.indexers.scrub import (
    public_indexer_hit,
    public_indexer_hits,
)
from librarian.kinds import ALL_KINDS, EXTRA_KINDS
from librarian.lists import chase_missing_items, curated_list_payload, list_presets
from librarian.nyt_books import normalize_list_date
from librarian.rate_limit import enforce_rate_limit
from librarian.search_forgive import search_with_forgiveness
from librarian.suggest import SUGGEST_FIELDS, suggest_items
from librarian.web.deps import WebDeps
from librarian.web.schemas import (
    FinishSetEtaPayload,
    LlmListChasePayload,
    LlmListPayload,
)
from librarian.web.serializers import public_work, public_works

# Visible stacks columns. ``series`` is the work's series_name. Omitted ``columns``
# exports every name in this order.
BROWSE_EXPORT_COLUMNS: tuple[str, ...] = (
    "title",
    "author",
    "year",
    "kind",
    "series",
    "genre",
)
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def parse_browse_export_columns(raw: str) -> List[str]:
    """Visible column list, or every export column when omitted or ``all``.

    Unknown names are rejected so a query cannot ask for paths, tokens, or secrets.
    """
    text = str(raw or "").strip()
    if not text or text.lower() == "all":
        return list(BROWSE_EXPORT_COLUMNS)
    selected: List[str] = []
    for part in text.split(","):
        name = part.strip().lower()
        if not name:
            continue
        if name not in BROWSE_EXPORT_COLUMNS:
            raise HTTPException(status_code=400, detail="Unknown export column")
        if name not in selected:
            selected.append(name)
    if not selected:
        raise HTTPException(
            status_code=400,
            detail="columns must name at least one export column",
        )
    return selected


def _year_text(year: Any) -> str:
    if isinstance(year, bool) or year is None:
        return ""
    if isinstance(year, int):
        return str(year)
    return str(year).strip()


def _csv_cell(value: Any) -> str:
    """Spreadsheet-safe cell. Formula-leading text is prefixed so Excel will not run it."""
    if value is None:
        return ""
    text = str(value)
    if text.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + text
    return text


def _browse_export_record(item: Any, columns: Sequence[str]) -> Dict[str, str]:
    public = public_work(item if isinstance(item, dict) else None) or {}
    values = {
        "title": _csv_cell(public.get("title")),
        "author": _csv_cell(public.get("author")),
        "year": _csv_cell(_year_text(public.get("year"))),
        "kind": _csv_cell(public.get("kind")),
        "series": _csv_cell(public.get("series_name")),
        "genre": _csv_cell(public.get("genre")),
    }
    return {column: values.get(column, "") for column in columns}


def render_browse_csv(items: Sequence[Any], columns: Sequence[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), extrasaction="ignore")
    writer.writeheader()
    for item in items:
        writer.writerow(_browse_export_record(item, columns))
    return buffer.getvalue()


def _resolve_browse_shelf(db: Any, user_id: str, shelf: str) -> Optional[str]:
    raw_shelf = str(shelf or "").strip()
    if not raw_shelf:
        return None
    if raw_shelf.lower() == "favorites":
        return "favorites"
    shelf_row = db.get_shelf(raw_shelf)
    if not shelf_row or not db.user_can_view_shelf(shelf_row, user_id):
        raise HTTPException(status_code=404, detail="Shelf not found")
    return str(shelf_row["id"])


def load_browse_page(
    db: Any,
    user: Dict[str, Any],
    *,
    kind: str,
    author: str,
    letter: str,
    series: str,
    genre: str,
    shelf: str,
    sort: str,
    sort_dir: str,
    offset: int,
    limit: int,
    max_limit: int,
) -> tuple[Dict[str, Any], Dict[str, str]]:
    """Shared stacks filters for the JSON page and the CSV export."""
    kind_key = kind if kind in ALL_KINDS else None
    shelf_key = _resolve_browse_shelf(db, user["id"], shelf)
    try:
        page = db.browse_works(
            kind=kind_key,
            author=author.strip() or None,
            letter=letter.strip() or None,
            series=series.strip() or None,
            genre=genre.strip() or None,
            shelf=shelf_key,
            user_id=user["id"] if shelf_key else None,
            sort=sort,
            sort_dir=sort_dir or None,
            offset=offset,
            limit=limit,
            max_limit=max_limit,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    filters = {
        "kind": kind_key or "",
        "author": author.strip(),
        "letter": letter.strip().upper(),
        "series": series.strip(),
        "genre": genre.strip(),
        "shelf": shelf_key or "",
    }
    return page, filters


def register_search_routes(app: FastAPI, deps: WebDeps) -> None:
    """Register search, browse, discover, and curated-list routes on the composition-root app."""
    root = deps.root
    db = deps.db
    settings = deps.settings

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
        forgiven = {"local": [], "did_you_mean": [], "forgave": False}
        if local_q:
            forgiven = search_with_forgiveness(db, local_q, limit=24, kind=local_kind)
        local = public_works(forgiven.get("local") or [])
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
            ranked = search_and_rank(settings(), data_dir=root, **sought)
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
        owner_trace = user["role"] in ("owner", "op")
        return {
            "q": q,
            "local": local,
            "did_you_mean": list(forgiven.get("did_you_mean") or []),
            "forgave": bool(forgiven.get("forgave")),
            "beyond": public_indexer_hits(indexer),
            "beyond_error": beyond_error,
            "pick": public_indexer_hit(pick) if isinstance(pick, dict) else pick,
            "candidates": public_indexer_hits(candidates),
            "rank_method": rank_method,
            "rank_reason": rank_reason,
            "search_trace": search_trace if owner_trace else None,
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
        sort_dir: str = "",
        offset: int = 0,
        limit: int = 48,
    ):
        page, filters = load_browse_page(
            db,
            request.state.user,
            kind=kind,
            author=author,
            letter=letter,
            series=series,
            genre=genre,
            shelf=shelf,
            sort=sort,
            sort_dir=sort_dir,
            offset=offset,
            limit=limit,
            max_limit=BROWSE_PAGE_MAX_LIMIT,
        )
        return {
            "items": public_works(page["items"]),
            "total": page["total"],
            "offset": page["offset"],
            "limit": page["limit"],
            "sort": page["sort"],
            "sort_dir": page["sort_dir"],
            "filters": filters,
        }

    @app.get("/api/browse/export.csv")
    def browse_export_csv(
        request: Request,
        kind: str = "",
        author: str = "",
        letter: str = "",
        series: str = "",
        genre: str = "",
        shelf: str = "",
        sort: str = "author",
        sort_dir: str = "",
        columns: str = "",
    ):
        """CSV for the current stacks filters, capped at ``BROWSE_EXPORT_ROW_CAP`` rows.

        Offset and limit are page controls on ``GET /api/browse`` only. This route
        always starts at the first match. ``columns`` selects a visible subset;
        omit it, or pass ``all``, for title, author, year, kind, series, genre.
        """
        selected = parse_browse_export_columns(columns)
        page, _filters = load_browse_page(
            db,
            request.state.user,
            kind=kind,
            author=author,
            letter=letter,
            series=series,
            genre=genre,
            shelf=shelf,
            sort=sort,
            sort_dir=sort_dir,
            offset=0,
            limit=BROWSE_EXPORT_ROW_CAP,
            max_limit=BROWSE_EXPORT_ROW_CAP,
        )
        body = render_browse_csv(page["items"], selected)
        returned = len(page["items"])
        return Response(
            content=body,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="librarian-stacks.csv"',
                "Cache-Control": "private, no-store",
                "X-Librarian-Export-Cap": str(BROWSE_EXPORT_ROW_CAP),
                "X-Librarian-Export-Total": str(page["total"]),
                "X-Librarian-Export-Returned": str(returned),
            },
        )

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
            "items": public_indexer_hits(items),
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
                "" if llm_ok else "Add a BYO LLM in Settings to load curated bestseller lists."
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
            global_samples = db.recent_job_durations(multipart=True if multipart else None)
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
