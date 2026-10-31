"""Schema version 5: sessions, password resets, security events, disabled cards.

Foreign keys on the new tables so member delete can cascade. Existing user-id
columns are still walked in application code (they predate numbered FKs).
"""

from __future__ import annotations

import sqlite3

VERSION = 5
NAME = "guest_accounts"


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def apply(conn: sqlite3.Connection) -> None:
    if not _has_column(conn, "users", "disabled"):
        conn.execute("ALTER TABLE users ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at REAL NOT NULL,
            last_seen_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            revoked_at REAL,
            user_agent TEXT NOT NULL DEFAULT '',
            ip TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, revoked_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS password_resets (
            id TEXT PRIMARY KEY,
            token_hash TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_by TEXT NOT NULL,
            expires_at REAL NOT NULL,
            used_at REAL,
            created_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_password_resets_user ON password_resets(user_id, used_at)"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS security_events (
            id TEXT PRIMARY KEY,
            at REAL NOT NULL,
            user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
            actor_id TEXT REFERENCES users(id) ON DELETE SET NULL,
            kind TEXT NOT NULL,
            detail_json TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_security_events_at ON security_events(at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_security_events_user ON security_events(user_id, at)")
