from fastapi.testclient import TestClient

from librarian.web.app import create_app
from librarian.web.build_info import parse_build_info


def test_health_status_ok_only(tmp_path):
    client = TestClient(create_app(tmp_path))
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok"}
    assert "version" not in body
    assert "build" not in body
    assert "rev" not in body
    assert "notes_match" not in body
    assert "notes_version" not in body
    assert "ok" not in body


def test_health_ready_200_or_503_empty_body(tmp_path):
    client = TestClient(create_app(tmp_path))
    resp = client.get("/api/health/ready")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert body == {}
    assert "db_ok" not in body
    assert "poller_alive" not in body
    assert "last_backup" not in body


def test_health_ready_503_when_poller_dead(tmp_path, monkeypatch):
    client = TestClient(create_app(tmp_path))
    monkeypatch.setattr("librarian.web.routers.auth.is_ready", lambda **_kwargs: False)
    resp = client.get("/api/health/ready")
    assert resp.status_code == 503
    assert resp.json() == {}


def test_parse_build_info_splits_stamp():
    parsed = parse_build_info("0.6.2 built 2026-10-31T04:00:00Z rev abcdef1")
    assert parsed["version"] == "0.6.2"
    assert parsed["built_at"] == "2026-10-31T04:00:00Z"
    assert parsed["rev"] == "abcdef1"
    empty = parse_build_info("")
    assert empty["rev"] == ""
    assert empty["built_at"] == ""
