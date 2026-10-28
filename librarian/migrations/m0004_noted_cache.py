"""Schema version 4: processed New & noted source rows."""

from __future__ import annotations

import sqlite3

VERSION = 4
NAME = "noted_cache"


def apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS noted_cache (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            source_key TEXT NOT NULL,
            isbn13 TEXT,
            asin TEXT,
            title TEXT NOT NULL,
            author TEXT NOT NULL DEFAULT '',
            list_name TEXT NOT NULL,
            published_date TEXT NOT NULL,
            work_id TEXT,
            kind TEXT NOT NULL DEFAULT 'book',
            rank INTEGER,
            cover TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(source, list_name, published_date, source_key)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_noted_cache_list "
        "ON noted_cache(source, list_name, published_date)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_noted_cache_work ON noted_cache(work_id)")
