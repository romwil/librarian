"""Schema version 6: household indexer call ledger for daily host budgets."""

from __future__ import annotations

import sqlite3

VERSION = 6
NAME = "provider_calls"


def apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_calls (
            day TEXT NOT NULL,
            provider TEXT NOT NULL,
            host TEXT NOT NULL,
            purpose TEXT NOT NULL,
            calls INTEGER NOT NULL DEFAULT 0,
            errors INTEGER NOT NULL DEFAULT 0,
            rate_limited INTEGER NOT NULL DEFAULT 0,
            wanted_cap INTEGER,
            PRIMARY KEY (day, provider, host, purpose)
        )
        """
    )
