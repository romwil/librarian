"""Clear extra-files: large splits queue; hung items time out."""

from __future__ import annotations

from pathlib import Path

from librarian.config import Settings
from librarian.db import Database
from librarian.organize import (
    EXTRA_FILES_SYNC_CHILD_LIMIT,
    reprocess_extra_files_reviews,
    reprocess_extra_files_work,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "magazines"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "audiobooks"),
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
        complete_root=str(tmp_path / "complete"),
    )


def test_large_author_split_enqueues_without_sync_process(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    db = Database(tmp_path / "librarian.db")
    try:
        settings = _settings(tmp_path)
        author = tmp_path / "media" / "newlib" / "Jenika Snow"
        count = EXTRA_FILES_SYNC_CHILD_LIMIT + 2
        for index in range(count):
            folder = author / f"Title {index} ({1000 + index})"
            folder.mkdir(parents=True)
            (folder / f"Title {index} - Jenika Snow.epub").write_bytes(b"epub")
        work = db.upsert_work(
            {
                "kind": "book",
                "title": "A Bad Man: Joey",
                "author": "Jenika Snow",
                "review_state": "needs_review",
                "review_reason": "extra_files",
                "folder_path": str(author),
            }
        )
        ticks: list[dict] = []
        outcome = reprocess_extra_files_work(
            db,
            settings,
            work_id=work["id"],
            on_progress=lambda **kw: ticks.append(kw),
        )
        assert outcome["action"] == "split"
        assert outcome["process_sync"] is False
        assert int(outcome["queued"]) == count
        assert int(outcome["targets"]) == count
        assert len(ticks) == count
        refreshed = db.get_work(work["id"])
        assert refreshed["review_state"] == "resolved"
        jobs = db.list_jobs(limit=200)
        assert len(jobs) >= count
        assert all(str(job.get("status") or "") == "identifying" for job in jobs[:count])
    finally:
        db.close()


def test_reprocess_skips_item_on_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    db = Database(tmp_path / "librarian.db")
    try:
        settings = _settings(tmp_path)
        folder = tmp_path / "complete" / "Slow Book"
        folder.mkdir(parents=True)
        (folder / "Slow Book.epub").write_bytes(b"epub")
        db.upsert_work(
            {
                "kind": "book",
                "title": "Slow Book",
                "author": "Anon",
                "review_state": "needs_review",
                "review_reason": "extra_files",
                "folder_path": str(folder),
            }
        )

        def _hang(*_a, **_k):
            import time

            time.sleep(2.0)
            return {"action": "apply", "organized": True}

        monkeypatch.setattr("librarian.organize.reprocess_extra_files_work", _hang)
        result = reprocess_extra_files_reviews(
            db,
            settings,
            item_timeout_s=0.2,
        )
        assert int(result["failed"]) == 1
        assert int(result["considered"]) == 1
        assert result["errors"]
        assert "Timed out" in result["errors"][0]
    finally:
        db.close()
