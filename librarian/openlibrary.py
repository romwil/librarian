"""Open Library ISBN and title lookup. Never invents an ISBN."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlencode

import httpx

from librarian.covers import DEFAULT_USER_AGENT, OPENLIB_ISBN_COVER
from librarian.identify import extract_isbn

OPENLIB_ISBN = "https://openlibrary.org/isbn/{isbn}.json"
OPENLIB_SEARCH = "https://openlibrary.org/search.json"
OPENLIB_COVER_ID = "https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
_SERIES_POS = re.compile(
    r"(?:#\s*|,\s*#\s*|,\s*book\s+|,\s*vol(?:ume)?\.?\s+|\s+\()\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _year_from(value: Any) -> Optional[int]:
    if isinstance(value, int) and 1000 <= value <= 2100:
        return value
    match = re.search(r"(19\d{2}|20\d{2})", str(value or ""))
    if match:
        return int(match.group(1))
    return None


def _description(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("value") or value.get("text") or "").strip()
    return str(value or "").strip()


def _series_name(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        for item in value:
            name = _series_name(item)
            if name:
                return name
    if isinstance(value, dict):
        return str(value.get("name") or value.get("title") or "").strip()
    return ""


def _title_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _sort_index(value: str) -> Tuple[int, str]:
    if re.fullmatch(r"\d+", value):
        return (int(value), "")
    match = re.fullmatch(r"(\d+)\.(\d+)", value)
    if match:
        return (int(match.group(1)), match.group(2))
    return (10**9, value)


def _series_index_from_label(label: str, series_name: str) -> str:
    text = str(label or "").strip()
    if not text:
        return ""
    match = _SERIES_POS.search(text)
    if match:
        index = match.group(1)
        if index.endswith(".0"):
            index = index[:-2]
        return index
    return ""


def _doc_in_series(doc: Mapping[str, Any], series_name: str) -> bool:
    want = _title_key(series_name)
    if not want:
        return False
    raw = doc.get("series")
    labels: List[str] = []
    if isinstance(raw, list):
        labels = [str(item) for item in raw]
    elif raw:
        labels = [str(raw)]
    if not labels:
        title = _title_key(doc.get("title"))
        return bool(title) and want in title
    for label in labels:
        key = _title_key(_SERIES_POS.sub("", label))
        if want == key or want in key or key in want:
            return True
    return False


def _volume_from_search_doc(doc: Mapping[str, Any], series_name: str) -> Dict[str, Any]:
    labels = doc.get("series") if isinstance(doc.get("series"), list) else [doc.get("series")]
    index = ""
    for label in labels:
        index = _series_index_from_label(str(label or ""), series_name)
        if index:
            break
    title = str(doc.get("title") or "").strip()
    authors = doc.get("author_name") or []
    author = authors[0] if isinstance(authors, list) and authors else ""
    year = _year_from(doc.get("first_publish_year"))
    isbn = ""
    raw_isbn = doc.get("isbn")
    if isinstance(raw_isbn, list) and raw_isbn:
        isbn = extract_isbn(str(raw_isbn[0]))
    elif raw_isbn:
        isbn = extract_isbn(str(raw_isbn))
    out: Dict[str, Any] = {
        "title": title or f"{series_name} {index}".strip(),
        "series_name": series_name,
        "series_index": index,
        "author": str(author or "").strip(),
        "source": "openlibrary",
    }
    if year:
        out["year"] = year
    if isbn:
        out["isbn"] = isbn
    return out


def _cover_url(edition: Mapping[str, Any], isbn: str = "") -> str:
    covers = edition.get("covers")
    if isinstance(covers, list) and covers:
        cover_id = covers[0]
        if isinstance(cover_id, int) or str(cover_id).isdigit():
            return OPENLIB_COVER_ID.format(cover_id=cover_id)
    cover = edition.get("cover")
    if isinstance(cover, dict):
        for key in ("large", "medium", "small"):
            url = str(cover.get(key) or "").strip()
            if url.startswith("http"):
                return url
    digits = extract_isbn(isbn) or extract_isbn(str((edition.get("isbn_13") or [""])[0] if isinstance(edition.get("isbn_13"), list) else edition.get("isbn_13") or ""))
    if digits:
        return OPENLIB_ISBN_COVER.format(isbn=digits)
    return ""


class OpenLibraryClient:
    def __init__(
        self,
        *,
        transport: Optional[httpx.BaseTransport] = None,
        client: Optional[httpx.Client] = None,
        timeout: float = 20.0,
    ) -> None:
        self._own = client is None
        self._client = client or httpx.Client(
            timeout=timeout, transport=transport, follow_redirects=True
        )

    def close(self) -> None:
        if self._own:
            self._client.close()

    def _get_json(self, url: str) -> Dict[str, Any]:
        try:
            response = self._client.get(
                url,
                headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"},
            )
        except httpx.HTTPError:
            return {}
        if response.status_code >= 400:
            return {}
        try:
            payload = response.json()
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _work_payload(self, work_key: str) -> Dict[str, Any]:
        key = str(work_key or "").strip()
        if not key:
            return {}
        if not key.startswith("/"):
            key = f"/works/{key}"
        return self._get_json(f"https://openlibrary.org{key}.json")

    def lookup_by_isbn(self, isbn: str) -> Dict[str, Any]:
        digits = extract_isbn(isbn)
        if not digits:
            return {}
        edition = self._get_json(OPENLIB_ISBN.format(isbn=digits))
        if not edition:
            return {}
        work: Dict[str, Any] = {}
        works = edition.get("works")
        if isinstance(works, list) and works and isinstance(works[0], dict):
            work = self._work_payload(str(works[0].get("key") or ""))
        description = _description(work.get("description") or edition.get("description"))
        year = _year_from(edition.get("publish_date") or work.get("first_publish_date"))
        series = _series_name(edition.get("series") or work.get("series"))
        authors = edition.get("authors") or work.get("authors") or []
        author = ""
        if isinstance(authors, list) and authors:
            first = authors[0]
            if isinstance(first, dict):
                author = str(first.get("name") or "").strip()
        out: Dict[str, Any] = {
            "title": str(edition.get("title") or work.get("title") or "").strip(),
            "author": author,
            "description": description,
            "cover_url": _cover_url(edition, digits),
            "source": "openlibrary",
        }
        if year:
            out["year"] = year
        if series:
            out["series_name"] = series
        return out

    def lookup_by_title(self, title: str, author: str = "") -> Dict[str, Any]:
        name = str(title or "").strip()
        if not name:
            return {}
        params = {"title": name, "limit": "1"}
        if str(author or "").strip():
            params["author"] = str(author).strip()
        payload = self._get_json(f"{OPENLIB_SEARCH}?{urlencode(params)}")
        docs = payload.get("docs") if isinstance(payload.get("docs"), list) else []
        if not docs or not isinstance(docs[0], dict):
            return {}
        doc = docs[0]
        work = self._work_payload(str(doc.get("key") or ""))
        description = _description(work.get("description"))
        year = _year_from(doc.get("first_publish_year") or work.get("first_publish_date"))
        cover_id = doc.get("cover_i")
        cover = ""
        if isinstance(cover_id, int) or str(cover_id or "").isdigit():
            cover = OPENLIB_COVER_ID.format(cover_id=cover_id)
        authors = doc.get("author_name") or []
        author_name = authors[0] if isinstance(authors, list) and authors else str(author or "")
        series = ""
        series_raw = doc.get("series")
        if isinstance(series_raw, list) and series_raw:
            series = str(series_raw[0]).strip()
        series = series or _series_name(work.get("series"))
        out: Dict[str, Any] = {
            "title": str(doc.get("title") or work.get("title") or name).strip(),
            "author": str(author_name or "").strip(),
            "description": description,
            "cover_url": cover,
            "source": "openlibrary",
        }
        if year:
            out["year"] = year
        if series:
            out["series_name"] = series
        # Title search may include ISBNs on the hit — we deliberately do not copy them.
        return out

    def series_volumes(self, series_name: str) -> List[Dict[str, Any]]:
        """Expected volumes for a series. No invented ISBNs; only catalog digits if present."""
        name = str(series_name or "").strip()
        if not name:
            return []
        payload = self._get_json(
            f"{OPENLIB_SEARCH}?{urlencode({'q': f'series:\"{name}\"', 'limit': '50'})}"
        )
        docs = payload.get("docs") if isinstance(payload.get("docs"), list) else []
        if not docs:
            payload = self._get_json(
                f"{OPENLIB_SEARCH}?{urlencode({'q': name, 'limit': '50'})}"
            )
            docs = payload.get("docs") if isinstance(payload.get("docs"), list) else []
        volumes: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            if not _doc_in_series(doc, name):
                continue
            volume = _volume_from_search_doc(doc, name)
            key = volume.get("series_index") or _title_key(volume.get("title"))
            if not key or key in seen:
                continue
            seen.add(str(key))
            volumes.append(volume)
        volumes.sort(key=lambda row: _sort_index(str(row.get("series_index") or "")))
        return volumes
