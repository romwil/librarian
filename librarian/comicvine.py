"""Comic Vine volume/issue lookups. Key stays in settings. Never invents issue numbers."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlencode

import httpx

from librarian.covers import DEFAULT_USER_AGENT

COMICVINE_API = "https://comicvine.gamespot.com/api"
_INTISH = re.compile(r"^\d+(?:\.\d+)?$")


class ComicVineError(RuntimeError):
    """Comic Vine HTTP failure. Messages must never include the API key."""


def _title_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _index_from_issue(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if not _INTISH.match(text):
        return ""
    if "." not in text:
        return str(int(text))
    return text


class ComicVineClient:
    def __init__(
        self,
        api_key: str,
        *,
        url: str = COMICVINE_API,
        transport: Optional[httpx.BaseTransport] = None,
        client: Optional[httpx.Client] = None,
        timeout: float = 12.0,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.url = str(url or COMICVINE_API).rstrip("/") or COMICVINE_API
        self._own = client is None
        self._client = client or httpx.Client(
            timeout=timeout, transport=transport, follow_redirects=True
        )

    def close(self) -> None:
        if self._own:
            self._client.close()

    def configured(self) -> bool:
        return bool(self.api_key)

    def _get(self, path: str, params: Mapping[str, str]) -> Dict[str, Any]:
        if not self.api_key:
            return {}
        query = {"api_key": self.api_key, "format": "json", **dict(params)}
        try:
            response = self._client.get(
                f"{self.url}{path}?{urlencode(query)}",
                headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"},
            )
        except httpx.HTTPError as error:
            raise ComicVineError("Comic Vine could not be reached") from error
        if response.status_code == 401:
            raise ComicVineError("Comic Vine key was refused")
        if response.status_code == 429:
            raise ComicVineError("Comic Vine rate-limited this lookup")
        if response.status_code >= 400:
            raise ComicVineError(f"Comic Vine HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as error:
            raise ComicVineError("Comic Vine returned non-JSON") from error
        if not isinstance(payload, dict):
            return {}
        status = payload.get("status_code")
        error_text = str(payload.get("error") or "")
        if status not in (1, None) and error_text.upper() not in ("OK", ""):
            raise ComicVineError("Comic Vine query failed")
        return payload

    def series_issues(self, series_name: str) -> List[Dict[str, Any]]:
        name = str(series_name or "").strip()
        if not name or not self.api_key:
            return []
        try:
            search = self._get("/search/", {"query": name, "resources": "volume", "limit": "8"})
        except ComicVineError:
            return []
        results = search.get("results") if isinstance(search.get("results"), list) else []
        volume: Dict[str, Any] = {}
        want = _title_key(name)
        for item in results:
            if isinstance(item, dict) and _title_key(item.get("name")) == want:
                volume = item
                break
        if not volume:
            return []
        volume_id = volume.get("id")
        if volume_id in (None, ""):
            return []
        try:
            detail = self._get(
                f"/volume/4050-{volume_id}/",
                {"field_list": "id,name,start_year,count_of_issues,issues,publisher"},
            )
        except ComicVineError:
            return []
        results_blob = detail.get("results")
        payload = results_blob if isinstance(results_blob, dict) else volume
        issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
        publisher = payload.get("publisher") if isinstance(payload.get("publisher"), dict) else {}
        author = str(publisher.get("name") or "").strip()
        start_year = str(payload.get("start_year") or volume.get("start_year") or "").strip()
        volumes: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            index = _index_from_issue(issue.get("issue_number"))
            if not index or index in seen:
                continue
            seen.add(index)
            title = str(issue.get("name") or "").strip() or f"{name} {index}"
            row: Dict[str, Any] = {
                "title": title,
                "series_name": name,
                "series_index": index,
                "author": author,
                "source": "comicvine",
            }
            cover = str(issue.get("cover_date") or "")
            year = cover[:4] if len(cover) >= 4 and cover[:4].isdigit() else start_year[:4]
            if year.isdigit():
                row["year"] = int(year)
            volumes.append(row)
        volumes.sort(key=lambda row: [int(part) if part.isdigit() else part for part in str(row["series_index"]).split(".")])
        return volumes
