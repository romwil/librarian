"""Safe undo for grooming — metadata-only timed window."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from librarian.db import Database
from librarian.grooming_undo import (
    assemble_grooming_undo,
    batch_is_active,
    record_grooming_batch,
    restore_grooming_batch,
    snapshot_work,
    undo_presence,
)
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def test_snapshot_and_presence():
    snap = snapshot_work({"id": "w1", "title": "Dune", "kind": "book", "review_state": "none"})
    assert snap["id"] == "w1"
    assert snap["title"] == "Dune"
    assert undo_presence(None).startswith("No recent")
    batch = {
        "label": "Purge shells",
        "works": [snap],
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1))
        .isoformat()
        .replace("+00:00", "Z"),
        "restored_at": "",
    }
    assert batch_is_active(batch) is True
    assert "still" in undo_presence(batch).lower() or "undo" in undo_presence(batch).lower()


def test_record_and_restore_round_trip(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = {
        "id": "shell-1",
        "title": "Ghost Volume",
        "kind": "book",
        "author": "A. Lamp",
        "review_state": "none",
        "review_reason": None,
    }
    db.upsert_work(work)
    assert db.get_work("shell-1") is not None
    record_grooming_batch(tmp_path, action="purge_shells", works=[work])
    assert assemble_grooming_undo(tmp_path)["available"] is True
    assert db.delete_work("shell-1") is True
    assert db.get_work("shell-1") is None
    result = restore_grooming_batch(db, tmp_path)
    assert result["ok"] is True
    assert result["restored"] == 1
    restored = db.get_work("shell-1")
    assert restored is not None
    assert restored["title"] == "Ghost Volume"
    assert assemble_grooming_undo(tmp_path)["available"] is False


def test_maintain_grooming_undo_api(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    clear_session_secret_cache()
    clear_rate_limits()
    client = TestClient(create_app(tmp_path))
    login = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
    )
    assert login.status_code == 200
    empty = client.get("/api/maintain/grooming-undo")
    assert empty.status_code == 200
    assert empty.json()["available"] is False

    record_grooming_batch(
        tmp_path,
        action="skip",
        works=[{"id": "skip-1", "title": "Skipped", "kind": "book", "review_state": "needs_review"}],
    )
    card = client.get("/api/maintain/grooming-undo")
    assert card.status_code == 200
    assert card.json()["available"] is True
    assert card.json()["count"] == 1

    restored = client.post("/api/maintain/grooming-undo")
    assert restored.status_code == 200
    assert restored.json()["ok"] is True
    assert restored.json()["restored"] >= 1
    db = Database(tmp_path / "librarian.db")
    assert db.get_work("skip-1") is not None
