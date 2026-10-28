"""Schema version 1: every table, index, and column the catalog had before numbered steps.

Frozen. New schema changes go in a new numbered step, never here. Every statement is
idempotent so a database created before ``PRAGMA user_version`` existed (version 0,
any subset of these columns) lands on exactly the same schema as a fresh one.
"""

from __future__ import annotations

import sqlite3
from typing import Dict, List

VERSION = 1
NAME = "baseline"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at REAL NOT NULL,
    last_login_at REAL,
    session_epoch INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS invites (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    created_by TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    expires_at REAL NOT NULL,
    redeemed_at REAL,
    redeemed_user_id TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS works (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    author TEXT,
    series_name TEXT,
    series_index TEXT,
    year INTEGER,
    isbn TEXT,
    mbid TEXT,
    description TEXT,
    publisher TEXT,
    genre TEXT,
    cover_path TEXT,
    folder_path TEXT,
    abs_item_id TEXT,
    synopsis_source TEXT,
    llm_blurb TEXT,
    atmosphere_path TEXT,
    art_attribution TEXT,
    review_state TEXT NOT NULL DEFAULT 'none',
    review_reason TEXT,
    music_state TEXT,
    indexer_guid TEXT,
    part_total INTEGER,
    part_style TEXT,
    part_base TEXT,
    part_origin INTEGER,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    work_id TEXT,
    path TEXT NOT NULL,
    filename TEXT NOT NULL,
    kind TEXT,
    size INTEGER,
    part INTEGER,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    work_id TEXT,
    nzo_id TEXT,
    status TEXT NOT NULL,
    indexer_guid TEXT,
    title TEXT,
    kind TEXT,
    requested_by TEXT,
    storage_path TEXT,
    error TEXT,
    sab_status TEXT,
    nzo_name TEXT,
    percent TEXT,
    bytes INTEGER,
    payload_json TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS shelves (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    shared INTEGER NOT NULL DEFAULT 0,
    UNIQUE(name, owner_user_id)
);
CREATE TABLE IF NOT EXISTS shelf_items (
    shelf_id TEXT NOT NULL,
    work_id TEXT NOT NULL,
    added_at REAL NOT NULL,
    PRIMARY KEY (shelf_id, work_id)
);
CREATE TABLE IF NOT EXISTS progress (
    user_id TEXT NOT NULL,
    work_id TEXT NOT NULL,
    position TEXT,
    fraction REAL NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL,
    PRIMARY KEY (user_id, work_id)
);
CREATE TABLE IF NOT EXISTS indexers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    base_url TEXT NOT NULL,
    token_set INTEGER NOT NULL DEFAULT 0,
    last_caps_at REAL,
    last_caps_ok INTEGER,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS works_fts USING fts5(
    work_id UNINDEXED,
    title,
    author,
    genre,
    description
);
CREATE INDEX IF NOT EXISTS idx_works_kind ON works(kind);
CREATE INDEX IF NOT EXISTS idx_works_review ON works(review_state);
CREATE INDEX IF NOT EXISTS idx_works_author ON works(author COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_works_kind_author ON works(kind, author COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_works_series ON works(series_name COLLATE NOCASE);
-- Hall / Stacks / facets gate on EXISTS (files.work_id = works.id); without this
-- index a ~20k-file catalog turns every browse into a multi-minute table scan.
CREATE INDEX IF NOT EXISTS idx_files_work_id ON files(work_id);
CREATE INDEX IF NOT EXISTS idx_jobs_nzo ON jobs(nzo_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE TABLE IF NOT EXISTS rss_feeds (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    kind TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_guid TEXT,
    last_error TEXT,
    last_poll_at REAL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS user_prefs (
    user_id TEXT PRIMARY KEY,
    ambient TEXT NOT NULL DEFAULT 'off',
    prefs_json TEXT,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS whispers (
    id TEXT PRIMARY KEY,
    work_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_whispers_work ON whispers(work_id, created_at DESC);
CREATE TABLE IF NOT EXISTS celebrations_seen (
    user_id TEXT NOT NULL,
    celebration_key TEXT NOT NULL,
    seen_at REAL NOT NULL,
    PRIMARY KEY (user_id, celebration_key)
);
CREATE TABLE IF NOT EXISTS user_notifications (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    payload_json TEXT,
    from_user_id TEXT,
    related_id TEXT,
    created_at REAL NOT NULL,
    seen_at REAL
);
CREATE INDEX IF NOT EXISTS idx_user_notifications_user
    ON user_notifications(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_notifications_unread
    ON user_notifications(user_id, seen_at);
CREATE INDEX IF NOT EXISTS idx_user_notifications_related
    ON user_notifications(user_id, kind, related_id);
CREATE TABLE IF NOT EXISTS notification_digest_queue (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    payload_json TEXT,
    related_id TEXT,
    period TEXT NOT NULL,
    created_at REAL NOT NULL,
    sent_at REAL
);
CREATE INDEX IF NOT EXISTS idx_notification_digest_pending
    ON notification_digest_queue(period, sent_at, user_id);
CREATE TABLE IF NOT EXISTS wanted (
    id TEXT PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    work_id TEXT,
    title TEXT,
    author TEXT,
    isbn TEXT,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    miss_streak INTEGER NOT NULL DEFAULT 0,
    next_search_at REAL NOT NULL,
    job_id TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wanted_due ON wanted(status, next_search_at);
CREATE INDEX IF NOT EXISTS idx_wanted_job ON wanted(job_id);
CREATE TABLE IF NOT EXISTS owned_slip_clearances (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT,
    shelf_work_id TEXT,
    reason TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_owned_slip_clearances_created
    ON owned_slip_clearances(created_at DESC);
CREATE TABLE IF NOT EXISTS indexer_kind_stats (
    host_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    searches INTEGER NOT NULL DEFAULT 0,
    hits INTEGER NOT NULL DEFAULT 0,
    empty INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    rate_limited INTEGER NOT NULL DEFAULT 0,
    last_spoken_at TEXT,
    last_hit_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (host_id, kind)
);
-- Releases that came back empty or would not convert. Identifiers only: never the
-- credential-bearing download URL.
CREATE TABLE IF NOT EXISTS bad_indexer_releases (
    host_id TEXT NOT NULL DEFAULT '',
    guid TEXT NOT NULL,
    wanted_id TEXT,
    reason TEXT NOT NULL,
    first_seen_at REAL NOT NULL,
    last_seen_at REAL NOT NULL,
    seen_count INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (host_id, guid)
);
CREATE INDEX IF NOT EXISTS idx_bad_indexer_releases_guid ON bad_indexer_releases(guid);
CREATE TABLE IF NOT EXISTS review_audit (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    work_id TEXT,
    wanted_id TEXT,
    job_id TEXT,
    guid TEXT,
    reason TEXT,
    detail_json TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_review_audit_work ON review_audit(work_id, created_at DESC);
CREATE TABLE IF NOT EXISTS review_suggestions (
    work_id TEXT PRIMARY KEY,
    outcome TEXT NOT NULL,
    suggestion_json TEXT,
    explanation TEXT,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS review_slip_cooldowns (
    folder_key TEXT PRIMARY KEY,
    signature TEXT NOT NULL,
    reason TEXT,
    until_at REAL NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS app_migrations (
    name TEXT PRIMARY KEY,
    finished_at REAL NOT NULL,
    report_json TEXT
);
"""


# Columns added after their table first shipped. Older databases got them via
# ALTER TABLE on boot; the baseline keeps doing that once, then records version 1.
EXTRA_COLUMNS: Dict[str, Dict[str, str]] = {
    "jobs": {
        "sab_status": "TEXT",
        "nzo_name": "TEXT",
        "percent": "TEXT",
        "bytes": "INTEGER",
    },
    "works": {
        "abs_item_id": "TEXT",
        "synopsis_source": "TEXT",
        "llm_blurb": "TEXT",
        "atmosphere_path": "TEXT",
        "art_attribution": "TEXT",
        "part_total": "INTEGER",
        "part_style": "TEXT",
        "part_base": "TEXT",
        "part_origin": "INTEGER",
        "repair_fail_count": "INTEGER",
        "asin": "TEXT",
        "narrator": "TEXT",
        "subtitle": "TEXT",
    },
    "files": {
        "part": "INTEGER",
    },
    "shelves": {
        "shared": "INTEGER NOT NULL DEFAULT 0",
    },
    "wanted": {
        "source": "TEXT",
    },
}


def split_statements(script: str) -> List[str]:
    """Split a SQL script into complete statements without committing (unlike executescript)."""
    statements: List[str] = []
    buffer = ""
    for line in script.splitlines(keepends=True):
        if not buffer and (not line.strip() or line.lstrip().startswith("--")):
            continue
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        statements.append(buffer.strip())
    return statements


def table_columns(conn: sqlite3.Connection, table: str) -> set:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_columns(conn: sqlite3.Connection) -> None:
    for table, columns in EXTRA_COLUMNS.items():
        existing = table_columns(conn, table)
        for name, decl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def apply(conn: sqlite3.Connection) -> None:
    for statement in split_statements(SCHEMA):
        conn.execute(statement)
    ensure_columns(conn)
