"""Conservative purge of catalog shells with no media on disk."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.purge_shells import classify_shell_purge, purge_shell_works
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def _client(tmp_path, monkeypatch, settings=None):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    if settings is not None:
        save_settings(tmp_path, settings)
    app = create_app(tmp_path)
    client = TestClient(app)
    assert client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
    ).status_code == 200
    return client, app


def _wait_status(client, *, timeout=8.0):
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        resp = client.get("/api/maintain/purge-shells/status")
        assert resp.status_code == 200
        last = resp.json()
        if last.get("status") in ("completed", "failed", "idle"):
            return last
        time.sleep(0.05)
    return last


def _book_settings(tmp_path):
    return Settings(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "magazines"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "audiobooks"),
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
        complete_root=str(tmp_path / "complete"),
    )


def test_purge_removes_resolved_shell_without_media(tmp_path, monkeypatch):
    settings = _book_settings(tmp_path)
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    shelf_dir = Path(settings.audiobooks_root) / "Author" / "Real Title"
    shelf_dir.mkdir(parents=True)
    media = shelf_dir / "Real Title.m4b"
    media.write_bytes(b"audio-bytes")
    shelf = db.upsert_work(
        {
            "kind": "audiobook",
            "title": "Real Title",
            "author": "Author",
            "folder_path": str(shelf_dir),
            "review_state": "none",
        }
    )
    db.upsert_file(
        {
            "work_id": shelf["id"],
            "path": str(media),
            "filename": media.name,
            "kind": "audiobook",
            "size": media.stat().st_size,
        }
    )
    shell = db.upsert_work(
        {
            "kind": "audiobook",
            "title": "Real.Title.Audio.book",
            "folder_path": str(tmp_path / "complete" / "Real.Title.Audio.book"),
            "review_state": "resolved",
        }
    )
    wishlist = db.upsert_work(
        {
            "kind": "book",
            "title": "Wishlist Stub",
            "author": "Someone",
            "isbn": "9781234567890",
            "review_state": "none",
        }
    )
    keep_folder = tmp_path / "newlib" / "Still Has Files"
    keep_folder.mkdir(parents=True)
    (keep_folder / "still.epub").write_bytes(b"epub")
    keep = db.upsert_work(
        {
            "kind": "book",
            "title": "Still Has Files",
            "folder_path": str(keep_folder),
            "review_state": "resolved",
        }
    )

    classified = classify_shell_purge(db, settings)
    assert shell["id"] in classified
    assert wishlist["id"] not in classified
    assert keep["id"] not in classified
    assert shelf["id"] not in classified

    result = purge_shell_works(db, settings)
    assert result["purged"] >= 1
    assert db.get_work(shell["id"]) is None
    assert db.get_work(shelf["id"]) is not None
    assert db.get_work(wishlist["id"]) is not None
    assert db.get_work(keep["id"]) is not None
    assert db.files_for_work(shelf["id"])


def test_maintain_purge_shells_api(tmp_path, monkeypatch):
    settings = _book_settings(tmp_path)
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    shell = db.upsert_work(
        {
            "kind": "audiobook",
            "title": "Dump.Title.Audio.book",
            "folder_path": str(tmp_path / "missing-dump"),
            "review_state": "resolved",
        }
    )
    started = client.post("/api/maintain/purge-shells")
    assert started.status_code == 200
    assert started.json().get("kicked_off") is True
    finished = _wait_status(client)
    assert finished.get("status") == "completed"
    assert int(finished.get("purged") or finished.get("result", {}).get("purged") or 0) >= 1
    assert db.get_work(shell["id"]) is None


def test_review_skip_deletes_slip(tmp_path, monkeypatch):
    settings = _book_settings(tmp_path)
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    slip = db.upsert_work(
        {
            "kind": "book",
            "title": "Skip Me",
            "folder_path": str(tmp_path / "complete" / "skip-me"),
            "review_state": "needs_review",
            "review_reason": "unknown",
        }
    )
    resp = client.post(f"/api/review/{slip['id']}/skip")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert db.get_work(slip["id"]) is None
