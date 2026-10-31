import sqlite3

from librarian.db import SCHEMA_VERSION, Database
from librarian.migrations import (
    LATEST_VERSION,
    MIGRATIONS,
    m0001_baseline,
    m0002_rebuild_works_fts,
    schema_version,
)

# A catalog from before numbered steps: the tables an early build created, missing
# every column the old _ensure_*_columns helpers added, and no review tables at all.
LEGACY_SCHEMA = """
CREATE TABLE users (
    id TEXT PRIMARY KEY, display_name TEXT NOT NULL UNIQUE, role TEXT NOT NULL,
    password_hash TEXT NOT NULL, created_at REAL NOT NULL, last_login_at REAL,
    session_epoch INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE works (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, author TEXT,
    series_name TEXT, series_index TEXT, year INTEGER, isbn TEXT, mbid TEXT,
    description TEXT, publisher TEXT, genre TEXT, cover_path TEXT, folder_path TEXT,
    review_state TEXT NOT NULL DEFAULT 'none', review_reason TEXT, music_state TEXT,
    indexer_guid TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE files (
    id TEXT PRIMARY KEY, work_id TEXT, path TEXT NOT NULL, filename TEXT NOT NULL,
    kind TEXT, size INTEGER, created_at REAL NOT NULL
);
CREATE TABLE jobs (
    id TEXT PRIMARY KEY, work_id TEXT, nzo_id TEXT, status TEXT NOT NULL,
    indexer_guid TEXT, title TEXT, kind TEXT, requested_by TEXT, storage_path TEXT,
    error TEXT, payload_json TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE shelves (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, owner_user_id TEXT NOT NULL,
    created_at REAL NOT NULL, UNIQUE(name, owner_user_id)
);
CREATE TABLE wanted (
    id TEXT PRIMARY KEY, dedupe_key TEXT NOT NULL UNIQUE, work_id TEXT, title TEXT,
    author TEXT, isbn TEXT, kind TEXT NOT NULL, status TEXT NOT NULL,
    miss_streak INTEGER NOT NULL DEFAULT 0, next_search_at REAL NOT NULL, job_id TEXT,
    created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE VIRTUAL TABLE works_fts USING fts5(work_id UNINDEXED, title, author, genre, description);
"""


def _schema(path):
    conn = sqlite3.connect(path)
    try:
        tables = {}
        for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall():
            tables[name] = {row[1] for row in conn.execute(f"PRAGMA table_info({name})")}
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
            )
        }
        return tables, indexes
    finally:
        conn.close()


def _legacy_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(LEGACY_SCHEMA)
    conn.execute(
        "INSERT INTO works (id, kind, title, author, created_at, updated_at)"
        " VALUES ('w-legacy', 'book', 'The Left Hand of Darkness', 'Le Guin', 1, 1)"
    )
    conn.execute(
        "INSERT INTO files (id, work_id, path, filename, kind, created_at)"
        " VALUES ('f-legacy', 'w-legacy', '/b/lhod.epub', 'lhod.epub', 'book', 1)"
    )
    conn.commit()
    assert schema_version(conn) == 0
    conn.close()


def _version_two_db(path):
    conn = sqlite3.connect(path)
    try:
        m0001_baseline.apply(conn)
        m0002_rebuild_works_fts.apply(conn)
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
        assert schema_version(conn) == 2
    finally:
        conn.close()


def test_steps_are_numbered_in_order():
    versions = [step.version for step in MIGRATIONS]
    assert versions == list(range(1, len(MIGRATIONS) + 1))
    assert LATEST_VERSION == SCHEMA_VERSION == 7


def test_fresh_database_lands_on_latest_version(tmp_path):
    db = Database(tmp_path / "librarian.db")
    assert db.schema_version == 7
    tables, indexes = _schema(tmp_path / "librarian.db")
    assert "source" in tables["wanted"]
    assert {"host_id", "guid", "wanted_id", "reason", "seen_count"} <= tables["bad_indexer_releases"]
    assert {"review_audit", "review_suggestions", "review_slip_cooldowns", "app_migrations"} <= set(tables)
    assert {"asin", "narrator", "subtitle", "repair_fail_count"} <= tables["works"]
    assert {"title_sort", "author_sort", "metadata_locked"} <= tables["works"]
    assert "sha256" in tables["files"]
    assert {"editions", "work_identifiers", "authors", "author_aliases", "work_authors", "noted_cache"} <= set(tables)
    assert {"sessions", "password_resets", "security_events", "provider_calls"} <= set(tables)
    assert {"review_diagnosis", "sorting_undo"} <= set(tables)
    assert "disabled" in tables["users"]
    assert "idx_bad_indexer_releases_guid" in indexes


def test_legacy_and_fresh_databases_end_on_the_same_schema(tmp_path):
    fresh_path = tmp_path / "fresh.db"
    legacy_path = tmp_path / "legacy.db"
    Database(fresh_path)
    _legacy_db(legacy_path)
    legacy = Database(legacy_path)

    assert legacy.schema_version == 7
    assert _schema(legacy_path) == _schema(fresh_path)


def test_version_two_and_fresh_databases_end_on_the_same_schema(tmp_path):
    fresh_path = tmp_path / "fresh.db"
    version_two_path = tmp_path / "version-two.db"
    Database(fresh_path)
    _version_two_db(version_two_path)

    version_two = Database(version_two_path)

    assert version_two.schema_version == 7
    assert _schema(version_two_path) == _schema(fresh_path)


def test_fts_rebuild_indexes_rows_written_before_the_index(tmp_path):
    path = tmp_path / "legacy.db"
    _legacy_db(path)
    db = Database(path)

    assert [row["title"] for row in db.search_works("Darkness")] == ["The Left Hand of Darkness"]
    # Legacy rows keep their data and accept the columns the baseline added.
    db.set_work_subtitle("w-legacy", "A Hainish novel")
    assert db.get_work("w-legacy")["subtitle"] == "A Hainish novel"


def test_reopening_does_not_rerun_steps(tmp_path):
    path = tmp_path / "librarian.db"
    db = Database(path)
    work = db.upsert_work({"kind": "book", "title": "Kindred", "author": "Butler"})
    db.add_file({"work_id": work["id"], "path": "/b/k.epub", "filename": "k.epub", "kind": "book"})
    with db._connect() as conn:
        conn.execute("DELETE FROM works_fts")

    reopened = Database(path)

    assert reopened.schema_version == 7
    # A second boot is a no-op: the FTS rebuild step does not run again.
    assert reopened.search_works("Kindred") == []


def test_newer_schema_is_left_untouched(tmp_path):
    path = tmp_path / "librarian.db"
    Database(path)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()

    assert Database(path).schema_version == 99
