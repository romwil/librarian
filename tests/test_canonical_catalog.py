"""Phase 4: schema integrity, finished m0003 paths, snapshot-gated merge, shells."""

from __future__ import annotations

import sqlite3
import warnings
from pathlib import Path

from fastapi.testclient import TestClient

from librarian.catalog_merge import apply_duplicate_merge, preview_duplicate_merge
from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.identity.titles import strip_calibre_suffix, title_match_key
from librarian.purge_shells import preview_shell_purge, purge_shell_works
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    save_settings(
        tmp_path,
        Settings(
            books_root=str(tmp_path / "books"),
            magazines_root=str(tmp_path / "magazines"),
            comics_root=str(tmp_path / "comics"),
            audiobooks_root=str(tmp_path / "audiobooks"),
            incoming_music_root=str(tmp_path / "incoming"),
            music_root=str(tmp_path / "music"),
            complete_root=str(tmp_path / "complete"),
        ),
    )
    client = TestClient(create_app(tmp_path))
    assert client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
    ).status_code == 200
    return client


def _shelve(db: Database, work: dict, folder: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "book.epub"
    path.write_bytes(b"payload")
    db.upsert_file(
        {
            "work_id": work["id"],
            "path": str(path),
            "filename": path.name,
            "kind": "book",
            "size": path.stat().st_size,
        }
    )
    return work


def test_calibre_suffix_is_not_a_different_title():
    assert strip_calibre_suffix("Death and What Comes Next (11630)") == "Death and What Comes Next"
    assert title_match_key("Death and What Comes Next (11630)") == title_match_key(
        "Death and What Comes Next"
    )
    assert strip_calibre_suffix("Volume (2)") == "Volume (2)"


def test_schema_has_catalog_foreign_keys_and_fts_triggers(tmp_path):
    db = Database(tmp_path / "librarian.db")
    try:
        with db._connect() as conn:
            parents = {
                row[2]
                for row in conn.execute("PRAGMA foreign_key_list(editions)")
            }
            assert "works" in parents
            files_fk = {
                row[2] for row in conn.execute("PRAGMA foreign_key_list(files)")
            }
            assert "works" in files_fk
            diagnosis_fk = {
                row[2] for row in conn.execute("PRAGMA foreign_key_list(review_diagnosis)")
            }
            assert "works" in diagnosis_fk
            indexes = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                )
            }
            assert "idx_files_path" in indexes
            assert "idx_works_isbn" in indexes
            assert "idx_jobs_indexer_guid" in indexes
            triggers = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger'"
                )
            }
            assert {"works_ai_fts", "works_au_fts", "works_ad_fts"} <= triggers
            plan = " ".join(
                str(part)
                for row in conn.execute(
                    "EXPLAIN QUERY PLAN SELECT * FROM files WHERE path = 'x'"
                )
                for part in row
            )
            assert "idx_files_path" in plan
    finally:
        db.close()


def test_raw_title_update_is_searchable_via_fts_trigger(tmp_path):
    db = Database(tmp_path / "librarian.db")
    try:
        work = db.upsert_work({"kind": "book", "title": "Kindred", "author": "Butler"})
        db.add_file(
            {
                "work_id": work["id"],
                "path": "/b/kindred.epub",
                "filename": "kindred.epub",
                "kind": "book",
            }
        )

        def _rename() -> None:
            with db._connect() as conn:
                conn.execute("UPDATE works SET title = ? WHERE id = ?", ("Fledgling", work["id"]))

        db.run_write(_rename, label="test_rename")
        assert [row["title"] for row in db.search_works("Fledgling")] == ["Fledgling"]
        assert db.search_works("Kindred") == []
    finally:
        db.close()


def test_connect_closes_the_sqlite_connection(tmp_path):
    db = Database(tmp_path / "librarian.db")
    try:
        with db._connect() as conn:
            conn.execute("SELECT 1")
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            try:
                conn.execute("SELECT 1")
            except sqlite3.ProgrammingError:
                return
            raise AssertionError("connection was still usable after with-block")
    finally:
        db.close()


def test_delete_work_leaves_no_edition_or_author_orphans(tmp_path):
    db = Database(tmp_path / "librarian.db")
    try:
        work = db.upsert_work(
            {
                "kind": "book",
                "title": "Kindred",
                "author": "Octavia Butler",
                "isbn": "9780807083697",
            }
        )
        work_id = work["id"]
        assert db.list_work_authors(work_id)
        assert db.list_editions_for_work(work_id)

        def _diag() -> None:
            with db._connect() as conn:
                conn.execute(
                    "INSERT INTO review_diagnosis (work_id, problem, updated_at) VALUES (?, '', 1)",
                    (work_id,),
                )

        db.run_write(_diag, label="test_diag")
        assert db.delete_work(work_id) is True
        with db._connect() as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM editions WHERE work_id = ?", (work_id,)
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM work_authors WHERE work_id = ?", (work_id,)
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM work_identifiers WHERE work_id = ?", (work_id,)
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM review_diagnosis WHERE work_id = ?", (work_id,)
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM works_fts WHERE work_id = ?", (work_id,)
            ).fetchone()[0] == 0
    finally:
        db.close()


def test_upsert_backfills_work_authors_and_browse_uses_them(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    db = client.app.state.db
    king = db.upsert_work(
        {
            "kind": "book",
            "title": "The Shining",
            "author": "King, Stephen",
            "folder_path": str(tmp_path / "shining"),
        }
    )
    _shelve(db, king, tmp_path / "shining")
    facets = client.get("/api/browse/facets")
    assert facets.status_code == 200
    authors = {row["name"]: row["count"] for row in facets.json()["authors"]}
    assert authors["Stephen King"] == 1
    filtered = client.get("/api/browse", params={"author": "Stephen King"})
    assert [row["title"] for row in filtered.json()["items"]] == ["The Shining"]


def test_work_page_returns_canonical_authors_and_editions(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    db = client.app.state.db
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "The 1619 Project",
            "author": "Nikole Hannah-Jones",
            "isbn": "9780593230572",
            "folder_path": str(tmp_path / "1619"),
        }
    )
    _shelve(db, work, tmp_path / "1619")
    detail = client.get(f"/api/works/{work['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert [row["display_name"] for row in body["authors"]] == ["Nikole Hannah-Jones"]
    assert any(row.get("isbn13") == "9780593230572" for row in body["editions"])


def test_duplicate_merge_after_snapshot_collapses_calibre_suffix(tmp_path):
    db = Database(tmp_path / "librarian.db")
    settings = Settings(books_root=str(tmp_path / "library" / "books"))
    try:
        first = db.upsert_work(
            {
                "id": "death-1",
                "kind": "book",
                "title": "Death and What Comes Next",
                "author": "Terry Pratchett",
                "isbn": "9780593230572",
            }
        )
        second = db.upsert_work(
            {
                "id": "death-2",
                "kind": "book",
                "title": "Death and What Comes Next (11630)",
                "author": "Pratchett, Terry",
                "isbn": "0593230574",
            }
        )
        media = tmp_path / "death.epub"
        media.write_bytes(b"bytes")
        db.add_file(
            {
                "work_id": second["id"],
                "path": str(media),
                "filename": media.name,
                "kind": "book",
                "size": media.stat().st_size,
            }
        )
        preview = preview_duplicate_merge(db)
        assert preview["merge_groups"] >= 1
        assert preview["calibre_suffixes"] >= 1
        assert preview["requires_snapshot"] is True

        result = apply_duplicate_merge(db, settings=settings, data_dir=tmp_path, snapshot=True)
        remaining = [db.get_work(first["id"]), db.get_work(second["id"])]
        present = [row for row in remaining if row]
        assert len(present) == 1
        assert "(11630)" not in present[0]["title"]
        assert result["snapshot"]
        assert list((tmp_path / "backups").glob("pre-duplicate-merge-*.db"))
    finally:
        db.close()


def test_duplicate_merge_api_is_owner_only(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    preview = client.get("/api/maintain/duplicate-merge/preview")
    assert preview.status_code == 200
    body = preview.json()
    assert "merge_groups" in body
    assert body["requires_snapshot"] is True


def test_shell_preview_names_wishlist_vs_junk(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    db = client.app.state.db
    settings = Settings(
        books_root=str(tmp_path / "books"),
        complete_root=str(tmp_path / "complete"),
    )
    db.upsert_work(
        {
            "kind": "book",
            "title": "Wishlist Stub",
            "author": "Someone",
            "isbn": "9781234567890",
            "review_state": "none",
        }
    )
    db.upsert_work(
        {
            "kind": "audiobook",
            "title": "Dump.Title.Audio.book",
            "folder_path": str(tmp_path / "missing-dump"),
            "review_state": "resolved",
        }
    )
    preview = preview_shell_purge(db, settings)
    assert preview["would_purge"] >= 1
    assert preview["kept_reasons"]["wishlist_stub"] >= 1
    assert "Dump.Title.Audio.book" in preview["sample"]
    result = purge_shell_works(db, settings, data_dir=tmp_path)
    assert result["snapshot"]
    assert result["purged"] >= 1
