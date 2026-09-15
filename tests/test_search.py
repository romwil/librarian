from fastapi.testclient import TestClient

from librarian.db import Database
from librarian.nzbfinder import NZBFinderError
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


def _login(client):
    resp = client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    assert resp.status_code == 200


def test_search_beyond_without_token_surfaces_error(tmp_path, monkeypatch):
    monkeypatch.setenv("NZBFINDER_API_TOKEN", "")
    client = _client(tmp_path, monkeypatch)
    _login(client)
    resp = client.get("/api/search", params={"q": "stephen king", "beyond": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["q"] == "stephen king"
    assert body["local"] == []
    assert body["beyond"] == []
    assert body["beyond_error"] == "NZBFinder api_token is not configured"


def test_search_beyond_indexer_error_keeps_local_and_surfaces_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("NZBFINDER_API_TOKEN", "tok")
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    db.upsert_work({"kind": "book", "title": "The Shining", "author": "Stephen King"})

    def fail_get(self, path, extra=None):
        raise NZBFinderError("NZBFinder returned non-JSON")

    monkeypatch.setattr("librarian.nzbfinder.NZBFinderClient._get", fail_get)
    resp = client.get("/api/search", params={"q": "king", "beyond": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert [row["title"] for row in body["local"]] == ["The Shining"]
    assert body["beyond"] == []
    assert body["beyond_error"] == "NZBFinder returned non-JSON"
