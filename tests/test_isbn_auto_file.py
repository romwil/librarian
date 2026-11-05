"""BD-3 opt 4 · ISBN-strong hybrid auto-file — opt-in, books only, undo + pulse."""

from __future__ import annotations

from librarian.config import Settings
from librarian.db import Database
from librarian.isbn_auto_file import (
    ACTION_ID,
    METRIC_FILED,
    METRIC_UNDO,
    is_eligible_slip,
    is_isbn_strong,
    isbn_auto_file_enabled,
    run_isbn_auto_file,
)
from librarian.pulse import assemble_pulse, increment
from librarian.sorting_undo import public_undo, restore_sorting_undo


VALID_ISBN = "9780143127741"


def _settings(**kwargs) -> Settings:
    base = dict(isbn_auto_file_enabled=False)
    base.update(kwargs)
    return Settings(**base)


def test_default_off_and_isbn_strong_gate():
    assert isbn_auto_file_enabled(_settings()) is False
    assert isbn_auto_file_enabled(_settings(isbn_auto_file_enabled=True)) is True
    strong = {
        "kind": "book",
        "title": "Born to Run",
        "author": "Christopher McDougall",
        "isbn": VALID_ISBN,
        "review_state": "needs_review",
        "review_reason": "low_confidence",
        "folder_path": "/data/complete/x",
    }
    assert is_isbn_strong(strong) is True
    assert is_eligible_slip(strong) is True
    comic = {**strong, "kind": "comic"}
    assert is_isbn_strong(comic) is False
    assert is_eligible_slip(comic) is False
    audio = {**strong, "kind": "audiobook"}
    assert is_eligible_slip(audio) is False
    hard = {**strong, "review_reason": "extra_files"}
    assert is_eligible_slip(hard) is False
    bad_isbn = {**strong, "isbn": "9780143127740"}
    assert is_isbn_strong(bad_isbn) is False


def test_run_respects_toggle_off(tmp_path):
    db = Database(tmp_path / "librarian.db")
    folder = tmp_path / "books" / "Ada" / "Title"
    folder.mkdir(parents=True)
    (folder / "book.epub").write_bytes(b"epub")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Title",
            "author": "Ada",
            "isbn": VALID_ISBN,
            "review_state": "needs_review",
            "review_reason": "low_confidence",
            "folder_path": str(folder),
        }
    )
    result = run_isbn_auto_file(db, _settings(isbn_auto_file_enabled=False))
    assert result["enabled"] is False
    assert result["filed"] == 0
    assert db.get_work(work["id"])["review_state"] == "needs_review"


def test_run_files_isbn_strong_books_skips_audio_and_records_undo(tmp_path, monkeypatch):
    called: list[str] = []

    def boom(*_args, **_kwargs):
        called.append("sab")
        raise AssertionError("isbn auto-file must never talk to SABnzbd")

    monkeypatch.setattr("librarian.sabnzbd.SABClient.addfile", boom)
    monkeypatch.setattr("librarian.jobs._queue_download", boom)

    db = Database(tmp_path / "librarian.db")
    book_dir = tmp_path / "books" / "Ada" / "Born to Run"
    book_dir.mkdir(parents=True)
    (book_dir / "book.epub").write_bytes(b"epub")
    book = db.upsert_work(
        {
            "kind": "book",
            "title": "Born to Run",
            "author": "Ada Lovelace",
            "isbn": VALID_ISBN,
            "review_state": "needs_review",
            "review_reason": "low_confidence",
            "folder_path": str(book_dir),
        }
    )
    audio_dir = tmp_path / "audio" / "Ada" / "Listen"
    audio_dir.mkdir(parents=True)
    (audio_dir / "a.m4b").write_bytes(b"m4b")
    audio = db.upsert_work(
        {
            "kind": "audiobook",
            "title": "Listen",
            "author": "Ada Lovelace",
            "isbn": VALID_ISBN,
            "review_state": "needs_review",
            "review_reason": "low_confidence",
            "folder_path": str(audio_dir),
        }
    )
    comic_dir = tmp_path / "comics" / "Series" / "1"
    comic_dir.mkdir(parents=True)
    (comic_dir / "1.cbz").write_bytes(b"cbz")
    comic = db.upsert_work(
        {
            "kind": "comic",
            "title": "Issue 1",
            "author": "Artist",
            "isbn": VALID_ISBN,
            "review_state": "needs_review",
            "review_reason": "low_confidence",
            "folder_path": str(comic_dir),
        }
    )

    result = run_isbn_auto_file(db, _settings(isbn_auto_file_enabled=True))
    assert result["enabled"] is True
    assert result["filed"] == 1
    assert result["undo_recorded"] is True
    assert called == []
    assert db.get_work(book["id"])["review_state"] != "needs_review"
    assert db.get_work(audio["id"])["review_state"] == "needs_review"
    assert db.get_work(comic["id"])["review_state"] == "needs_review"
    undo = public_undo(db)
    assert undo["available"] is True
    assert undo["action"] == ACTION_ID


def test_undo_increments_mis_shelve_pulse(tmp_path):
    db = Database(tmp_path / "librarian.db")
    folder = tmp_path / "books" / "Ada" / "Title"
    folder.mkdir(parents=True)
    (folder / "book.epub").write_bytes(b"epub")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Title",
            "author": "Ada",
            "isbn": VALID_ISBN,
            "review_state": "needs_review",
            "review_reason": "quiet_hours",
            "folder_path": str(folder),
        }
    )
    run_isbn_auto_file(db, _settings(isbn_auto_file_enabled=True))
    assert db.get_work(work["id"])["review_state"] != "needs_review"
    restored = restore_sorting_undo(db)
    assert restored["ok"] is True
    assert restored["restored"] >= 1
    assert db.get_work(work["id"])["review_state"] == "needs_review"
    pulse = assemble_pulse(db, data_dir=tmp_path)
    assert int(pulse["isbn_auto_file"]["value"]) >= 1
    assert int(pulse["isbn_auto_file_undo"]["value"]) >= 1


def test_pulse_metrics_round_trip(tmp_path):
    db = Database(tmp_path / "librarian.db")
    increment(db, METRIC_FILED, count=3)
    increment(db, METRIC_UNDO, count=1)
    pulse = assemble_pulse(db, data_dir=tmp_path)
    assert pulse["isbn_auto_file"]["value"] == 3
    assert pulse["isbn_auto_file_undo"]["value"] == 1


def test_isbn_auto_file_source_never_imports_sab():
    import ast
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "librarian" / "isbn_auto_file.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert all("sabnzbd" not in item and item != "librarian.jobs" for item in imported)
