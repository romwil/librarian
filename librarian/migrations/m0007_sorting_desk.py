"""Schema version 7: Sorting desk diagnosis cache and 24h batch undo."""

from __future__ import annotations

import sqlite3

VERSION = 7
NAME = "sorting_desk"


def apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS review_diagnosis (
            work_id TEXT PRIMARY KEY,
            problem TEXT NOT NULL DEFAULT '',
            path_clear INTEGER NOT NULL DEFAULT 0,
            collection_dump INTEGER NOT NULL DEFAULT 0,
            payload_count INTEGER NOT NULL DEFAULT 0,
            archive_count INTEGER NOT NULL DEFAULT 0,
            junk_count INTEGER NOT NULL DEFAULT 0,
            par2_count INTEGER NOT NULL DEFAULT 0,
            distinct_title_count INTEGER NOT NULL DEFAULT 0,
            folder_path TEXT NOT NULL DEFAULT '',
            diagnosis_json TEXT,
            updated_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_review_diagnosis_problem ON review_diagnosis(problem)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sorting_undo (
            id TEXT PRIMARY KEY,
            action TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            label TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            restored_at REAL,
            snapshot_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sorting_undo_created ON sorting_undo(created_at DESC)"
    )
