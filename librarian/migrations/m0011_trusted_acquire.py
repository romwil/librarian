"""Schema version 11: reader trusted-acquire flag (Search beyond + auto-confirm)."""

from __future__ import annotations

import sqlite3

VERSION = 11
NAME = "trusted_acquire"


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def apply(conn: sqlite3.Connection) -> None:
    if not _has_column(conn, "users", "trusted_acquire"):
        conn.execute(
            "ALTER TABLE users ADD COLUMN trusted_acquire INTEGER NOT NULL DEFAULT 0"
        )
