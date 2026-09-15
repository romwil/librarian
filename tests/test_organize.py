from pathlib import Path

import pytest

from librarian.config import Settings
from librarian.db import Database
from librarian.organize import (
    MISSING_FOLDER_APPLY_ERROR,
    apply_review,
    organize_identified,
    promote_music,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "magazines"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "audiobooks"),
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
    )


def test_organize_epub_book_writes_opf(tmp_path):
    folder = tmp_path / "complete" / "Le Guin - The Left Hand of Darkness 9780441478125"
    folder.mkdir(parents=True)
    (folder / "book.epub").write_bytes(b"epub")
    db = Database(tmp_path / "librarian.db")
    result = organize_identified(
        db,
        _settings(tmp_path),
        folder=folder,
        indexer_item={
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": "9780441478125",
            "category": 7020,
            "guid": "guid-1",
            "name": folder.name,
        },
    )
    assert result["organized"] is True
    dest = Path(result["files"][0])
    assert dest.name == "The Left Hand of Darkness.epub"
    assert dest.parent.name == "The Left Hand of Darkness"
    assert dest.parent.parent.name == "Le Guin"
    assert (dest.parent / "metadata.opf").is_file()
    opf = (dest.parent / "metadata.opf").read_text(encoding="utf-8")
    assert "The Left Hand of Darkness" in opf
    assert "9780441478125" in opf
    work = db.get_work(result["work"]["id"])
    assert work["review_state"] == "none"
    assert work["kind"] == "book"


def test_collision_goes_to_review(tmp_path):
    settings = _settings(tmp_path)
    dest_dir = Path(settings.books_root) / "Le Guin" / "The Left Hand of Darkness"
    dest_dir.mkdir(parents=True)
    (dest_dir / "The Left Hand of Darkness.epub").write_bytes(b"old")
    folder = tmp_path / "complete" / "fresh"
    folder.mkdir(parents=True)
    (folder / "book.epub").write_bytes(b"new")
    db = Database(tmp_path / "librarian.db")
    result = organize_identified(
        db,
        settings,
        folder=folder,
        indexer_item={
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": "9780441478125",
            "category": 7020,
            "name": "Le Guin - The Left Hand of Darkness 9780441478125",
        },
    )
    assert result["organized"] is False
    assert result["identity"]["review_reason"] == "collision"
    assert result["work"]["review_state"] == "needs_review"


def test_promote_music_moves_tree(tmp_path):
    settings = _settings(tmp_path)
    incoming = Path(settings.incoming_music_root) / "Miles" / "Kind of Blue"
    incoming.mkdir(parents=True)
    (incoming / "track.flac").write_bytes(b"flac")
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "music",
            "title": "Kind of Blue",
            "author": "Miles",
            "folder_path": str(incoming),
            "music_state": "incoming",
        }
    )
    promoted = promote_music(db, settings, work["id"])
    dest = Path(settings.music_root) / "Miles" / "Kind of Blue"
    assert dest.is_dir()
    assert (dest / "track.flac").is_file()
    assert not incoming.exists()
    assert promoted["music_state"] == "promoted"
    assert promoted["folder_path"] == str(dest)


def test_loose_comic_images_convert_and_cover(tmp_path):
    folder = tmp_path / "Saga.2024.001.Digital"
    folder.mkdir()
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 80
    (folder / "page-01.jpg").write_bytes(jpeg)
    (folder / "page-02.jpg").write_bytes(jpeg)
    db = Database(tmp_path / "librarian.db")
    result = organize_identified(db, _settings(tmp_path), folder=folder)
    assert result["organized"] is True
    dest = Path(result["files"][0])
    assert dest.suffix == ".cbz"
    assert dest.name == "Saga #1.cbz"
    assert (dest.parent / "ComicInfo.xml").is_file()
    assert (dest.parent / "cover.jpg").read_bytes() == jpeg
    work = db.get_work(result["work"]["id"])
    assert work["cover_path"] == str(dest.parent / "cover.jpg")
    assert work["kind"] == "comic"
    assert work["series_index"] == "1"


def test_review_persists_source_folder_and_apply_uses_identity(tmp_path):
    folder = tmp_path / "complete" / "Mystery.Release"
    folder.mkdir(parents=True)
    (folder / "book.epub").write_bytes(b"epub")
    db = Database(tmp_path / "librarian.db")
    parked = organize_identified(db, _settings(tmp_path), folder=folder, apply=False)
    assert parked["organized"] is False
    assert parked["work"]["folder_path"] == str(folder)
    result = apply_review(
        db,
        _settings(tmp_path),
        work_id=parked["work"]["id"],
        folder=folder,
        identity_overrides={
            "title": "Christine",
            "author": "Stephen King",
            "isbn": "9780670800000",
            "kind": "book",
        },
    )
    assert result["organized"] is True
    stored = db.get_work(parked["work"]["id"])
    assert stored["title"] == "Christine"
    assert stored["author"] == "Stephen King"
    assert stored["review_state"] == "none"
    dest = Path(result["files"][0])
    assert dest.parent.name == "Christine"
    assert dest.parent.parent.name == "Stephen King"


def test_apply_review_no_payload_raises(tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir()
    db = Database(tmp_path / "librarian.db")
    parked = organize_identified(
        db,
        _settings(tmp_path),
        folder=folder,
        indexer_item={"title": "Mystery", "category": 7020},
    )
    assert parked["work"]["review_reason"] == "no_payload"
    assert parked["work"]["folder_path"] == str(folder)
    with pytest.raises(ValueError, match="cannot invent"):
        apply_review(
            db,
            _settings(tmp_path),
            work_id=parked["work"]["id"],
            folder=folder,
            identity_overrides={"title": "Nope", "kind": "book"},
        )


def test_apply_review_empty_folder_does_not_scan_cwd(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {"kind": "book", "title": "Mystery", "review_state": "needs_review", "review_reason": "no_payload"}
    )
    with pytest.raises(ValueError, match="No complete folder"):
        apply_review(db, _settings(tmp_path), work_id=work["id"], folder=Path(""), identity_overrides={})
    assert MISSING_FOLDER_APPLY_ERROR


def test_apply_review_complete_root_remap(tmp_path):
    host = tmp_path / "downloads" / "books" / "King"
    host.mkdir(parents=True)
    (host / "book.epub").write_bytes(b"epub")
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Christine",
            "author": "King",
            "isbn": "9780670800000",
            "review_state": "needs_review",
            "review_reason": "no_payload",
            "folder_path": "/downloads/books/King",
        }
    )
    settings = _settings(tmp_path)
    settings.complete_root = str(tmp_path / "downloads")
    result = apply_review(
        db,
        settings,
        work_id=work["id"],
        folder=Path("/downloads/books/King"),
        identity_overrides={"title": "Christine", "author": "King", "isbn": "9780670800000", "kind": "book"},
    )
    assert result["organized"] is True
    stored = db.get_work(work["id"])
    assert stored["review_state"] == "none"
    assert Path(result["files"][0]).parent.name == "Christine"

