"""Stale enrich progress after process restart."""

from __future__ import annotations

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.enrich_progress import begin_enrich_run
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


def test_enrich_status_clears_stale_running_after_restart(tmp_path, monkeypatch):
    save_settings(
        tmp_path,
        Settings.from_mapping(
            {
                "books_root": str(tmp_path / "books"),
                "magazines_root": str(tmp_path / "magazines"),
                "comics_root": str(tmp_path / "comics"),
                "audiobooks_root": str(tmp_path / "audiobooks"),
                "incoming_music_root": str(tmp_path / "incoming"),
                "music_root": str(tmp_path / "music"),
            }
        ),
    )
    begin_enrich_run(tmp_path, source="manual", total=3, phase="enriching")
    client = _client(tmp_path, monkeypatch)
    assert client.post(
        "/api/auth/local/login", json={"username": "owner", "password": "password123"}
    ).status_code == 200
    status = client.get("/api/settings/enrich/status")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "failed"
    assert "restarted" in body["error"].lower()
