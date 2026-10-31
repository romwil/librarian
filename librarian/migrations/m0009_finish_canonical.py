"""Schema version 9: backfill m0003 authors, editions, and identifiers.

Existing catalogs that ran ``m0003`` schema-only get one work_authors row (and a
primary edition when ISBN/folder/cover exist) per work. Reader paths can then
stop treating ``works.author`` as a second source of truth.
"""

from __future__ import annotations

import sqlite3

from librarian.canonical import backfill_canonical

VERSION = 9
NAME = "finish_canonical"


def apply(conn: sqlite3.Connection) -> None:
    backfill_canonical(conn)
