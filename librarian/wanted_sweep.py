"""Local catalog pass: shelved fiction books with no companion audiobook become Wanted.

This module does not talk to an indexer. A later shelved match deletes the row.
Dismissed rows stay dismissed until someone adds them again. Only fiction is
auto-wanted. Nonfiction wins inside ``classify_genre``; unknown genres are skipped.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from librarian.audiobook_match import match_prepared_catalog, prepare_catalog_candidates
from librarian.db import Database
from librarian.fiction import classify_genre
from librarian.kinds import KIND_AUDIOBOOK, KIND_BOOK
from librarian.wanted import STATUS_WANTED, dedupe_key


def _source(row: Dict[str, Any]) -> str:
    return str(row.get("source") or "").strip().lower()


def _untouched(row: Dict[str, Any]) -> bool:
    """Still wanted, and no queue job has been attached."""
    if str(row.get("status") or "") != STATUS_WANTED:
        return False
    return not str(row.get("job_id") or "").strip()


def _drop(db: Database, known: Dict[str, Dict[str, Any]], key: str, row: Dict[str, Any]) -> None:
    db.delete_wanted(str(row["id"]))
    known.pop(key, None)


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
        if _source(row):
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


def sweep_wanted_audiobooks(db: Database, *, now: Optional[float] = None) -> int:
    """Mark every shelved fiction book with no audiobook match as Wanted.

    Returns rows created. Untouched sweep rows whose book is no longer fiction
    are deleted. Dismissed rows still block re-creation.
    """
    moment = time.time() if now is None else float(now)
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
    created = 0
    for book in books:
        key = dedupe_key(kind=KIND_AUDIOBOOK, work_id=str(book.get("id") or ""))
        existing = known.get(key)
        if match_prepared_catalog(book, pool) is not None:
            if existing is not None:
                _drop(db, known, key, existing)
            continue
        if classify_genre(str(book.get("genre") or "")) != "fiction":
            if existing is not None and _untouched(existing) and _source(existing) == "sweep":
                _drop(db, known, key, existing)
            continue
        if existing is not None:
            continue
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
                "source": "sweep",
            }
        )
        known[key] = inserted
        created += 1
    return created
