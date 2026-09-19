"""Curated book lists via BYO LLM — match the shelves, request the gaps.

Primary source for Hall/Find bestsellers. Structured title/author JSON only;
ISBN kept only when the model returns a check-digit-valid value. Fail closed
when the LLM is not configured. Brief list+match cache under DATA_DIR.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import httpx

from librarian.audiobook_match import audiobook_find_fields, match_companion_audiobook
from librarian.identify import isbn_match_keys, tidy_title, validated_isbn
from librarian.llm import LLMClient, LLMError, client_from_settings, parse_json_object
from librarian.nyt_books import (
    DEFAULT_LIST_NAMES,
    match_local_work,
    normalize_list_date,
    normalize_list_name,
    public_list_name,
)

logger = logging.getLogger(__name__)

CACHE_DIR_NAME = "lists-cache"
CACHE_TTL_SECONDS = 2 * 60 * 60
_MAX_BOOKS = 40

LIST_PROMPT = """You return curated book lists for a private household library.
Return ONLY JSON with this shape:
{"books":[{"title":"...","author":"...","rank":1,"isbn":null}],"display_name":"...","published_date":""}
Rules:
- Include title and author for every book. Rank is optional (1-based).
- Never invent an ISBN. Set isbn to null unless you are certain of a real ISBN-10 or ISBN-13.
- Prefer well-known published lists (New York Times bestseller categories, etc.).
- If a date is given, return the list closest to that date; otherwise the most recent.
- At most 20 books. No commentary outside JSON.
"""

_MEMORY: Dict[str, Tuple[float, Any]] = {}


def list_presets() -> List[Dict[str, str]]:
    """Stable preset chips for the Bestsellers panel."""
    return [public_list_name(row) for row in DEFAULT_LIST_NAMES]


def parse_json_list_payload(raw: str) -> Dict[str, Any]:
    """Accept a JSON object or a bare books array from the model."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = parse_json_object(text)
        if not data:
            match = re.search(r"\[.*\]", text, re.S)
            if match:
                try:
                    data = json.loads(match.group(0))
                except json.JSONDecodeError:
                    data = {}
            else:
                data = {}
    if isinstance(data, list):
        return {"books": data, "display_name": "", "published_date": ""}
    if isinstance(data, dict):
        books = data.get("books")
        if not isinstance(books, list):
            books = data.get("items") if isinstance(data.get("items"), list) else []
        return {
            "books": books if isinstance(books, list) else [],
            "display_name": str(data.get("display_name") or data.get("list_name") or "").strip(),
            "published_date": str(data.get("published_date") or data.get("date") or "").strip(),
        }
    return {"books": [], "display_name": "", "published_date": ""}


def normalize_list_book(row: Mapping[str, Any], *, rank: int = 0, list_name: str = "") -> Optional[Dict[str, Any]]:
    """One list row — title+author required; ISBN only when validated."""
    if not isinstance(row, Mapping):
        return None
    title = tidy_title(str(row.get("title") or ""))
    author = tidy_title(str(row.get("author") or row.get("author_or_artist") or ""))
    if not title or not author:
        return None
    isbn = validated_isbn(str(row.get("isbn") or row.get("isbn13") or row.get("isbn10") or ""))
    isbns = isbn_match_keys(isbn) if isbn else []
    raw_rank = row.get("rank", rank)
    try:
        rank_i = int(raw_rank) if raw_rank is not None and str(raw_rank).strip() != "" else rank or None
    except (TypeError, ValueError):
        rank_i = rank or None
    return {
        "source": "llm",
        "kind": "book",
        "rank": rank_i,
        "title": title,
        "author": author,
        "isbn": isbn,
        "isbns": isbns,
        "description": str(row.get("description") or "").strip(),
        "publisher": str(row.get("publisher") or "").strip(),
        "cover": str(row.get("cover") or row.get("book_image") or "").strip(),
        "list_name": list_name,
    }


def normalize_list_books(rows: Sequence[Any], *, list_name: str = "") -> List[Dict[str, Any]]:
    books: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            continue
        book = normalize_list_book(row, rank=index, list_name=list_name)
        if book is None:
            continue
        key = f"{book['title'].lower()}|{book['author'].lower()}|{book.get('isbn') or ''}"
        if key in seen:
            continue
        seen.add(key)
        books.append(book)
        if len(books) >= _MAX_BOOKS:
            break
    return books


def preset_prompt(*, preset: str, date: str = "current", query: str = "") -> str:
    slug = normalize_list_name(preset) or "hardcover-fiction"
    when = normalize_list_date(date) or "current"
    display = next(
        (row["display_name"] for row in list_presets() if row["list_name_encoded"] == slug),
        slug.replace("-", " ").title(),
    )
    custom = str(query or "").strip()
    if custom:
        return (
            f"Curated list request: {custom}\n"
            f"Prefer books (fiction/nonfiction as appropriate). "
            f"Date hint: {when}."
        )
    if when == "current":
        return (
            f"Return the current New York Times bestseller list for category "
            f'"{display}" (slug: {slug}), most recent published list.'
        )
    return (
        f"Return the New York Times bestseller list for category "
        f'"{display}" (slug: {slug}) closest to date {when}.'
    )


def cache_dir(data_dir: Path) -> Path:
    return Path(data_dir) / CACHE_DIR_NAME


def clear_lists_memory_cache() -> None:
    _MEMORY.clear()


def _cache_path(data_dir: Path, name: str) -> Path:
    root = cache_dir(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", name)[:180]
    return root / f"{safe}.json"


def _read_cache(data_dir: Optional[Path], key: str, ttl: float) -> Optional[Any]:
    now = time.time()
    mem = _MEMORY.get(key)
    if mem and now - mem[0] <= ttl:
        return mem[1]
    if data_dir is None:
        return None
    path = _cache_path(data_dir, key)
    if not path.is_file():
        return None
    try:
        age = now - path.stat().st_mtime
        if age > ttl:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    _MEMORY[key] = (now, payload)
    return payload


def _write_cache(data_dir: Optional[Path], key: str, payload: Any) -> None:
    _MEMORY[key] = (time.time(), payload)
    if data_dir is None:
        return
    try:
        _cache_path(data_dir, key).write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


def fetch_llm_list(
    client: LLMClient,
    *,
    preset: str = "hardcover-fiction",
    date: str = "current",
    query: str = "",
    data_dir: Optional[Path] = None,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Ask the BYO LLM for a curated list. Raises LLMError on transport failure."""
    slug = normalize_list_name(preset) or "hardcover-fiction"
    when = normalize_list_date(date) or "current"
    custom = str(query or "").strip()
    cache_key = f"llm:{when}:{slug}:{custom[:80]}"
    if use_cache:
        cached = _read_cache(data_dir, cache_key, CACHE_TTL_SECONDS)
        if isinstance(cached, dict) and isinstance(cached.get("books"), list):
            return cached

    user = preset_prompt(preset=slug, date=when, query=custom)
    raw = client.chat_raw(system=LIST_PROMPT, user=user, temperature=0.2)
    parsed = parse_json_list_payload(raw)
    books = normalize_list_books(parsed.get("books") or [], list_name=slug)
    display = str(parsed.get("display_name") or "").strip()
    if not display:
        display = next(
            (row["display_name"] for row in list_presets() if row["list_name_encoded"] == slug),
            slug.replace("-", " ").title(),
        )
    out = {
        "configured": True,
        "source": "llm",
        "list_name": slug,
        "date": when,
        "query": custom,
        "published_date": str(parsed.get("published_date") or "").strip(),
        "display_name": display,
        "books": books,
        "empty_reason": "" if books else "empty_list",
    }
    if books:
        _write_cache(data_dir, cache_key, out)
    return out


def _shelved_stub(row: Mapping[str, Any], *, kind: str = "book") -> Dict[str, Any]:
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "author": row.get("author"),
        "kind": kind,
        "has_cover": bool(row.get("cover_path") or row.get("has_cover")),
    }


def _catalog_candidates(db: Any, book: Mapping[str, Any], *, kind: str) -> List[Dict[str, Any]]:
    query = " ".join(
        part for part in (str(book.get("author") or "").strip(), str(book.get("title") or "").strip()) if part
    )
    candidates: List[Dict[str, Any]] = []
    isbn = str(book.get("isbn") or "").strip()
    if isbn:
        candidates.extend(db.search_works(isbn, limit=8, kind=kind))
    if query:
        candidates.extend(db.search_works(query, limit=12, kind=kind))
    seen: set[str] = set()
    uniq: List[Dict[str, Any]] = []
    for row in candidates:
        wid = str(row.get("id") or "")
        if not wid or wid in seen:
            continue
        seen.add(wid)
        uniq.append(row)
    return uniq


def match_books_to_catalog(db: Any, books: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Split a list into shelved vs missing. Also notes companion audiobooks on the shelves."""
    shelved: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    annotated: List[Dict[str, Any]] = []
    for book in books:
        local = match_local_work(book, _catalog_candidates(db, book, kind="book"))
        audio_candidates = _catalog_candidates(db, book, kind="audiobook")
        # Companion matcher expects kind=book on the probe row.
        probe = {**dict(book), "kind": "book"}
        audio = match_companion_audiobook(probe, audio_candidates)
        if audio is None:
            audio = match_local_work(book, audio_candidates)
        entry = dict(book)
        entry["shelved"] = _shelved_stub(local, kind="book") if local else None
        entry["shelved_audiobook"] = _shelved_stub(audio, kind="audiobook") if audio else None
        entry["audiobook_find"] = audiobook_find_fields(probe)
        if local:
            shelved.append(entry)
        else:
            missing.append(entry)
        annotated.append(entry)
    return {"books": annotated, "shelved": shelved, "missing": missing}


def public_beyond_hit(hit: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """Safe indexer hit fields for the Bestsellers chase UI. Never invents ISBN."""
    if not hit or not isinstance(hit, Mapping):
        return None
    isbn = validated_isbn(str(hit.get("isbn") or ""))
    return {
        "guid": str(hit.get("guid") or "").strip(),
        "title": str(hit.get("title") or hit.get("book_title") or "").strip(),
        "book_title": str(hit.get("book_title") or "").strip(),
        "author": str(hit.get("author") or "").strip(),
        "isbn": isbn,
        "kind": str(hit.get("kind") or "").strip(),
        "size": hit.get("size"),
        "cover": str(hit.get("cover") or "").strip(),
        "download_url": str(hit.get("download_url") or "").strip(),
        "category": hit.get("category"),
        "category_name": str(hit.get("category_name") or "").strip(),
        "host_id": str(hit.get("host_id") or "").strip(),
        "host_name": str(hit.get("host_name") or "").strip(),
        "poster": str(hit.get("poster") or "").strip(),
    }


def chase_missing_item(
    settings: Any,
    book: Mapping[str, Any],
    *,
    transport: Optional[httpx.BaseTransport] = None,
) -> Dict[str, Any]:
    """Find beyond for book and audiobook. Does not enqueue — Confirm still required."""
    from librarian.indexers.hosts import search_beyond

    title = str(book.get("title") or "").strip()
    author = str(book.get("author") or "").strip()
    isbn = validated_isbn(str(book.get("isbn") or ""))
    q = " ".join(part for part in (author, title) if part).strip() or title
    sought_book = {
        "q": q,
        "kind": "book",
        "title": title,
        "author": author,
        "isbn": isbn,
    }
    sought_audio = {
        "q": q,
        "kind": "audiobook",
        "title": title,
        "author": author,
        "isbn": isbn,
    }
    book_hits, book_error = search_beyond(settings, transport=transport, **sought_book)
    audio_hits, audio_error = search_beyond(settings, transport=transport, **sought_audio)
    book_hit = public_beyond_hit(book_hits[0] if book_hits else None)
    audio_hit = public_beyond_hit(audio_hits[0] if audio_hits else None)
    if book_hit and not book_hit.get("kind"):
        book_hit["kind"] = "book"
    if audio_hit and not audio_hit.get("kind"):
        audio_hit["kind"] = "audiobook"
    return {
        "title": title,
        "author": author,
        "isbn": isbn,
        "sought": {"book": sought_book, "audiobook": sought_audio},
        "book_hit": book_hit,
        "audiobook_hit": audio_hit,
        "book_error": book_error,
        "audiobook_error": audio_error,
        "audiobook_available": bool(audio_hit and audio_hit.get("guid")),
    }


def chase_missing_items(
    settings: Any,
    items: Sequence[Mapping[str, Any]],
    *,
    transport: Optional[httpx.BaseTransport] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Chase several missing list rows. Caps work; never auto-queues."""
    out: List[Dict[str, Any]] = []
    for row in items[: max(0, int(limit))]:
        if not isinstance(row, Mapping):
            continue
        if not str(row.get("title") or "").strip() or not str(row.get("author") or "").strip():
            continue
        out.append(chase_missing_item(settings, row, transport=transport))
    return out


def curated_list_payload(
    settings: Any,
    db: Any,
    *,
    preset: str = "hardcover-fiction",
    date: str = "current",
    query: str = "",
    data_dir: Optional[Path] = None,
    transport: Optional[httpx.BaseTransport] = None,
    llm: Optional[LLMClient] = None,
) -> Dict[str, Any]:
    """Fail-closed list+match for the Bestsellers panel."""
    slug = normalize_list_name(preset) or "hardcover-fiction"
    when = normalize_list_date(date) or "current"
    empty_base = {
        "configured": False,
        "source": "llm",
        "list_name": slug,
        "date": when,
        "query": str(query or "").strip(),
        "published_date": "",
        "display_name": next(
            (row["display_name"] for row in list_presets() if row["list_name_encoded"] == slug),
            slug.replace("-", " ").title(),
        ),
        "books": [],
        "shelved": [],
        "missing": [],
        "presets": list_presets(),
        "empty_reason": "missing_llm",
        "empty_copy": "Add a BYO LLM in Settings to load curated bestseller lists.",
    }
    own_client = False
    client = llm
    if client is None:
        client = client_from_settings(settings, transport=transport)
        own_client = client is not None
    if client is None:
        return empty_base
    try:
        payload = fetch_llm_list(
            client,
            preset=slug,
            date=when,
            query=query,
            data_dir=data_dir,
        )
    except LLMError as error:
        logger.info("LLM curated list failed: %s", error)
        return {
            **empty_base,
            "configured": True,
            "empty_reason": "error",
            "empty_copy": str(error) or "The reading room could not reach the LLM.",
        }
    finally:
        if own_client and client is not None:
            client.close()

    matched = match_books_to_catalog(db, payload.get("books") or [])
    empty_reason = str(payload.get("empty_reason") or "")
    empty_copy = ""
    if empty_reason == "empty_list":
        empty_copy = "That list came back empty for this date."
    elif not matched["books"] and not empty_reason:
        empty_copy = "No titles on this list yet."
    return {
        **payload,
        **matched,
        "configured": True,
        "presets": list_presets(),
        "empty_copy": empty_copy,
        "empty_reason": empty_reason,
    }
