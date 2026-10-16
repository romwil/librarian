"""Local catalog pass: shelved books with no companion audiobook become Wanted.

This module does not talk to an indexer. A later shelved match deletes the row.
Dismissed rows stay dismissed until someone adds them again.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from librarian.audiobook_match import match_prepared_catalog, prepare_catalog_candidates
from librarian.db import Database
from librarian.kinds import KIND_AUDIOBOOK, KIND_BOOK
from librarian.wanted import STATUS_WANTED, dedupe_key


def sweep_wanted_audiobooks(db: Database, *, now: Optional[float] = None) -> int:
    """Mark every shelved book with no audiobook match as Wanted. Returns rows created."""
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
    created = 0
    for book in books:
        key = dedupe_key(kind=KIND_AUDIOBOOK, work_id=str(book.get("id") or ""))
        existing = known.get(key)
        if match_prepared_catalog(book, pool) is not None:
            if existing is not None:
                db.delete_wanted(str(existing["id"]))
                known.pop(key, None)
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
            }
        )
        known[key] = inserted
        created += 1
    return created
