"""MusicBrainz release-group track lists and artist albums. User-Agent required. Fail closed."""

from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Mapping, Optional
from urllib.parse import quote_plus, urlencode

import httpx

from librarian.covers import DEFAULT_USER_AGENT

MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"
SKIP_SECONDARY = {
    "Compilation",
    "Live",
    "Soundtrack",
    "Remix",
    "DJ-mix",
    "Mixtape/Street",
    "Interview",
    "Audiobook",
}


class MusicBrainzError(RuntimeError):
    """MusicBrainz HTTP failure. Do not invent MBIDs."""


def _title_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _quote_lucene(value: str) -> str:
    cleaned = str(value or "").replace("\\", " ").replace('"', " ").strip()
    return cleaned


class MusicBrainzClient:
    def __init__(
        self,
        *,
        url: str = MUSICBRAINZ_API,
        transport: Optional[httpx.BaseTransport] = None,
        client: Optional[httpx.Client] = None,
        timeout: float = 12.0,
        min_interval: float = 1.1,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.url = str(url or MUSICBRAINZ_API).rstrip("/") or MUSICBRAINZ_API
        self._own = client is None
        self._client = client or httpx.Client(
            timeout=timeout, transport=transport, follow_redirects=True
        )
        self.min_interval = max(0.0, float(min_interval))
        self._sleeper = sleeper
        self._last = 0.0

    def close(self) -> None:
        if self._own:
            self._client.close()

    def _pace(self) -> None:
        if self.min_interval <= 0:
            return
        now = time.monotonic()
        wait = self.min_interval - (now - self._last)
        if wait > 0:
            self._sleeper(wait)
        self._last = time.monotonic()

    def _get(self, path: str, params: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
        self._pace()
        query = {"fmt": "json", **dict(params or {})}
        try:
            response = self._client.get(
                f"{self.url}{path}?{urlencode(query, quote_via=quote_plus)}",
                headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"},
            )
        except httpx.HTTPError as error:
            raise MusicBrainzError("MusicBrainz could not be reached") from error
        if response.status_code == 400:
            raise MusicBrainzError("MusicBrainz rejected this lookup")
        if response.status_code == 429:
            raise MusicBrainzError("MusicBrainz rate-limited this lookup")
        if response.status_code >= 400:
            raise MusicBrainzError(f"MusicBrainz HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as error:
            raise MusicBrainzError("MusicBrainz returned non-JSON") from error
        return payload if isinstance(payload, dict) else {}

    def release_tracks(
        self,
        *,
        title: str,
        artist: str,
        mbid: str = "",
    ) -> Dict[str, Any]:
        """Track list for an owned album. Empty dict on failure. Never invents an MBID."""
        group_id = str(mbid or "").strip()
        try:
            if not group_id:
                group_id = self._search_release_group(title, artist)
            if not group_id:
                return {}
            tracks = self._tracks_for_group(group_id)
        except MusicBrainzError:
            return {}
        if not tracks:
            return {}
        return {
            "mbid": group_id,
            "title": str(title or "").strip(),
            "author": str(artist or "").strip(),
            "tracks": tracks,
            "source": "musicbrainz",
        }

    def artist_albums(self, artist: str) -> List[Dict[str, Any]]:
        name = str(artist or "").strip()
        if not name:
            return []
        try:
            artist_id = self._search_artist(name)
            if not artist_id:
                return []
            payload = self._get(
                "/release-group",
                {"artist": artist_id, "type": "album", "limit": "50"},
            )
        except MusicBrainzError:
            return []
        albums: List[Dict[str, Any]] = []
        for row in payload.get("release-groups") or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("primary-type") or "") != "Album":
                continue
            secondary = {str(item) for item in (row.get("secondary-types") or [])}
            if secondary & SKIP_SECONDARY:
                continue
            title = str(row.get("title") or "").strip()
            mbid = str(row.get("id") or "").strip()
            if not title or not mbid:
                continue
            year = str(row.get("first-release-date") or "")[:4]
            album: Dict[str, Any] = {
                "title": title,
                "author": name,
                "mbid": mbid,
                "source": "musicbrainz",
            }
            if year.isdigit():
                album["year"] = int(year)
            albums.append(album)
        return albums

    def _search_release_group(self, title: str, artist: str) -> str:
        album = _quote_lucene(title)
        if not album:
            return ""
        query = f'release:"{album}"'
        who = _quote_lucene(artist)
        if who:
            query += f' AND artist:"{who}"'
        payload = self._get("/release-group", {"query": query, "limit": "5"})
        groups = payload.get("release-groups") or []
        want = _title_key(title)
        for row in groups:
            if not isinstance(row, dict):
                continue
            if want and _title_key(row.get("title")) != want:
                continue
            mbid = str(row.get("id") or "").strip()
            if mbid:
                return mbid
        return ""

    def _search_artist(self, artist: str) -> str:
        who = _quote_lucene(artist)
        if not who:
            return ""
        payload = self._get("/artist", {"query": f'artist:"{who}"', "limit": "5"})
        want = _title_key(artist)
        for row in payload.get("artists") or []:
            if not isinstance(row, dict):
                continue
            if want and _title_key(row.get("name")) != want:
                continue
            mbid = str(row.get("id") or "").strip()
            if mbid:
                return mbid
        return ""

    def _tracks_for_group(self, group_id: str) -> List[Dict[str, str]]:
        payload = self._get(
            "/release",
            {
                "release-group": group_id,
                "status": "official",
                "inc": "recordings",
                "limit": "1",
            },
        )
        releases = payload.get("releases") or []
        if not releases or not isinstance(releases[0], dict):
            return []
        tracks: List[Dict[str, str]] = []
        seen: set[str] = set()
        for medium in releases[0].get("media") or []:
            if not isinstance(medium, dict):
                continue
            for raw in medium.get("tracks") or []:
                if not isinstance(raw, dict):
                    continue
                number = str(raw.get("number") or raw.get("position") or "").strip()
                if number.isdigit():
                    number = str(int(number))
                title = str(raw.get("title") or "").strip()
                if not number or number in seen:
                    continue
                seen.add(number)
                tracks.append({"number": number, "title": title})
        return tracks

    def lookup_release(
        self,
        *,
        artist: str = "",
        album: str = "",
        mbid: str = "",
        recording_mbid: str = "",
    ) -> Dict[str, Any]:
        """Album fields from a tagged MBID or a strong artist+album. Never invents an MBID."""
        group_id = str(mbid or "").strip()
        recording_id = str(recording_mbid or "").strip()
        try:
            if recording_id and not group_id:
                group_id = self._release_group_from_recording(recording_id)
            if not group_id:
                group_id = self._search_release_group(album, artist)
            if not group_id:
                return {}
            payload = self._get(f"/release-group/{group_id}", {"inc": "artist-credits"})
        except MusicBrainzError:
            return {}
        title = str(payload.get("title") or album or "").strip()
        if not title:
            return {}
        author = str(artist or "").strip()
        credits = payload.get("artist-credit")
        if isinstance(credits, list) and credits and isinstance(credits[0], dict):
            artist_blob = credits[0].get("name") or ""
            if not artist_blob and isinstance(credits[0].get("artist"), dict):
                artist_blob = credits[0]["artist"].get("name") or ""
            author = str(artist_blob or author).strip()
        year = str(payload.get("first-release-date") or "")[:4]
        out: Dict[str, Any] = {
            "title": title,
            "series_name": title,
            "album": title,
            "author": author,
            "mbid": str(payload.get("id") or group_id),
            "source": "musicbrainz",
        }
        if year.isdigit():
            out["year"] = int(year)
        return out

    def _release_group_from_recording(self, recording_id: str) -> str:
        payload = self._get(f"/recording/{recording_id}", {"inc": "releases"})
        for rel in payload.get("releases") or []:
            if not isinstance(rel, dict):
                continue
            group = rel.get("release-group")
            if isinstance(group, dict) and group.get("id"):
                return str(group["id"]).strip()
            release_id = str(rel.get("id") or "").strip()
            if not release_id:
                continue
            detail = self._get(f"/release/{release_id}", {})
            nested = detail.get("release-group")
            if isinstance(nested, dict) and nested.get("id"):
                return str(nested["id"]).strip()
            nested_id = str(detail.get("release-group-id") or "").strip()
            if nested_id:
                return nested_id
        return ""
