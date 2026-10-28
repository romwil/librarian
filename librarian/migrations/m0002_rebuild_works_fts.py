"""Schema version 2: rebuild ``works_fts`` from ``works``.

Older catalogs could drift (a crash between the works write and the FTS insert, or
rows written before the FTS table existed). One rebuild puts every work back in the
index with the same columns ``upsert_work`` writes.
"""

from __future__ import annotations

import sqlite3

VERSION = 2
NAME = "rebuild_works_fts"


def rebuild_works_fts(conn: sqlite3.Connection) -> int:
    conn.execute("DELETE FROM works_fts")
    cursor = conn.execute(
        """
        INSERT INTO works_fts (work_id, title, author, genre, description)
        SELECT id, COALESCE(title, ''), COALESCE(author, ''),
               COALESCE(genre, ''), COALESCE(description, '')
        FROM works
        """
    )
    return int(cursor.rowcount or 0)


def apply(conn: sqlite3.Connection) -> None:
    rebuild_works_fts(conn)
