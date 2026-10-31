"""Find: search, Stacks browse and export, curated lists, and finish-set estimates."""

from __future__ import annotations

import csv
import io
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from librarian.db import BROWSE_EXPORT_ROW_CAP, BROWSE_PAGE_MAX_LIMIT
from librarian.delight import (
    estimate_finish_eta_minutes,
    finish_set_label,
    in_quiet_hours,
)
from librarian.indexers.discover import discover_beyond, resolve_discover_offset, resolve_feed_limit
from librarian.indexers.rank import search_and_rank
from librarian.indexers.scrub import public_indexer_hit, public_indexer_hits
from librarian.kinds import ALL_KINDS
from librarian.lists import curated_list_payload, list_presets
from librarian.public_domain import PublicDomainError, search_public_domain, shelve_edition
from librarian.search_forgive import search_with_forgiveness
from librarian.search_modes import apply_search_mode, normalize_search_mode
from librarian.services import NotFoundError, ServiceError
from librarian.web.serializers import public_work, public_works

# Visible stacks columns. ``series`` is the work's series_name. Omitted ``columns``
# exports every name in this order. Sort keys and canonical ids are reader-facing
# catalog fields; filesystem paths and the raw ``works.isbn`` string are not.
BROWSE_EXPORT_COLUMNS: tuple[str, ...] = (
    "title",
    "author",
    "title_sort",
    "author_sort",
    "year",
    "kind",
    "series",
    "genre",
    "work_id",
    "isbn13",
    "asin",
    "ol_work",
    "hardcover",
    "comicvine",
    "calibre",
)
_CANONICAL_ID_SCHEMES: tuple[str, ...] = (
    "isbn13",
    "asin",
    "ol_work",
    "hardcover",
    "comicvine",
    "calibre",
)
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

REQUEST_ROLES = ("owner", "op", "reader")
CONFIRM_ROLES = ("owner", "op")
BEYOND_DEADLINE_SECONDS = 10.0
BEYOND_CACHE_TTL_SECONDS = 10 * 60.0

_BEYOND_CACHE: Dict[str, tuple[float, Dict[str, Any]]] = {}
_BEYOND_CACHE_LOCK = threading.Lock()


def _text(value: Any) -> str:
    return str(value or "").strip()


def beyond_disclosure(settings: Any) -> Dict[str, Any]:
    """Names the services a beyond look may contact. No secrets."""
    from librarian.indexers.hosts import enabled_hosts
    from librarian.llm_providers import PROVIDER_CATALOG, resolve_llm_connection

    hosts = enabled_hosts(settings)
    indexers = [str(host.get("name") or "").strip() for host in hosts if str(host.get("name") or "").strip()]
    model = ""
    try:
        connection = resolve_llm_connection(settings)
    except Exception:  # noqa: BLE001 — disclosure must not fail the local lane
        connection = {}
    if connection.get("api_key"):
        provider = str(connection.get("provider") or "")
        model = str((PROVIDER_CATALOG.get(provider) or {}).get("label") or provider)
    return {
        "indexers": indexers,
        "model": model,
        "public_domain": ["Project Gutenberg", "Standard Ebooks"],
    }


def _sought_payload(
    *,
    q: str,
    kind: str,
    title: str,
    author: str,
    isbn: str,
    series: str,
    issue: str,
    artist: str,
    album: str,
    year: str,
    mode: str,
) -> Dict[str, Any]:
    search_mode = normalize_search_mode(mode)
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
    if search_mode:
        sought = apply_search_mode(sought, search_mode, (q or "").strip() or q)
    return {"sought": sought, "mode": search_mode}


def _beyond_cache_key(sought: Mapping[str, Any], *, heuristic_only: bool, hosts: str = "") -> str:
    parts = [f"h={int(heuristic_only)}"]
    if hosts:
        parts.append(f"hosts={hosts}")
    for key in ("kind", "q", "title", "author", "isbn", "series", "issue", "artist", "album", "year"):
        value = _text(sought.get(key))
        if value:
            parts.append(f"{key}={value.lower()}")
    return "|".join(parts)


def _beyond_cache_get(key: str) -> Optional[Dict[str, Any]]:
    now = time.monotonic()
    with _BEYOND_CACHE_LOCK:
        row = _BEYOND_CACHE.get(key)
        if row is None:
            return None
        stamped, payload = row
        if now - stamped > BEYOND_CACHE_TTL_SECONDS:
            _BEYOND_CACHE.pop(key, None)
            return None
        return dict(payload)


def _beyond_cache_put(key: str, payload: Mapping[str, Any]) -> None:
    with _BEYOND_CACHE_LOCK:
        if len(_BEYOND_CACHE) > 128:
            oldest = sorted(_BEYOND_CACHE.items(), key=lambda item: item[1][0])[:32]
            for stale, _ in oldest:
                _BEYOND_CACHE.pop(stale, None)
        _BEYOND_CACHE[key] = (time.monotonic(), dict(payload))


def clear_beyond_cache() -> None:
    with _BEYOND_CACHE_LOCK:
        _BEYOND_CACHE.clear()


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
            raise ServiceError("Unknown export column")
        if name not in selected:
            selected.append(name)
    if not selected:
        raise ServiceError("columns must name at least one export column")
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


def _canonical_id_cells(item: Any) -> Dict[str, str]:
    """Identifier columns stamped by ``_stamp_canonical_export_fields``. Never the raw ISBN field."""
    raw = item if isinstance(item, dict) else {}
    stamped = raw.get("_canonical_ids")
    cells = stamped if isinstance(stamped, dict) else {}
    return {scheme: _csv_cell(cells.get(scheme) or "") for scheme in _CANONICAL_ID_SCHEMES}


def _stamp_canonical_export_fields(db: Any, items: Sequence[Any]) -> None:
    """Fill canonical identifier cells from ``work_identifiers``, then edition isbn13/asin."""
    list_ids = getattr(db, "list_work_identifiers", None)
    list_editions = getattr(db, "list_editions_for_work", None)
    for item in items:
        if not isinstance(item, dict):
            continue
        buckets = {scheme: [] for scheme in _CANONICAL_ID_SCHEMES}
        work_id = str(item.get("id") or "").strip()
        if work_id and callable(list_ids):
            for row in list_ids(work_id) or []:
                scheme = str(row.get("scheme") or "")
                value = str(row.get("value") or "").strip()
                if scheme in buckets and value and value not in buckets[scheme]:
                    buckets[scheme].append(value)
        if work_id and callable(list_editions):
            for edition in list_editions(work_id) or []:
                for scheme in ("isbn13", "asin"):
                    value = str(edition.get(scheme) or "").strip()
                    if value and value not in buckets[scheme]:
                        buckets[scheme].append(value)
        item["_canonical_ids"] = {scheme: "; ".join(values) for scheme, values in buckets.items()}


def _browse_export_record(item: Any, columns: Sequence[str]) -> Dict[str, str]:
    public = public_work(item if isinstance(item, dict) else None) or {}
    raw = item if isinstance(item, dict) else {}
    values = {
        "title": _csv_cell(public.get("title")),
        "author": _csv_cell(public.get("author")),
        "title_sort": _csv_cell(raw.get("title_sort")),
        "author_sort": _csv_cell(raw.get("author_sort")),
        "year": _csv_cell(_year_text(public.get("year"))),
        "kind": _csv_cell(public.get("kind")),
        "series": _csv_cell(public.get("series_name")),
        "genre": _csv_cell(public.get("genre")),
        "work_id": _csv_cell(raw.get("id")),
        **_canonical_id_cells(raw),
    }
    return {column: values.get(column, "") for column in columns}


def render_browse_csv(items: Sequence[Any], columns: Sequence[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), extrasaction="ignore")
    writer.writeheader()
    for item in items:
        writer.writerow(_browse_export_record(item, columns))
    return buffer.getvalue()


def resolve_browse_shelf(db: Any, user_id: str, shelf: str) -> Optional[str]:
    raw_shelf = str(shelf or "").strip()
    if not raw_shelf:
        return None
    if raw_shelf.lower() == "favorites":
        return "favorites"
    shelf_row = db.get_shelf(raw_shelf)
    if not shelf_row or not db.user_can_view_shelf(shelf_row, user_id):
        raise NotFoundError("Shelf not found")
    return str(shelf_row["id"])


def load_browse_page(
    db: Any,
    user: Mapping[str, Any],
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
    shelf_key = resolve_browse_shelf(db, user["id"], shelf)
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
        raise NotFoundError(str(error)) from error
    filters = {
        "kind": kind_key or "",
        "author": author.strip(),
        "letter": letter.strip().upper(),
        "series": series.strip(),
        "genre": genre.strip(),
        "shelf": shelf_key or "",
    }
    return page, filters


def browse_page(
    db: Any,
    user: Mapping[str, Any],
    *,
    annotate: Callable[[Any, List[Dict[str, Any]]], Any],
    **filters: Any,
) -> Dict[str, Any]:
    """``GET /api/browse`` body: one public Stacks page with availability flags."""
    page, applied = load_browse_page(
        db, user, max_limit=BROWSE_PAGE_MAX_LIMIT, **filters
    )
    items = public_works(page["items"])
    annotate(db, items)
    return {
        "items": items,
        "total": page["total"],
        "offset": page["offset"],
        "limit": page["limit"],
        "sort": page["sort"],
        "sort_dir": page["sort_dir"],
        "filters": applied,
    }


@dataclass(frozen=True)
class BrowseExport:
    body: str
    cap: int
    total: int
    returned: int


def export_browse_csv(
    db: Any,
    user: Mapping[str, Any],
    *,
    columns: str,
    **filters: Any,
) -> BrowseExport:
    """CSV for the current stacks filters, starting at the first match, capped."""
    selected = parse_browse_export_columns(columns)
    cap = BROWSE_EXPORT_ROW_CAP
    page, _applied = load_browse_page(
        db, user, offset=0, limit=cap, max_limit=cap, **filters
    )
    _stamp_canonical_export_fields(db, page["items"])
    return BrowseExport(
        body=render_browse_csv(page["items"], selected),
        cap=cap,
        total=int(page["total"]),
        returned=len(page["items"]),
    )


def browse_facets(db: Any, user: Mapping[str, Any], *, kind: str, shelf: str) -> Dict[str, Any]:
    kind_key = kind if kind in ALL_KINDS else None
    shelf_key = resolve_browse_shelf(db, user["id"], shelf)
    return db.browse_facets(
        kind=kind_key,
        shelf=shelf_key,
        user_id=user["id"] if shelf_key else None,
    )


def run_search(
    db: Any,
    settings: Callable[[], Any],
    *,
    root: Path,
    user: Mapping[str, Any],
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
    mode: str = "",
) -> Dict[str, Any]:
    """``GET /api/search``: local shelf only. ``beyond`` is ignored — use ``/beyond``."""
    del beyond  # local lane never fans out
    local_kind = kind if kind in ALL_KINDS else None
    local_q = q.strip()
    packed = _sought_payload(
        q=q,
        kind=kind,
        title=title,
        author=author,
        isbn=isbn,
        series=series,
        issue=issue,
        artist=artist,
        album=album,
        year=year,
        mode=mode,
    )
    search_mode = packed["mode"]
    forgiven: Dict[str, Any] = {"local": [], "did_you_mean": [], "forgave": False}
    if local_q and search_mode:
        forgiven = {
            "local": db.search_works_mode(local_q, search_mode, limit=24, kind=local_kind),
            "did_you_mean": [],
            "forgave": False,
        }
    elif local_q:
        forgiven = search_with_forgiveness(db, local_q, limit=24, kind=local_kind)
    local = public_works(forgiven.get("local") or [])
    return {
        "q": q,
        "mode": search_mode,
        "local": local,
        "did_you_mean": list(forgiven.get("did_you_mean") or []),
        "forgave": bool(forgiven.get("forgave")),
        "beyond": [],
        "beyond_error": None,
        "public_domain": [],
        "public_domain_error": None,
        "pick": None,
        "candidates": [],
        "rank_method": "",
        "rank_reason": "",
        "search_trace": None,
        "beyond_disclosure": beyond_disclosure(settings()),
        "can_request": user["role"] in REQUEST_ROLES,
        "can_beyond": user["role"] in CONFIRM_ROLES,
    }


def run_search_beyond(
    db: Any,
    settings: Callable[[], Any],
    *,
    root: Path,
    user: Mapping[str, Any],
    q: str = "",
    kind: str = "",
    title: str = "",
    author: str = "",
    isbn: str = "",
    series: str = "",
    issue: str = "",
    artist: str = "",
    album: str = "",
    year: str = "",
    mode: str = "",
) -> Dict[str, Any]:
    """``GET /api/search/beyond``: indexers + public domain. Owner/op only."""
    if user["role"] not in CONFIRM_ROLES:
        raise ServiceError("Stay on the shelves, or Ask the house.", status_code=403)
    packed = _sought_payload(
        q=q,
        kind=kind,
        title=title,
        author=author,
        isbn=isbn,
        series=series,
        issue=issue,
        artist=artist,
        album=album,
        year=year,
        mode=mode,
    )
    sought = packed["sought"]
    search_mode = packed["mode"]
    has_query = any(_text(sought.get(key)) for key in sought if key != "kind")
    if str(kind or "").strip().lower() in {"movie", "tv", "xxx"} or not has_query:
        return {
            "q": q,
            "mode": search_mode,
            "beyond": [],
            "beyond_error": None,
            "public_domain": [],
            "public_domain_error": None,
            "pick": None,
            "candidates": [],
            "rank_method": "",
            "rank_reason": "",
            "search_trace": None,
            "can_request": user["role"] in REQUEST_ROLES,
            "cached": False,
        }
    heuristic_only = user["role"] not in CONFIRM_ROLES
    cfg = settings()
    from librarian.indexers.hosts import enabled_hosts

    host_ids = ",".join(str(host.get("id") or "") for host in enabled_hosts(cfg))
    cache_key = _beyond_cache_key(sought, heuristic_only=heuristic_only, hosts=host_ids)
    cached = _beyond_cache_get(cache_key)
    if cached is not None:
        cached["cached"] = True
        return cached
    ranked: Dict[str, Any] = {}
    public_domain: List[Dict[str, Any]] = []
    public_domain_error = None

    def _indexers() -> Dict[str, Any]:
        return search_and_rank(
            cfg,
            data_dir=root,
            deadline=BEYOND_DEADLINE_SECONDS,
            heuristic_only=heuristic_only,
            **sought,
        )

    def _public() -> List[Dict[str, Any]]:
        return search_public_domain(q.strip() or q, mode=search_mode or "title")

    with ThreadPoolExecutor(max_workers=2) as pool:
        indexer_future = pool.submit(_indexers)
        public_future = pool.submit(_public)
        try:
            ranked = indexer_future.result(timeout=BEYOND_DEADLINE_SECONDS)
        except Exception as error:  # noqa: BLE001 — partial beyond is still a result
            ranked = {"hits": [], "error": str(error)}
        try:
            public_domain = public_future.result(timeout=BEYOND_DEADLINE_SECONDS)
        except Exception as error:  # noqa: BLE001 — lane must not blank indexer hits
            public_domain = []
            public_domain_error = str(error)

    indexer = list(ranked.get("hits") or [])
    beyond_error = ranked.get("error")
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
    payload = {
        "q": q,
        "mode": search_mode,
        "beyond": public_indexer_hits(indexer),
        "beyond_error": beyond_error,
        "public_domain": public_domain,
        "public_domain_error": public_domain_error,
        "pick": public_indexer_hit(pick) if isinstance(pick, dict) else pick,
        "candidates": public_indexer_hits(candidates),
        "rank_method": rank_method,
        "rank_reason": rank_reason,
        "search_trace": search_trace if user["role"] in CONFIRM_ROLES else None,
        "can_request": user["role"] in REQUEST_ROLES,
        "cached": False,
    }
    _beyond_cache_put(cache_key, payload)
    return payload


def ask_from_search(
    db: Any,
    user: Mapping[str, Any],
    *,
    q: str = "",
    kind: str = "",
    title: str = "",
    author: str = "",
    isbn: str = "",
) -> Dict[str, Any]:
    """File a Wanted row from a search. Never searches indexers. Never calls SABnzbd."""
    from librarian.wanted import AlreadyShelved, WantedError, add_wanted, public_wanted

    if user["role"] not in REQUEST_ROLES:
        raise ServiceError("Stay on the shelves, or Ask the house.", status_code=403)
    wanted_kind = kind if kind in ALL_KINDS else "book"
    wanted_title = _text(title) or _text(q)
    try:
        row = add_wanted(
            db,
            {
                "title": wanted_title,
                "author": _text(author),
                "isbn": _text(isbn),
                "kind": wanted_kind,
            },
        )
    except AlreadyShelved as error:
        raise ServiceError("Already on the shelf", status_code=409) from error
    except WantedError as error:
        raise ServiceError(str(error)) from error
    return {
        "item": public_wanted(row),
        "searched": False,
        "can_confirm": user["role"] in CONFIRM_ROLES,
    }


def discover_page(
    cfg: Any,
    *,
    root: Path,
    user: Mapping[str, Any],
    kind: str = "",
    cat: str = "",
    limit: int = 0,
    offset: int = 0,
    page: int = 0,
) -> Dict[str, Any]:
    """One page of an indexer Discover feed.

    ``page`` is 1-based. A positive ``offset`` wins. The first page is offset 0.
    Readers stay on the shelves; Discover is an indexer door for owner and op.
    """
    if user["role"] not in CONFIRM_ROLES:
        raise ServiceError("Stay on the shelves, or Ask the house.", status_code=403)
    feed_limit = resolve_feed_limit(cat=cat, limit=limit if limit else None)
    skip = resolve_discover_offset(offset=offset, page=page, limit=feed_limit)
    items, categories, beyond_error = discover_beyond(
        cfg,
        kind=kind,
        cat=cat,
        limit=feed_limit,
        offset=skip,
        data_dir=root,
    )
    shown_page = (skip // feed_limit) + 1 if feed_limit else 1
    return {
        "kind": kind,
        "cat": cat,
        "limit": feed_limit,
        "offset": skip,
        "page": shown_page,
        "items": public_indexer_hits(items),
        "categories": categories,
        "beyond_error": beyond_error,
        "can_request": user["role"] in REQUEST_ROLES,
    }


def curated_list_presets(cfg: Any) -> Dict[str, Any]:
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


def curated_llm_list(
    db: Any,
    cfg: Any,
    *,
    root: Path,
    user: Mapping[str, Any],
    preset: Any,
    date: str,
    query: Any,
) -> Dict[str, Any]:
    """BYO LLM curated list matched against local shelves, with shelved stubs enriched."""
    result = curated_list_payload(
        cfg,
        db,
        preset=preset,
        date=date,
        query=query,
        data_dir=root,
    )
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
                    "has_cover": bool(work.get("has_cover")),
                }
    result["can_request"] = user["role"] in REQUEST_ROLES
    result["can_confirm"] = user["role"] in CONFIRM_ROLES
    return result


def shelve_public_domain(db: Any, cfg: Any, payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Shelve one Gutenberg or Standard Ebooks epub. No SABnzbd."""
    try:
        result = shelve_edition(db, cfg, dict(payload))
    except PublicDomainError as error:
        raise ServiceError(str(error)) from error
    work = public_work(db.get_work(str(result.get("work_id") or "")))
    return {**result, "work": work}


def finish_set_eta(
    db: Any,
    cfg: Any,
    *,
    missing_count: Optional[int],
    kind: Optional[str],
    multipart: bool,
    total_bytes: Optional[int],
) -> Dict[str, Any]:
    """Minutes to finish a set, sampled from this kind's downloads, else every download."""
    miss = int(missing_count or 0)
    kind_key = str(kind or "").strip()
    part_filter = True if multipart else None
    kind_samples = (
        db.recent_job_durations(kind=kind_key, multipart=part_filter) if kind_key else []
    )
    pool_approximate = False
    if len(kind_samples) >= 2:
        samples = kind_samples
    else:
        global_samples = db.recent_job_durations(multipart=part_filter)
        if len(global_samples) >= 2:
            samples = global_samples
            pool_approximate = bool(kind_key)
        elif kind_samples:
            samples = kind_samples
            pool_approximate = True
        else:
            samples = global_samples
            pool_approximate = True
    eta = estimate_finish_eta_minutes(
        missing_count=miss,
        recent_seconds=samples,
        total_bytes=total_bytes,
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
        "quiet_hours": in_quiet_hours(cfg),
    }
