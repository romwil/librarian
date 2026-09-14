from fastapi.testclient import TestClient

from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    return TestClient(create_app(tmp_path))


def test_reader_forbidden_on_settings_and_invite_op(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"}).status_code == 200
    minted = client.post("/api/invites", json={"role": "reader"})
    token = minted.json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    redeemed = client.post(
        "/api/invites/redeem/local",
        json={"token": token, "username": "reader1", "password": "password123"},
    )
    assert redeemed.status_code == 200
    assert client.get("/api/settings").status_code == 403
    assert client.put("/api/settings", json={"household_name": "Nope"}).status_code == 403
    assert client.post("/api/invites", json={"role": "reader"}).status_code == 403
    assert client.get("/api/people").status_code == 403


def test_op_cannot_invite_op_via_http(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    minted = client.post("/api/invites", json={"role": "op"})
    token = minted.json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert (
        client.post(
            "/api/invites/redeem/local",
            json={"token": token, "username": "ops", "password": "password123"},
        ).status_code
        == 200
    )
    forbidden = client.post("/api/invites", json={"role": "op"})
    assert forbidden.status_code == 403
    reader = client.post("/api/invites", json={"role": "reader"})
    assert reader.status_code == 200
    assert "token" in reader.json()


def test_unauthenticated_handshake_only(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.cookies.clear()
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/features").status_code == 200
    assert client.get("/api/hall").status_code == 401
    assert client.get("/api/search", params={"q": "dune"}).status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_login_then_hall_and_favorite(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    login = client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "owner"
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["review_count"] == 0
    hall = client.get("/api/hall")
    assert hall.status_code == 200
    assert hall.json()["empty"] is True
    from librarian.db import Database

    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work({"kind": "book", "title": "Dune", "author": "Herbert"})
    fav = client.post(f"/api/works/{work['id']}/favorite")
    assert fav.status_code == 200
    assert fav.json()["favorite"] is True
    detail = client.get(f"/api/works/{work['id']}")
    assert detail.status_code == 200
    assert detail.json()["work"]["title"] == "Dune"
    assert detail.json()["favorite"] is True
    search = client.get("/api/search", params={"q": "Dune"})
    assert search.status_code == 200
    assert [row["title"] for row in search.json()["local"]] == ["Dune"]
