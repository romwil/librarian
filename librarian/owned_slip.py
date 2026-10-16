"""Drop Holds slips when the house already has that title on the shelf.

Matching follows the companion matcher: ISBN first, then exact title+author,
then series name + index. Fail closed — title alone never matches. A slip is
cleared only when a different catalog row has a real file (book, audiobook,
magazine, or comic). The shelved work and its files stay. An unfinished
archive that is not yet a shelved work stays on the desk for Repair / Retry.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

from librarian.db import Database
from librarian.identify import isbn_match_keys
from librarian.kinds import KIND_AUDIOBOOK, KIND_BOOK, KIND_COMIC, KIND_MAGAZINE

ALREADY_ON_SHELF = "Already on the shelf"
OWNED_KINDS = (KIND_BOOK, KIND_AUDIOBOOK, KIND_MAGAZINE, KIND_COMIC)
NOTE_WINDOW_S = 7 * 24 * 3600
SWEEP_LIMIT = 8000
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _norm_name(value: Any) -> str:
    return _NON_ALNUM.sub("", str(value or "").lower())


def _index_key(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text.lower()


class _OwnedCatalog:
    """First-wins indexes so a sweep matches in one pass, not slips × shelves."""

    def __init__(self) -> None:
        self.by_isbn: Dict[str, tuple] = {}
        self.by_title_author: Dict[tuple, Dict[str, Any]] = {}
        self.by_series: Dict[tuple, Dict[str, Any]] = {}

    @classmethod
    def build(cls, owned: Sequence[Mapping[str, Any]]) -> "_OwnedCatalog":
        catalog = cls()
        for rank, row in enumerate(owned):
            if str(row.get("kind") or "") not in OWNED_KINDS:
                continue
            stored = dict(row)
            for key in isbn_match_keys(str(row.get("isbn") or "")):
                catalog.by_isbn.setdefault(key, (rank, stored))
            title_key = _norm_name(row.get("title"))
            author_key = _norm_name(row.get("author"))
            if title_key and author_key:
                catalog.by_title_author.setdefault((title_key, author_key), stored)
            series = _norm_name(row.get("series_name"))
            index = _index_key(row.get("series_index"))
            if series and index:
                catalog.by_series.setdefault((series, index), stored)
        return catalog

    def match(self, slip: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        want_isbn = isbn_match_keys(str(slip.get("isbn") or ""))
        if want_isbn:
            best: Optional[tuple] = None
            for key in want_isbn:
                hit = self.by_isbn.get(key)
                if hit is None:
                    continue
                if best is None or hit[0] < best[0]:
                    best = hit
            if best is not None:
                return dict(best[1])
        title_key = _norm_name(slip.get("title"))
        author_key = _norm_name(slip.get("author"))
        if title_key and author_key:
            row = self.by_title_author.get((title_key, author_key))
            if row is not None:
                return dict(row)
        series = _norm_name(slip.get("series_name"))
        index = _index_key(slip.get("series_index"))
        if series and index:
            row = self.by_series.get((series, index))
            if row is not None:
                return dict(row)
        return None


def match_owned_media(
    slip: Mapping[str, Any],
    owned: Sequence[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Pick a shelved work this slip duplicates. None when unsure."""
    slip_id = str(slip.get("id") or "")
    rows = [row for row in owned if str(row.get("id") or "") != slip_id]
    return _OwnedCatalog.build(rows).match(slip)


def owned_media_rows(db: Database) -> List[Dict[str, Any]]:
    """Shelved book, audiobook, magazine, and comic works that have a file."""
    rows: List[Dict[str, Any]] = []
    for kind in OWNED_KINDS:
        for work in db.list_shelved_works(kind):
            if str(work.get("review_state") or "") == "needs_review":
                continue
            rows.append(work)
    return rows


def format_owned_slip_note(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return ""
    labels: List[str] = []
    for row in rows:
        title = str(row.get("title") or "").strip() or "Untitled"
        author = str(row.get("author") or "").strip()
        labels.append(f"{title} — {author}" if author else title)
    shown = labels[:8]
    extra = len(labels) - len(shown)
    body = ", ".join(shown)
    if extra:
        body += f", and {extra} more"
    return f"Already on the shelf — cleared {body}."


def owned_slip_note(db: Database, *, now: Optional[float] = None) -> str:
    moment = time.time() if now is None else float(now)
    rows = db.list_owned_slip_clearances(since=moment - NOTE_WINDOW_S, limit=12)
    return format_owned_slip_note(rows)


def _drop_owned_slip(
    db: Database,
    slip: Mapping[str, Any],
    owned: Sequence[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Delete one open slip that matches owned media. Leave the shelf alone."""
    hit = match_owned_media(slip, owned)
    if hit is None:
        return None
    return _drop_matched_slip(db, slip, hit)


def _drop_matched_slip(
    db: Database,
    slip: Mapping[str, Any],
    hit: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    if str(slip.get("review_state") or "") != "needs_review":
        return None
    slip_id = str(slip.get("id") or "")
    if not slip_id or db.files_for_work(slip_id):
        return None
    shelf_id = str(hit.get("id") or "")
    shelf = db.get_work(shelf_id)
    if shelf is None or str(shelf.get("review_state") or "") == "needs_review":
        return None
    if not db.files_for_work(shelf_id):
        return None
    if not db.delete_work(slip_id):
        return None
    if db.get_work(shelf_id) is None:
        return None
    db.record_owned_slip_clearance(
        title=str(slip.get("title") or ""),
        author=str(slip.get("author") or ""),
        shelf_work_id=shelf_id,
        reason=ALREADY_ON_SHELF,
    )
    return {
        "id": slip_id,
        "title": slip.get("title") or "",
        "author": slip.get("author") or "",
        "reason": ALREADY_ON_SHELF,
        "shelf_work_id": shelf_id,
        "work": shelf,
    }


def sweep_owned_slips(db: Database, *, limit: int = SWEEP_LIMIT) -> Dict[str, Any]:
    """Clear open slips the catalog already owns. Returns the desk note."""
    owned, slips = db.load_owned_slip_sweep(kinds=OWNED_KINDS, limit=max(1, int(limit)))
    catalog = _OwnedCatalog.build(owned)
    cleared: List[Dict[str, Any]] = []
    for slip in slips:
        hit = catalog.match(slip)
        if hit is None:
            continue
        dropped = _drop_matched_slip(db, slip, hit)
        if dropped is not None:
            cleared.append(
                {
                    "id": dropped["id"],
                    "title": dropped["title"],
                    "author": dropped["author"],
                    "reason": dropped["reason"],
                    "shelf_work_id": dropped["shelf_work_id"],
                }
            )
    return {"cleared": cleared, "note": owned_slip_note(db)}


def release_slip_already_on_shelf(
    db: Database,
    work: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    """Close a slip that was just parked because the title is already shelved."""
    dropped = _drop_owned_slip(db, work, owned_media_rows(db))
    if dropped is None:
        return None
    return {
        "work": dropped["work"],
        "already_on_shelf": True,
        "reason": ALREADY_ON_SHELF,
    }
