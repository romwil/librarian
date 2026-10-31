"""Phase 1 guest-ready accounts: sessions, reset, roles, delete, export, privacy."""

from fastapi.testclient import TestClient

from librarian.auth import PUBLIC_HANDSHAKE_EXACT
from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.privacy import household_privacy_notice
from librarian.rate_limit import ACCOUNT_BACKOFF_LIMIT, clear_rate_limits
from librarian.sessions import SESSION_COOKIE_NAME, clear_session_secret_cache
from librarian.web.app import create_app


def _client(tmp_path, monkeypatch, **settings_kw):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    clear_rate_limits()
    if settings_kw:
        save_settings(tmp_path, Settings(**settings_kw))
    return TestClient(create_app(tmp_path))


def _mint_and_redeem(client, *, role="reader", username="reader1"):
    minted = client.post("/api/invites", json={"role": role})
    assert minted.status_code == 200, minted.text
    token = minted.json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    redeemed = client.post(
        "/api/invites/redeem/local",
        json={"token": token, "username": username, "password": "password123"},
    )
    assert redeemed.status_code == 200, redeemed.text
    return redeemed.json()["user"]


def test_logout_revokes_session_row(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    login = client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    assert login.status_code == 200
    assert client.get("/api/auth/me").status_code == 200
    cookie = client.cookies.get(SESSION_COOKIE_NAME)
    assert cookie
    assert client.post("/api/auth/logout").status_code == 200
    client.cookies.set(SESSION_COOKIE_NAME, cookie)
    assert client.get("/api/auth/me").status_code == 401


def test_sign_out_everywhere_and_password_change(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    clear_session_secret_cache()
    clear_rate_limits()
    app = create_app(tmp_path)
    client = TestClient(app)
    other = TestClient(app)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    user = _mint_and_redeem(client, username="ada")
    assert other.post("/api/auth/local/login", json={"username": "ada", "password": "password123"}).status_code == 200
    changed = client.post(
        "/api/auth/password",
        json={"current_password": "password123", "new_password": "new-secret-99"},
    )
    assert changed.status_code == 200
    assert other.get("/api/auth/me").status_code == 401
    client.cookies.clear()
    assert (
        client.post("/api/auth/local/login", json={"username": "ada", "password": "password123"}).status_code == 401
    )
    assert (
        client.post("/api/auth/local/login", json={"username": "ada", "password": "new-secret-99"}).status_code
        == 200
    )
    everywhere = client.post("/api/auth/sessions/revoke-all")
    assert everywhere.status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert user["display_name"] == "ada"


def test_owner_reset_is_single_use_and_24h(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    member = _mint_and_redeem(client, username="rowan")
    client.post("/api/auth/logout")
    client.cookies.clear()
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    issued = client.post(f"/api/people/{member['id']}/reset")
    assert issued.status_code == 200
    assert issued.json()["reset_url"].startswith("http://")
    token = issued.json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    validated = client.get("/api/auth/reset/validate", params={"token": token})
    assert validated.status_code == 200
    assert validated.json()["display_name"] == "rowan"
    first = client.post("/api/auth/reset/redeem", json={"token": token, "password": "fresh-pass-1"})
    assert first.status_code == 200
    replay = client.post("/api/auth/reset/redeem", json={"token": token, "password": "fresh-pass-2"})
    assert replay.status_code == 400
    client.cookies.clear()
    assert (
        client.post("/api/auth/local/login", json={"username": "rowan", "password": "password123"}).status_code
        == 401
    )
    assert (
        client.post("/api/auth/local/login", json={"username": "rowan", "password": "fresh-pass-1"}).status_code
        == 200
    )


def test_owner_reset_refuses_owner_account(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    me = client.get("/api/auth/me").json()["user"]
    refused = client.post(f"/api/people/{me['id']}/reset")
    assert refused.status_code == 400


def test_op_people_ui_matches_api(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    _mint_and_redeem(client, role="op", username="opal")
    people = client.get("/api/people")
    assert people.status_code == 200
    assert people.json()["can_manage"] is False
    reader_invite = client.post("/api/invites", json={"role": "reader"})
    assert reader_invite.status_code == 200
    op_invite = client.post("/api/invites", json={"role": "op"})
    assert op_invite.status_code == 403
    listed = client.get("/api/invites").json()["invites"]
    assert all(row["role"] == "reader" for row in listed)
    member = _mint_and_redeem(client, username="wren")
    client.post("/api/auth/logout")
    client.cookies.clear()
    client.post("/api/auth/local/login", json={"username": "opal", "password": "password123"})
    assert client.post(f"/api/people/{member['id']}/role", json={"role": "op"}).status_code == 403
    assert client.post(f"/api/people/{member['id']}/disable", json={"disabled": True}).status_code == 403
    assert client.delete(f"/api/people/{member['id']}").status_code == 403
    assert client.post(f"/api/people/{member['id']}/reset").status_code == 403


def test_reader_op_disable_delete_cascade(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    member = _mint_and_redeem(client, username="ash")
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.post("/api/auth/local/login", json={"username": "ash", "password": "password123"}).status_code == 200
    client.get("/api/auth/export")
    client.post("/api/auth/logout")
    client.cookies.clear()
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    promoted = client.post(f"/api/people/{member['id']}/role", json={"role": "op"})
    assert promoted.status_code == 200
    assert promoted.json()["user"]["role"] == "op"
    demoted = client.post(f"/api/people/{member['id']}/role", json={"role": "reader"})
    assert demoted.json()["user"]["role"] == "reader"
    paused = client.post(f"/api/people/{member['id']}/disable", json={"disabled": True})
    assert paused.json()["user"]["disabled"] is True
    client.post("/api/auth/logout")
    client.cookies.clear()
    blocked = client.post("/api/auth/local/login", json={"username": "ash", "password": "password123"})
    assert blocked.status_code == 403
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    client.post(f"/api/people/{member['id']}/disable", json={"disabled": False})
    gone = client.delete(f"/api/people/{member['id']}")
    assert gone.status_code == 200
    db = Database(tmp_path / "librarian.db")
    assert db.get_user(member["id"]) is None
    with db._connect() as conn:
        progress = conn.execute("SELECT COUNT(*) AS n FROM progress WHERE user_id = ?", (member["id"],)).fetchone()
        prefs = conn.execute("SELECT COUNT(*) AS n FROM user_prefs WHERE user_id = ?", (member["id"],)).fetchone()
        shelves = conn.execute(
            "SELECT COUNT(*) AS n FROM shelves WHERE owner_user_id = ?", (member["id"],)
        ).fetchone()
        sessions = conn.execute("SELECT COUNT(*) AS n FROM sessions WHERE user_id = ?", (member["id"],)).fetchone()
    assert int(progress["n"]) == 0
    assert int(prefs["n"]) == 0
    assert int(shelves["n"]) == 0
    assert int(sessions["n"]) == 0
    owner = client.get("/api/auth/me").json()["user"]
    assert client.delete(f"/api/people/{owner['id']}").status_code == 403


def test_export_is_own_card_only(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    _mint_and_redeem(client, username="export-me")
    bundle = client.get("/api/auth/export")
    assert bundle.status_code == 200
    payload = bundle.json()
    assert payload["user"]["display_name"] == "export-me"
    assert "password_hash" not in payload["user"]
    dumped = str(payload)
    assert "password123" not in dumped
    assert "owner" not in payload["user"]["display_name"]
    assert all(row.get("display_name") != "owner" for row in [payload["user"]])


def test_privacy_notice_from_live_config(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, llm_provider="openai", llm_api_key="sk-test", llm_model="gpt-4o-mini")
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    notice = client.get("/api/privacy")
    assert notice.status_code == 200
    text = " ".join(notice.json()["paragraphs"])
    assert "7 days" in text
    assert "24 hours" in text
    assert "35 days" in text
    assert "openai" in text.lower() or "language" in text.lower()
    assert "analytics" in text.lower()
    generated = household_privacy_notice(Settings(llm_api_key="", nzbfinder_api_token=""))
    quiet = " ".join(generated["paragraphs"])
    assert "No language-model key" in quiet


def test_account_login_backoff(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    for i in range(ACCOUNT_BACKOFF_LIMIT):
        resp = client.post("/api/auth/local/login", json={"username": "owner", "password": f"wrong-{i}"})
        assert resp.status_code == 401
    blocked = client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    assert blocked.status_code == 429


def test_route_policy_matrix_owner_op_reader(tmp_path, monkeypatch):
    """ARCH-013: new Phase 1 routes do not exceed the UI."""
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    op = _mint_and_redeem(client, role="op", username="opal")
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    reader = _mint_and_redeem(client, username="reader1")
    client.post("/api/auth/logout")
    client.cookies.clear()

    owner_only = [
        ("POST", f"/api/people/{reader['id']}/reset", {}),
        ("POST", f"/api/people/{reader['id']}/role", {"role": "op"}),
        ("POST", f"/api/people/{reader['id']}/disable", {"disabled": True}),
        ("DELETE", f"/api/people/{reader['id']}", None),
    ]
    shared = [
        ("GET", "/api/people", None),
        ("GET", "/api/invites", None),
        ("GET", "/api/privacy", None),
        ("GET", "/api/auth/export", None),
    ]

    def login_as(name: str) -> None:
        client.cookies.clear()
        assert client.post("/api/auth/local/login", json={"username": name, "password": "password123"}).status_code == 200

    login_as("opal")
    for method, path, body in owner_only:
        if method == "DELETE":
            assert client.delete(path).status_code == 403
        else:
            assert client.request(method, path, json=body).status_code == 403
    for method, path, _body in shared:
        assert client.request(method, path).status_code == 200, path

    login_as("reader1")
    for method, path, body in owner_only + [("GET", "/api/people", None), ("GET", "/api/invites", None)]:
        if method == "DELETE":
            assert client.delete(path).status_code == 403
        else:
            assert client.request(method, path, json=body).status_code == 403
    assert client.get("/api/privacy").status_code == 200
    assert client.get("/api/auth/export").status_code == 200
    assert op["role"] == "op"


def test_reset_routes_are_public_handshake():
    assert ("GET", "/api/auth/reset/validate") in PUBLIC_HANDSHAKE_EXACT
    assert ("POST", "/api/auth/reset/redeem") in PUBLIC_HANDSHAKE_EXACT
