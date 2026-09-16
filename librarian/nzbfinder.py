"""Newznab v2 JSON client. NZBFinder is the first host; extras reuse this shape."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urljoin

import httpx

from librarian._version import __version__
from librarian.kinds import kind_from_newznab, search_category_for_kind

_UA_VERSION = ".".join(str(__version__).split(".")[:2]) or "0.1"
DEFAULT_USER_AGENT = f"Librarian/{_UA_VERSION} (Automat; +https://github.com/romwil/librarian)"


class NZBFinderError(RuntimeError):
    """Indexer HTTP or payload failure. Messages must never include tokens."""


NewznabError = NZBFinderError


def normalize_nzbfinder_url(base_url: str) -> str:
    """Require https:// (NZBFinder is HTTPS). Strip a trailing /api or /api/v2."""
    raw = str(base_url or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    raw = raw.rstrip("/")
    lowered = raw.lower()
    for suffix in ("/api/v2", "/api"):
        if lowered.endswith(suffix):
            raw = raw[: -len(suffix)].rstrip("/")
            break
    return raw


def describe_nzbfinder_response(response: httpx.Response, label: str = "NZBFinder") -> str:
    """Turn a non-JSON (or error) body into a specific message. Never include tokens."""
    status = response.status_code
    host = str(label or "NZBFinder").strip() or "NZBFinder"
    ctype = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    body = response.text or ""
    head = body.lstrip()[:48].lower()
    if status == 401:
        return f"{host} HTTP 401 (invalid or missing api_token)"
    if "html" in ctype or head.startswith("<!doctype") or head.startswith("<html"):
        return f"{host} HTTP {status} returned HTML (login page or wrong URL), not JSON"
    if "xml" in ctype or head.startswith("<?xml") or "<rss" in head or "<error" in body[:200].lower():
        return f"{host} HTTP {status} returned XML Newznab (use /api/v2/), not JSON"
    if ctype and "json" not in ctype:
        return f"{host} HTTP {status} returned non-JSON ({ctype})"
    return f"{host} HTTP {status} returned non-JSON"


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _attr_map(item: Dict[str, Any]) -> Dict[str, str]:
    attrs: Dict[str, str] = {}
    for raw in _as_list(item.get("attr") or item.get("newznab:attr")):
        if not isinstance(raw, dict):
            continue
        data = raw.get("@attributes") or raw
        name = str(data.get("name") or "").strip()
        if name:
            attrs[name] = str(data.get("value") or "")
    return attrs


def _v2_guid(item: Dict[str, Any]) -> str:
    details = str(item.get("details") or "")
    if "/details/" in details:
        return details.rsplit("/", 1)[-1]
    url = str(item.get("url") or "")
    if "id=" in url:
        raw = url.split("id=", 1)[1].split("&", 1)[0]
        return raw.removesuffix(".nzb")
    return ""


def _optional_int(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    return None


def _optional_year(value: Any) -> Optional[int]:
    year = _optional_int(value)
    if year is not None and 1800 <= year <= 2100:
        return year
    return None


def normalize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    attrs = _attr_map(item)
    enclosure = item.get("enclosure") or {}
    if isinstance(enclosure, dict):
        enclosure = enclosure.get("@attributes") or enclosure
    guid = item.get("guid")
    if isinstance(guid, dict):
        guid = guid.get("#text") or guid.get("text") or guid.get("@attributes", {}).get("guid")
    category = attrs.get("category") or item.get("category")
    cats: List[Any] = []
    if isinstance(category, list) and category:
        cats = list(category)
        category = category[0]
    cat_id = attrs.get("category") or category
    if cat_id not in (None, "") and not cats:
        cats = [cat_id]
    size = attrs.get("size") or item.get("size") or (
        enclosure.get("length") if isinstance(enclosure, dict) else None
    )
    enclosure_url = enclosure.get("url") if isinstance(enclosure, dict) else None
    year = _optional_year(attrs.get("year") or item.get("year"))
    return {
        "title": item.get("title") or "",
        "guid": str(guid or attrs.get("guid") or _v2_guid(item) or ""),
        "link": item.get("link") or item.get("details") or "",
        "pub_date": item.get("pubDate") or item.get("pub_date") or item.get("postdate") or item.get("adddate") or "",
        "category": cat_id,
        "cats": cats,
        "category_name": item.get("category_name") or attrs.get("category_name") or "",
        "kind": kind_from_newznab(cat_id),
        "size": _optional_int(size),
        "author": attrs.get("author") or item.get("author") or "",
        "book_title": attrs.get("booktitle") or item.get("book_title") or "",
        "isbn": attrs.get("isbn") or item.get("isbn13") or item.get("isbn10") or item.get("isbn") or "",
        "year": year,
        "poster": attrs.get("poster") or item.get("poster") or "",
        "cover": attrs.get("coverurl") or attrs.get("cover") or item.get("cover") or "",
        "download_url": enclosure_url or item.get("url") or item.get("link") or "",
        "tmdb_id": _optional_int(attrs.get("tmdbid") or item.get("tmdbId") or item.get("tmdb_id")),
        "tvdb_id": _optional_int(attrs.get("tvdbid") or item.get("tvdbId") or item.get("tvdb_id")),
        "imdb_id": str(attrs.get("imdb") or attrs.get("imdbid") or item.get("imdbid") or "").strip(),
        "raw": {key: value for key, value in item.items() if key != "description"},
    }


def parse_search_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [normalize_item(item) for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("results"), list):
        return [normalize_item(item) for item in payload["results"] if isinstance(item, dict)]
    channel = payload.get("channel") or payload
    items = channel.get("item") if isinstance(channel, dict) else None
    return [normalize_item(item) for item in _as_list(items) if isinstance(item, dict)]


class NZBFinderClient:
    def __init__(
        self,
        base_url: str,
        api_token: str,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        transport: Optional[httpx.BaseTransport] = None,
        label: str = "NZBFinder",
    ) -> None:
        self.base_url = normalize_nzbfinder_url(base_url)
        self.api_token = str(api_token or "").strip()
        self.user_agent = user_agent
        self.label = str(label or "NZBFinder").strip() or "NZBFinder"
        self._client = httpx.Client(timeout=30.0, transport=transport, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def _params(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_token:
            raise NZBFinderError(f"{self.label} api_token is not configured")
        params = {"api_token": self.api_token, "apikey": self.api_token}
        params.update({key: value for key, value in extra.items() if value not in (None, "")})
        return params

    def _error_from_response(self, response: httpx.Response) -> NZBFinderError:
        try:
            payload = response.json()
        except ValueError:
            return NZBFinderError(describe_nzbfinder_response(response, self.label))
        if isinstance(payload, dict):
            detail = payload.get("error") or payload.get("message")
            if detail:
                return NZBFinderError(f"{self.label} HTTP {response.status_code}: {detail}")
        return NZBFinderError(describe_nzbfinder_response(response, self.label))

    def _get(self, path: str, extra: Optional[Dict[str, Any]] = None) -> Any:
        url = urljoin(self.base_url + "/", f"api/v2/{path.lstrip('/')}")
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        try:
            response = self._client.get(url, params=self._params(extra or {}), headers=headers)
        except httpx.HTTPError as error:
            raise NZBFinderError(str(error)) from error
        if response.status_code >= 400:
            raise self._error_from_response(response)
        try:
            return response.json()
        except ValueError as error:
            raise NZBFinderError(describe_nzbfinder_response(response, self.label)) from error

    def capabilities(self) -> Any:
        return self._get("capabilities")

    def search(
        self,
        query: str,
        *,
        cat: Optional[str] = None,
        kind: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
        keep_untyped: bool = False,
    ) -> List[Dict[str, Any]]:
        category = cat or (search_category_for_kind(kind) if kind else None)
        payload = self._get(
            "search",
            {"query": query, "cat": category, "limit": limit, "offset": offset},
        )
        items = parse_search_payload(payload)
        if keep_untyped:
            return items
        return [item for item in items if item.get("kind")]

    def latest(self, cat: str, *, limit: int = 25, path: str = "search") -> List[Dict[str, Any]]:
        """Newest items in a category. Empty-query v2 search (Newznab latest-in-cat)."""
        extra: Dict[str, Any] = {"cat": str(cat), "limit": limit}
        payload = self._get(path, extra)
        return parse_search_payload(payload)

    def fetch_rss_category(self, cat: str, *, limit: int = 25) -> str:
        """Classic Newznab `/rss?t=CAT`. Returns XML text. Never logs tokens."""
        url = urljoin(self.base_url + "/", "rss")
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/rss+xml, application/xml, text/xml, application/json",
        }
        try:
            response = self._client.get(
                url,
                params=self._params({"t": str(cat), "num": limit, "dl": 1}),
                headers=headers,
            )
        except httpx.HTTPError as error:
            raise NZBFinderError(str(error)) from error
        if response.status_code >= 400:
            raise self._error_from_response(response)
        return response.text or ""

    def books(
        self,
        *,
        query: str = "",
        title: str = "",
        author: str = "",
        isbn: str = "",
        cat: Optional[str] = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        payload = self._get(
            "books",
            {
                "title": title or query,
                "author": author,
                "isbn": isbn,
                "cat": cat,
                "limit": limit,
            },
        )
        return [item for item in parse_search_payload(payload) if item.get("kind")]

    def details(self, guid: str) -> Dict[str, Any]:
        payload = self._get("details", {"id": guid})
        items = parse_search_payload(payload)
        if items:
            return items[0]
        if isinstance(payload, dict):
            return normalize_item(payload)
        raise NZBFinderError(f"{self.label} details empty")

    def download_url(self, guid: str) -> str:
        if not self.api_token:
            raise NZBFinderError(f"{self.label} api_token is not configured")
        nzb_id = guid if str(guid).endswith(".nzb") else f"{guid}.nzb"
        query = urlencode({"id": nzb_id, "api_token": self.api_token, "apikey": self.api_token})
        return urljoin(self.base_url + "/", f"api/v2/download?{query}")
