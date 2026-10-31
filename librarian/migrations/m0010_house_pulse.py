"""Schema version 10: on-box House pulse aggregates (no member ids)."""

from __future__ import annotations

import sqlite3

VERSION = 10
NAME = "house_pulse"


def apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metrics_daily (
            day TEXT NOT NULL,
            version TEXT NOT NULL,
            metric TEXT NOT NULL,
            dim TEXT NOT NULL DEFAULT '',
            count INTEGER NOT NULL DEFAULT 0,
            sum_ms INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (day, version, metric, dim)
        )
        """
    )
