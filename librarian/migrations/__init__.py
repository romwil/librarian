"""Numbered SQLite schema steps tracked by ``PRAGMA user_version``.

Each step runs once, in order, inside one ``BEGIN IMMEDIATE`` transaction with the
version bump, so a crash leaves the database on the last fully applied step and two
processes booting together cannot both run the same step.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Callable, List, Tuple

from librarian.migrations import (
    m0001_baseline,
    m0002_rebuild_works_fts,
    m0003_canonical_works,
    m0004_noted_cache,
    m0005_guest_accounts,
    m0006_provider_calls,
    m0007_sorting_desk,
)

logger = logging.getLogger("librarian.migrations")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


MIGRATIONS: Tuple[Migration, ...] = (
    Migration(m0001_baseline.VERSION, m0001_baseline.NAME, m0001_baseline.apply),
    Migration(
        m0002_rebuild_works_fts.VERSION,
        m0002_rebuild_works_fts.NAME,
        m0002_rebuild_works_fts.apply,
    ),
    Migration(
        m0003_canonical_works.VERSION,
        m0003_canonical_works.NAME,
        m0003_canonical_works.apply,
    ),
    Migration(m0004_noted_cache.VERSION, m0004_noted_cache.NAME, m0004_noted_cache.apply),
    Migration(m0005_guest_accounts.VERSION, m0005_guest_accounts.NAME, m0005_guest_accounts.apply),
    Migration(
        m0006_provider_calls.VERSION, m0006_provider_calls.NAME, m0006_provider_calls.apply
    ),
    Migration(m0007_sorting_desk.VERSION, m0007_sorting_desk.NAME, m0007_sorting_desk.apply),
)
LATEST_VERSION = MIGRATIONS[-1].version


def schema_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def pending_migrations(conn: sqlite3.Connection) -> List[Migration]:
    current = schema_version(conn)
    return [step for step in MIGRATIONS if step.version > current]


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Apply every pending step and return the resulting ``user_version``."""
    current = schema_version(conn)
    if current > LATEST_VERSION:
        logger.warning(
            "Database schema version %s is newer than this build (%s); leaving it as is",
            current,
            LATEST_VERSION,
        )
        return current
    if current == LATEST_VERSION:
        return current
    conn.execute("BEGIN IMMEDIATE")
    try:
        for step in pending_migrations(conn):
            logger.info("Applying schema step %s (%s)", step.version, step.name)
            step.apply(conn)
            conn.execute(f"PRAGMA user_version = {int(step.version)}")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return schema_version(conn)


__all__ = [
    "LATEST_VERSION",
    "MIGRATIONS",
    "Migration",
    "apply_migrations",
    "pending_migrations",
    "schema_version",
]
