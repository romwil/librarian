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


_BOOK_N_PREFIX = re.compile(
    r"^(.+?),\s*Book\s+\d+\s*[-–—:]\s*(.+)$",
    re.IGNORECASE,
)
_TITLE_BRACKETS = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
_EDITION_NOISE = re.compile(
    r"\b("
    r"unabridged|abridged|remastered|expanded|deluxe|anniversary|"
    r"special\s+edition|limited\s+edition|collector'?s\s+edition|"
    r"edition"
    r")\b",
    re.IGNORECASE,
)
_AUTHOR_TOKENS = re.compile(r"[a-z0-9]+")


def _title_core(value: Any) -> str:
    """Strip bracketed notes and edition noise (``(Unabridged)``, ``Deluxe Edition``)."""
    text = _TITLE_BRACKETS.sub(" ", _text(value))
    text = _EDITION_NOISE.sub(" ", text)
    return " ".join(text.split())


def _title_match_keys(value: Any) -> set[str]:
    """Normed title keys: full, after last dash, series Book N suffix, long colon head."""
    raw = _text(value)
    if not raw:
        return set()
    keys: set[str] = set()
    variants = [raw]
    core = _title_core(raw)
    if core and core.casefold() != raw.casefold():
        variants.append(core)
    for variant in variants:
        full = _norm_name(variant)
        if full:
            keys.add(full)
        for sep in (" - ", " – ", " — "):
            if sep in variant:
                tail = _norm_name(_title_core(variant.rsplit(sep, 1)[-1]))
                if tail:
                    keys.add(tail)
        book_n = _BOOK_N_PREFIX.match(variant)
        if book_n:
            tail = _norm_name(_title_core(book_n.group(2)))
            if tail:
                keys.add(tail)
        if ":" in variant:
            head = _norm_name(_title_core(variant.split(":", 1)[0]))
            # Long heads only — short ones like "book" collide.
            if head and len(head) >= 8:
                keys.add(head)
    return keys


def _author_is_usable(value: Any) -> bool:
    """Reject empty / punctuation-only dump authors like ``^`` or ``-``."""
    return len(_norm_name(value)) >= 3


def _author_form(value: Any) -> Optional[tuple[str, str]]:
    """``(lastname, given_initials)`` — ``R. F. Kuang`` / ``Rebecca F. Kuang`` → ``(kuang, rf)``."""
    raw = _text(value)
    if not raw:
        return None
    if "," in raw:
        last, _, first = raw.partition(",")
        last_parts = _AUTHOR_TOKENS.findall(last.lower())
        first_parts = _AUTHOR_TOKENS.findall(first.lower())
        if not last_parts:
            return None
        last_name = last_parts[0]
        if len(last_name) < 2:
            return None
        initials = "".join(part[0] for part in first_parts if part)
        return (last_name, initials)
    parts = _AUTHOR_TOKENS.findall(raw.lower())
    if not parts:
        return None
    last_name = parts[-1]
    if len(last_name) < 2:
        return None
    initials = "".join(part[0] for part in parts[:-1] if part)
    return (last_name, initials)


def _author_forms_compatible(left: tuple[str, str], right: tuple[str, str]) -> bool:
    if left[0] != right[0]:
        return False
    a, b = left[1], right[1]
    if not a or not b:
        return False
    # Require multi-initial agreement (rf ↔ rf, rf ↔ r). A lone shared first
    # initial (John/Jane Smith → j) is too weak even with a title gate.
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return len(longer) >= 2 and longer.startswith(shorter)


def _authors_match(work_author: Any, item_author_names: Sequence[Any]) -> bool:
    key = _norm_name(work_author)
    if len(key) < 3:
        return False
    item_keys = {_norm_name(name) for name in item_author_names if _text(name)}
    if key in item_keys:
        return True
    for other in item_keys:
        if not other:
            continue
        shorter, longer = (key, other) if len(key) <= len(other) else (other, key)
        if len(shorter) >= 5 and shorter in longer:
            return True
    work_form = _author_form(work_author)
    if work_form is None:
        return False
    for name in item_author_names:
        other_form = _author_form(name)
        if other_form and _author_forms_compatible(work_form, other_form):
            return True
    return False


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
        except ValueError:
            # ABS library scan returns 200 text/plain "OK". Success with a non-JSON
            # body is still success — callers that need objects check isinstance.
            return None


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
        """Page ABS library items (500/page) so large libraries are not truncated."""
        lib_id = _text(library_id)
        if not lib_id:
            return []
        items: List[Dict[str, Any]] = []
        page = 0
        page_size = 500
        while page < 40:
            payload = self._get(f"api/libraries/{lib_id}/items?limit={page_size}&page={page}")
            batch: List[Dict[str, Any]] = []
            if isinstance(payload, dict) and isinstance(payload.get("results"), list):
                batch = [row for row in payload["results"] if isinstance(row, dict)]
            elif isinstance(payload, list):
                batch = [row for row in payload if isinstance(row, dict)]
            items.extend(batch)
            if len(batch) < page_size:
                break
            page += 1
        return items

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
    # ABS library list payloads often omit `authors[]` and only set authorName.
    author = _text(
        meta.get("author")
        or meta.get("authorName")
        or item.get("author")
        or item.get("authorName")
    )
    if author:
        names.append(author)
    return names


_ASIN_TOKEN = re.compile(r"^[A-Z0-9]{10}$")


def asin_match_key(value: Any) -> str:
    """10-character ASIN with a letter. ISBN-10 stays on the ISBN path."""
    text = re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()
    if not _ASIN_TOKEN.fullmatch(text):
        return ""
    if text.isdigit() or (text.endswith("X") and text[:-1].isdigit()):
        return ""
    if isbn_match_keys(text):
        return ""
    return text


def _item_meta(item: Mapping[str, Any]) -> Dict[str, Any]:
    media = item.get("media") if isinstance(item.get("media"), dict) else {}
    meta = media.get("metadata") if isinstance(media.get("metadata"), dict) else {}
    return meta if isinstance(meta, dict) else {}


def _item_isbns(item: Dict[str, Any]) -> List[str]:
    meta = _item_meta(item)
    return isbn_match_keys(
        meta.get("isbn"),
        meta.get("isbn13"),
        item.get("isbn"),
    )


def _item_asins(item: Dict[str, Any]) -> set[str]:
    meta = _item_meta(item)
    keys = {
        asin_match_key(meta.get("asin")),
        asin_match_key(item.get("asin")),
        asin_match_key(meta.get("isbn")),
        asin_match_key(item.get("isbn")),
    }
    return {key for key in keys if key}


def _work_asins(work: Mapping[str, Any]) -> set[str]:
    keys = {asin_match_key(work.get("asin")), asin_match_key(work.get("isbn"))}
    return {key for key in keys if key}


def match_item(work: Dict[str, Any], items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """ASIN, then ISBN, then title cores (+ author when usable).

    Title cores cover ABS series prefixes (``Series, Book 1 - Title``) and subtitles.
    Junk authors (``^``, ``-``, empty) allow a match only when exactly one ABS item
    shares a title core — still fail closed on ambiguous title-only piles.
    """
    work_asins = _work_asins(work)
    if work_asins:
        for item in items:
            if work_asins.intersection(_item_asins(item)):
                return item
    work_keys = set(isbn_match_keys(work.get("isbn"), work.get("asin")))
    if work_keys:
        for item in items:
            if work_keys.intersection(_item_isbns(item)):
                return item
    title_keys = _title_match_keys(work.get("title"))
    if not title_keys:
        return None
    candidates: List[Dict[str, Any]] = []
    for item in items:
        item_keys = _title_match_keys(_item_title(item))
        if title_keys.intersection(item_keys):
            candidates.append(item)
    if not candidates:
        return None
    if _author_is_usable(work.get("author")):
        for item in candidates:
            if _authors_match(work.get("author"), _item_authors(item)):
                return item
        return None
    if len(candidates) == 1:
        return candidates[0]
    return None


_ABS_CATALOG_LIMIT = 10000
_UNMATCHED_SAMPLE = 24


def abs_match_counts(db: Database) -> Dict[str, int]:
    works = db.list_works(kind="audiobook", limit=_ABS_CATALOG_LIMIT)
    matched = sum(1 for row in works if _text(row.get("abs_item_id")))
    audiobooks = len(works)
    return {"matched": matched, "audiobooks": audiobooks, "unmatched": max(0, audiobooks - matched)}


def _unmatched_sample(rows: Sequence[Mapping[str, Any]], *, limit: int = _UNMATCHED_SAMPLE) -> List[Dict[str, str]]:
    sample: List[Dict[str, str]] = []
    for row in rows[: max(0, int(limit))]:
        sample.append(
            {
                "id": _text(row.get("id")),
                "title": _text(row.get("title")),
                "author": _text(row.get("author")),
            }
        )
    return sample


def match_audiobooks(
    db: Database,
    settings: Settings,
    *,
    client: Optional[AudiobookshelfClient] = None,
    force: bool = False,
    scan_first: bool = False,
) -> Dict[str, Any]:
    """Match catalog audiobooks to ABS items. No token → no HTTP, no catalog load."""
    url = _text(getattr(settings, "audiobookshelf_url", ""))
    token = _text(getattr(settings, "audiobookshelf_api_token", ""))
    if not url or not token:
        return {
            "matched": 0,
            "audiobooks": 0,
            "updated": 0,
            "called": False,
            "unmatched": 0,
            "unmatched_sample": [],
        }
    counts = abs_match_counts(db)
    works = db.list_works(kind="audiobook", limit=_ABS_CATALOG_LIMIT)
    unmatched = [row for row in works if not _text(row.get("abs_item_id"))]
    if not unmatched and not force:
        return {
            **counts,
            "updated": 0,
            "called": False,
            "unmatched": 0,
            "unmatched_sample": [],
        }
    own_client = client is None
    abs_client = client or AudiobookshelfClient(url, token)
    updated = 0
    scanned: List[str] = []
    still: List[Dict[str, Any]] = list(unmatched)
    try:
        if scan_first:
            try:
                scanned = abs_client.scan_audiobook_libraries()
            except AudiobookshelfError as error:
                logger.info("ABS scan before match skipped: %s", error)
        items = abs_client.audiobook_items()
        still = []
        for work in unmatched:
            hit = match_item(work, items)
            if hit is None:
                still.append(work)
                continue
            item_id = _text(hit.get("id"))
            if not item_id:
                still.append(work)
                continue
            db.upsert_work({**work, "abs_item_id": item_id})
            updated += 1
    except AudiobookshelfError as error:
        logger.info("ABS match skipped: %s", error)
        leftover = [
            row
            for row in unmatched
            if not _text((db.get_work(_text(row.get("id"))) or {}).get("abs_item_id"))
        ]
        return {
            **abs_match_counts(db),
            "updated": updated,
            "called": True,
            "error": str(error),
            "unmatched": len(leftover),
            "unmatched_sample": _unmatched_sample(leftover),
            "scanned_libraries": scanned,
        }
    finally:
        if own_client:
            abs_client.close()
    return {
        **abs_match_counts(db),
        "updated": updated,
        "called": True,
        "unmatched": len(still),
        "unmatched_sample": _unmatched_sample(still),
        "scanned_libraries": scanned,
    }


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
    from librarian.listen import (
        decode_listen_position,
        prefer_lamp_bookmark,
        should_write_listen_progress,
    )

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

        kept = prefer_lamp_bookmark(
            local=existing,
            incoming={
                "position": str(mapped.get("position") or ""),
                "fraction": float(mapped.get("fraction") or 0.0),
            },
        )
        kept_pos = str(kept.get("position") or "")
        kept_frac = float(kept.get("fraction") or 0.0)
        if (
            existing
            and str(existing.get("position") or "") == kept_pos
            and abs(float(existing.get("fraction") or 0.0) - kept_frac) < 0.001
        ):
            return existing

        return db.upsert_progress(
            user_id=user_id,
            work_id=str(work["id"]),
            position=kept_pos,
            fraction=kept_frac,
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
