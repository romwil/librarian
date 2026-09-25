from fastapi.testclient import TestClient

from librarian.db import Database
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


def test_continue_rail_orders_unfinished(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    db = Database(tmp_path / "librarian.db")
    dune = db.upsert_work({"kind": "book", "title": "Dune", "author": "Herbert"})
    kindred = db.upsert_work({"kind": "book", "title": "Kindred", "author": "Butler"})
    db.add_file({"work_id": dune["id"], "path": "/b/Dune.epub", "filename": "Dune.epub", "kind": "book"})
    db.add_file({"work_id": kindred["id"], "path": "/b/Kindred.epub", "filename": "Kindred.epub", "kind": "book"})
    hall = client.get("/api/hall")
    assert hall.json()["continue"] == []
    touch = client.post(f"/api/works/{dune['id']}/progress", json={})
    assert touch.status_code == 200
    assert touch.json()["progress"]["fraction"] == 0.05
    client.post(f"/api/works/{kindred['id']}/progress", json={"fraction": 0.4})
    client.post(f"/api/works/{dune['id']}/progress", json={"finished": True})
    rail = client.get("/api/hall").json()["continue"]
    assert [row["title"] for row in rail] == ["Kindred"]
    assert rail[0]["progress"] == 40


def test_reader_forbidden_on_indexer_ping(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    minted = client.post("/api/invites", json={"role": "reader"})
    token = minted.json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    client.post(
        "/api/invites/redeem/local",
        json={"token": token, "username": "reader1", "password": "password123"},
    )
    assert client.post("/api/indexers/ping").status_code == 403
    assert client.get("/api/indexers").status_code == 403
