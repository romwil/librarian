"""Local catalog pass: shelved fiction books with no companion audiobook become Wanted.

This module does not talk to an indexer. A later shelved match deletes the row.
Dismissed rows stay dismissed until someone restores them (30 days) or adds them
again. Only fiction is auto-wanted. Nonfiction wins inside ``classify_genre``;
unknown genres are skipped. Open sweep rows never exceed ``OPEN_SWEEP_CAP``.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from librarian.audiobook_match import match_prepared_catalog, prepare_catalog_candidates
from librarian.db import Database
from librarian.fiction import classify_genre
from librarian.kinds import KIND_AUDIOBOOK, KIND_BOOK
from librarian.wanted import SOURCE_SWEEP, STATUS_WANTED, dedupe_key, wanted_source

# PRD-006: cap open sweep-generated rows. Owner-added wants do not count.
OPEN_SWEEP_CAP = 200


def _source(row: Dict[str, Any]) -> str:
    return wanted_source(row)


def _untouched(row: Dict[str, Any]) -> bool:
    """Still wanted, and no queue job has been attached."""
    if str(row.get("status") or "") != STATUS_WANTED:
        return False
    return not str(row.get("job_id") or "").strip()


def _drop(db: Database, known: Dict[str, Dict[str, Any]], key: str, row: Dict[str, Any]) -> None:
    db.delete_wanted(str(row["id"]))
    known.pop(key, None)


def _open_sweep_count(known: Dict[str, Dict[str, Any]]) -> int:
    return sum(
        1
        for row in known.values()
        if str(row.get("status") or "") != "dismissed" and _source(row) == SOURCE_SWEEP
    )


def _rank_key(book: Dict[str, Any], last_read: Dict[str, float]) -> Tuple[float, float]:
    work_id = str(book.get("id") or "")
    return (float(last_read.get(work_id) or 0), float(book.get("updated_at") or 0))


def _clear_unsourced_nonfiction(
    db: Database,
    books: List[Dict[str, Any]],
    known: Dict[str, Dict[str, Any]],
) -> None:
    """One-time cleanup of older audiobook rows that have no source yet.

    Removes status=wanted, job_id NULL rows whose shelved book is nonfiction or
    unknown. Rows with a job, a source, or a dismissed status stay.
    """
    by_id = {str(book.get("id") or ""): book for book in books}
    for key, row in list(known.items()):
        stored = str(row.get("source") or "").strip().lower()
        if stored:
            continue
        if str(row.get("kind") or "") != KIND_AUDIOBOOK:
            continue
        if not _untouched(row):
            continue
        book = by_id.get(str(row.get("work_id") or ""))
        if book is None:
            continue
        if classify_genre(str(book.get("genre") or "")) in ("nonfiction", "unknown"):
            _drop(db, known, key, row)


def sweep_wanted_audiobooks(
    db: Database,
    *,
    now: Optional[float] = None,
    created_ids: Optional[List[str]] = None,
    cap: int = OPEN_SWEEP_CAP,
) -> int:
    """Mark shelved fiction books with no audiobook match as Wanted, up to the cap.

    Returns rows created, and appends their ids to ``created_ids`` so the caller
    can search them right away. Untouched sweep rows whose book is no longer
    fiction are deleted. Dismissed rows still block re-creation. Owner-added
    wants are never dropped to make room.
    """
    moment = time.time() if now is None else float(now)
    limit = max(0, int(cap))
    books = db.list_shelved_works(KIND_BOOK)
    audiobooks: List[Dict[str, Any]] = db.list_shelved_works(KIND_AUDIOBOOK)
    pool = prepare_catalog_candidates(
        [row for row in audiobooks if str(row.get("kind") or "") in ("", "audiobook")]
    )
    known = {
        str(row.get("dedupe_key") or ""): row
        for row in db.list_wanted(include_dismissed=True)
    }
    _clear_unsourced_nonfiction(db, books, known)
    last_read = db.latest_progress_by_work()
    candidates: List[Dict[str, Any]] = []
    for book in books:
        key = dedupe_key(kind=KIND_AUDIOBOOK, work_id=str(book.get("id") or ""))
        existing = known.get(key)
        if match_prepared_catalog(book, pool) is not None:
            if existing is not None:
                _drop(db, known, key, existing)
            continue
        if classify_genre(str(book.get("genre") or "")) != "fiction":
            if existing is not None and _untouched(existing) and _source(existing) == SOURCE_SWEEP:
                _drop(db, known, key, existing)
            continue
        if existing is not None:
            continue
        candidates.append(book)
    candidates.sort(key=lambda book: _rank_key(book, last_read), reverse=True)
    room = max(0, limit - _open_sweep_count(known))
    created = 0
    for book in candidates[:room]:
        key = dedupe_key(kind=KIND_AUDIOBOOK, work_id=str(book.get("id") or ""))
        inserted = db.insert_wanted(
            {
                "dedupe_key": key,
                "work_id": book.get("id"),
                "title": book.get("title") or "",
                "author": book.get("author") or "",
                "isbn": book.get("isbn") or "",
                "kind": KIND_AUDIOBOOK,
                "status": STATUS_WANTED,
                "miss_streak": 0,
                "next_search_at": moment,
                "created_at": moment,
                "updated_at": moment,
                "source": SOURCE_SWEEP,
            }
        )
        known[key] = inserted
        created += 1
        if created_ids is not None and inserted.get("id"):
            created_ids.append(str(inserted["id"]))
    return created
