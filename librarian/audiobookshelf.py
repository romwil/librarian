"""Audiobookshelf HTTP match. Link Librarian audiobooks — do not replace Plex or music_root."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx

from librarian.config import Settings
from librarian.covers import DEFAULT_USER_AGENT
from librarian.db import Database
from librarian.identify import isbn_match_keys

logger = logging.getLogger(__name__)


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


class AudiobookshelfClient:
    def __init__(
        self,
        base_url: str,
        api_token: str,
        *,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.base_url = normalize_abs_url(base_url)
        self.api_token = _text(api_token)
        self._client = httpx.Client(timeout=30.0, transport=transport, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def configured(self) -> bool:
        return bool(self.base_url and self.api_token)

    def _headers(self) -> Dict[str, str]:
        return {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_token}",
        }

    def _get(self, path: str) -> Any:
        if not self.configured():
            return None
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        try:
            response = self._client.get(url, headers=self._headers())
        except httpx.HTTPError as error:
            raise AudiobookshelfError("Audiobookshelf could not be reached") from error
        if response.status_code in (401, 403):
            raise AudiobookshelfError("Audiobookshelf token was refused")
        if response.status_code >= 400:
            raise AudiobookshelfError(f"Audiobookshelf HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as error:
            raise AudiobookshelfError("Audiobookshelf returned non-JSON") from error

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
            media_type = _text(library.get("mediaType") or (library.get("settings") or {}).get("mediaType")).lower()
            if media_type and media_type not in {"book", "audiobook"}:
                continue
            lib_id = _text(library.get("id"))
            if not lib_id:
                continue
            items.extend(self.library_items(lib_id))
        return items


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
