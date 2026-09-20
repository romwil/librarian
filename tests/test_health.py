from fastapi.testclient import TestClient

from librarian import __version__
from librarian.web.app import create_app


def test_health_status_ok(tmp_path):
    client = TestClient(create_app(tmp_path))
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["ok"] is True
    assert body["version"] == __version__
    assert "build" in body
    assert body["build"] == "" or isinstance(body["build"], str)


def test_health_build_from_file(tmp_path, monkeypatch):
    stamp = tmp_path / ".build-info"
    stamp.write_text("0.4.4 built test rev abc\n", encoding="utf-8")
    monkeypatch.setattr("librarian.web.app._REPO_ROOT", tmp_path)
    client = TestClient(create_app(tmp_path))
    body = client.get("/api/health").json()
    assert body["build"] == "0.4.4 built test rev abc"


def test_features_public_and_owner_ready(tmp_path):
    client = TestClient(create_app(tmp_path))
    resp = client.get("/api/features")
    assert resp.status_code == 200
    assert resp.json()["owner_ready"] is True
    assert resp.json()["auth_methods"] == ["local"]


def test_me_is_not_public(tmp_path):
    client = TestClient(create_app(tmp_path))
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
