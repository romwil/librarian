"""New York Times Books API bestseller lists.

Key lives in settings (`nyt_books_api_key`) or `NYT_BOOKS_API_KEY`. Fail closed
with no key — never invents list rows. Messages must never include the key.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import httpx

from librarian.covers import DEFAULT_USER_AGENT
from librarian.identify import isbn_match_keys

NYT_BOOKS_API = "https://api.nytimes.com/svc/books/v3"
CACHE_DIR_NAME = "nyt-cache"
# Current lists change weekly; historical dates are stable.
CACHE_TTL_CURRENT_SECONDS = 6 * 60 * 60
CACHE_TTL_DATED_SECONDS = 7 * 24 * 60 * 60
CACHE_TTL_NAMES_SECONDS = 24 * 60 * 60

# Curated defaults when /lists/names is unavailable (no key / cache miss).
DEFAULT_LIST_NAMES: Tuple[Dict[str, str], ...] = (
    {"list_name_encoded": "hardcover-fiction", "display_name": "Hardcover Fiction"},
    {"list_name_encoded": "hardcover-nonfiction", "display_name": "Hardcover Nonfiction"},
    {
        "list_name_encoded": "combined-print-and-e-book-fiction",
        "display_name": "Combined Print & E-Book Fiction",
    },
    {
        "list_name_encoded": "combined-print-and-e-book-nonfiction",
        "display_name": "Combined Print & E-Book Nonfiction",
    },
    {"list_name_encoded": "paperback-nonfiction", "display_name": "Paperback Nonfiction"},
    {"list_name_encoded": "young-adult-hardcover", "display_name": "Young Adult Hardcover"},
    {"list_name_encoded": "childrens-middle-grade-hardcover", "display_name": "Children’s Middle Grade"},
)

_LIST_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MEMORY: Dict[str, Tuple[float, Any]] = {}


class NytBooksError(RuntimeError):
    """NYT Books HTTP failure. Messages must never include the API key."""


def cache_dir(data_dir: Path) -> Path:
    return Path(data_dir) / CACHE_DIR_NAME


def normalize_list_name(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw or ".." in raw or "/" in raw or "\\" in raw:
        return ""
    raw = raw.replace("_", "-").replace(" ", "-")
    raw = re.sub(r"[^a-z0-9-]+", "", raw)
    raw = re.sub(r"-{2,}", "-", raw).strip("-")
    return raw if _LIST_SLUG.match(raw) else ""


def normalize_list_date(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text or text == "current":
        return "current"
    if _DATE.match(text):
        return text
    return ""


def _title_case(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.isupper() and len(text) > 3:
        return text.title()
    return text


def _norm_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def public_list_name(row: Mapping[str, Any]) -> Dict[str, str]:
    encoded = normalize_list_name(
        str(row.get("list_name_encoded") or row.get("list_name") or row.get("id") or "")
    )
    display = str(row.get("display_name") or row.get("list_name") or encoded).strip()
    return {
        "id": encoded,
        "list_name_encoded": encoded,
        "display_name": display or encoded,
        "updated": str(row.get("updated") or "").strip(),
    }


def public_book(row: Mapping[str, Any], *, list_name: str = "") -> Dict[str, Any]:
    """Normalize one NYT book row for Search/Find deep links."""
    isbns = []
    for item in row.get("isbns") or []:
        if isinstance(item, dict):
            isbns.extend(isbn_match_keys(str(item.get("isbn13") or ""), str(item.get("isbn10") or "")))
    primary = isbn_match_keys(str(row.get("primary_isbn13") or ""), str(row.get("primary_isbn10") or ""))
    for key in primary:
        if key not in isbns:
            isbns.insert(0, key)
    isbn = isbns[0] if isbns else ""
    title = _title_case(row.get("title"))
    author = str(row.get("author") or "").strip()
    rank = row.get("rank")
    try:
        rank_i = int(rank) if rank is not None and str(rank).strip() != "" else None
    except (TypeError, ValueError):
        rank_i = None
    return {
        "source": "nyt",
        "kind": "book",
        "rank": rank_i,
        "title": title,
        "author": author,
        "isbn": isbn,
        "isbns": isbns,
        "description": str(row.get("description") or "").strip(),
        "publisher": str(row.get("publisher") or "").strip(),
        "cover": str(row.get("book_image") or "").strip(),
        "weeks_on_list": row.get("weeks_on_list"),
        "list_name": list_name,
        "nyt_uri": str(row.get("book_uri") or "").strip(),
    }


class NytBooksClient:
    def __init__(
        self,
        api_key: str,
        *,
        url: str = NYT_BOOKS_API,
        transport: Optional[httpx.BaseTransport] = None,
        client: Optional[httpx.Client] = None,
        timeout: float = 12.0,
        data_dir: Optional[Path] = None,
        cache_ttl_current: float = CACHE_TTL_CURRENT_SECONDS,
        cache_ttl_dated: float = CACHE_TTL_DATED_SECONDS,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.url = str(url or NYT_BOOKS_API).rstrip("/") or NYT_BOOKS_API
        self._own = client is None
        self._client = client or httpx.Client(
            timeout=timeout, transport=transport, follow_redirects=True
        )
        self.data_dir = Path(data_dir) if data_dir is not None else None
        self.cache_ttl_current = float(cache_ttl_current)
        self.cache_ttl_dated = float(cache_ttl_dated)

    def close(self) -> None:
        if self._own:
            self._client.close()

    def configured(self) -> bool:
        return bool(self.api_key)

    def _cache_path(self, name: str) -> Optional[Path]:
        if self.data_dir is None:
            return None
        root = cache_dir(self.data_dir)
        root.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", name)[:180]
        return root / f"{safe}.json"

    def _read_cache(self, key: str, ttl: float) -> Optional[Any]:
        now = time.time()
        mem = _MEMORY.get(key)
        if mem and now - mem[0] <= ttl:
            return mem[1]
        path = self._cache_path(key)
        if path is None or not path.is_file():
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

    def _write_cache(self, key: str, payload: Any) -> None:
        _MEMORY[key] = (time.time(), payload)
        path = self._cache_path(key)
        if path is None:
            return
        try:
            path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass

    def _get(self, path: str, params: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
        if not self.api_key:
            return {}
        query = {"api-key": self.api_key, **dict(params or {})}
        try:
            response = self._client.get(
                f"{self.url}{path}",
                params=query,
                headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"},
            )
        except httpx.HTTPError as error:
            raise NytBooksError("New York Times Books could not be reached") from error
        if response.status_code == 401:
            raise NytBooksError("New York Times Books key was refused")
        if response.status_code == 429:
            raise NytBooksError("New York Times Books rate-limited this lookup")
        if response.status_code == 404:
            raise NytBooksError("That bestseller list was not found")
        if response.status_code >= 400:
            raise NytBooksError(f"New York Times Books HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as error:
            raise NytBooksError("New York Times Books returned non-JSON") from error
        return payload if isinstance(payload, dict) else {}

    def list_names(self, *, use_cache: bool = True) -> List[Dict[str, str]]:
        if not self.configured():
            return []
        cache_key = "names"
        if use_cache:
            cached = self._read_cache(cache_key, CACHE_TTL_NAMES_SECONDS)
            if isinstance(cached, list):
                return [public_list_name(row) for row in cached if isinstance(row, dict)]
        payload = self._get("/lists/names.json")
        rows = payload.get("results") if isinstance(payload.get("results"), list) else []
        names = [public_list_name(row) for row in rows if isinstance(row, dict) and public_list_name(row)["id"]]
        if names:
            self._write_cache(cache_key, names)
        return names

    def bestseller_list(
        self,
        list_name: str,
        *,
        date: str = "current",
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """Fetch one list. Empty payload when unconfigured; raises on HTTP errors."""
        slug = normalize_list_name(list_name)
        when = normalize_list_date(date)
        if not slug or not when:
            raise NytBooksError("Unknown bestseller list or date")
        if not self.configured():
            return {
                "configured": False,
                "list_name": slug,
                "date": when,
                "published_date": "",
                "display_name": slug,
                "books": [],
                "empty_reason": "missing_key",
            }
        cache_key = f"list:{when}:{slug}"
        ttl = self.cache_ttl_current if when == "current" else self.cache_ttl_dated
        if use_cache:
            cached = self._read_cache(cache_key, ttl)
            if isinstance(cached, dict) and isinstance(cached.get("books"), list):
                return cached
        payload = self._get(f"/lists/{when}/{slug}.json")
        results = payload.get("results") if isinstance(payload.get("results"), dict) else {}
        books_raw = results.get("books") if isinstance(results.get("books"), list) else []
        display = str(results.get("display_name") or results.get("list_name") or slug).strip()
        books = [public_book(row, list_name=slug) for row in books_raw if isinstance(row, dict)]
        out = {
            "configured": True,
            "list_name": slug,
            "date": when,
            "published_date": str(results.get("published_date") or "").strip(),
            "bestsellers_date": str(results.get("bestsellers_date") or "").strip(),
            "display_name": display,
            "books": books,
            "empty_reason": "" if books else "empty_list",
        }
        self._write_cache(cache_key, out)
        return out


def default_list_names() -> List[Dict[str, str]]:
    return [public_list_name(row) for row in DEFAULT_LIST_NAMES]


def match_local_work(book: Mapping[str, Any], candidates: List[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """ISBN first, then exact title+author. Fail closed — no title-only guesses."""
    want_isbn = set(isbn_match_keys(*(book.get("isbns") or []), str(book.get("isbn") or "")))
    if want_isbn:
        for row in candidates:
            if want_isbn.intersection(isbn_match_keys(str(row.get("isbn") or ""))):
                return dict(row)
    title_key = _norm_name(book.get("title"))
    author_key = _norm_name(book.get("author"))
    if not title_key or not author_key:
        return None
    for row in candidates:
        if _norm_name(row.get("title")) != title_key:
            continue
        if _norm_name(row.get("author")) == author_key:
            return dict(row)
    return None


def clear_nyt_memory_cache() -> None:
    _MEMORY.clear()
