"""P2-CRIT-01: GET /api/queue is read-only; mutating work lives on POST /api/queue/tick."""

from __future__ import annotations

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.db import Database
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


def test_get_queue_does_not_call_pollers(tmp_path, monkeypatch):
    """GET /api/queue must not run watch / RSS / SAB poll side effects."""
    calls = {"watch": 0, "rss": 0, "active": 0}

    def fake_watch(*_a, **_k):
        calls["watch"] += 1
        return 0

    def fake_rss(*_a, **_k):
        calls["rss"] += 1
        return 0

    def fake_active(*_a, **_k):
        calls["active"] += 1
        return 0

    monkeypatch.setattr("librarian.web.routers.queue.poll_watch_folder", fake_watch)
    monkeypatch.setattr("librarian.web.routers.queue.poll_rss_feeds", fake_rss)
    monkeypatch.setattr("librarian.web.routers.queue.poll_active_jobs", fake_active)

    client = _owner_client(tmp_path, monkeypatch)
    db = Database(tmp_path / "librarian.db")
    db.create_job(
        {
            "status": "asked",
            "title": "Dune",
            "kind": "book",
            "requested_by": "owner",
            "payload": {"title": "Dune", "guid": "g1"},
        }
    )
    resp = client.get("/api/queue")
    assert resp.status_code == 200
    jobs = resp.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Dune"
    assert calls == {"watch": 0, "rss": 0, "active": 0}


def test_post_queue_tick_runs_pollers(tmp_path, monkeypatch):
    """POST /api/queue/tick is the explicit kick for watch / RSS / SAB."""
    calls = {"watch": 0, "rss": 0, "active": 0}

    def fake_watch(*_a, **_k):
        calls["watch"] += 1
        return 1

    def fake_rss(*_a, **_k):
        calls["rss"] += 1
        return 0

    def fake_active(*_a, **_k):
        calls["active"] += 1
        return 0

    monkeypatch.setattr("librarian.web.routers.queue.poll_watch_folder", fake_watch)
    monkeypatch.setattr("librarian.web.routers.queue.poll_rss_feeds", fake_rss)
    monkeypatch.setattr("librarian.web.routers.queue.poll_active_jobs", fake_active)

    client = _owner_client(tmp_path, monkeypatch)
    resp = client.post("/api/queue/tick")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert calls == {"watch": 1, "rss": 1, "active": 1}


def test_get_queue_does_not_ingest_watch_drop(tmp_path, monkeypatch):
    """Value: a watch-folder drop stays untouched after GET /api/queue."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    monkeypatch.setattr("librarian.config.load_dotenv", lambda path=None: None)
    watch = tmp_path / "inbox"
    watch.mkdir()
    drop = watch / "Le Guin - The Left Hand of Darkness 9780441478125.epub"
    drop.write_bytes(b"epub")
    books = tmp_path / "books"
    books.mkdir()
    save_settings(
        tmp_path,
        Settings.from_mapping(
            {
                "llm_api_key": "",
                "watch_root": str(watch),
                "watch_enabled": True,
                "books_root": str(books),
                "magazines_root": str(tmp_path / "magazines"),
                "comics_root": str(tmp_path / "comics"),
                "audiobooks_root": str(tmp_path / "audiobooks"),
                "incoming_music_root": str(tmp_path / "incoming"),
                "music_root": str(tmp_path / "music"),
                "nzbfinder_api_token": "",
                "sabnzbd_api_key": "",
            }
        ),
    )
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
    listed = client.get("/api/queue")
    assert listed.status_code == 200
    assert drop.exists()
    assert listed.json()["jobs"] == []

    kicked = client.post("/api/queue/tick")
    assert kicked.status_code == 200
    after = client.get("/api/queue")
    assert after.status_code == 200
    assert not drop.exists()
    assert after.json()["jobs"]
    assert after.json()["jobs"][0]["payload"]["source"] == "watch"
