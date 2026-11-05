"""PRD-011: Downloads default view is actionable; Arrived/Failed dismissible."""

from __future__ import annotations

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.jobs import dismiss_queue_job
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def _owner_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    monkeypatch.setattr("librarian.config.load_dotenv", lambda path=None: None)
    save_settings(tmp_path, Settings(llm_api_key=""))
    clear_session_secret_cache()
    clear_rate_limits()
    client = TestClient(create_app(tmp_path))
    assert (
        client.post(
            "/api/auth/local/login",
            json={"username": "owner", "password": "password123"},
        ).status_code
        == 200
    )
    return client


def _seed(db: Database) -> dict[str, str]:
    asked = db.create_job({"status": "asked", "title": "Ask me", "kind": "book"})
    failed = db.create_job(
        {"status": "failed", "title": "Broke", "kind": "book", "error": "nzb gone"}
    )
    review = db.create_job({"status": "review", "title": "Sort me", "kind": "book"})
    active = db.create_job({"status": "downloading", "title": "In flight", "kind": "book"})
    arrived = db.create_job({"status": "organized", "title": "Shelved", "kind": "book"})
    skipped = db.create_job({"status": "skipped", "title": "Old skip", "kind": "book"})
    return {
        "asked": asked["id"],
        "failed": failed["id"],
        "review": review["id"],
        "active": active["id"],
        "arrived": arrived["id"],
        "skipped": skipped["id"],
    }


def test_queue_defaults_to_actionable_subset(tmp_path, monkeypatch):
    client = _owner_client(tmp_path, monkeypatch)
    db = Database(tmp_path / "librarian.db")
    _seed(db)

    resp = client.get("/api/queue")
    assert resp.status_code == 200
    body = resp.json()
    assert body["view"] == "actionable"
    statuses = {row["status"] for row in body["jobs"]}
    assert statuses == {"asked", "failed", "review"}
    assert body["counts"]["actionable"] == 3
    assert body["counts"]["active"] == 1
    assert body["counts"]["history"] == 1
    assert body["counts"]["all"] == 6


def test_queue_history_and_all_escape_hatch(tmp_path, monkeypatch):
    client = _owner_client(tmp_path, monkeypatch)
    db = Database(tmp_path / "librarian.db")
    _seed(db)

    history = client.get("/api/queue", params={"view": "history"})
    assert history.status_code == 200
    assert {row["status"] for row in history.json()["jobs"]} == {"organized"}

    active = client.get("/api/queue", params={"view": "active"})
    assert active.status_code == 200
    assert {row["status"] for row in active.json()["jobs"]} == {"downloading"}

    all_jobs = client.get("/api/queue", params={"view": "all"})
    assert all_jobs.status_code == 200
    assert len(all_jobs.json()["jobs"]) == 6


def test_dismiss_arrived_and_refuse_active(tmp_path, monkeypatch):
    client = _owner_client(tmp_path, monkeypatch)
    db = Database(tmp_path / "librarian.db")
    ids = _seed(db)

    arrived = client.post(f"/api/queue/{ids['arrived']}/dismiss")
    assert arrived.status_code == 200
    assert arrived.json()["job"]["status"] == "skipped"

    active = client.post(f"/api/queue/{ids['active']}/dismiss")
    assert active.status_code == 400
    assert "cannot be dismissed" in active.json()["detail"].lower()

    review = client.post(f"/api/queue/{ids['review']}/dismiss")
    assert review.status_code == 400


def test_dismiss_queue_job_allows_organized(tmp_path):
    db = Database(tmp_path / "librarian.db")
    job = db.create_job({"status": "organized", "title": "Done", "kind": "book"})
    updated = dismiss_queue_job(db, job["id"])
    assert updated["status"] == "skipped"
