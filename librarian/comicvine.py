"""Comic Vine volume/issue lookups. Key stays in settings. Never invents issue numbers.

Deepened client: 1 req/s throttle, SQLite response cache, volume start-year ranking,
issue credit harvest, and numeric match confidence (≥0.85 auto / else Review).
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.parse import urlencode

import httpx

from librarian.covers import DEFAULT_USER_AGENT

COMICVINE_API = "https://comicvine.gamespot.com/api"
_INTISH = re.compile(r"^\d+(?:\.\d+)?$")
_HTML_TAG = re.compile(r"<[^>]+>")
_RATE_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0
MIN_INTERVAL_SECONDS = 1.0
CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS cv_cache (
  cache_key TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  fetched_at REAL NOT NULL
);
"""


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


def _strip_html(value: Any) -> str:
    text = unescape(str(value or ""))
    text = _HTML_TAG.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _year_int(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    if len(text) >= 4 and text[:4].isdigit():
        year = int(text[:4])
        if 1900 <= year <= 2100:
            return year
    return None


class ComicVineCache:
    """SQLite cache for ComicVine JSON payloads. Never mocked in tests — use a temp path."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(CACHE_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def get(self, key: str, *, max_age_seconds: float = 7 * 24 * 3600) -> Optional[Dict[str, Any]]:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload, fetched_at FROM cv_cache WHERE cache_key = ?",
                (key,),
            ).fetchone()
        if not row:
            return None
        payload_text, fetched_at = row
        if max_age_seconds > 0 and (now - float(fetched_at)) > max_age_seconds:
            return None
        try:
            data = json.loads(payload_text)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def set(self, key: str, payload: Mapping[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cv_cache(cache_key, payload, fetched_at) VALUES (?, ?, ?)",
                (key, json.dumps(dict(payload)), time.time()),
            )
            conn.commit()


def score_volume_match(
    *,
    query_name: str,
    volume: Mapping[str, Any],
    volume_year: Optional[int] = None,
    cover_year: Optional[int] = None,
    issue: str = "",
    issue_indexes: Sequence[str] = (),
) -> float:
    """Numeric confidence for a volume (and optional issue) candidate."""
    want = _title_key(query_name)
    got = _title_key(volume.get("name") or volume.get("series_name") or "")
    if not want or not got:
        return 0.0
    score = 0.0
    if want == got:
        score += 0.55
    elif want in got or got in want:
        score += 0.35
    else:
        return 0.0

    start = _year_int(volume.get("start_year") or volume.get("volume_year"))
    if volume_year is not None and start is not None:
        if start == volume_year:
            score += 0.30
        elif abs(start - volume_year) <= 1:
            score += 0.10
        else:
            score -= 0.15
    elif cover_year is not None and start is not None:
        if start == cover_year:
            score += 0.15
        elif start <= cover_year:
            score += 0.08
        else:
            score -= 0.05

    want_issue = _index_from_issue(issue) or str(issue or "").strip()
    if want_issue:
        indexes = {_index_from_issue(item) or str(item) for item in issue_indexes}
        if want_issue in indexes or want_issue.casefold() in {i.casefold() for i in indexes}:
            score += 0.15
        else:
            score -= 0.05

    return max(0.0, min(1.0, score))


class ComicVineClient:
    def __init__(
        self,
        api_key: str,
        *,
        url: str = COMICVINE_API,
        transport: Optional[httpx.BaseTransport] = None,
        client: Optional[httpx.Client] = None,
        timeout: float = 12.0,
        cache: Optional[ComicVineCache] = None,
        cache_path: Optional[Path] = None,
        rate_limit: bool = True,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.url = str(url or COMICVINE_API).rstrip("/") or COMICVINE_API
        self._own = client is None
        self._client = client or httpx.Client(
            timeout=timeout, transport=transport, follow_redirects=True
        )
        self._rate_limit = rate_limit
        if cache is not None:
            self.cache = cache
        elif cache_path is not None:
            self.cache = ComicVineCache(cache_path)
        else:
            self.cache = None

    def close(self) -> None:
        if self._own:
            self._client.close()

    def configured(self) -> bool:
        return bool(self.api_key)

    def _throttle(self) -> None:
        if not self._rate_limit:
            return
        global _LAST_REQUEST_AT
        with _RATE_LOCK:
            now = time.monotonic()
            wait = MIN_INTERVAL_SECONDS - (now - _LAST_REQUEST_AT)
            if wait > 0:
                time.sleep(wait)
            _LAST_REQUEST_AT = time.monotonic()

    def _get(self, path: str, params: Mapping[str, str]) -> Dict[str, Any]:
        if not self.api_key:
            return {}
        cache_key = f"{path}?{urlencode(sorted({**dict(params)}.items()))}"
        if self.cache is not None:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        query = {"api_key": self.api_key, "format": "json", **dict(params)}
        self._throttle()
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
        if self.cache is not None:
            self.cache.set(cache_key, payload)
        return payload

    def search_volumes(self, series_name: str, *, limit: int = 12) -> List[Dict[str, Any]]:
        name = str(series_name or "").strip()
        if not name or not self.api_key:
            return []
        try:
            search = self._get(
                "/search/",
                {"query": name, "resources": "volume", "limit": str(max(1, min(int(limit), 20)))},
            )
        except ComicVineError:
            return []
        results = search.get("results") if isinstance(search.get("results"), list) else []
        out: List[Dict[str, Any]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            volume_id = item.get("id")
            if volume_id in (None, ""):
                continue
            publisher = item.get("publisher") if isinstance(item.get("publisher"), dict) else {}
            out.append(
                {
                    "volume_id": int(volume_id),
                    "name": str(item.get("name") or "").strip(),
                    "start_year": _year_int(item.get("start_year")),
                    "count_of_issues": item.get("count_of_issues"),
                    "publisher": str(publisher.get("name") or "").strip(),
                    "site_detail_url": str(item.get("site_detail_url") or "").strip(),
                    "source": "comicvine",
                }
            )
        return out

    def volume_detail(self, volume_id: int) -> Dict[str, Any]:
        try:
            detail = self._get(
                f"/volume/4050-{int(volume_id)}/",
                {"field_list": "id,name,start_year,count_of_issues,issues,publisher,site_detail_url"},
            )
        except ComicVineError:
            return {}
        results_blob = detail.get("results")
        payload = results_blob if isinstance(results_blob, dict) else {}
        if not payload:
            return {}
        publisher = payload.get("publisher") if isinstance(payload.get("publisher"), dict) else {}
        issues_raw = payload.get("issues") if isinstance(payload.get("issues"), list) else []
        issues: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for issue in issues_raw:
            if not isinstance(issue, dict):
                continue
            index = _index_from_issue(issue.get("issue_number"))
            if not index or index in seen:
                continue
            seen.add(index)
            issues.append(
                {
                    "issue_id": issue.get("id"),
                    "series_index": index,
                    "title": str(issue.get("name") or "").strip(),
                    "api_detail_url": str(issue.get("api_detail_url") or "").strip(),
                }
            )
        issues.sort(
            key=lambda row: [
                int(part) if part.isdigit() else part for part in str(row["series_index"]).split(".")
            ]
        )
        return {
            "volume_id": int(payload.get("id") or volume_id),
            "name": str(payload.get("name") or "").strip(),
            "start_year": _year_int(payload.get("start_year")),
            "count_of_issues": payload.get("count_of_issues"),
            "publisher": str(publisher.get("name") or "").strip(),
            "site_detail_url": str(payload.get("site_detail_url") or "").strip(),
            "issues": issues,
            "source": "comicvine",
        }

    def issue_detail(self, issue_id: int) -> Dict[str, Any]:
        try:
            detail = self._get(
                f"/issue/4000-{int(issue_id)}/",
                {
                    "field_list": (
                        "id,name,issue_number,cover_date,description,site_detail_url,"
                        "image,volume,person_credits,publisher"
                    )
                },
            )
        except ComicVineError:
            return {}
        payload = detail.get("results") if isinstance(detail.get("results"), dict) else {}
        if not payload:
            return {}
        volume = payload.get("volume") if isinstance(payload.get("volume"), dict) else {}
        image = payload.get("image") if isinstance(payload.get("image"), dict) else {}
        credits = self._credits_from_people(payload.get("person_credits"))
        cover = str(payload.get("cover_date") or "")
        year = _year_int(cover)
        month = int(cover[5:7]) if len(cover) >= 7 and cover[5:7].isdigit() else None
        day = int(cover[8:10]) if len(cover) >= 10 and cover[8:10].isdigit() else None
        index = _index_from_issue(payload.get("issue_number"))
        series_name = str(volume.get("name") or "").strip()
        publisher = ""
        pub = payload.get("publisher") if isinstance(payload.get("publisher"), dict) else {}
        if pub:
            publisher = str(pub.get("name") or "").strip()
        return {
            "issue_id": int(payload.get("id") or issue_id),
            "volume_id": volume.get("id"),
            "series_name": series_name,
            "series_index": index,
            "title": str(payload.get("name") or "").strip() or (f"{series_name} #{index}" if series_name and index else ""),
            "year": year,
            "month": month,
            "day": day,
            "description": _strip_html(payload.get("description")),
            "publisher": publisher,
            "cover_url": str(image.get("super_url") or image.get("medium_url") or image.get("original_url") or "").strip(),
            "web": str(payload.get("site_detail_url") or "").strip(),
            "source": "comicvine",
            **credits,
        }

    @staticmethod
    def _credits_from_people(raw: Any) -> Dict[str, str]:
        buckets: Dict[str, List[str]] = {
            "writer": [],
            "penciller": [],
            "inker": [],
            "colorist": [],
            "cover_artist": [],
            "letterer": [],
        }
        role_map = {
            "writer": "writer",
            "penciler": "penciller",
            "penciller": "penciller",
            "artist": "penciller",
            "inker": "inker",
            "colorist": "colorist",
            "cover": "cover_artist",
            "cover artist": "cover_artist",
            "letterer": "letterer",
        }
        people = raw if isinstance(raw, list) else []
        for person in people:
            if not isinstance(person, dict):
                continue
            name = str(person.get("name") or "").strip()
            if not name:
                continue
            roles = str(person.get("role") or "").lower()
            for part in re.split(r"[,/;]+", roles):
                key = role_map.get(part.strip())
                if key and name not in buckets[key]:
                    buckets[key].append(name)
        return {
            "writer": ", ".join(buckets["writer"]),
            "penciller": ", ".join(buckets["penciller"]),
            "inker": ", ".join(buckets["inker"]),
            "colorist": ", ".join(buckets["colorist"]),
            "cover_artist": ", ".join(buckets["cover_artist"]),
            "letterer": ", ".join(buckets["letterer"]),
            "author": ", ".join(buckets["writer"]) or ", ".join(buckets["penciller"]),
        }

    def rank_volumes(
        self,
        series_name: str,
        *,
        volume_year: Optional[int] = None,
        cover_year: Optional[int] = None,
        issue: str = "",
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        volumes = self.search_volumes(series_name, limit=limit)
        ranked: List[Dict[str, Any]] = []
        for volume in volumes:
            detail = self.volume_detail(int(volume["volume_id"]))
            merged = {**volume, **detail} if detail else dict(volume)
            indexes = [str(row.get("series_index") or "") for row in (merged.get("issues") or [])]
            score = score_volume_match(
                query_name=series_name,
                volume=merged,
                volume_year=volume_year,
                cover_year=cover_year,
                issue=issue,
                issue_indexes=indexes,
            )
            merged["match_score"] = score
            ranked.append(merged)
        ranked.sort(key=lambda row: (-float(row.get("match_score") or 0), str(row.get("name") or "")))
        return ranked

    def match_issue(
        self,
        series_name: str,
        issue: str,
        *,
        volume_year: Optional[int] = None,
        cover_year: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return best issue match with candidates and confidence band."""
        ranked = self.rank_volumes(
            series_name,
            volume_year=volume_year,
            cover_year=cover_year,
            issue=issue,
        )
        want = _index_from_issue(issue) or str(issue or "").strip()
        candidates: List[Dict[str, Any]] = []
        best: Dict[str, Any] = {}
        for volume in ranked:
            score = float(volume.get("match_score") or 0)
            issue_row = None
            for row in volume.get("issues") or []:
                idx = str(row.get("series_index") or "")
                if idx == want or idx.casefold() == want.casefold():
                    issue_row = row
                    break
            candidate = {
                "match_key": f"cv:volume:{volume.get('volume_id')}"
                + (f":issue:{issue_row.get('issue_id')}" if issue_row and issue_row.get("issue_id") else ""),
                "volume_id": volume.get("volume_id"),
                "series_name": volume.get("name"),
                "start_year": volume.get("start_year"),
                "publisher": volume.get("publisher"),
                "series_index": want,
                "issue_id": (issue_row or {}).get("issue_id"),
                "issue_title": (issue_row or {}).get("title"),
                "match_score": score,
                "source": "comicvine",
            }
            candidates.append(candidate)
            if not best and issue_row:
                detail = {}
                if issue_row.get("issue_id"):
                    detail = self.issue_detail(int(issue_row["issue_id"]))
                best = {
                    **candidate,
                    **detail,
                    "volume_year": volume.get("start_year"),
                    "publisher": detail.get("publisher") or volume.get("publisher"),
                    "author": detail.get("author") or detail.get("writer") or volume.get("publisher"),
                    "year": detail.get("year") or cover_year or volume.get("start_year"),
                    "title": detail.get("title")
                    or (issue_row or {}).get("title")
                    or f"{volume.get('name')} #{want}",
                }
        top_score = float((best or candidates and candidates[0] or {}).get("match_score") or 0)
        band = "high" if top_score >= 0.85 else ("mid" if top_score >= 0.65 else "low")
        return {
            "best": best,
            "candidates": candidates[:8],
            "match_score": top_score,
            "band": band,
            "source": "comicvine",
        }

    def series_issues(self, series_name: str) -> List[Dict[str, Any]]:
        """Legacy thin API: first title-key volume's issues (gaps / catalog)."""
        name = str(series_name or "").strip()
        if not name or not self.api_key:
            return []
        ranked = self.rank_volumes(name, limit=8)
        volume = next((row for row in ranked if _title_key(row.get("name")) == _title_key(name)), None)
        if volume is None and ranked:
            volume = ranked[0]
        if not volume:
            return []
        detail = volume if volume.get("issues") else self.volume_detail(int(volume["volume_id"]))
        publisher = str(detail.get("publisher") or "").strip()
        start_year = detail.get("start_year")
        out: List[Dict[str, Any]] = []
        for issue in detail.get("issues") or []:
            index = str(issue.get("series_index") or "")
            if not index:
                continue
            title = str(issue.get("title") or "").strip() or f"{name} {index}"
            row: Dict[str, Any] = {
                "title": title,
                "series_name": name,
                "series_index": index,
                "author": publisher,
                "publisher": publisher,
                "source": "comicvine",
                "volume_id": detail.get("volume_id"),
                "volume_year": start_year,
            }
            if isinstance(start_year, int):
                row["year"] = start_year
            out.append(row)
        return out
