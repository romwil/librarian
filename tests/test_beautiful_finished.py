"""Beautiful Finished — ceremony whisper + someone_finished household fan-out."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from librarian.db import Database
from librarian.delight import finished_notice_copy, progress_already_finished, sanitize_whisper
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    clear_rate_limits()
    return TestClient(create_app(tmp_path))


def test_finished_notice_copy_and_progress_gate():
    assert finished_notice_copy(finisher_name="Ada", work_title="Dune") == {
        "title": "Ada finished Dune",
        "body": "",
    }
    with_note = finished_notice_copy(
        finisher_name="",
        work_title="",
        whisper_body="  Soft pages.  ",
    )
    assert with_note["title"] == "Someone finished a title"
    assert with_note["body"] == "Soft pages."
    assert progress_already_finished(None) is False
    assert progress_already_finished({"fraction": 0.4}) is False
    assert progress_already_finished({"fraction": 1.0}) is True
    assert progress_already_finished({"fraction": "nope"}) is False


def test_finish_fans_out_someone_finished_once_with_optional_whisper(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.post(
        "/api/auth/local/login", json={"username": "owner", "password": "password123"}
    ).status_code == 200
    minted = client.post("/api/invites", json={"role": "reader"})
    token = minted.json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    clear_rate_limits()
    assert (
        client.post(
            "/api/invites/redeem/local",
            json={"token": token, "username": "reader1", "password": "password123"},
        ).status_code
        == 200
    )

    db = Database(Path(tmp_path) / "librarian.db")
    work = db.upsert_work({"kind": "book", "title": "Kindred", "author": "Butler"})
    db.add_file(
        {
            "work_id": work["id"],
            "path": "/b/Kindred.epub",
            "filename": "Kindred.epub",
            "kind": "book",
        }
    )

    # Reader finishes with an optional household whisper.
    finished = client.post(
        f"/api/works/{work['id']}/progress",
        json={"finished": True, "whisper": "Left it warm on the table."},
    )
    assert finished.status_code == 200
    assert finished.json()["progress"]["fraction"] == 1.0
    assert finished.json()["whisper"]["body"] == "Left it warm on the table."
    assert len(finished.json()["whispers"]) == 1

    owner = db.get_user_by_display_name("owner")
    reader = db.get_user_by_display_name("reader1")
    assert owner and reader
    owner_notes = db.list_notifications_for_user(owner["id"], unread_only=True, limit=20)
    finished_notes = [n for n in owner_notes if n.get("kind") == "someone_finished"]
    assert len(finished_notes) == 1
    assert finished_notes[0]["title"] == "reader1 finished Kindred"
    assert finished_notes[0]["body"] == "Left it warm on the table."
    assert finished_notes[0]["payload"]["work_id"] == work["id"]

    # Finisher does not notify themselves.
    self_notes = [
        n
        for n in db.list_notifications_for_user(reader["id"], unread_only=False, limit=20)
        if n.get("kind") == "someone_finished"
    ]
    assert self_notes == []

    # Re-finish does not spam another notice (even with a new whisper).
    again = client.post(
        f"/api/works/{work['id']}/progress",
        json={"finished": True, "whisper": "Second thought."},
    )
    assert again.status_code == 200
    assert again.json()["whisper"]["body"] == "Second thought."
    owner_notes_again = [
        n
        for n in db.list_notifications_for_user(owner["id"], unread_only=False, limit=20)
        if n.get("kind") == "someone_finished"
    ]
    assert len(owner_notes_again) == 1


def test_whisper_payload_rejects_overlong_body(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.post(
        "/api/auth/local/login", json={"username": "owner", "password": "password123"}
    ).status_code == 200
    db = Database(Path(tmp_path) / "librarian.db")
    work = db.upsert_work({"kind": "book", "title": "Short", "author": "A"})
    huge = "x" * 400
    assert len(sanitize_whisper(huge)) == 280
    rejected = client.post(f"/api/works/{work['id']}/whispers", json={"body": huge})
    assert rejected.status_code == 422
