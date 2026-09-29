"""P4-MED-01 — foyer /api/features vs authenticated /api/features/ops."""

from __future__ import annotations

from fastapi.testclient import TestClient

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


def test_public_features_is_foyer_minimal(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.cookies.clear()
    resp = client.get("/api/features")
    assert resp.status_code == 200
    body = resp.json()
    assert body["owner_ready"] is True
    assert body["auth_methods"] == ["local"]
    assert "household_name" in body
    assert "version" in body
    assert "session_secret_ok" not in body
    assert "show_extra_categories" not in body
    assert "notifications" not in body


def test_features_ops_requires_auth(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.cookies.clear()
    assert client.get("/api/features/ops").status_code == 401


def test_features_ops_returns_ops_posture(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert (
        client.post(
            "/api/auth/local/login",
            json={"username": "owner", "password": "password123"},
        ).status_code
        == 200
    )
    resp = client.get("/api/features/ops")
    assert resp.status_code == 200
    body = resp.json()
    assert "session_secret_ok" in body
    assert "show_extra_categories" in body
    assert "notifications" in body
    assert "mail_configured" in body["notifications"]
    assert "channels" in body["notifications"]
    assert "owner_ready" not in body
