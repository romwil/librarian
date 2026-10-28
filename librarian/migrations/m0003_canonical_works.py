"""Schema version 3: canonical works, editions, identifiers, and authors.

This step is intentionally schema-only. Existing catalog rows are neither backfilled
nor merged here; later cleanup work owns those data changes.
"""

from __future__ import annotations

import sqlite3

VERSION = 3
NAME = "canonical_works"


def apply(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS editions (
            id TEXT PRIMARY KEY,
            work_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            isbn13 TEXT,
            asin TEXT,
            publisher TEXT,
            year INTEGER,
            format TEXT,
            folder_path TEXT,
            cover_path TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_editions_work_id ON editions(work_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_editions_isbn13 ON editions(isbn13)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_editions_asin ON editions(asin)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS work_identifiers (
            scheme TEXT NOT NULL,
            value TEXT NOT NULL,
            work_id TEXT NOT NULL,
            PRIMARY KEY (scheme, value)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_work_identifiers_work_id ON work_identifiers(work_id)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS authors (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            sort_name TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS author_aliases (
            alias TEXT NOT NULL COLLATE NOCASE PRIMARY KEY,
            author_id TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_author_aliases_author_id ON author_aliases(author_id)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS work_authors (
            work_id TEXT NOT NULL,
            author_id TEXT NOT NULL,
            PRIMARY KEY (work_id, author_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_work_authors_author_id ON work_authors(author_id)")

    works_columns = {row[1] for row in conn.execute("PRAGMA table_info(works)")}
    for name, declaration in (
        ("title_sort", "TEXT"),
        ("author_sort", "TEXT"),
        ("metadata_locked", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if name not in works_columns:
            conn.execute(f"ALTER TABLE works ADD COLUMN {name} {declaration}")

    files_columns = {row[1] for row in conn.execute("PRAGMA table_info(files)")}
    if "sha256" not in files_columns:
        conn.execute("ALTER TABLE files ADD COLUMN sha256 TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_files_sha256 ON files(sha256)")
