"""Path-clear books and readable rar unpacks are shelved before a slip exists."""

from pathlib import Path

from librarian.config import Settings
from librarian.db import Database
from librarian.organize import organize_identified
from librarian.slip_gate import accept_path_clear_slips, match_shelved


def _settings(tmp_path: Path) -> Settings:
    return Settings.from_mapping(
        {
            "books_root": str(tmp_path / "books"),
            "magazines_root": str(tmp_path / "magazines"),
            "comics_root": str(tmp_path / "comics"),
            "audiobooks_root": str(tmp_path / "audiobooks"),
            "incoming_music_root": str(tmp_path / "incoming"),
            "music_root": str(tmp_path / "music"),
            "nzbfinder_api_token": "",
            "sabnzbd_api_key": "",
        }
    )


def _shelf_file(db: Database, folder: Path, *, blob: bytes = b"shelf", **work):
    folder.mkdir(parents=True, exist_ok=True)
    payload = folder / str(work.pop("filename", "book.epub"))
    payload.write_bytes(blob)
    row = db.upsert_work(
        {
            "kind": "book",
            "review_state": "none",
            "folder_path": str(folder),
            **work,
        }
    )
    db.upsert_file(
        {
            "work_id": row["id"],
            "path": str(payload),
            "filename": payload.name,
            "kind": "book",
            "size": len(blob),
        }
    )
    return row, payload


def test_path_clear_book_is_shelved_before_a_slip(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    settings = _settings(tmp_path)
    folder = tmp_path / "William W. Johnstone" / "Fire in the Ashes"
    folder.mkdir(parents=True)
    source = folder / "Fire in the Ashes.epub"
    source.write_bytes(b"epub-bytes")
    db = Database(tmp_path / "librarian.db")
    result = organize_identified(db, settings, folder=folder, move_source=False)
    assert result["organized"] is True
    assert db.count_works(review_state="needs_review") == 0
    work = result["work"]
    assert work["review_state"] == "none"
    assert work["author"] == "William W Johnstone"
    assert work["title"] == "Fire in the Ashes"
    assert work["isbn"] in (None, "")
    dest = Path(settings.books_root) / "William W Johnstone" / "Fire in the Ashes"
    shelved = next(dest.glob("*.epub"))
    assert shelved.read_bytes() == b"epub-bytes"


def test_path_clear_pdf_is_shelved_without_a_slip(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    folder = tmp_path / "Le Guin" / "The Left Hand of Darkness"
    folder.mkdir(parents=True)
    (folder / "book.pdf").write_bytes(b"%PDF-shelf")
    db = Database(tmp_path / "librarian.db")
    result = organize_identified(db, _settings(tmp_path), folder=folder, move_source=False)
    assert result["organized"] is True
    assert result["work"]["review_state"] == "none"
    assert db.count_works(review_state="needs_review") == 0


def test_author_equal_to_title_parses_the_folder_before_a_slip(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    folder = tmp_path / "William W. Johnstone" / "Fire in the Ashes"
    folder.mkdir(parents=True)
    (folder / "book.epub").write_bytes(b"epub")
    db = Database(tmp_path / "librarian.db")
    result = organize_identified(
        db,
        _settings(tmp_path),
        folder=folder,
        move_source=False,
        identity_overrides={
            "kind": "book",
            "title": "Fire in the Ashes",
            "author": "Fire in the Ashes",
        },
    )
    assert result["organized"] is True
    assert result["work"]["author"] == "William W Johnstone"
    assert result["work"]["review_state"] == "none"
    assert db.count_works(review_state="needs_review") == 0


def test_title_alone_stays_a_slip_and_does_not_take_a_shelf_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    settings = _settings(tmp_path)
    db = Database(tmp_path / "librarian.db")
    _shelf, payload = _shelf_file(
        db,
        tmp_path / "shelf" / "Ada" / "Shared Title",
        title="Shared Title",
        author="Ada Lovelace",
        blob=b"keep-me",
    )
    incoming = tmp_path / "inbox" / "Shared Title"
    incoming.mkdir(parents=True)
    (incoming / "book.epub").write_bytes(b"other")
    result = organize_identified(db, settings, folder=incoming, move_source=False)
    assert result["organized"] is False
    assert result["work"]["review_state"] == "needs_review"
    assert payload.read_bytes() == b"keep-me"
    assert payload.is_file()


def test_isbn_match_drops_the_incoming_copy_and_keeps_the_shelf_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    settings = _settings(tmp_path)
    db = Database(tmp_path / "librarian.db")
    shelf, payload = _shelf_file(
        db,
        Path(settings.books_root) / "Le Guin" / "The Left Hand of Darkness",
        title="The Left Hand of Darkness",
        author="Le Guin",
        isbn="9780441478125",
        blob=b"shelf-bytes",
    )
    incoming = tmp_path / "drop" / "Le Guin" / "The Left Hand of Darkness"
    incoming.mkdir(parents=True)
    source = incoming / "book.epub"
    source.write_bytes(b"incoming-bytes")
    result = organize_identified(
        db,
        settings,
        folder=incoming,
        move_source=True,
        identity_overrides={"isbn": "9780441478125", "kind": "book"},
    )
    assert result.get("already_on_shelf") is True
    assert db.count_works(review_state="needs_review") == 0
    assert payload.read_bytes() == b"shelf-bytes"
    assert payload.is_file()
    assert db.get_work(shelf["id"])["review_state"] == "none"
    assert source.is_file()


def test_title_and_author_match_drops_without_deleting_the_shelf(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    settings = _settings(tmp_path)
    db = Database(tmp_path / "librarian.db")
    _shelf, payload = _shelf_file(
        db,
        Path(settings.books_root) / "Octavia Butler" / "Kindred",
        title="Kindred",
        author="Octavia Butler",
        blob=b"kindred",
    )
    incoming = tmp_path / "Octavia Butler" / "Kindred"
    incoming.mkdir(parents=True)
    (incoming / "Kindred.epub").write_bytes(b"second-copy")
    result = organize_identified(db, settings, folder=incoming, move_source=True)
    assert result.get("already_on_shelf") is True
    assert db.count_works(review_state="needs_review") == 0
    assert payload.read_bytes() == b"kindred"


def test_subtitle_then_series_match_before_title_alone(tmp_path):
    db = Database(tmp_path / "librarian.db")
    subtitle_work, subtitle_file = _shelf_file(
        db,
        tmp_path / "shelf" / "sub",
        title="Descender",
        author="Jeff Lemire",
        blob=b"sub",
    )
    db.set_work_subtitle(subtitle_work["id"], "Tin Stars")
    series_work, series_file = _shelf_file(
        db,
        tmp_path / "shelf" / "series",
        title="Other",
        author="Someone",
        series_name="Saga",
        series_index="12",
        blob=b"series",
    )
    by_subtitle = match_shelved(db, {"kind": "book", "title": "Unrelated", "subtitle": "Tin Stars"})
    assert by_subtitle["status"] == "unique"
    assert by_subtitle["work"]["id"] == subtitle_work["id"]
    by_series = match_shelved(
        db,
        {"kind": "book", "title": "Alone", "series_name": "Saga", "series_index": "12"},
    )
    assert by_series["status"] == "unique"
    assert by_series["work"]["id"] == series_work["id"]
    title_only = match_shelved(db, {"kind": "book", "title": "Descender"})
    assert title_only["status"] == "none"
    assert subtitle_file.read_bytes() == b"sub"
    assert series_file.read_bytes() == b"series"


def test_two_close_shelf_matches_stay_on_the_desk(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    settings = _settings(tmp_path)
    db = Database(tmp_path / "librarian.db")
    _first, first_file = _shelf_file(
        db,
        tmp_path / "shelf" / "a",
        title="Kindred",
        author="Octavia Butler",
        blob=b"one",
    )
    _second, second_file = _shelf_file(
        db,
        tmp_path / "shelf" / "b",
        title="Kindred",
        author="Octavia Butler",
        blob=b"two",
    )
    incoming = tmp_path / "Octavia Butler" / "Kindred"
    incoming.mkdir(parents=True)
    (incoming / "Kindred.epub").write_bytes(b"third")
    result = organize_identified(db, settings, folder=incoming, move_source=False)
    assert result["organized"] is False
    assert result["work"]["review_state"] == "needs_review"
    assert result["work"]["review_reason"] == "collision"
    assert first_file.read_bytes() == b"one"
    assert second_file.read_bytes() == b"two"


def test_rar_unpack_is_shelved_before_a_slip(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    monkeypatch.setattr("librarian.convert.which_unar", lambda: "/usr/bin/unar")
    folder = tmp_path / "William W. Johnstone" / "Fire in the Ashes"
    folder.mkdir(parents=True)
    archive = folder / "book.rar"
    archive.write_bytes(b"Rar!")

    def runner(argv, timeout=300):
        if argv and "unar" in str(argv[0]):
            (folder / "Fire in the Ashes.epub").write_bytes(b"unpacked")
            return type("R", (), {"returncode": 0})()
        return type("R", (), {"returncode": 1})()

    db = Database(tmp_path / "librarian.db")
    result = organize_identified(
        db,
        _settings(tmp_path),
        folder=folder,
        move_source=False,
        convert_runner=runner,
    )
    assert result["organized"] is True
    assert db.count_works(review_state="needs_review") == 0
    assert result["work"]["title"] == "Fire in the Ashes"


def test_unreadable_rar_is_a_skip_not_a_slip(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    folder = tmp_path / "inbox" / "dump"
    folder.mkdir(parents=True)
    (folder / "disk.rar").write_bytes(b"Rar!")
    db = Database(tmp_path / "librarian.db")
    result = organize_identified(db, _settings(tmp_path), folder=folder)
    assert result.get("skipped_unreadable") is True
    assert result.get("work") is None
    assert db.count_works(review_state="needs_review") == 0
    assert (folder / "disk.rar").is_file()


def test_convert_that_fails_twice_is_a_slip(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    folder = tmp_path / "Vampirella 006"
    folder.mkdir()
    (folder / "Vampirella.pdf").write_bytes(b"%PDF")
    calls = {"n": 0}

    def _fail(folder, kind, **kwargs):
        calls["n"] += 1
        return {"converted": False, "files": [], "payload": []}

    monkeypatch.setattr("librarian.organize.maybe_convert_payload", _fail)
    db = Database(tmp_path / "librarian.db")
    result = organize_identified(
        db,
        _settings(tmp_path),
        folder=folder,
        indexer_item={"kind": "comic", "title": "Vampirella #6", "series": "Vampirella", "issue": "6"},
        category=7030,
    )
    assert calls["n"] == 2
    assert result["organized"] is False
    assert result["work"]["review_reason"] == "convert_failed"
    assert result["work"]["review_state"] == "needs_review"


def test_accept_the_clear_ones_shelves_path_clear_rows_only(tmp_path):
    db = Database(tmp_path / "librarian.db")
    clear = tmp_path / "William W. Johnstone" / "Fire in the Ashes"
    clear.mkdir(parents=True)
    book = clear / "Fire in the Ashes.epub"
    book.write_bytes(b"stay")
    slip = db.upsert_work(
        {
            "kind": "book",
            "title": "Fire in the Ashes",
            "author": "William W. Johnstone",
            "folder_path": str(clear),
            "review_state": "needs_review",
            "review_reason": "low_confidence",
        }
    )
    muddy = tmp_path / "inbox" / "Dokument1"
    muddy.mkdir(parents=True)
    (muddy / "note.txt").write_text("nope", encoding="utf-8")
    kept = db.upsert_work(
        {
            "kind": "book",
            "title": "Dokument1",
            "author": "Dokument1",
            "folder_path": str(muddy),
            "review_state": "needs_review",
            "review_reason": "low_confidence",
        }
    )
    result = accept_path_clear_slips(db, reason="low_confidence")
    assert result["accepted"] == 1
    assert db.get_work(slip["id"])["review_state"] == "none"
    assert db.get_work(kept["id"])["review_state"] == "needs_review"
    assert book.read_bytes() == b"stay"
    claimed = db.get_file_by_path(str(book))
    assert claimed is not None
    assert claimed["work_id"] == slip["id"]
