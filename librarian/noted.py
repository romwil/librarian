"""New & noted: one desk, three sources.

Open Library trending JSON, the existing LLM bestseller presets (with the
companion-audiobook note from lists), and Discover latest for books (70xx)
and audiobooks (3030). No HTML scrape. Adding a card to Wanted is a separate
route and does not call SABnzbd.
"""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import httpx

from librarian.covers import DEFAULT_USER_AGENT
from librarian.identify import tidy_title, validated_isbn
from librarian.identity.isbn import canonical_isbn13
from librarian.identity.resolve import resolve_work
from librarian.indexers.discover import discover_beyond
from librarian.kinds import NEWZNAB_AUDIOBOOK, NEWZNAB_COMIC, NEWZNAB_MAGAZINE
from librarian.lists import curated_list_payload
from librarian.llm import (
    LLM_RATE_LIMIT_COPY,
    LLMClient,
    client_from_settings,
    seconds_until_llm_ready,
)
from librarian.nyt_books import (
    NytBooksClient,
    default_list_names,
    normalize_list_date,
    normalize_list_name,
)
from librarian.owned import ShelfIndex, annotate_noted_lanes
from librarian.wanted import AlreadyShelved, WantedError, add_wanted, dedupe_key

logger = logging.getLogger(__name__)

OPEN_LIBRARY_TRENDING = "https://openlibrary.org/trending/{period}.json"
PERIODS = ("daily", "weekly")
TRENDING_LIMIT = 20
DISCOVER_LIMIT = 12
DISCOVER_ITEM_CAP = 24
DISCOVER_FEEDS_PER_KIND = 1
BOOK_FAMILY = 7000
# The desk must paint even when a lane's host is quiet. Abandoned HTTP may finish later.
NOTE_LANE_WAIT_S = 8.0
NOTE_LLM_TIMEOUT_S = 12.0

LANE_TRENDING = "trending"
LANE_BESTSELLERS = "bestsellers"
LANE_DISCOVER = "discover"


class NotedError(ValueError):
    """Caller-facing New & noted validation error."""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _person(value: str) -> str:
    """Collapse whitespace and keep initials. Title tidying would turn 'K.' into 'K'."""
    return " ".join(_text(value).split())


def _query(author: str, title: str, isbn: str) -> str:
    return " ".join(part for part in (author, title) if part).strip() or title or isbn


def _category_int(value: Any) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def noted_card(
    *,
    title: str,
    author: str,
    isbn: str,
    kind: str,
    source: str,
    rank: Optional[int] = None,
    cover: str = "",
    category: str = "",
    open_library_key: str = "",
    shelved: Optional[Mapping[str, Any]] = None,
    shelved_audiobook: Optional[Mapping[str, Any]] = None,
    companion_note: str = "",
    companion_find: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Fields the client needs to search the shelves, find beyond, or add to Wanted."""
    clean_title = tidy_title(title)
    clean_author = _person(author)
    clean_isbn = validated_isbn(isbn)
    shelf_kind = kind if kind in ("book", "audiobook") else "book"
    sought = {
        "q": _query(clean_author, clean_title, clean_isbn),
        "kind": shelf_kind,
        "title": clean_title,
        "author": clean_author,
        "isbn": clean_isbn,
    }
    return {
        "title": clean_title,
        "author": clean_author,
        "isbn": clean_isbn,
        "kind": shelf_kind,
        "source": source,
        "rank": rank,
        "cover": _text(cover),
        "category": _text(category),
        "open_library_key": _text(open_library_key),
        "shelved": dict(shelved) if shelved else None,
        "shelved_audiobook": dict(shelved_audiobook) if shelved_audiobook else None,
        "companion_note": _text(companion_note),
        "companion_find": dict(companion_find) if companion_find else None,
        "search": dict(sought),
        "find": dict(sought),
        "wanted": {
            "title": clean_title,
            "author": clean_author,
            "isbn": clean_isbn,
            "kind": shelf_kind,
            "kinds": ["book", "audiobook"],
        },
    }


def _first_author(row: Mapping[str, Any]) -> str:
    names = row.get("author_name")
    if isinstance(names, str) and names.strip():
        return names.strip()
    if isinstance(names, list):
        for name in names:
            text = _text(name)
            if text:
                return text
    authors = row.get("authors")
    if isinstance(authors, list):
        for author in authors:
            if isinstance(author, str) and author.strip():
                return author.strip()
            if isinstance(author, Mapping):
                text = _text(author.get("name") or author.get("author"))
                if text:
                    return text
    return _text(row.get("author"))


def _first_isbn(row: Mapping[str, Any]) -> str:
    raw = row.get("isbn")
    candidates: List[Any]
    if isinstance(raw, list):
        candidates = list(raw)
    elif raw:
        candidates = [raw]
    else:
        candidates = []
    for candidate in candidates:
        isbn = validated_isbn(str(candidate))
        if isbn:
            return isbn
    return ""


def _cover_url(row: Mapping[str, Any]) -> str:
    cover_i = row.get("cover_i")
    if cover_i in (None, "", 0, "0"):
        return ""
    try:
        cover_id = int(cover_i)
    except (TypeError, ValueError):
        return ""
    if cover_id <= 0:
        return ""
    return f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"


def normalize_open_library_work(row: Mapping[str, Any], *, rank: int) -> Optional[Dict[str, Any]]:
    if not isinstance(row, Mapping):
        return None
    title = tidy_title(_text(row.get("title")))
    if not title:
        return None
    return noted_card(
        title=title,
        author=_first_author(row),
        isbn=_first_isbn(row),
        kind="book",
        source="open_library",
        rank=rank,
        cover=_cover_url(row),
        open_library_key=_text(row.get("key")),
    )


def parse_open_library_trending(payload: Any, *, limit: int = TRENDING_LIMIT) -> List[Dict[str, Any]]:
    works = payload.get("works") if isinstance(payload, Mapping) else None
    if not isinstance(works, list):
        return []
    items: List[Dict[str, Any]] = []
    for row in works:
        if not isinstance(row, Mapping):
            continue
        card = normalize_open_library_work(row, rank=len(items) + 1)
        if card is None:
            continue
        items.append(card)
        if len(items) >= limit:
            break
    return items


def fetch_open_library_trending(
    period: str,
    *,
    transport: Optional[httpx.BaseTransport] = None,
    timeout: float = 8.0,
) -> Any:
    """Public trending JSON. No API key. Raises httpx.HTTPError on transport failure."""
    slug = _text(period).lower()
    if slug not in PERIODS:
        raise NotedError("Period must be daily or weekly")
    url = OPEN_LIBRARY_TRENDING.format(period=slug)
    headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
    with httpx.Client(transport=transport, timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = client.get(url, params={"limit": TRENDING_LIMIT})
        response.raise_for_status()
        return response.json()


def _empty_lane(
    lane_id: str,
    *,
    source: str,
    label: str,
    empty_reason: str,
    empty_copy: str,
    configured: bool,
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    lane: Dict[str, Any] = {
        "id": lane_id,
        "source": source,
        "label": label,
        "configured": configured,
        "empty_reason": empty_reason,
        "empty_copy": empty_copy,
        "items": [],
    }
    if extra:
        lane.update(dict(extra))
    return lane


def trending_lane(period: str, *, transport: Optional[httpx.BaseTransport] = None) -> Dict[str, Any]:
    slug = _text(period).lower() or "daily"
    label = "Open Library trending"
    try:
        payload = fetch_open_library_trending(slug, transport=transport)
        items = parse_open_library_trending(payload)
    except NotedError:
        raise
    except (httpx.HTTPError, ValueError) as error:
        logger.info("Open Library trending failed: %s", error)
        lane = _empty_lane(
            LANE_TRENDING,
            source="open_library",
            label=label,
            empty_reason="unavailable",
            empty_copy="Open Library trending is unavailable right now.",
            configured=True,
            extra={"period": slug},
        )
        return lane
    empty_copy = "" if items else "Nothing is trending on Open Library right now."
    return {
        "id": LANE_TRENDING,
        "source": "open_library",
        "label": label,
        "period": slug,
        "configured": True,
        "empty_reason": "" if items else "empty",
        "empty_copy": empty_copy,
        "items": items,
    }


def _companion_note(entry: Mapping[str, Any]) -> str:
    audio = entry.get("shelved_audiobook")
    if isinstance(audio, Mapping) and audio.get("id"):
        return "Companion audiobook is on the shelf."
    return "No companion audiobook on the shelf."


def bestseller_items(books: Sequence[Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in books:
        if not isinstance(row, Mapping):
            continue
        title = _text(row.get("title"))
        if not title:
            continue
        rank = row.get("rank")
        try:
            rank_i = int(rank) if rank is not None and str(rank).strip() != "" else None
        except (TypeError, ValueError):
            rank_i = None
        shelved = row.get("shelved") if isinstance(row.get("shelved"), Mapping) else None
        audio = row.get("shelved_audiobook") if isinstance(row.get("shelved_audiobook"), Mapping) else None
        find = row.get("audiobook_find") if isinstance(row.get("audiobook_find"), Mapping) else None
        items.append(
            noted_card(
                title=title,
                author=_text(row.get("author")),
                isbn=_text(row.get("isbn")),
                kind="book",
                source="llm",
                rank=rank_i,
                cover=_text(row.get("cover")),
                shelved=shelved,
                shelved_audiobook=audio,
                companion_note=_companion_note(row),
                companion_find=find,
            )
        )
    return items


def bestsellers_lane(
    settings: Any,
    db: Any,
    *,
    preset: str,
    date: str,
    data_dir: Any = None,
    transport: Optional[httpx.BaseTransport] = None,
    llm: Optional[LLMClient] = None,
) -> Dict[str, Any]:
    payload = curated_list_payload(
        settings,
        db,
        preset=preset,
        date=date,
        data_dir=data_dir,
        transport=transport,
        llm=llm,
    )
    configured = bool(payload.get("configured"))
    empty_reason = _text(payload.get("empty_reason"))
    empty_copy = _text(payload.get("empty_copy"))
    items = bestseller_items(payload.get("books") or []) if configured and not empty_reason else []
    if configured and not empty_reason and not items:
        empty_reason = "empty_list"
        empty_copy = empty_copy or "That list came back empty."
    return {
        "id": LANE_BESTSELLERS,
        "source": "llm",
        "label": _text(payload.get("display_name")) or "Bestsellers",
        "configured": configured,
        "empty_reason": empty_reason,
        "empty_copy": empty_copy,
        "list_name": _text(payload.get("list_name")),
        "display_name": _text(payload.get("display_name")),
        "date": _text(payload.get("date")),
        "presets": list(payload.get("presets") or []),
        "items": items,
    }


def _book_category(category: Any) -> bool:
    cat = _category_int(category)
    if cat is None:
        return True
    if cat in (NEWZNAB_COMIC, NEWZNAB_MAGAZINE):
        return False
    return (cat // 1000) * 1000 == BOOK_FAMILY


def _audiobook_category(category: Any) -> bool:
    cat = _category_int(category)
    if cat is None:
        return True
    return cat == NEWZNAB_AUDIOBOOK


def discover_card(hit: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    kind = _text(hit.get("kind")).lower()
    if kind not in ("book", "audiobook"):
        return None
    category = hit.get("category")
    if kind == "book" and not _book_category(category):
        return None
    if kind == "audiobook" and not _audiobook_category(category):
        return None
    title = tidy_title(_text(hit.get("book_title") or hit.get("title")))
    if not title:
        return None
    cat_text = "" if category in (None, "") else str(category)
    return noted_card(
        title=title,
        author=_text(hit.get("author")),
        isbn=_text(hit.get("isbn")),
        kind=kind,
        source="discover",
        cover=_text(hit.get("cover")),
        category=cat_text,
    )


def discover_lane(
    settings: Any,
    *,
    transport: Optional[httpx.BaseTransport] = None,
    data_dir: Any = None,
) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    errors: List[str] = []
    seen: set[str] = set()
    for kind in ("book", "audiobook"):
        try:
            hits, _categories, error = discover_beyond(
                settings,
                kind=kind,
                limit=DISCOVER_LIMIT,
                transport=transport,
                max_feeds=DISCOVER_FEEDS_PER_KIND,
                data_dir=data_dir,
            )
        except Exception as error:  # noqa: BLE001 — one host failure must not drop the other lanes
            logger.info("Discover latest failed for %s: %s", kind, error)
            errors.append("Discover latest is unavailable right now.")
            continue
        if error:
            errors.append(_text(error))
        for hit in hits:
            if not isinstance(hit, Mapping):
                continue
            card = discover_card(hit)
            if card is None:
                continue
            key = "|".join(
                (
                    card["kind"],
                    card["title"].lower(),
                    card["author"].lower(),
                    card["isbn"],
                    card["category"],
                )
            )
            if key in seen:
                continue
            seen.add(key)
            items.append(card)
            if len(items) >= DISCOVER_ITEM_CAP:
                break
        if len(items) >= DISCOVER_ITEM_CAP:
            break
    beyond = "; ".join(dict.fromkeys(part for part in errors if part))
    missing = "not configured" in beyond.lower()
    if missing and not items:
        return _empty_lane(
            LANE_DISCOVER,
            source="discover",
            label="Discover latest",
            empty_reason="missing_indexer",
            empty_copy="Add an NZBFinder token in Settings to see Discover latest.",
            configured=False,
            extra={"beyond_error": beyond},
        )
    if not items and beyond:
        return _empty_lane(
            LANE_DISCOVER,
            source="discover",
            label="Discover latest",
            empty_reason="error",
            empty_copy="Discover latest is unavailable right now.",
            configured=True,
            extra={"beyond_error": beyond},
        )
    return {
        "id": LANE_DISCOVER,
        "source": "discover",
        "label": "Discover latest",
        "configured": True,
        "empty_reason": "" if items else "empty",
        "empty_copy": "" if items else "Nothing new in books or audiobooks right now.",
        "beyond_error": beyond or None,
        "items": items,
    }


def _take_lane(future: Any, fallback: Callable[[], Dict[str, Any]], *, wait: float) -> Dict[str, Any]:
    try:
        return future.result(timeout=max(0.05, float(wait)))
    except FuturesTimeout:
        logger.info("New & noted lane exceeded %.1fs", wait)
        return fallback()
    except Exception as error:  # noqa: BLE001 — one lane must not drop the desk
        logger.info("New & noted lane failed: %s", error)
        return fallback()


def _bestsellers_for_desk(
    settings: Any,
    db: Any,
    *,
    preset: str,
    date: str,
    data_dir: Any,
    llm: Optional[LLMClient],
) -> Dict[str, Any]:
    """Name the bestseller list without sleeping through a process-wide cooldown."""
    if llm is None and seconds_until_llm_ready() > 1:
        probe = client_from_settings(settings, timeout=NOTE_LLM_TIMEOUT_S)
        if probe is not None:
            probe.close()
            return _empty_lane(
                LANE_BESTSELLERS,
                source="llm",
                label="Bestsellers",
                empty_reason="rate_limited",
                empty_copy=LLM_RATE_LIMIT_COPY,
                configured=True,
            )
    created: Optional[LLMClient] = None
    client = llm
    if client is None:
        created = client_from_settings(settings, timeout=NOTE_LLM_TIMEOUT_S)
        client = created
    try:
        return bestsellers_lane(
            settings,
            db,
            preset=preset,
            date=date,
            data_dir=data_dir,
            llm=client,
        )
    finally:
        if created is not None:
            created.close()


def noted_desk(
    settings: Any,
    db: Any,
    *,
    period: str = "daily",
    preset: str = "hardcover-fiction",
    date: str = "current",
    data_dir: Any = None,
    ol_transport: Optional[httpx.BaseTransport] = None,
    discover_transport: Optional[httpx.BaseTransport] = None,
    llm: Optional[LLMClient] = None,
) -> Dict[str, Any]:
    """One payload. A failed lane stays empty and the others still return."""
    slug_period = _text(period).lower() or "daily"
    if slug_period not in PERIODS:
        raise NotedError("Period must be daily or weekly")
    when = normalize_list_date(date)
    if not when:
        raise NotedError("Date must be YYYY-MM-DD or current")
    list_slug = normalize_list_name(preset) or "hardcover-fiction"
    started = time.monotonic()
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="noted")
    trending_future = pool.submit(trending_lane, slug_period, transport=ol_transport)
    discover_future = pool.submit(
        discover_lane, settings, transport=discover_transport, data_dir=data_dir
    )
    try:
        try:
            bestsellers = _bestsellers_for_desk(
                settings,
                db,
                preset=list_slug,
                date=when,
                data_dir=data_dir,
                llm=llm,
            )
        except Exception as error:  # noqa: BLE001 — bestseller failure must leave the other lanes up
            logger.info("Bestseller lane failed: %s", error)
            bestsellers = _empty_lane(
                LANE_BESTSELLERS,
                source="llm",
                label="Bestsellers",
                empty_reason="error",
                empty_copy="Curated bestseller lists are unavailable right now.",
                configured=True,
            )
        remaining = NOTE_LANE_WAIT_S - (time.monotonic() - started)
        trending = _take_lane(
            trending_future,
            lambda: _empty_lane(
                LANE_TRENDING,
                source="open_library",
                label="Open Library trending",
                empty_reason="unavailable",
                empty_copy="Open Library trending is unavailable right now.",
                configured=True,
            ),
            wait=remaining,
        )
        remaining = NOTE_LANE_WAIT_S - (time.monotonic() - started)
        discover = _take_lane(
            discover_future,
            lambda: _empty_lane(
                LANE_DISCOVER,
                source="discover",
                label="Discover latest",
                empty_reason="unavailable",
                empty_copy="Discover latest is unavailable right now.",
                configured=True,
            ),
            wait=remaining,
        )
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    lanes = [trending, bestsellers, discover]
    annotate_noted_lanes(db, lanes)
    return {
        "period": slug_period,
        "preset": list_slug,
        "date": when,
        "lanes": lanes,
    }


# Processed cache -----------------------------------------------------------
#
# The old desk above remains a small, independently useful feed adapter.  The
# routes below use this cache so changing a chip never starts another HTTP
# request and NYT's immutable dated lists are only read once.


def _today() -> str:
    return date.today().isoformat()


def _cache_rows(db: Any, *, source: str, list_name: str, published_date: str = "") -> List[Dict[str, Any]]:
    sql = "SELECT * FROM noted_cache WHERE source = ? AND list_name = ?"
    args: list[Any] = [source, list_name]
    if published_date:
        sql += " AND published_date = ?"
        args.append(published_date)
    sql += " ORDER BY rank IS NULL, rank, title COLLATE NOCASE, id"
    with db._connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [dict(row) for row in rows]


def _cache_upsert(db: Any, row: Mapping[str, Any]) -> None:
    now = time.time()
    isbn13 = canonical_isbn13(row.get("isbn13") or row.get("isbn") or "")
    asin = _text(row.get("asin"))
    candidate = {
        "title": _text(row.get("title")),
        "author": _text(row.get("author")),
        "kind": _text(row.get("kind")) or "book",
        "isbn13": isbn13,
        "asin": asin,
        "ol_work": _text(row.get("open_library_key")),
    }
    work_id = resolve_work(db, candidate)
    source_key = _text(row.get("source_key")) or isbn13 or asin or _text(row.get("open_library_key"))
    if not source_key:
        source_key = f"{candidate['title'].lower()}|{candidate['author'].lower()}"

    def write() -> None:
        with db._connect() as conn:
            conn.execute(
                """
                INSERT INTO noted_cache (
                    id, source, source_key, isbn13, asin, title, author, list_name,
                    published_date, work_id, kind, rank, cover, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, list_name, published_date, source_key) DO UPDATE SET
                    isbn13 = excluded.isbn13, asin = excluded.asin, title = excluded.title,
                    author = excluded.author, work_id = excluded.work_id, kind = excluded.kind,
                    rank = excluded.rank, cover = excluded.cover, updated_at = excluded.updated_at
                """,
                (
                    uuid.uuid4().hex,
                    _text(row.get("source")),
                    source_key,
                    isbn13 or None,
                    asin or None,
                    candidate["title"],
                    candidate["author"],
                    _text(row.get("list_name")),
                    _text(row.get("published_date")),
                    work_id,
                    candidate["kind"],
                    row.get("rank"),
                    _text(row.get("cover")),
                    now,
                    now,
                ),
            )

    db.run_write(write, label="noted_cache")


def _open_library_edition_isbn(
    work_key: str, *, transport: Optional[httpx.BaseTransport] = None
) -> str:
    """Resolve a work-only trending result to an edition ISBN before caching it."""
    key = _text(work_key)
    if not key:
        return ""
    path = key if key.startswith("/") else f"/works/{key}"
    with httpx.Client(transport=transport, timeout=8.0, follow_redirects=True) as client:
        response = client.get(f"https://openlibrary.org{path}/editions.json", params={"limit": 20})
        response.raise_for_status()
        payload = response.json()
    entries = payload.get("entries") if isinstance(payload, Mapping) else []
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, Mapping):
            isbn = _first_isbn(entry)
            if isbn:
                return isbn
    return ""


def _store_open_library(
    db: Any, period: str, *, transport: Optional[httpx.BaseTransport] = None, published_date: str = ""
) -> int:
    payload = fetch_open_library_trending(period, transport=transport)
    cards = parse_open_library_trending(payload)
    when = published_date or _today()
    for card in cards:
        isbn = card.get("isbn") or ""
        if not isbn and card.get("open_library_key"):
            try:
                isbn = _open_library_edition_isbn(card["open_library_key"], transport=transport)
            except (httpx.HTTPError, ValueError):
                logger.info("Open Library edition lookup failed for %s", card["open_library_key"])
        _cache_upsert(
            db,
            {
                **card,
                "source": "open_library",
                "source_key": card.get("open_library_key") or isbn,
                "isbn13": isbn,
                "list_name": period,
                "published_date": when,
            },
        )
    return len(cards)


def _store_discover(db: Any, settings: Any, *, data_dir: Any = None) -> int:
    lane = discover_lane(settings, data_dir=data_dir)
    when = _today()
    for card in lane.get("items") or []:
        _cache_upsert(
            db,
            {
                **card,
                "source": "discover",
                "source_key": "|".join(
                    (_text(card.get("category")), _text(card.get("isbn")), _text(card.get("title")), _text(card.get("author")))
                ),
                "list_name": "latest",
                "published_date": when,
            },
        )
    return len(lane.get("items") or [])


def refresh_nyt_list(
    db: Any,
    settings: Any,
    *,
    list_name: str,
    published_date: str = "current",
    data_dir: Any = None,
    transport: Optional[httpx.BaseTransport] = None,
) -> int:
    """Fetch a NYT list once when it has a fixed publication date."""
    slug = normalize_list_name(list_name)
    when = normalize_list_date(published_date)
    if not slug or not when:
        raise NotedError("Date must be YYYY-MM-DD or current")
    if when != "current" and _cache_rows(db, source="nyt", list_name=slug, published_date=when):
        return 0
    client = NytBooksClient(
        _text(getattr(settings, "nyt_books_api_key", "")),
        data_dir=data_dir,
        transport=transport,
    )
    try:
        payload = client.bestseller_list(slug, date=when)
    finally:
        client.close()
    actual_date = _text(payload.get("published_date")) or when
    if when == "current" and actual_date != "current" and _cache_rows(
        db, source="nyt", list_name=slug, published_date=actual_date
    ):
        return 0
    for book in payload.get("books") or []:
        _cache_upsert(
            db,
            {
                **book,
                "source": "nyt",
                "source_key": _text(book.get("isbn")) or f"{_text(book.get('title')).lower()}|{_text(book.get('author')).lower()}",
                "list_name": slug,
                "published_date": actual_date,
            },
        )
    return len(payload.get("books") or [])


def run_noted_refresh(
    db: Any,
    settings: Any,
    *,
    data_dir: Any = None,
    ol_transport: Optional[httpx.BaseTransport] = None,
    nyt_transport: Optional[httpx.BaseTransport] = None,
) -> Dict[str, int]:
    """Refresh mutable lists.  The poller may call this on its six-hour cadence."""
    result = {"open_library": 0, "nyt": 0, "discover": 0}
    for period in PERIODS:
        try:
            result["open_library"] += _store_open_library(db, period, transport=ol_transport)
        except (httpx.HTTPError, ValueError) as error:
            logger.info("Open Library %s refresh failed: %s", period, error)
    for row in default_list_names():
        try:
            result["nyt"] += refresh_nyt_list(
                db, settings, list_name=row["id"], data_dir=data_dir, transport=nyt_transport
            )
        except Exception as error:  # one unavailable category should not stop the desk
            logger.info("NYT %s refresh failed: %s", row["id"], error)
    try:
        result["discover"] = _store_discover(db, settings, data_dir=data_dir)
    except Exception as error:  # noqa: BLE001
        logger.info("Discover latest refresh failed: %s", error)
    return result


def _cached_cards(db: Any, rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    cards = [
        noted_card(
            title=_text(row.get("title")),
            author=_text(row.get("author")),
            isbn=_text(row.get("isbn13")),
            kind=_text(row.get("kind")) or "book",
            source=_text(row.get("source")),
            rank=row.get("rank"),
            cover=_text(row.get("cover")),
        )
        for row in rows
    ]
    annotate_noted_lanes(db, [{"items": cards}])
    return cards


def cached_noted_desk(db: Any, settings: Any, *, data_dir: Any = None) -> Dict[str, Any]:
    """Return all cached lanes in one response; the SPA switches locally."""
    if not _cache_rows(db, source="open_library", list_name="daily"):
        run_noted_refresh(db, settings, data_dir=data_dir)
    lanes: List[Dict[str, Any]] = []
    for period, label in (("daily", "Open Library daily"), ("weekly", "Open Library weekly")):
        rows = _cache_rows(db, source="open_library", list_name=period)
        lanes.append({"id": f"open-library-{period}", "label": label, "source": "open_library", "items": _cached_cards(db, rows)})
    for item in default_list_names():
        rows = _cache_rows(db, source="nyt", list_name=item["id"])
        lanes.append({"id": f"nyt-{item['id']}", "label": item["display_name"], "source": "nyt", "items": _cached_cards(db, rows)})
    rows = _cache_rows(db, source="discover", list_name="latest")
    lanes.append({"id": "discover-latest", "label": "Indexer latest", "source": "discover", "items": _cached_cards(db, rows)})
    return {"lanes": lanes, "lists": [{"id": lane["id"], "label": lane["label"]} for lane in lanes]}


def _week_dates(start: str, end: str) -> List[str]:
    begin = date.fromisoformat(start)
    finish = date.fromisoformat(end)
    if finish < begin:
        raise NotedError("End date must be after start date")
    if finish - begin > timedelta(days=190):
        raise NotedError("Choose six months or less")
    dates: List[str] = []
    while begin <= finish:
        dates.append(begin.isoformat())
        begin += timedelta(days=7)
    return dates


def noted_history(
    db: Any, settings: Any, *, list_name: str, start: str, end: str, data_dir: Any = None
) -> Dict[str, Any]:
    slug = normalize_list_name(list_name)
    if not slug:
        raise NotedError("Choose a New York Times category")
    weeks = _week_dates(start, end)
    for week in weeks:
        refresh_nyt_list(db, settings, list_name=slug, published_date=week, data_dir=data_dir)
    rows = _cache_rows(db, source="nyt", list_name=slug)
    rows = [row for row in rows if start <= _text(row.get("published_date")) <= end]
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = _text(row.get("isbn13")) or f"{_text(row.get('title')).lower()}|{_text(row.get('author')).lower()}"
        entry = grouped.setdefault(key, {**row, "weeks": []})
        entry["weeks"].append(_text(row.get("published_date")))
    index = ShelfIndex(db)
    items = []
    for row in grouped.values():
        book, audio = index.pair(row)
        items.append({**row, "weeks": sorted(set(row["weeks"])), "shelved": bool(book or audio)})
    return {"list_name": slug, "start": start, "end": end, "items": sorted(items, key=lambda item: item["title"].lower())}


def add_missing_noted_history(db: Any, items: Sequence[Mapping[str, Any]]) -> int:
    """Add only unshelved, not-already-wanted history titles."""
    index = ShelfIndex(db)
    added = 0
    for item in items:
        if index.of_kind(item, "book") or index.of_kind(item, "audiobook"):
            continue
        try:
            key = dedupe_key(
                kind="book",
                work_id="",
                title=_text(item.get("title")),
                author=_text(item.get("author")),
                isbn=_text(item.get("isbn13")),
            )
            if db.get_wanted_by_dedupe(key):
                continue
            add_wanted(
                db,
                {
                    "title": _text(item.get("title")),
                    "author": _text(item.get("author")),
                    "isbn": _text(item.get("isbn13")),
                    "kind": "book",
                },
            )
            added += 1
        except (AlreadyShelved, WantedError):
            continue
    return added
