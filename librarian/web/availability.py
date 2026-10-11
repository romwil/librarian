"""Attach companion Listen / Wanted onto catalog cards and work detail.

Browse already returns shelved works. A book also needs the existing companion
payload and any open or dismissed Wanted row so the card can say Listen or Wanted
without a second round trip.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from librarian.audiobook_match import companion_audiobook_payload
from librarian.db import Database
from librarian.wanted import dedupe_key, public_wanted


def _probe(work: Dict[str, Any]) -> str:
    return " ".join(
        part
        for part in (str(work.get("author") or "").strip(), str(work.get("title") or "").strip())
        if part
    ).strip() or str(work.get("series_name") or "").strip()


def wanted_for_book(db: Database, work: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Audiobook Wanted row for this shelved book, including a dismissal."""
    if str(work.get("kind") or "") != "book" or not str(work.get("id") or "").strip():
        return None
    key = dedupe_key(
        kind="audiobook",
        work_id=str(work.get("id") or ""),
        title=str(work.get("title") or ""),
        author=str(work.get("author") or ""),
        isbn=str(work.get("isbn") or ""),
    )
    row = db.get_wanted_by_dedupe(key)
    if row is None:
        return None
    return public_wanted(row)


def annotate_browse_availability(db: Database, items: List[Dict[str, Any]]) -> None:
    """Mutate public browse items with `audiobook` and `wanted` for books."""
    for item in items:
        if str(item.get("kind") or "") != "book" or not item.get("id"):
            continue
        probe = _probe(item)
        candidates = db.search_works(probe, limit=40, kind="audiobook") if probe else []
        item["audiobook"] = companion_audiobook_payload(item, audiobooks=candidates)
        wanted = wanted_for_book(db, item)
        if wanted is not None:
            item["wanted"] = wanted
