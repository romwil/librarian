"""Local catalog pass: shelved books with no companion audiobook become Wanted.

This module does not talk to an indexer. A later shelved match deletes the row.
Dismissed rows stay dismissed until someone adds them again.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from librarian.audiobook_match import match_companion_audiobook
from librarian.db import Database
from librarian.kinds import KIND_AUDIOBOOK, KIND_BOOK
from librarian.wanted import STATUS_WANTED, dedupe_key


def sweep_wanted_audiobooks(db: Database, *, now: Optional[float] = None) -> int:
    """Mark every shelved book with no audiobook match as Wanted. Returns rows created."""
    moment = time.time() if now is None else float(now)
    books = db.list_shelved_works(KIND_BOOK)
    audiobooks: List[Dict[str, Any]] = db.list_shelved_works(KIND_AUDIOBOOK)
    created = 0
    for book in books:
        key = dedupe_key(kind=KIND_AUDIOBOOK, work_id=str(book.get("id") or ""))
        existing = db.get_wanted_by_dedupe(key)
        if match_companion_audiobook(book, audiobooks) is not None:
            if existing is not None:
                db.delete_wanted(str(existing["id"]))
            continue
        if existing is not None:
            continue
        db.insert_wanted(
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
            }
        )
        created += 1
    return created
