"""NZBFinder Newznab v2 JSON client. Token + User-Agent required."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urljoin

import httpx

from librarian._version import __version__
from librarian.kinds import kind_from_newznab, search_category_for_kind

DEFAULT_USER_AGENT = f"Librarian/{__version__} (+https://github.com/romwil/librarian)"


class NZBFinderError(RuntimeError):
    """Indexer HTTP or payload failure."""


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


def normalize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    attrs = _attr_map(item)
    enclosure = item.get("enclosure") or {}
    if isinstance(enclosure, dict):
        enclosure = enclosure.get("@attributes") or enclosure
    guid = item.get("guid")
    if isinstance(guid, dict):
        guid = guid.get("#text") or guid.get("text") or guid.get("@attributes", {}).get("guid")
    category = attrs.get("category") or item.get("category")
    if isinstance(category, list) and category:
        category = category[0]
    cat_id = attrs.get("category") or category
    size = attrs.get("size") or item.get("size") or (
        enclosure.get("length") if isinstance(enclosure, dict) else None
    )
    enclosure_url = enclosure.get("url") if isinstance(enclosure, dict) else None
    return {
        "title": item.get("title") or "",
        "guid": str(guid or attrs.get("guid") or _v2_guid(item) or ""),
        "link": item.get("link") or item.get("details") or "",
        "pub_date": item.get("pubDate") or item.get("pub_date") or item.get("postdate") or item.get("adddate") or "",
        "category": cat_id,
        "kind": kind_from_newznab(cat_id),
        "size": int(size) if str(size or "").isdigit() else None,
        "author": attrs.get("author") or item.get("author") or "",
        "book_title": attrs.get("booktitle") or item.get("book_title") or "",
        "isbn": attrs.get("isbn") or item.get("isbn13") or item.get("isbn10") or item.get("isbn") or "",
        "cover": attrs.get("coverurl") or attrs.get("cover") or item.get("cover") or "",
        "download_url": enclosure_url or item.get("url") or item.get("link") or "",
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
    ) -> None:
        self.base_url = str(base_url or "").rstrip("/")
        self.api_token = str(api_token or "").strip()
        self.user_agent = user_agent
        self._client = httpx.Client(timeout=30.0, transport=transport, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def _params(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_token:
            raise NZBFinderError("NZBFinder api_token is not configured")
        params = {"o": "json", "api_token": self.api_token, "apikey": self.api_token}
        params.update({key: value for key, value in extra.items() if value not in (None, "")})
        return params

    def _get(self, extra: Dict[str, Any]) -> Any:
        url = f"{self.base_url}/api"
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        try:
            response = self._client.get(url, params=self._params(extra), headers=headers)
        except httpx.HTTPError as error:
            raise NZBFinderError(str(error)) from error
        if response.status_code >= 400:
            raise NZBFinderError(f"NZBFinder HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as error:
            raise NZBFinderError("NZBFinder returned non-JSON") from error

    def capabilities(self) -> Any:
        return self._get({"t": "caps"})

    def search(
        self,
        query: str,
        *,
        cat: Optional[str] = None,
        kind: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        category = cat or (search_category_for_kind(kind) if kind else None)
        payload = self._get(
            {"t": "search", "q": query, "cat": category, "limit": limit, "offset": offset, "extended": 1}
        )
        return [item for item in parse_search_payload(payload) if item.get("kind")]

    def books(
        self,
        *,
        query: str = "",
        title: str = "",
        author: str = "",
        cat: Optional[str] = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        payload = self._get(
            {
                "t": "book",
                "q": query,
                "title": title,
                "author": author,
                "cat": cat or "7000",
                "limit": limit,
                "extended": 1,
            }
        )
        return [item for item in parse_search_payload(payload) if item.get("kind")]

    def details(self, guid: str) -> Dict[str, Any]:
        payload = self._get({"t": "details", "id": guid, "extended": 1})
        items = parse_search_payload(payload)
        if items:
            return items[0]
        if isinstance(payload, dict):
            return normalize_item(payload)
        raise NZBFinderError("NZBFinder details empty")

    def download_url(self, guid: str) -> str:
        if not self.api_token:
            raise NZBFinderError("NZBFinder api_token is not configured")
        query = urlencode({"t": "get", "id": guid, "api_token": self.api_token, "apikey": self.api_token})
        return urljoin(self.base_url + "/", f"api?{query}")
