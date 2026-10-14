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


def _norm_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _index_key(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text.lower()


def match_owned_media(
    slip: Mapping[str, Any],
    owned: Sequence[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Pick a shelved work this slip duplicates. None when unsure."""
    slip_id = str(slip.get("id") or "")
    rows = [row for row in owned if str(row.get("id") or "") != slip_id]
    want_isbn = set(isbn_match_keys(str(slip.get("isbn") or "")))
    if want_isbn:
        for row in rows:
            if str(row.get("kind") or "") not in OWNED_KINDS:
                continue
            if want_isbn.intersection(isbn_match_keys(str(row.get("isbn") or ""))):
                return dict(row)
    title_key = _norm_name(slip.get("title"))
    author_key = _norm_name(slip.get("author"))
    if title_key and author_key:
        for row in rows:
            if str(row.get("kind") or "") not in OWNED_KINDS:
                continue
            if _norm_name(row.get("title")) != title_key:
                continue
            if _norm_name(row.get("author")) == author_key:
                return dict(row)
    series = _norm_name(slip.get("series_name"))
    index = _index_key(slip.get("series_index"))
    if series and index:
        for row in rows:
            if str(row.get("kind") or "") not in OWNED_KINDS:
                continue
            if _norm_name(row.get("series_name")) != series:
                continue
            if _index_key(row.get("series_index")) == index:
                return dict(row)
    return None


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
    if str(slip.get("review_state") or "") != "needs_review":
        return None
    slip_id = str(slip.get("id") or "")
    if not slip_id or db.files_for_work(slip_id):
        return None
    hit = match_owned_media(slip, owned)
    if hit is None:
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
    owned = owned_media_rows(db)
    slips = db.list_works(review_state="needs_review", limit=max(1, int(limit)))
    cleared: List[Dict[str, Any]] = []
    for slip in slips:
        dropped = _drop_owned_slip(db, slip, owned)
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
