"""Slips for titles the house already shelved with a file are unnecessary."""

from pathlib import Path

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.organize import organize_identified
from librarian.owned_slip import ALREADY_ON_SHELF, match_owned_media, sweep_owned_slips
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app

ISBN = "9780441172719"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "magazines"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "audiobooks"),
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
        complete_root=str(tmp_path / "usenet" / "complete"),
    )


def _shelve(db: Database, folder: Path, **fields):
    folder.mkdir(parents=True, exist_ok=True)
    media = folder / "book.epub"
    media.write_bytes(b"owned-epub")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Crying in H Mart",
            "author": "Michelle Zauner",
            "isbn": ISBN,
            "review_state": "none",
            "folder_path": str(folder),
            **fields,
        }
    )
    db.add_file(
        {
            "work_id": work["id"],
            "path": str(media),
            "filename": media.name,
            "kind": "book",
            "size": media.stat().st_size,
        }
    )
    return work, media


def _slip(db: Database, **fields):
    return db.upsert_work(
        {
            "kind": "book",
            "title": "Crying in H Mart",
            "author": "Michelle Zauner",
            "isbn": ISBN,
            "review_state": "needs_review",
            "review_reason": "unknown_identity",
            "folder_path": "",
            **fields,
        }
    )


def test_isbn_match_removes_slip_and_keeps_shelved_file(tmp_path):
    db = Database(tmp_path / "librarian.db")
    shelf, media = _shelve(db, tmp_path / "books" / "mart")
    slip = _slip(
        db,
        title="Crying in H Mart (retail)",
        author="Someone Else",
        folder_path=str(tmp_path / "complete" / "grab"),
    )
    result = sweep_owned_slips(db)
    assert db.get_work(slip["id"]) is None
    assert db.get_work(shelf["id"])["title"] == "Crying in H Mart"
    assert media.read_bytes() == b"owned-epub"
    assert db.files_for_work(shelf["id"])[0]["path"] == str(media)
    assert result["cleared"][0]["reason"] == ALREADY_ON_SHELF
    assert result["cleared"][0]["shelf_work_id"] == shelf["id"]
    assert "Already on the shelf" in result["note"]
    assert "Crying in H Mart" in result["note"]


def test_slip_with_no_catalog_match_stays(tmp_path):
    db = Database(tmp_path / "librarian.db")
    slip = _slip(db, title="Think Again", author="Adam Grant", isbn="9781984878106")
    result = sweep_owned_slips(db)
    assert db.get_work(slip["id"])["review_state"] == "needs_review"
    assert result["cleared"] == []
    assert result["note"] == ""


def test_title_only_similarity_does_not_match(tmp_path):
    db = Database(tmp_path / "librarian.db")
    shelf, media = _shelve(db, tmp_path / "books" / "mart", isbn="")
    same_title = _slip(db, title="Crying in H Mart", author="", isbn="")
    near_title = _slip(
        db,
        title="Crying in H Mart: A Memoir",
        author="Michelle Zauner",
        isbn="",
    )
    other_author = _slip(db, title="Crying in H Mart", author="Ada Grant", isbn="")
    result = sweep_owned_slips(db)
    assert result["cleared"] == []
    for slip in (same_title, near_title, other_author):
        assert db.get_work(slip["id"])["review_state"] == "needs_review"
    assert media.is_file()
    assert match_owned_media(
        {"title": "Crying in H Mart", "author": "", "isbn": ""},
        [shelf],
    ) is None


def test_empty_stub_is_not_owned_media(tmp_path):
    db = Database(tmp_path / "librarian.db")
    stub = db.upsert_work(
        {
            "kind": "book",
            "title": "A Calamity of Souls",
            "author": "David Baldacci",
            "isbn": "9781538709245",
            "review_state": "none",
            "folder_path": str(tmp_path / "books" / "empty"),
        }
    )
    slip = _slip(
        db,
        title="A Calamity of Souls",
        author="David Baldacci",
        isbn="9781538709245",
    )
    sweep_owned_slips(db)
    assert db.get_work(slip["id"])["review_state"] == "needs_review"
    assert db.get_work(stub["id"]) is not None
    assert db.files_for_work(stub["id"]) == []


def test_incomplete_archive_in_complete_folder_stays(tmp_path):
    db = Database(tmp_path / "librarian.db")
    grab = tmp_path / "usenet" / "complete" / "downloads" / "Think Again"
    grab.mkdir(parents=True)
    archive = grab / "think.rar"
    archive.write_bytes(b"Rar!")
    slip = _slip(
        db,
        title="Think Again",
        author="Adam Grant",
        isbn="",
        review_reason="unpack_stuck",
        folder_path=str(grab),
    )
    sweep_owned_slips(db)
    assert db.get_work(slip["id"])["review_state"] == "needs_review"
    assert archive.read_bytes() == b"Rar!"


def test_series_index_match_clears_slip(tmp_path):
    db = Database(tmp_path / "librarian.db")
    shelf, _media = _shelve(
        db,
        tmp_path / "books" / "dune",
        title="Dune Messiah",
        author="Frank Herbert",
        isbn="",
        series_name="Dune",
        series_index="2",
    )
    slip = _slip(
        db,
        title="Messiah",
        author="",
        isbn="",
        series_name="Dune",
        series_index="2.0",
    )
    result = sweep_owned_slips(db)
    assert db.get_work(slip["id"]) is None
    assert db.get_work(shelf["id"]) is not None
    assert result["cleared"][0]["reason"] == ALREADY_ON_SHELF


def test_new_slip_closes_immediately_when_already_shelved(tmp_path):
    settings = _settings(tmp_path)
    db = Database(tmp_path / "librarian.db")
    dest = Path(settings.books_root) / "Le Guin" / "The Left Hand of Darkness"
    dest.mkdir(parents=True)
    media = dest / "The Left Hand of Darkness.epub"
    media.write_bytes(b"old")
    shelf = db.upsert_work(
        {
            "kind": "book",
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": "9780441478125",
            "review_state": "none",
            "folder_path": str(dest),
        }
    )
    db.add_file(
        {
            "work_id": shelf["id"],
            "path": str(media),
            "filename": media.name,
            "kind": "book",
            "size": media.stat().st_size,
        }
    )
    grab = tmp_path / "usenet" / "complete" / "fresh"
    grab.mkdir(parents=True)
    incoming = grab / "book.epub"
    incoming.write_bytes(b"new")
    result = organize_identified(
        db,
        settings,
        folder=grab,
        indexer_item={
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": "9780441478125",
            "category": 7020,
            "name": "Le Guin - The Left Hand of Darkness 9780441478125",
        },
    )
    assert result["already_on_shelf"] is True
    assert result["reason"] == ALREADY_ON_SHELF
    assert result["work"]["id"] == shelf["id"]
    assert media.read_bytes() == b"old"
    assert incoming.read_bytes() == b"new"
    assert db.list_works(review_state="needs_review", limit=20) == []
    assert db.files_for_work(shelf["id"])


def test_review_list_leaves_owned_slips_for_the_background_sweep(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    save_settings(tmp_path, _settings(tmp_path))
    app = create_app(tmp_path)
    client = TestClient(app)
    assert (
        client.post(
            "/api/auth/local/login",
            json={"username": "owner", "password": "password123"},
        ).status_code
        == 200
    )
    db = app.state.db
    _shelve(db, tmp_path / "books" / "mart")
    owned = _slip(db, title="Crying in H Mart", author="Michelle Zauner", isbn=ISBN)
    kept = _slip(db, title="Think Again", author="Adam Grant", isbn="9781984878106")

    def _refuse_catalog_scan(self, kind):
        raise AssertionError(f"review list scanned shelved {kind}")

    monkeypatch.setattr(Database, "list_shelved_works", _refuse_catalog_scan)
    listed = client.get("/api/review")
    assert listed.status_code == 200
    body = listed.json()
    ids = {row["id"] for row in body["works"]}
    assert owned["id"] in ids
    assert kept["id"] in ids
    assert body["owned_slip_note"] == ""
    assert db.get_work(owned["id"]) is not None


def test_review_list_shows_note_after_background_sweep(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    save_settings(tmp_path, _settings(tmp_path))
    app = create_app(tmp_path)
    client = TestClient(app)
    assert (
        client.post(
            "/api/auth/local/login",
            json={"username": "owner", "password": "password123"},
        ).status_code
        == 200
    )
    db = app.state.db
    shelf, media = _shelve(db, tmp_path / "books" / "mart")
    owned = _slip(db, title="Crying in H Mart", author="Michelle Zauner", isbn=ISBN)
    kept = _slip(db, title="Think Again", author="Adam Grant", isbn="9781984878106")
    sweep_owned_slips(db)

    def _refuse_catalog_scan(self, kind):
        raise AssertionError(f"review list scanned shelved {kind}")

    monkeypatch.setattr(Database, "list_shelved_works", _refuse_catalog_scan)
    listed = client.get("/api/review")
    assert listed.status_code == 200
    body = listed.json()
    ids = {row["id"] for row in body["works"]}
    assert owned["id"] not in ids
    assert kept["id"] in ids
    assert "Already on the shelf" in body["owned_slip_note"]
    assert db.get_work(shelf["id"]) is not None
    assert media.is_file()


def test_idle_sweep_reuses_one_connection(tmp_path, monkeypatch):
    """Non-matching slips must not reopen SQLite once per row."""
    db = Database(tmp_path / "librarian.db")
    _shelve(db, tmp_path / "books" / "mart", isbn="")
    for index in range(20):
        _slip(db, title=f"Unrelated {index}", author=f"Author {index}", isbn="")
    calls = {"n": 0}
    original = db._connect

    def counting():
        calls["n"] += 1
        return original()

    monkeypatch.setattr(db, "_connect", counting)
    sweep_owned_slips(db)
    first = calls["n"]
    assert first <= 2
    calls["n"] = 0
    for index in range(20, 40):
        _slip(db, title=f"Also unrelated {index}", author=f"Author {index}", isbn="")
    calls["n"] = 0
    sweep_owned_slips(db)
    assert calls["n"] == first
