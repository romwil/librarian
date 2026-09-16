"""Hardcover GraphQL lookups. Token stays in settings. Never invents an ISBN."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional

import httpx

from librarian.covers import DEFAULT_USER_AGENT
from librarian.identify import extract_isbn, isbn10_to_isbn13, isbn13_to_isbn10

HARDCOVER_GRAPHQL = "https://api.hardcover.app/v1/graphql"

EDITION_BY_ISBN13 = """
query EditionByIsbn13($isbn: String!) {
  editions(where: {isbn_13: {_eq: $isbn}}, limit: 1) {
    isbn_13
    isbn_10
    release_date
    cached_image
    book {
      title
      description
      release_year
      cached_image
      cached_featured_series
    }
  }
}
"""

EDITION_BY_ISBN10 = """
query EditionByIsbn10($isbn: String!) {
  editions(where: {isbn_10: {_eq: $isbn}}, limit: 1) {
    isbn_13
    isbn_10
    release_date
    cached_image
    book {
      title
      description
      release_year
      cached_image
      cached_featured_series
    }
  }
}
"""

BOOK_SEARCH = """
query BookSearch($query: String!) {
  search(query: $query, query_type: "Book", per_page: 1, page: 1) {
    results
  }
}
"""

SERIES_SEARCH = """
query SeriesSearch($query: String!) {
  search(query: $query, query_type: "Series", per_page: 1, page: 1) {
    results
  }
}
"""

SERIES_BODY = """
    id
    name
    author { name }
    book_series(
      distinct_on: position
      order_by: [{position: asc}, {book: {users_count: desc}}]
      where: {
        compilation: {_eq: false}
        book: {canonical_id: {_is_null: true}, is_partial_book: {_eq: false}}
      }
    ) {
      position
      book { id title release_year }
    }
"""

SERIES_BY_NAME = f"""
query SeriesByName($name: String!) {{
  series(where: {{name: {{_eq: $name}}, canonical_id: {{_is_null: true}}, books_count: {{_gt: 0}}}}, limit: 1) {{
    {SERIES_BODY}
  }}
}}
"""

SERIES_BY_PK = f"""
query SeriesByPk($id: Int!) {{
  series_by_pk(id: $id) {{
    {SERIES_BODY}
  }}
}}
"""

SERIES_BY_SLUG = f"""
query SeriesBySlug($slug: String!) {{
  series(where: {{slug: {{_eq: $slug}}}}, limit: 1) {{
    {SERIES_BODY}
  }}
}}
"""


class HardcoverError(RuntimeError):
    """Hardcover HTTP or GraphQL failure. Messages must never include the token."""


def _authorization(token: str) -> str:
    raw = str(token or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("bearer "):
        return raw
    return f"Bearer {raw}"


def _image_url(value: Any) -> str:
    if isinstance(value, str) and value.startswith("http"):
        return value.strip()
    if isinstance(value, dict):
        for key in ("url", "image", "large", "medium"):
            found = value.get(key)
            if isinstance(found, str) and found.startswith("http"):
                return found.strip()
            nested = _image_url(found) if isinstance(found, dict) else ""
            if nested:
                return nested
    return ""


def _series_fields(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    series = value.get("series") if isinstance(value.get("series"), dict) else value
    name = str(series.get("name") or series.get("title") or value.get("name") or "").strip()
    position = value.get("position")
    if position is None:
        position = value.get("featured_series_position") or series.get("position")
    index = str(position).strip() if position not in (None, "") else ""
    if index.endswith(".0"):
        index = index[:-2]
    out: Dict[str, str] = {}
    if name:
        out["series_name"] = name
    if index:
        out["series_index"] = index
    return out


def _year_from(value: Any) -> Optional[int]:
    if isinstance(value, int) and 1000 <= value <= 2100:
        return value
    text = str(value or "")
    digits = "".join(ch for ch in text[:4] if ch.isdigit())
    if len(digits) == 4:
        year = int(digits)
        if 1000 <= year <= 2100:
            return year
    return None


def _strip_html(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def enrichment_from_edition(edition: Mapping[str, Any]) -> Dict[str, Any]:
    book = edition.get("book") if isinstance(edition.get("book"), dict) else {}
    description = _strip_html(str(book.get("description") or edition.get("description") or ""))
    year = _year_from(book.get("release_year")) or _year_from(edition.get("release_date"))
    cover = _image_url(book.get("cached_image")) or _image_url(edition.get("cached_image"))
    series = _series_fields(book.get("cached_featured_series"))
    out: Dict[str, Any] = {
        "title": str(book.get("title") or edition.get("title") or "").strip(),
        "description": description,
        "cover_url": cover,
        "source": "hardcover",
    }
    if year:
        out["year"] = year
    out.update(series)
    return out


def enrichment_from_search_hit(hit: Mapping[str, Any]) -> Dict[str, Any]:
    description = _strip_html(str(hit.get("description") or ""))
    year = _year_from(hit.get("release_year") or hit.get("release_date"))
    cover = _image_url(hit.get("image") or hit.get("cached_image") or hit.get("cover"))
    series = _series_fields(hit.get("featured_series") or hit.get("cached_featured_series") or {})
    out: Dict[str, Any] = {
        "title": str(hit.get("title") or "").strip(),
        "description": description,
        "cover_url": cover,
        "source": "hardcover",
    }
    if year:
        out["year"] = year
    out.update(series)
    return out


def _unwrap_hit(hit: Any) -> Dict[str, Any]:
    if not isinstance(hit, dict):
        return {}
    document = hit.get("document")
    return document if isinstance(document, dict) else hit


def _first_search_hit(results: Any) -> Dict[str, Any]:
    if isinstance(results, list) and results:
        return _unwrap_hit(results[0])
    if not isinstance(results, dict):
        return {}
    for key in ("hits", "results", "books"):
        nested = results.get(key)
        if isinstance(nested, list) and nested and isinstance(nested[0], dict):
            return _unwrap_hit(nested[0])
    if results.get("title") or results.get("description") or results.get("name"):
        return results
    return {}


def _index_from_position(value: Any) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def volumes_from_series_payload(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Normalize Hardcover series.book_series into expected volumes. No ISBNs (query depth)."""
    if not isinstance(payload, dict):
        return []
    series_name = str(payload.get("name") or "").strip()
    author = ""
    author_obj = payload.get("author")
    if isinstance(author_obj, dict):
        author = str(author_obj.get("name") or "").strip()
    rows = payload.get("book_series") or []
    volumes: List[Dict[str, Any]] = []
    if not isinstance(rows, list):
        return volumes
    for row in rows:
        if not isinstance(row, dict):
            continue
        book = row.get("book") if isinstance(row.get("book"), dict) else {}
        index = _index_from_position(row.get("position"))
        title = str(book.get("title") or "").strip()
        if not index and not title:
            continue
        year = _year_from(book.get("release_year"))
        volume: Dict[str, Any] = {
            "title": title or f"{series_name} {index}".strip(),
            "series_name": series_name,
            "series_index": index,
            "author": author,
            "source": "hardcover",
        }
        if year:
            volume["year"] = year
        volumes.append(volume)
    return volumes


class HardcoverClient:
    def __init__(
        self,
        token: str,
        *,
        url: str = HARDCOVER_GRAPHQL,
        transport: Optional[httpx.BaseTransport] = None,
        client: Optional[httpx.Client] = None,
        timeout: float = 20.0,
    ) -> None:
        self.token = str(token or "").strip()
        self.url = str(url or HARDCOVER_GRAPHQL).strip() or HARDCOVER_GRAPHQL
        self._own = client is None
        self._client = client or httpx.Client(
            timeout=timeout, transport=transport, follow_redirects=True
        )

    def close(self) -> None:
        if self._own:
            self._client.close()

    def configured(self) -> bool:
        return bool(self.token)

    def graphql(self, query: str, variables: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        if not self.token:
            raise HardcoverError("Hardcover token is not configured")
        try:
            response = self._client.post(
                self.url,
                headers={
                    "Authorization": _authorization(self.token),
                    "Content-Type": "application/json",
                    "User-Agent": DEFAULT_USER_AGENT,
                },
                json={"query": query, "variables": dict(variables or {})},
            )
        except httpx.HTTPError as error:
            raise HardcoverError("Hardcover could not be reached") from error
        if response.status_code == 401:
            raise HardcoverError("Hardcover token was refused")
        if response.status_code == 429:
            raise HardcoverError("Hardcover rate-limited this lookup")
        if response.status_code >= 400:
            raise HardcoverError(f"Hardcover HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as error:
            raise HardcoverError("Hardcover returned non-JSON") from error
        if not isinstance(payload, dict):
            return {}
        errors = payload.get("errors")
        if errors:
            raise HardcoverError("Hardcover query failed")
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def lookup_by_isbn(self, isbn: str) -> Dict[str, Any]:
        digits = extract_isbn(isbn)
        if not digits:
            return {}
        isbn13 = isbn10_to_isbn13(digits) or (digits if len(digits) == 13 else "")
        isbn10 = isbn13_to_isbn10(digits) or (digits if len(digits) == 10 else "")
        if isbn13:
            data = self.graphql(EDITION_BY_ISBN13, {"isbn": isbn13})
            editions = data.get("editions") or []
            if isinstance(editions, list) and editions and isinstance(editions[0], dict):
                return enrichment_from_edition(editions[0])
        if isbn10:
            data = self.graphql(EDITION_BY_ISBN10, {"isbn": isbn10})
            editions = data.get("editions") or []
            if isinstance(editions, list) and editions and isinstance(editions[0], dict):
                return enrichment_from_edition(editions[0])
        return {}

    def lookup_by_title(self, title: str, author: str = "") -> Dict[str, Any]:
        query = " ".join(part for part in (title, author) if str(part or "").strip()).strip()
        if not query:
            return {}
        data = self.graphql(BOOK_SEARCH, {"query": query})
        search = data.get("search") if isinstance(data.get("search"), dict) else {}
        hit = _first_search_hit(search.get("results"))
        if not hit:
            return {}
        return enrichment_from_search_hit(hit)

    def _series_payload(self, data: Mapping[str, Any], key: str) -> Dict[str, Any]:
        raw = data.get(key)
        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
            return raw[0]
        return raw if isinstance(raw, dict) else {}

    def lookup_series(self, name: str) -> List[Dict[str, Any]]:
        """Expected volumes for a book/audiobook series. Empty if unconfigured or unknown."""
        series_name = str(name or "").strip()
        if not series_name or not self.token:
            return []
        try:
            data = self.graphql(SERIES_BY_NAME, {"name": series_name})
            volumes = volumes_from_series_payload(self._series_payload(data, "series"))
            if volumes:
                return volumes
            search = self.graphql(SERIES_SEARCH, {"query": series_name})
            blob = search.get("search") if isinstance(search.get("search"), dict) else {}
            hit = _first_search_hit(blob.get("results"))
            series_id = hit.get("id")
            slug = str(hit.get("slug") or "").strip()
            if series_id not in (None, ""):
                try:
                    pk = int(series_id)
                except (TypeError, ValueError):
                    pk = None
                if pk is not None:
                    data = self.graphql(SERIES_BY_PK, {"id": pk})
                    volumes = volumes_from_series_payload(self._series_payload(data, "series_by_pk"))
                    if volumes:
                        return volumes
            if slug:
                data = self.graphql(SERIES_BY_SLUG, {"slug": slug})
                volumes = volumes_from_series_payload(self._series_payload(data, "series"))
                if volumes:
                    return volumes
        except HardcoverError:
            return []
        return []
