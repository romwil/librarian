from fastapi.testclient import TestClient

from librarian.auth import PUBLIC_HANDSHAKE_EXACT, is_public_handshake
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import SESSION_COOKIE_NAME, clear_session_secret_cache
from librarian.web.app import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    clear_rate_limits()
    return TestClient(create_app(tmp_path))


def test_public_handshake_exact_is_exhaustive():
    assert PUBLIC_HANDSHAKE_EXACT == {
        ("GET", "/api/health"),
        ("GET", "/api/features"),
        ("GET", "/api/invites/validate"),
        ("POST", "/api/invites/redeem/local"),
        ("POST", "/api/auth/local/login"),
        ("POST", "/api/auth/logout"),
    }
    assert is_public_handshake("GET", "/api/health?x=1") is True
    assert is_public_handshake("GET", "/api/auth/me") is False
    assert is_public_handshake("POST", "/api/auth/local/register") is False
    assert is_public_handshake("GET", "/api/auth/") is False
    assert is_public_handshake("GET", "/api/hall") is False


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
    assert client.post("/api/settings/scan").status_code == 403
    assert client.post("/api/settings/enrich").status_code == 403
    assert client.post("/api/settings/suggest-cache").status_code == 403
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
    assert client.get("/api/invites/validate").status_code == 404
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/hall").status_code == 401
    assert client.get("/api/search", params={"q": "dune"}).status_code == 401
    assert client.get("/api/suggest", params={"field": "author", "q": "frank"}).status_code == 401
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/local/register", json={"username": "x", "password": "password123"}).status_code == 401


def test_login_then_hall_and_favorite(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    login = client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "owner"
    set_cookie = login.headers.get("set-cookie", "")
    assert f"{SESSION_COOKIE_NAME}=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Lax" in set_cookie or "lax" in set_cookie.lower()
    assert "Secure" not in set_cookie
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


def test_secure_cookie_ignored_without_trusted_proxy(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-For": "198.51.100.20"},
    )
    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie", "")
    assert f"{SESSION_COOKIE_NAME}=" in set_cookie
    assert "Secure" not in set_cookie


def test_secure_cookie_when_proxy_is_trusted(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_TRUST_PROXY_HEADERS", "1")
    client = _client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
        headers={"X-Forwarded-Proto": "https"},
    )
    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie", "")
    assert f"{SESSION_COOKIE_NAME}=" in set_cookie
    assert "Secure" in set_cookie


def test_spoofed_xff_cannot_bypass_login_rate_limit(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    for i in range(11):
        client.post(
            "/api/auth/local/login",
            json={"username": "nobody", "password": f"wrong-{i}"},
            headers={"X-Forwarded-For": f"198.51.100.{i}"},
        )
    blocked = client.post(
        "/api/auth/local/login",
        json={"username": "nobody", "password": "wrong-final"},
        headers={"X-Forwarded-For": "198.51.100.99"},
    )
    assert blocked.status_code == 429
    assert "retry-after" in {k.lower() for k in blocked.headers}


def test_invite_validate_rate_limit(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    for _ in range(30):
        assert client.get("/api/invites/validate").status_code == 404
    blocked = client.get("/api/invites/validate")
    assert blocked.status_code == 429


def test_owner_indexer_ping_without_token(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    ping = client.post("/api/indexers/ping")
    assert ping.status_code == 200
    assert ping.json()["ok"] is False
    assert "api_token" in ping.json()["error"]
    listed = client.get("/api/indexers")
    assert listed.status_code == 200
    assert listed.json()["indexers"][0]["id"] == "nzbfinder"
    convert = client.post("/api/works/missing/convert", json={"format": "pdf"})
    assert convert.status_code == 404
