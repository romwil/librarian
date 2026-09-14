from pathlib import Path

from librarian.config import Settings
from librarian.db import Database
from librarian.organize import organize_identified, promote_music


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
