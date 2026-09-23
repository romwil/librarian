"""Value-based tests for conservative Review duplicate purge."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.purge_duplicates import classify_purge_candidates, purge_duplicate_reviews
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


def _wait_purge_status(client, *, timeout=8.0):
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        resp = client.get("/api/review/purge-duplicates/status")
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
    )


def test_purge_dismisses_shelf_fingerprint_twin(tmp_path, monkeypatch):
    settings = _book_settings(tmp_path)
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    payload = b"same-bytes-for-shelf-twin-purge"
    dest_dir = Path(settings.books_root) / "Allison Brennan" / "Notorious"
    dest_dir.mkdir(parents=True)
    (dest_dir / "Notorious - Allison Brennan.epub").write_bytes(payload)
    shelf = db.upsert_work(
        {
            "kind": "book",
            "title": "Notorious",
            "author": "Allison Brennan",
            "folder_path": str(dest_dir),
            "review_state": "none",
        }
    )
    folder = tmp_path / "newlib" / "Allison Brennan" / "Notorious (8350)"
    folder.mkdir(parents=True)
    (folder / "Notorious - Allison Brennan.epub").write_bytes(payload)
    slip = db.upsert_work(
        {
            "kind": "book",
            "title": "Notorious",
            "author": "Allison Brennan",
            "review_state": "needs_review",
            "review_reason": "collision",
            "folder_path": str(folder),
        }
    )
    unsure = tmp_path / "newlib" / "Mystery Dump"
    unsure.mkdir(parents=True)
    (unsure / "mystery.epub").write_bytes(b"unique-unsure-bytes")
    unsure_slip = db.upsert_work(
        {
            "kind": "book",
            "title": "Mystery Dump",
            "author": "",
            "review_state": "needs_review",
            "review_reason": "unknown_identity",
            "folder_path": str(unsure),
        }
    )

    result = purge_duplicate_reviews(db, settings)
    assert result["purged"] == 1
    assert result["shelf_twins"] == 1
    assert result["kept"] >= 1
    assert db.get_work(slip["id"])["review_state"] == "resolved"
    assert db.get_work(unsure_slip["id"])["review_state"] == "needs_review"
    assert db.get_work(shelf["id"])["review_state"] == "none"
    assert (folder / "Notorious - Allison Brennan.epub").is_file()


def test_purge_keeps_one_of_identical_slips(tmp_path, monkeypatch):
    settings = _book_settings(tmp_path)
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    payload = b"identical-slip-twin-bytes"
    first_dir = tmp_path / "complete" / "dup-a"
    second_dir = tmp_path / "complete" / "dup-b"
    first_dir.mkdir(parents=True)
    second_dir.mkdir(parents=True)
    (first_dir / "Same Book.epub").write_bytes(payload)
    (second_dir / "Same Book.epub").write_bytes(payload)
    first = db.upsert_work(
        {
            "kind": "book",
            "title": "Same Book",
            "author": "Author",
            "review_state": "needs_review",
            "review_reason": "low_confidence",
            "folder_path": str(first_dir),
            "created_at": 1000.0,
        }
    )
    second = db.upsert_work(
        {
            "kind": "book",
            "title": "Same Book",
            "author": "Author",
            "review_state": "needs_review",
            "review_reason": "low_confidence",
            "folder_path": str(second_dir),
            "created_at": 2000.0,
        }
    )
    to_purge, _ = classify_purge_candidates(db, settings, [first, second])
    assert len(to_purge) == 1
    assert second["id"] in to_purge
    assert to_purge[second["id"]] == "slip_duplicate"

    result = purge_duplicate_reviews(db, settings)
    assert result["slip_twins"] == 1
    assert result["purged"] == 1
    assert db.get_work(first["id"])["review_state"] == "needs_review"
    assert db.get_work(second["id"])["review_state"] == "resolved"


def test_purge_does_not_touch_unsure_without_twin(tmp_path, monkeypatch):
    settings = _book_settings(tmp_path)
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    folder = tmp_path / "complete" / "only-one"
    folder.mkdir(parents=True)
    (folder / "Alone.epub").write_bytes(b"solo-unsure-payload")
    slip = db.upsert_work(
        {
            "kind": "book",
            "title": "Alone",
            "author": "Someone",
            "review_state": "needs_review",
            "review_reason": "unknown_identity",
            "folder_path": str(folder),
        }
    )
    result = purge_duplicate_reviews(db, settings)
    assert result["purged"] == 0
    assert result["kept"] == 1
    assert db.get_work(slip["id"])["review_state"] == "needs_review"


def test_review_purge_duplicates_api_background(tmp_path, monkeypatch):
    settings = _book_settings(tmp_path)
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    payload = b"api-purge-shelf-twin"
    dest_dir = Path(settings.books_root) / "Le Guin" / "The Left Hand of Darkness"
    dest_dir.mkdir(parents=True)
    (dest_dir / "The Left Hand of Darkness.epub").write_bytes(payload)
    db.upsert_work(
        {
            "kind": "book",
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "folder_path": str(dest_dir),
            "review_state": "none",
        }
    )
    folder = tmp_path / "complete" / "lefthand-dup"
    folder.mkdir(parents=True)
    (folder / "The Left Hand of Darkness.epub").write_bytes(payload)
    slip = db.upsert_work(
        {
            "kind": "book",
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "review_state": "needs_review",
            "review_reason": "collision",
            "folder_path": str(folder),
        }
    )
    listed = client.get("/api/review")
    assert listed.status_code == 200
    assert listed.json()["needs_review_count"] >= 1

    resp = client.post("/api/review/purge-duplicates")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("kicked_off") is True or body.get("status") in ("running", "completed")
    status = _wait_purge_status(client, timeout=15.0)
    assert status["status"] == "completed", status
    assert int(status.get("purged") or (status.get("result") or {}).get("purged") or 0) >= 1
    assert db.get_work(slip["id"])["review_state"] == "resolved"


def test_purge_duplicates_status_idle(tmp_path, monkeypatch):
    client, _app = _client(tmp_path, monkeypatch)
    idle = client.get("/api/review/purge-duplicates/status")
    assert idle.status_code == 200
    body = idle.json()
    assert body["status"] in ("idle", "completed", "failed")
    assert "needs_review_remaining" in body
