from fastapi.testclient import TestClient

from librarian.web.app import create_app


def test_health_status_ok(tmp_path):
    client = TestClient(create_app(tmp_path))
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["ok"] is True
    assert body["version"] == "0.1.0"


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
