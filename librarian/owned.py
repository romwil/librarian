"""Which book and audiobook formats the house already has on the shelves.

Matching is the companion matcher: ISBN when both sides have one, then the same
author with an equal title or a subtitle, then series+index. A title with no
author and no ISBN is not a match. A shared word is not a match.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from librarian.audiobook_match import match_catalog_work, match_companion_audiobook
from librarian.covers import cover_file_ok

BOOK = "book"
AUDIOBOOK = "audiobook"


def _stub(row: Optional[Mapping[str, Any]], *, kind: str) -> Optional[Dict[str, Any]]:
    if not row or not str(row.get("id") or "").strip():
        return None
    return {
        "id": row.get("id"),
        "title": row.get("title") or "",
        "author": row.get("author") or "",
        "kind": kind,
        "has_cover": cover_file_ok(row) if row.get("cover_path") else bool(row.get("has_cover")),
    }


def _probe(item: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "kind": BOOK,
        "title": item.get("title") or "",
        "author": item.get("author") or "",
        "isbn": item.get("isbn") or "",
        "series_name": item.get("series_name") or item.get("series") or "",
        "series_index": item.get("series_index") or "",
    }


class ShelfIndex:
    """Shelved books and audiobooks, loaded once per request."""

    def __init__(self, db: Any) -> None:
        self.books: List[Dict[str, Any]] = list(db.list_shelved_works(BOOK)) if db is not None else []
        self.audiobooks: List[Dict[str, Any]] = (
            list(db.list_shelved_works(AUDIOBOOK)) if db is not None else []
        )

    def pair(self, item: Mapping[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        probe = _probe(item)
        book = _stub(match_catalog_work(probe, self.books), kind=BOOK)
        audio = _stub(match_companion_audiobook(probe, self.audiobooks), kind=AUDIOBOOK)
        return book, audio

    def of_kind(self, item: Mapping[str, Any], kind: str) -> Optional[Dict[str, Any]]:
        book, audio = self.pair(item)
        if kind == BOOK:
            return book
        if kind == AUDIOBOOK:
            return audio
        return None

    def by_id(self, kind: str, work_id: str) -> Optional[Dict[str, Any]]:
        wanted = str(work_id or "").strip()
        if not wanted:
            return None
        pool = self.books if kind == BOOK else self.audiobooks if kind == AUDIOBOOK else []
        for row in pool:
            if str(row.get("id") or "") == wanted:
                return _stub(row, kind=kind)
        return None


def _owned_kinds(book: Optional[Mapping[str, Any]], audio: Optional[Mapping[str, Any]]) -> List[str]:
    kinds: List[str] = []
    if book and book.get("id"):
        kinds.append(BOOK)
    if audio and audio.get("id"):
        kinds.append(AUDIOBOOK)
    return kinds


def annotate_noted_lanes(db: Any, lanes: Sequence[Mapping[str, Any]]) -> None:
    """Set shelved book and audiobook stubs on every noted card."""
    index = ShelfIndex(db)
    for lane in lanes:
        items = lane.get("items") if isinstance(lane, Mapping) else None
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            book, audio = index.pair(item)
            item["shelved"] = book
            item["shelved_audiobook"] = audio
            owned = _owned_kinds(book, audio)
            wanted = item.get("wanted")
            if isinstance(wanted, dict):
                current = wanted.get("kinds")
                if isinstance(current, list):
                    wanted["kinds"] = [kind for kind in current if kind not in owned]
                else:
                    wanted["kinds"] = [kind for kind in (BOOK, AUDIOBOOK) if kind not in owned]
            if item.get("source") == "llm":
                item["companion_note"] = (
                    "Companion audiobook is on the shelf." if audio else "No companion audiobook on the shelf."
                )


def annotate_wanted_row(
    row: Mapping[str, Any],
    index: ShelfIndex,
    *,
    work: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Copy a public Wanted row and attach the shelved book and audiobook, if any."""
    item = dict(row)
    probe = dict(item)
    if work:
        if not str(probe.get("series_name") or "").strip():
            probe["series_name"] = work.get("series_name") or ""
        if not str(probe.get("series_index") or "").strip():
            probe["series_index"] = work.get("series_index") or ""
        if not str(probe.get("isbn") or "").strip():
            probe["isbn"] = work.get("isbn") or ""
        if not str(probe.get("title") or "").strip():
            probe["title"] = work.get("title") or ""
        if not str(probe.get("author") or "").strip():
            probe["author"] = work.get("author") or ""
    book, audio = index.pair(probe)
    kind = str(item.get("kind") or "")
    direct = index.by_id(kind, str(item.get("work_id") or ""))
    if kind == BOOK and direct:
        book = direct
    elif kind == AUDIOBOOK and direct:
        audio = direct
    item["shelved_book"] = book
    item["shelved_audiobook"] = audio
    if kind == BOOK:
        item["shelved"] = book
    elif kind == AUDIOBOOK:
        item["shelved"] = audio
    else:
        item["shelved"] = None
    return item
