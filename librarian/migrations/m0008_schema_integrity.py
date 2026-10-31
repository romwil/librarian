"""Schema version 8: catalog foreign keys, identity indexes, and FTS triggers.

SQLite cannot add ``REFERENCES`` with ``ALTER TABLE``, so child tables are rebuilt
in place. Orphan ``work_id`` rows are cleared first so the new constraints can
enable. ``works_fts`` is kept in sync by triggers after this step (ARCH-016/025/026).
Runs after ``m0007_sorting_desk`` so ``review_diagnosis`` is included in the rebuild.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Iterable, Sequence

VERSION = 8
NAME = "schema_integrity"

logger = logging.getLogger("librarian.migrations")

# Child tables whose work_id (or author_id) must point at a live parent.
_CASCADE_WORK_TABLES = (
    "files",
    "editions",
    "work_identifiers",
    "work_authors",
    "shelf_items",
    "progress",
    "whispers",
    "review_suggestions",
    "review_diagnosis",
)
# jobs/owned_slip_clearances are live associations. wanted.work_id can name a
# companion that is not on the shelf yet; review_audit and noted_cache keep
# historical ids after the work is gone — those tables must not grow FKs.
_SET_NULL_WORK_TABLES = (
    ("jobs", "work_id"),
    ("owned_slip_clearances", "shelf_work_id"),
)


def _column_names(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def _column_sql(conn: sqlite3.Connection, table: str) -> tuple[str, str]:
    """Return ``(column_defs, table_pk_clause)`` matching the live table."""
    rows = list(conn.execute(f"PRAGMA table_info({table})"))
    defs: list[str] = []
    pks: list[str] = []
    for _cid, name, ctype, notnull, dflt, is_pk in rows:
        piece = f"{name} {ctype}" if ctype else str(name)
        if notnull:
            piece += " NOT NULL"
        if dflt is not None:
            piece += f" DEFAULT {dflt}"
        defs.append(piece)
        if is_pk:
            pks.append(str(name))
    pk_sql = ""
    if len(pks) > 1:
        pk_sql = f", PRIMARY KEY ({', '.join(pks)})"
    elif len(pks) == 1:
        # Composite-style PK clause even for one column so we can add FKs beside it.
        pk_sql = f", PRIMARY KEY ({pks[0]})"
    return ", ".join(defs), pk_sql


def _named_indexes(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT sql FROM sqlite_master
        WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL
        """,
        (table,),
    ).fetchall()
    return [str(row[0]) for row in rows if row[0]]


_EXPLICIT_NEW_SQL = {
    "author_aliases": """
        CREATE TABLE author_aliases__new (
            alias TEXT NOT NULL COLLATE NOCASE PRIMARY KEY,
            author_id TEXT NOT NULL,
            FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE CASCADE
        )
        """,
}

_UNIQUE_CLAUSES: dict[str, str] = {}


def _rebuild(
    conn: sqlite3.Connection,
    table: str,
    *,
    extra: str,
    unique: str = "",
) -> None:
    """Recreate ``table`` as ``table__new`` with extra FK/UNIQUE clauses, then swap."""
    if table not in {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }:
        return
    old_names = _column_names(conn, table)
    indexes = _named_indexes(conn, table)
    explicit = _EXPLICIT_NEW_SQL.get(table)
    if explicit:
        conn.execute(explicit)
    else:
        col_sql, pk_sql = _column_sql(conn, table)
        unique_sql = unique or _UNIQUE_CLAUSES.get(table, "")
        unique_part = f", {unique_sql}" if unique_sql else ""
        conn.execute(
            f"CREATE TABLE {table}__new ({col_sql}{pk_sql}{unique_part}{extra})"
        )
    new_names = _column_names(conn, f"{table}__new")
    shared = [name for name in old_names if name in new_names]
    cols = ", ".join(shared)
    conn.execute(f"INSERT INTO {table}__new ({cols}) SELECT {cols} FROM {table}")
    conn.execute(f"DROP TABLE {table}")
    conn.execute(f"ALTER TABLE {table}__new RENAME TO {table}")
    for sql in indexes:
        conn.execute(sql)


def _clear_orphans(conn: sqlite3.Connection) -> None:
    live_works = "(SELECT id FROM works)"
    for table in _CASCADE_WORK_TABLES:
        if table not in {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }:
            continue
        cols = set(_column_names(conn, table))
        if "work_id" not in cols:
            continue
        conn.execute(
            f"DELETE FROM {table} WHERE work_id IS NOT NULL AND work_id NOT IN {live_works}"
        )
    for table, column in _SET_NULL_WORK_TABLES:
        if table not in {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }:
            continue
        cols = set(_column_names(conn, table))
        if column not in cols:
            continue
        conn.execute(
            f"UPDATE {table} SET {column} = NULL "
            f"WHERE {column} IS NOT NULL AND {column} NOT IN {live_works}"
        )
    if "author_aliases" in {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }:
        conn.execute(
            "DELETE FROM author_aliases WHERE author_id NOT IN (SELECT id FROM authors)"
        )
    if "work_authors" in {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }:
        conn.execute(
            "DELETE FROM work_authors WHERE author_id NOT IN (SELECT id FROM authors)"
        )


def _dedupe_file_paths(conn: sqlite3.Connection) -> None:
    """Keep one row per path so ``files.path`` can be unique."""
    dupes = conn.execute(
        "SELECT path FROM files GROUP BY path HAVING COUNT(*) > 1"
    ).fetchall()
    for (path,) in dupes:
        ids = [
            row[0]
            for row in conn.execute(
                "SELECT id FROM files WHERE path = ? ORDER BY created_at DESC, id DESC",
                (path,),
            )
        ]
        for file_id in ids[1:]:
            conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
        logger.warning("Dropped duplicate files.path rows for %s", path)


def _install_fts_triggers(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TRIGGER IF EXISTS works_ai_fts")
    conn.execute("DROP TRIGGER IF EXISTS works_au_fts")
    conn.execute("DROP TRIGGER IF EXISTS works_ad_fts")
    conn.execute(
        """
        CREATE TRIGGER works_ai_fts AFTER INSERT ON works BEGIN
            INSERT INTO works_fts (work_id, title, author, genre, description)
            VALUES (
                new.id,
                coalesce(new.title, ''),
                coalesce(new.author, ''),
                coalesce(new.genre, ''),
                coalesce(new.description, '')
            );
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER works_au_fts AFTER UPDATE OF title, author, genre, description ON works
        BEGIN
            DELETE FROM works_fts WHERE work_id = old.id;
            INSERT INTO works_fts (work_id, title, author, genre, description)
            VALUES (
                new.id,
                coalesce(new.title, ''),
                coalesce(new.author, ''),
                coalesce(new.genre, ''),
                coalesce(new.description, '')
            );
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER works_ad_fts AFTER DELETE ON works BEGIN
            DELETE FROM works_fts WHERE work_id = old.id;
        END
        """
    )


def apply(conn: sqlite3.Connection) -> None:
    _clear_orphans(conn)
    _dedupe_file_paths(conn)

    _rebuild(
        conn,
        "files",
        extra=", FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE",
    )
    _rebuild(
        conn,
        "editions",
        extra=", FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE",
    )
    _rebuild(
        conn,
        "work_identifiers",
        extra=", FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE",
    )
    _rebuild(
        conn,
        "work_authors",
        extra=(
            ", FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE"
            ", FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE CASCADE"
        ),
    )
    _rebuild(
        conn,
        "author_aliases",
        extra=", FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE CASCADE",
    )
    _rebuild(
        conn,
        "shelf_items",
        extra=", FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE",
    )
    _rebuild(
        conn,
        "progress",
        extra=", FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE",
    )
    _rebuild(
        conn,
        "whispers",
        extra=", FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE",
    )
    _rebuild(
        conn,
        "review_suggestions",
        extra=", FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE",
    )
    _rebuild(
        conn,
        "review_diagnosis",
        extra=", FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE",
    )
    _rebuild(
        conn,
        "jobs",
        extra=", FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE SET NULL",
    )
    _rebuild(
        conn,
        "owned_slip_clearances",
        extra=", FOREIGN KEY (shelf_work_id) REFERENCES works(id) ON DELETE SET NULL",
    )

    conn.execute("CREATE INDEX IF NOT EXISTS idx_files_work_id ON files(work_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_files_sha256 ON files(sha256)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_files_path ON files(path)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_works_isbn ON works(isbn)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_works_folder_path ON works(folder_path)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_indexer_guid ON jobs(indexer_guid)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_work_id ON jobs(work_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_editions_work_id ON editions(work_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_editions_isbn13 ON editions(isbn13)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_editions_asin ON editions(asin)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_work_identifiers_work_id ON work_identifiers(work_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_work_authors_author_id ON work_authors(author_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_author_aliases_author_id ON author_aliases(author_id)"
    )

    _install_fts_triggers(conn)


def foreign_key_parents(conn: sqlite3.Connection, table: str) -> Sequence[str]:
    """Helper for tests: parent tables ``table`` references."""
    return tuple(str(row[2]) for row in conn.execute(f"PRAGMA foreign_key_list({table})"))


def iter_integrity_tables() -> Iterable[str]:
    return (
        *_CASCADE_WORK_TABLES,
        *(table for table, _column in _SET_NULL_WORK_TABLES),
        "author_aliases",
    )
