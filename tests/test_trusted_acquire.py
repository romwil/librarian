"""Reader trusted-acquire: People flag, /auth/me, Search beyond + Discover gates."""

from __future__ import annotations

from fastapi.testclient import TestClient

from librarian.auth import hash_password, public_user, user_trusted_acquire
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


def _login(client, username: str) -> None:
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert (
        client.post(
            "/api/auth/local/login",
            json={"username": username, "password": "password123"},
        ).status_code
        == 200
    )


def test_public_user_exposes_paired_acquire_flags(tmp_path):
    db = Database(tmp_path / "librarian.db")
    reader = db.create_local_user(
        user_id="u-reader",
        display_name="reader",
        role="reader",
        password_hash=hash_password("password123"),
    )
    view = public_user(reader)
    assert view["trusted_acquire"] is False
    assert view["can_search_beyond"] is False
    assert view["can_auto_confirm"] is False

    db.set_user_trusted_acquire(reader["id"], True)
    fresh = db.get_user(reader["id"])
    assert fresh is not None
    trusted = public_user(fresh)
    assert trusted["trusted_acquire"] is True
    assert trusted["can_search_beyond"] is True
    assert trusted["can_auto_confirm"] is True
    assert user_trusted_acquire(fresh) is True


def test_owner_and_op_always_trusted_acquire_without_flag(tmp_path):
    db = Database(tmp_path / "librarian.db")
    owner = db.create_local_user(
        user_id="u-owner",
        display_name="owner",
        role="owner",
        password_hash=hash_password("password123"),
    )
    op = db.create_local_user(
        user_id="u-op",
        display_name="helper",
        role="op",
        password_hash=hash_password("password123"),
    )
    assert user_trusted_acquire(owner) is True
    assert user_trusted_acquire(op) is True
    assert public_user(owner)["can_search_beyond"] is True
    assert public_user(op)["can_auto_confirm"] is True


def test_people_trusted_acquire_endpoint_and_gates(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    db = Database(tmp_path / "librarian.db")
    reader = db.create_local_user(
        user_id="u-reader",
        display_name="reader",
        role="reader",
        password_hash=hash_password("password123"),
    )
    owner = db.get_user_by_display_name("owner")
    assert owner is not None

    _login(client, "owner")
    denied = client.post(
        f"/api/people/{owner['id']}/trusted-acquire",
        json={"trusted_acquire": True},
    )
    assert denied.status_code == 400

    on = client.post(
        f"/api/people/{reader['id']}/trusted-acquire",
        json={"trusted_acquire": True},
    )
    assert on.status_code == 200, on.text
    assert on.json()["user"]["trusted_acquire"] is True
    assert on.json()["user"]["can_search_beyond"] is True
    assert on.json()["user"]["can_auto_confirm"] is True

    people = client.get("/api/people")
    assert people.status_code == 200
    listed = next(row for row in people.json()["users"] if row["id"] == reader["id"])
    assert listed["trusted_acquire"] is True

    _login(client, "reader")
    reader_me = client.get("/api/auth/me")
    assert reader_me.status_code == 200
    assert reader_me.json()["user"]["trusted_acquire"] is True
    assert reader_me.json()["user"]["can_search_beyond"] is True

    beyond = client.get("/api/search/beyond", params={"q": "Dune", "kind": "book"})
    assert beyond.status_code != 403

    discover = client.get("/api/discover")
    assert discover.status_code != 403

    _login(client, "owner")
    off = client.post(
        f"/api/people/{reader['id']}/trusted-acquire",
        json={"trusted_acquire": False},
    )
    assert off.status_code == 200
    assert off.json()["user"]["trusted_acquire"] is False

    _login(client, "reader")
    assert client.get("/api/search/beyond", params={"q": "Dune"}).status_code == 403
    assert client.get("/api/discover").status_code == 403
