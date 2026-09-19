"""Audiobookshelf federation — match, scan notify, listen progress sync.

Fail-soft; never invent item ids; messages must never include tokens.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.parse import quote, urljoin

import httpx

from librarian.config import Settings
from librarian.covers import DEFAULT_USER_AGENT
from librarian.db import Database
from librarian.identify import isbn_match_keys
from librarian.kinds import KIND_AUDIOBOOK

logger = logging.getLogger(__name__)

ABS_PUSH_MIN_INTERVAL_S = 25.0
_ABS_PUSH_AT: Dict[str, float] = {}
_ABS_DURATION: Dict[str, float] = {}


class AudiobookshelfError(RuntimeError):
    """ABS HTTP failure. Messages must never include tokens."""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def normalize_abs_url(base_url: str) -> str:
    raw = _text(base_url)
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"http://{raw}"
    return raw.rstrip("/")


def _is_book_library(library: Mapping[str, Any]) -> bool:
    media_type = _text(
        library.get("mediaType") or (library.get("settings") or {}).get("mediaType")
    ).lower()
    return not media_type or media_type in {"book", "audiobook"}


class AudiobookshelfClient:
    def __init__(
        self,
        base_url: str,
        api_token: str,
        *,
        transport: Optional[httpx.BaseTransport] = None,
        client: Optional[httpx.Client] = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = normalize_abs_url(base_url)
        self.api_token = _text(api_token)
        self._own = client is None
        self._client = client or httpx.Client(
            timeout=timeout, transport=transport, follow_redirects=True
        )

    def close(self) -> None:
        if self._own:
            self._client.close()

    def configured(self) -> bool:
        return bool(self.base_url and self.api_token)

    def _headers(self, *, json_body: bool = False) -> Dict[str, str]:
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_token}",
        }
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def _url(self, path: str) -> str:
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Any] = None,
        allow_404: bool = False,
    ) -> Any:
        if not self.configured():
            return None
        try:
            response = self._client.request(
                method,
                self._url(path),
                headers=self._headers(json_body=json_body is not None),
                json=json_body,
            )
        except httpx.HTTPError as error:
            raise AudiobookshelfError("Audiobookshelf could not be reached") from error
        if allow_404 and response.status_code == 404:
            return None
        if response.status_code in (401, 403):
            raise AudiobookshelfError("Audiobookshelf token was refused")
        if response.status_code >= 400:
            raise AudiobookshelfError(f"Audiobookshelf HTTP {response.status_code}")
        if response.status_code in (204,) or not response.content:
            return None
        try:
            return response.json()
        except ValueError as error:
            raise AudiobookshelfError("Audiobookshelf returned non-JSON") from error

    def _get(self, path: str, *, allow_404: bool = False) -> Any:
        return self._request("GET", path, allow_404=allow_404)

    def libraries(self) -> List[Dict[str, Any]]:
        payload = self._get("api/libraries")
        if isinstance(payload, dict) and isinstance(payload.get("libraries"), list):
            return [row for row in payload["libraries"] if isinstance(row, dict)]
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        return []

    def library_items(self, library_id: str) -> List[Dict[str, Any]]:
        payload = self._get(f"api/libraries/{library_id}/items?limit=1000")
        if isinstance(payload, dict) and isinstance(payload.get("results"), list):
            return [row for row in payload["results"] if isinstance(row, dict)]
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        return []

    def audiobook_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for library in self.libraries():
            if not _is_book_library(library):
                continue
            lib_id = _text(library.get("id"))
            if not lib_id:
                continue
            items.extend(self.library_items(lib_id))
        return items

    def trigger_scan(self, library_id: str) -> bool:
        """POST library scan. Returns True on success; raises on hard failure."""
        lib_id = _text(library_id)
        if not self.configured() or not lib_id:
            return False
        self._request("POST", f"api/libraries/{quote(lib_id, safe='')}/scan")
        return True

    def scan_audiobook_libraries(self) -> List[str]:
        """Scan every book/audiobook library. Returns scanned library ids."""
        scanned: List[str] = []
        for library in self.libraries():
            if not _is_book_library(library):
                continue
            lib_id = _text(library.get("id"))
            if not lib_id:
                continue
            if self.trigger_scan(lib_id):
                scanned.append(lib_id)
        return scanned

    def get_media_progress(self, library_item_id: str) -> Optional[Dict[str, Any]]:
        item_id = _text(library_item_id)
        if not item_id:
            return None
        payload = self._get(f"api/me/progress/{quote(item_id, safe='')}", allow_404=True)
        return payload if isinstance(payload, dict) else None

    def update_media_progress(
        self,
        library_item_id: str,
        *,
        current_time: float = 0.0,
        progress: float = 0.0,
        duration: float = 0.0,
        is_finished: bool = False,
    ) -> bool:
        item_id = _text(library_item_id)
        if not item_id:
            return False
        body: Dict[str, Any] = {
            "currentTime": max(0.0, float(current_time or 0.0)),
            "progress": max(0.0, min(1.0, float(progress or 0.0))),
            "isFinished": bool(is_finished),
        }
        if duration and float(duration) > 0:
            body["duration"] = float(duration)
        if is_finished:
            body["progress"] = 1.0
        self._request("PATCH", f"api/me/progress/{quote(item_id, safe='')}", json_body=body)
        return True


def _item_title(item: Dict[str, Any]) -> str:
    media = item.get("media") if isinstance(item.get("media"), dict) else {}
    meta = media.get("metadata") if isinstance(media.get("metadata"), dict) else {}
    return _text(meta.get("title") or item.get("title") or item.get("name"))


def _item_authors(item: Dict[str, Any]) -> List[str]:
    media = item.get("media") if isinstance(item.get("media"), dict) else {}
    meta = media.get("metadata") if isinstance(media.get("metadata"), dict) else {}
    authors = meta.get("authors") or item.get("authors") or []
    names: List[str] = []
    if isinstance(authors, list):
        for author in authors:
            if isinstance(author, dict):
                name = _text(author.get("name"))
            else:
                name = _text(author)
            if name:
                names.append(name)
    author = _text(meta.get("author") or item.get("author"))
    if author:
        names.append(author)
    return names


def _item_isbns(item: Dict[str, Any]) -> List[str]:
    media = item.get("media") if isinstance(item.get("media"), dict) else {}
    meta = media.get("metadata") if isinstance(media.get("metadata"), dict) else {}
    return isbn_match_keys(
        meta.get("isbn"),
        meta.get("isbn13"),
        meta.get("asin"),
        item.get("isbn"),
    )


def match_item(work: Dict[str, Any], items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """ISBN first, then exact author+title. Fail closed — no title-only guesses."""
    work_keys = set(isbn_match_keys(str(work.get("isbn") or "")))
    if work_keys:
        for item in items:
            if work_keys.intersection(_item_isbns(item)):
                return item
    title_key = _norm_name(work.get("title"))
    author_key = _norm_name(work.get("author"))
    if not title_key or not author_key:
        return None
    for item in items:
        if _norm_name(_item_title(item)) != title_key:
            continue
        item_authors = {_norm_name(name) for name in _item_authors(item)}
        if author_key in item_authors:
            return item
    return None


def abs_match_counts(db: Database) -> Dict[str, int]:
    works = db.list_works(kind="audiobook", limit=500)
    matched = sum(1 for row in works if _text(row.get("abs_item_id")))
    return {"matched": matched, "audiobooks": len(works)}


def match_audiobooks(
    db: Database,
    settings: Settings,
    *,
    client: Optional[AudiobookshelfClient] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Match catalog audiobooks to ABS items. No token → no HTTP."""
    url = _text(getattr(settings, "audiobookshelf_url", ""))
    token = _text(getattr(settings, "audiobookshelf_api_token", ""))
    counts = abs_match_counts(db)
    if not url or not token:
        return {**counts, "updated": 0, "called": False}
    works = db.list_works(kind="audiobook", limit=500)
    unmatched = [row for row in works if not _text(row.get("abs_item_id"))]
    if not unmatched and not force:
        return {**counts, "updated": 0, "called": False}
    own_client = client is None
    abs_client = client or AudiobookshelfClient(url, token)
    updated = 0
    try:
        items = abs_client.audiobook_items()
        for work in unmatched:
            hit = match_item(work, items)
            if hit is None:
                continue
            item_id = _text(hit.get("id"))
            if not item_id:
                continue
            db.upsert_work({**work, "abs_item_id": item_id})
            updated += 1
    except AudiobookshelfError as error:
        logger.info("ABS match skipped: %s", error)
        return {**abs_match_counts(db), "updated": 0, "called": True, "error": str(error)}
    finally:
        if own_client:
            abs_client.close()
    return {**abs_match_counts(db), "updated": updated, "called": True}


def notify_abs_scan(
    settings: Any,
    *,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[AudiobookshelfClient] = None,
) -> Dict[str, Any]:
    """Fail-soft POST scan for book/audiobook libraries after shelve."""
    url = _text(getattr(settings, "audiobookshelf_url", ""))
    token = _text(getattr(settings, "audiobookshelf_api_token", ""))
    if not (url and token):
        return {"ok": False, "skipped": True, "reason": "not_configured"}
    own_client = client is None
    abs_client = client or AudiobookshelfClient(url, token, transport=transport)
    try:
        libraries = abs_client.scan_audiobook_libraries()
        return {"ok": True, "skipped": False, "libraries": libraries}
    except AudiobookshelfError as error:
        logger.warning("ABS scan failed: %s", error)
        return {"ok": False, "skipped": False, "error": str(error)}
    except Exception as error:  # noqa: BLE001 — fail-soft federation
        logger.warning("ABS scan unexpected failure: %s", error)
        return {"ok": False, "skipped": False, "error": "unexpected"}
    finally:
        if own_client:
            abs_client.close()


def should_adopt_abs_progress(
    *,
    local_fraction: float = 0.0,
    local_seconds: float = 0.0,
    abs_fraction: float = 0.0,
    abs_current_time: float = 0.0,
    abs_finished: bool = False,
) -> bool:
    """Prefer ABS only when it is ahead or local is empty — never wipe a better bookmark."""
    local_frac = max(0.0, float(local_fraction or 0.0))
    local_sec = max(0.0, float(local_seconds or 0.0))
    abs_frac = max(0.0, float(abs_fraction or 0.0))
    abs_sec = max(0.0, float(abs_current_time or 0.0))
    if abs_finished and local_frac < 0.999:
        return True
    if abs_frac <= 0.0 and abs_sec <= 0.0:
        return False
    if local_frac <= 0.001 and local_sec < 1.0:
        return True
    if local_frac >= abs_frac + 0.01:
        return False
    if abs_frac >= local_frac + 0.01:
        return True
    if abs_sec >= local_sec + 30.0 and abs_frac + 0.001 >= local_frac:
        return True
    return False


def map_abs_progress_to_local(
    abs_row: Mapping[str, Any],
    *,
    file_ids: Sequence[str] = (),
) -> Dict[str, Any]:
    """Map ABS media progress into Librarian fraction + encoded position."""
    from librarian.listen import encode_listen_position

    finished = bool(abs_row.get("isFinished"))
    try:
        fraction = float(abs_row.get("progress") or 0.0)
    except (TypeError, ValueError):
        fraction = 0.0
    try:
        current_time = float(abs_row.get("currentTime") or 0.0)
    except (TypeError, ValueError):
        current_time = 0.0
    try:
        duration = float(abs_row.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    fraction = max(0.0, min(1.0, fraction))
    if finished:
        fraction = 1.0
    elif duration > 0 and current_time > 0 and fraction <= 0:
        fraction = min(0.999, current_time / duration)

    ids = [_text(fid) for fid in file_ids if _text(fid)]
    if finished:
        return {
            "fraction": 1.0,
            "position": encode_listen_position(file_id=ids[0] if ids else "", seconds=0.0),
            "seconds": 0.0,
        }

    if len(ids) <= 1:
        fid = ids[0] if ids else ""
        return {
            "fraction": fraction,
            "position": encode_listen_position(file_id=fid, seconds=current_time),
            "seconds": current_time,
        }

    count = len(ids)
    # Equal-length file split. When ABS omits duration, infer it from
    # currentTime/progress so we keep mid-file seconds instead of zeroing.
    effective_duration = duration
    if effective_duration <= 0 and current_time > 0 and fraction > 0:
        effective_duration = current_time / fraction
    if effective_duration > 0 and current_time > 0:
        per = effective_duration / count
        index = min(count - 1, int(current_time / per) if per > 0 else 0)
        local_secs = max(0.0, current_time - (index * per))
    else:
        index = min(count - 1, int(fraction * count))
        # Still preserve absolute currentTime when we cannot split by duration.
        local_secs = max(0.0, current_time)
    return {
        "fraction": fraction,
        "position": encode_listen_position(file_id=ids[index], seconds=local_secs),
        "seconds": local_secs,
    }


def pull_abs_listen_progress(
    db: Database,
    settings: Any,
    *,
    user_id: str,
    work: Mapping[str, Any],
    files: Optional[Sequence[Mapping[str, Any]]] = None,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[AudiobookshelfClient] = None,
) -> Optional[Dict[str, Any]]:
    """Pull ABS progress into Librarian when opening Listen. Fail-soft."""
    from librarian.listen import decode_listen_position, should_write_listen_progress

    if _text(work.get("kind")) != KIND_AUDIOBOOK:
        return None
    item_id = _text(work.get("abs_item_id"))
    url = _text(getattr(settings, "audiobookshelf_url", ""))
    token = _text(getattr(settings, "audiobookshelf_api_token", ""))
    if not (item_id and url and token and user_id):
        return None

    existing = db.get_progress(user_id, str(work.get("id") or ""))
    local = decode_listen_position((existing or {}).get("position"))
    local_fraction = float((existing or {}).get("fraction") or 0.0)

    own_client = client is None
    abs_client = client or AudiobookshelfClient(url, token, transport=transport)
    try:
        abs_row = abs_client.get_media_progress(item_id)
        if not abs_row:
            return None
        try:
            duration = float(abs_row.get("duration") or 0.0)
        except (TypeError, ValueError):
            duration = 0.0
        if duration > 0:
            _ABS_DURATION[item_id] = duration

        abs_finished = bool(abs_row.get("isFinished"))
        try:
            abs_fraction = float(abs_row.get("progress") or 0.0)
        except (TypeError, ValueError):
            abs_fraction = 0.0
        try:
            abs_current = float(abs_row.get("currentTime") or 0.0)
        except (TypeError, ValueError):
            abs_current = 0.0

        if not should_adopt_abs_progress(
            local_fraction=local_fraction,
            local_seconds=local["seconds"],
            abs_fraction=abs_fraction,
            abs_current_time=abs_current,
            abs_finished=abs_finished,
        ):
            return None

        file_ids = [str(row.get("id") or "") for row in (files or [])]
        mapped = map_abs_progress_to_local(abs_row, file_ids=file_ids)
        if not should_write_listen_progress(
            ready=True,
            seconds=float(mapped.get("seconds") or 0.0),
            resume_seconds=local["seconds"],
            force=abs_finished or (local_fraction <= 0.001 and local["seconds"] < 1.0),
        ):
            return None

        return db.upsert_progress(
            user_id=user_id,
            work_id=str(work["id"]),
            position=str(mapped.get("position") or ""),
            fraction=float(mapped.get("fraction") or 0.0),
        )
    except AudiobookshelfError as error:
        logger.info("ABS progress pull skipped: %s", error)
        return None
    except Exception as error:  # noqa: BLE001 — fail-soft federation
        logger.info("ABS progress pull unexpected: %s", error)
        return None
    finally:
        if own_client:
            abs_client.close()


def push_abs_listen_progress(
    settings: Any,
    work: Mapping[str, Any],
    *,
    fraction: float = 0.0,
    position: str = "",
    finished: bool = False,
    force: bool = False,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[AudiobookshelfClient] = None,
) -> Dict[str, Any]:
    """Push Librarian listen progress to ABS. Throttled; fail-soft."""
    from librarian.listen import decode_listen_position

    if _text(work.get("kind")) != KIND_AUDIOBOOK:
        return {"ok": False, "skipped": True, "reason": "not_audiobook"}
    item_id = _text(work.get("abs_item_id"))
    url = _text(getattr(settings, "audiobookshelf_url", ""))
    token = _text(getattr(settings, "audiobookshelf_api_token", ""))
    if not (item_id and url and token):
        return {"ok": False, "skipped": True, "reason": "not_configured"}

    now = time.monotonic()
    if not force and not finished:
        last = _ABS_PUSH_AT.get(item_id, 0.0)
        if now - last < ABS_PUSH_MIN_INTERVAL_S:
            return {"ok": False, "skipped": True, "reason": "throttled"}

    decoded = decode_listen_position(position)
    frac = 1.0 if finished else max(0.0, min(1.0, float(fraction or 0.0)))
    duration = _ABS_DURATION.get(item_id, 0.0)
    if duration > 0 and frac > 0:
        current_time = frac * duration
    else:
        current_time = float(decoded.get("seconds") or 0.0)

    own_client = client is None
    abs_client = client or AudiobookshelfClient(url, token, transport=transport)
    try:
        abs_client.update_media_progress(
            item_id,
            current_time=current_time,
            progress=frac,
            duration=duration,
            is_finished=bool(finished) or frac >= 0.999,
        )
        _ABS_PUSH_AT[item_id] = now
        return {"ok": True, "skipped": False}
    except AudiobookshelfError as error:
        logger.info("ABS progress push skipped: %s", error)
        return {"ok": False, "skipped": False, "error": str(error)}
    except Exception as error:  # noqa: BLE001 — fail-soft federation
        logger.info("ABS progress push unexpected: %s", error)
        return {"ok": False, "skipped": False, "error": "unexpected"}
    finally:
        if own_client:
            abs_client.close()
