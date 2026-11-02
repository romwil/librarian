"""Apply permission copy: SAB complete vs library shelf, audiobook nested extracts."""

from pathlib import Path

import pytest

from librarian.config import Settings
from librarian.db import Database
from librarian.organize import apply_review
from librarian.organize.move import _copy_into
from librarian.organize.review import (
    COMPLETE_APPLY_ERROR,
    _permission_apply_error,
)


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


def test_permission_apply_error_complete_file_is_not_books_root(tmp_path):
    settings = _settings(tmp_path)
    Path(settings.audiobooks_root).mkdir(parents=True)
    src = (
        tmp_path
        / "usenet"
        / "complete"
        / "downloads"
        / "102.Minutes.Audio.book.MP3"
        / "102.Minutes.Audio.book.MP3"
        / "01-05.102.Minutes.mp3"
    )
    dest = Path(settings.audiobooks_root) / "Unknown Author" / "102 Minutes" / "01-05.102.Minutes.mp3"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"mp3")
    error = PermissionError(13, "Permission denied", str(src), None, str(dest))
    detail = _permission_apply_error(error, settings)
    assert "under the books root" not in detail
    assert "SAB complete" in detail
    assert str(src) in detail
    assert COMPLETE_APPLY_ERROR.split(".")[0] in detail


def test_permission_apply_error_unwritable_audiobooks_names_shelf(tmp_path):
    settings = _settings(tmp_path)
    shelf = Path(settings.audiobooks_root)
    shelf.mkdir(parents=True)
    shelf.chmod(0o555)
    src = (
        tmp_path
        / "usenet"
        / "complete"
        / "downloads"
        / "Elvis.m4b.mp3"
        / "Elvis.m4b.mp3"
        / "Careless.Love.m4b"
    )
    dest = shelf / "Peter Guralnick" / "Elvis" / "Careless.Love.m4b"
    try:
        error = PermissionError(13, "Permission denied", str(src), None, str(dest))
        detail = _permission_apply_error(error, settings)
    finally:
        shelf.chmod(0o755)
    assert "audiobooks root" in detail
    assert "under the books root" not in detail
    assert str(dest) in detail
    assert "SAB complete" not in detail
    assert str(src) not in detail


def test_permission_apply_error_books_dest_keeps_puid_copy(tmp_path):
    settings = _settings(tmp_path)
    locked = Path(settings.books_root) / "Author" / "Locked"
    error = PermissionError(13, "Permission denied", str(locked))
    detail = _permission_apply_error(error, settings)
    assert "library shelf" in detail
    assert "PUID" in detail
    assert "books root" in detail
    assert "Locked path:" in detail
    assert "Author" in detail


def test_copy_into_move_falls_back_when_source_dir_locked(tmp_path):
    nested = tmp_path / "usenet" / "complete" / "downloads" / "Book.MP3" / "Book.MP3"
    nested.mkdir(parents=True)
    src = nested / "01-05.book.mp3"
    src.write_bytes(b"audio-bytes")
    dest = tmp_path / "audiobooks" / "Author" / "Title" / "01-05.book.mp3"
    nested.chmod(0o555)
    try:
        written = _copy_into(src, dest, move=True)
    finally:
        nested.chmod(0o755)
    assert written == dest
    assert dest.read_bytes() == b"audio-bytes"
    assert src.exists()


def test_apply_review_audiobook_nested_complete_copies_onto_shelf(tmp_path):
    complete = (
        tmp_path
        / "usenet"
        / "complete"
        / "downloads"
        / "102.Minutes.The.Untold.Story.Audio.book.MP3"
    )
    nested = complete / "102.Minutes.The.Untold.Story.Audio.book.MP3"
    nested.mkdir(parents=True)
    src = nested / "01-05.102.Minutes.mp3"
    src.write_bytes(b"mp3-audio")
    settings = _settings(tmp_path)
    for root in (
        settings.books_root,
        settings.audiobooks_root,
        settings.magazines_root,
        settings.comics_root,
    ):
        Path(root).mkdir(parents=True, exist_ok=True)
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "audiobook",
            "title": "102 Minutes: The Untold Story of the Fight to Survive Inside the Twin Towers",
            "author": "",
            "review_state": "needs_review",
            "review_reason": "unknown_identity",
            "folder_path": str(complete),
        }
    )
    nested.chmod(0o555)
    try:
        result = apply_review(
            db,
            settings,
            work_id=work["id"],
            folder=complete,
            identity_overrides={
                "kind": "audiobook",
                "title": "102 Minutes: The Untold Story of the Fight to Survive Inside the Twin Towers",
                "author": "",
            },
        )
    finally:
        nested.chmod(0o755)
    assert result["organized"] is True
    dest = Path(result["files"][0])
    assert dest.is_relative_to(Path(settings.audiobooks_root))
    assert dest.read_bytes() == b"mp3-audio"
    assert not dest.is_relative_to(Path(settings.books_root))
    assert not dest.is_relative_to(Path(settings.complete_root))


def test_apply_review_audiobook_unwritable_shelf_names_audiobooks_root(tmp_path):
    complete = tmp_path / "usenet" / "complete" / "downloads" / "Elvis.m4b.mp3"
    nested = complete / "Elvis.m4b.mp3"
    nested.mkdir(parents=True)
    (nested / "Careless.Love.m4b").write_bytes(b"m4b")
    settings = _settings(tmp_path)
    Path(settings.audiobooks_root).mkdir(parents=True)
    Path(settings.books_root).mkdir(parents=True)
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "audiobook",
            "title": "Elvis: Last Train to Memphis and Careless Love",
            "author": "Peter Guralnick",
            "review_state": "needs_review",
            "review_reason": "unknown_identity",
            "folder_path": str(complete),
        }
    )
    Path(settings.audiobooks_root).chmod(0o555)
    try:
        with pytest.raises(ValueError) as raised:
            apply_review(
                db,
                settings,
                work_id=work["id"],
                folder=complete,
                identity_overrides={
                    "kind": "audiobook",
                    "title": "Elvis: Last Train to Memphis and Careless Love",
                    "author": "Peter Guralnick",
                },
            )
    finally:
        Path(settings.audiobooks_root).chmod(0o755)
    detail = str(raised.value)
    assert "audiobooks root" in detail
    assert "under the books root" not in detail
    assert str(settings.audiobooks_root) in detail
    assert "SAB complete" not in detail
