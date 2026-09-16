"""Radarr / Sonarr clients for extra-category Request.

Copied from Projectionist's *arr contract (not vendored):
- Header ``X-Api-Key`` on ``/api/v3``
- Movies: lookup TMDB, ``POST /api/v3/movie`` with ``addOptions.searchForMovie=false``
  (Librarian already queued SAB — do not fire ``MoviesSearch``)
- TV: lookup TVDB/title, ``POST /api/v3/series`` with ``searchForMissingEpisodes=false``
  (do not fire ``SeriesSearch``)
- After SAB completes: ``DownloadedMoviesScan`` / ``DownloadedEpisodesScan``
- SAB categories default ``movies`` / ``tv`` so *arr completed-download handling can
  watch the same folder. XXX never calls *arr.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import quote

import httpx

from librarian.config import Settings
from librarian.kinds import KIND_MOVIE, KIND_TV, KIND_XXX


class ArrError(RuntimeError):
    """Radarr/Sonarr HTTP or lookup failure. Messages must never include tokens."""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_int(value: Any) -> Optional[int]:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


class ArrClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        label: str,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.base_url = _text(base_url).rstrip("/")
        self.api_key = _text(api_key)
        self.label = _text(label) or "arr"
        self._client = httpx.Client(timeout=30.0, transport=transport, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise ArrError(f"{self.label} API key is not configured")
        if not self.base_url:
            raise ArrError(f"{self.label} URL is not configured")
        return {"X-Api-Key": self.api_key, "Accept": "application/json"}

    def _error(self, response: httpx.Response) -> ArrError:
        status = response.status_code
        if status in {401, 403}:
            return ArrError(f"{self.label} HTTP {status} (invalid or missing API key)")
        return ArrError(f"{self.label} HTTP {status}")

    def _request(self, method: str, path: str, *, json_body: Optional[Mapping[str, Any]] = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = self._client.request(method, url, headers=self._headers(), json=json_body)
        except httpx.HTTPError as error:
            raise ArrError(f"{self.label} could not be reached") from error
        if response.status_code >= 400:
            raise self._error(response)
        if response.status_code == 204 or not (response.content or b""):
            return {}
        try:
            return response.json()
        except ValueError as error:
            raise ArrError(f"{self.label} returned non-JSON") from error

    def quality_profile_id(self) -> int:
        payload = self._request("GET", "/api/v3/qualityprofile")
        rows = payload if isinstance(payload, list) else []
        for row in rows:
            if isinstance(row, dict) and _as_int(row.get("id")):
                return int(row["id"])
        raise ArrError(f"{self.label} has no quality profile")

    def root_folder(self) -> str:
        payload = self._request("GET", "/api/v3/rootfolder")
        rows = payload if isinstance(payload, list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            path = _text(row.get("path"))
            if path:
                return path
        raise ArrError(f"{self.label} has no root folder")

    def command(self, body: Mapping[str, Any]) -> Any:
        return self._request("POST", "/api/v3/command", json_body=dict(body))

    def lookup_movies(self, term: str) -> List[Dict[str, Any]]:
        encoded = quote(_text(term))
        payload = self._request("GET", f"/api/v3/movie/lookup?term={encoded}")
        return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []

    def lookup_movie_tmdb(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        payload = self._request("GET", f"/api/v3/movie/lookup/tmdb?tmdbId={int(tmdb_id)}")
        return payload if isinstance(payload, dict) else None

    def movie_by_tmdb(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        payload = self._request("GET", f"/api/v3/movie?tmdbId={int(tmdb_id)}")
        if isinstance(payload, list):
            for row in payload:
                if isinstance(row, dict) and _as_int(row.get("tmdbId")) == tmdb_id:
                    return row
            return None
        if isinstance(payload, dict) and _as_int(payload.get("tmdbId")) == tmdb_id:
            return payload
        return None

    def add_movie(self, lookup: Mapping[str, Any], *, root_folder: str, quality_profile_id: int) -> Dict[str, Any]:
        body = dict(lookup)
        body["rootFolderPath"] = root_folder
        body["qualityProfileId"] = quality_profile_id
        body["monitored"] = True
        body["addOptions"] = {"searchForMovie": False}
        body.pop("path", None)
        result = self._request("POST", "/api/v3/movie", json_body=body)
        return result if isinstance(result, dict) else {}

    def lookup_series(self, term: str) -> List[Dict[str, Any]]:
        encoded = quote(_text(term))
        payload = self._request("GET", f"/api/v3/series/lookup?term={encoded}")
        return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []

    def series_by_tvdb(self, tvdb_id: int) -> Optional[Dict[str, Any]]:
        payload = self._request("GET", f"/api/v3/series?tvdbId={int(tvdb_id)}")
        if isinstance(payload, list):
            for row in payload:
                if isinstance(row, dict) and _as_int(row.get("tvdbId")) == tvdb_id:
                    return row
            return None
        if isinstance(payload, dict) and _as_int(payload.get("tvdbId")) == tvdb_id:
            return payload
        return None

    def add_series(self, lookup: Mapping[str, Any], *, root_folder: str, quality_profile_id: int) -> Dict[str, Any]:
        body = dict(lookup)
        body["rootFolderPath"] = root_folder
        body["qualityProfileId"] = quality_profile_id
        body["monitored"] = True
        body["seasonFolder"] = True
        body["addOptions"] = {"searchForMissingEpisodes": False}
        body.pop("path", None)
        result = self._request("POST", "/api/v3/series", json_body=body)
        return result if isinstance(result, dict) else {}


def sab_category_for_kind(settings: Settings, kind: str) -> str:
    if kind == KIND_MOVIE:
        return _text(getattr(settings, "sab_movie_category", "")) or "movies"
    if kind == KIND_TV:
        return _text(getattr(settings, "sab_tv_category", "")) or "tv"
    return ""


def _movie_lookup(client: ArrClient, item: Mapping[str, Any]) -> Dict[str, Any]:
    tmdb_id = _as_int(item.get("tmdb_id") or (item.get("selected") or {}).get("tmdb_id"))
    if tmdb_id:
        found = client.lookup_movie_tmdb(tmdb_id)
        if found:
            return found
    title = _text(item.get("title") or item.get("book_title") or (item.get("selected") or {}).get("title"))
    if not title:
        raise ArrError("Radarr needs a title or TMDB id to expect this movie")
    hits = client.lookup_movies(title)
    if not hits:
        raise ArrError("Radarr could not match that title")
    return hits[0]


def _series_lookup(client: ArrClient, item: Mapping[str, Any]) -> Dict[str, Any]:
    tvdb_id = _as_int(item.get("tvdb_id") or (item.get("selected") or {}).get("tvdb_id"))
    title = _text(item.get("title") or (item.get("selected") or {}).get("title"))
    if tvdb_id:
        hits = client.lookup_series(f"tvdb:{tvdb_id}")
        for row in hits:
            if _as_int(row.get("tvdbId")) == tvdb_id:
                return row
        if hits:
            return hits[0]
    if not title:
        raise ArrError("Sonarr needs a title or TVDB id to expect this show")
    hits = client.lookup_series(title)
    if not hits:
        raise ArrError("Sonarr could not match that title")
    return hits[0]


def expect_on_arr(
    settings: Settings,
    kind: str,
    item: Mapping[str, Any],
    *,
    transport: Optional[httpx.BaseTransport] = None,
) -> Dict[str, Any]:
    """Add the title to Radarr/Sonarr so the SAB category download can import.

    Does not grab/search — Librarian already queued SABnzbd. XXX is not *arr.
    """
    if kind == KIND_XXX:
        return {"service": None}
    if kind == KIND_MOVIE:
        url = _text(getattr(settings, "radarr_url", ""))
        key = _text(getattr(settings, "radarr_api_key", ""))
        if not url or not key:
            raise ArrError("Radarr is not configured")
        client = ArrClient(url, key, label="Radarr", transport=transport)
        try:
            lookup = _movie_lookup(client, item)
            tmdb_id = _as_int(lookup.get("tmdbId"))
            existing = client.movie_by_tmdb(tmdb_id) if tmdb_id else None
            if existing:
                return {
                    "service": "radarr",
                    "arr_id": existing.get("id"),
                    "tmdb_id": tmdb_id,
                    "title": existing.get("title") or lookup.get("title"),
                }
            added = client.add_movie(
                lookup,
                root_folder=client.root_folder(),
                quality_profile_id=client.quality_profile_id(),
            )
            return {
                "service": "radarr",
                "arr_id": added.get("id"),
                "tmdb_id": _as_int(added.get("tmdbId") or tmdb_id),
                "title": added.get("title") or lookup.get("title"),
            }
        finally:
            client.close()
    if kind == KIND_TV:
        url = _text(getattr(settings, "sonarr_url", ""))
        key = _text(getattr(settings, "sonarr_api_key", ""))
        if not url or not key:
            raise ArrError("Sonarr is not configured")
        client = ArrClient(url, key, label="Sonarr", transport=transport)
        try:
            lookup = _series_lookup(client, item)
            tvdb_id = _as_int(lookup.get("tvdbId"))
            existing = client.series_by_tvdb(tvdb_id) if tvdb_id else None
            if existing:
                return {
                    "service": "sonarr",
                    "arr_id": existing.get("id"),
                    "tvdb_id": tvdb_id,
                    "title": existing.get("title") or lookup.get("title"),
                }
            added = client.add_series(
                lookup,
                root_folder=client.root_folder(),
                quality_profile_id=client.quality_profile_id(),
            )
            return {
                "service": "sonarr",
                "arr_id": added.get("id"),
                "tvdb_id": _as_int(added.get("tvdbId") or tvdb_id),
                "title": added.get("title") or lookup.get("title"),
            }
        finally:
            client.close()
    raise ArrError("Not an extra category")


def notify_arr_downloaded(
    settings: Settings,
    kind: str,
    path: str,
    *,
    transport: Optional[httpx.BaseTransport] = None,
) -> Dict[str, Any]:
    """Projectionist downloaded-scan: tell *arr the SAB complete folder is ready."""
    target = _text(path)
    if kind == KIND_MOVIE:
        url = _text(getattr(settings, "radarr_url", ""))
        key = _text(getattr(settings, "radarr_api_key", ""))
        if not url or not key:
            raise ArrError("Radarr is not configured")
        client = ArrClient(url, key, label="Radarr", transport=transport)
        try:
            body: Dict[str, Any] = {"name": "DownloadedMoviesScan"}
            if target:
                body["path"] = target
            return {"service": "radarr", "command": client.command(body)}
        finally:
            client.close()
    if kind == KIND_TV:
        url = _text(getattr(settings, "sonarr_url", ""))
        key = _text(getattr(settings, "sonarr_api_key", ""))
        if not url or not key:
            raise ArrError("Sonarr is not configured")
        client = ArrClient(url, key, label="Sonarr", transport=transport)
        try:
            body = {"name": "DownloadedEpisodesScan"}
            if target:
                body["path"] = target
            return {"service": "sonarr", "command": client.command(body)}
        finally:
            client.close()
    return {"service": None}
