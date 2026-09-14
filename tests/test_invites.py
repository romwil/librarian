import threading

import pytest
from fastapi.testclient import TestClient

from librarian.db import Database
from librarian.invites import (
    create_household_invite,
    encode_invite_token,
    hash_invite_token,
    parse_invite_token,
    redeem_local_invite,
)
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def test_parse_garbage_fails_closed_without_db():
    with pytest.raises(ValueError, match="Invite not found"):
        parse_invite_token("not-a-token")
    with pytest.raises(ValueError, match="Invite not found"):
        parse_invite_token("abc.def.deadbeef")


def test_encode_parse_roundtrip():
    signed = encode_invite_token("inviteid", "raw-token-value")
    invite_id, raw = parse_invite_token(signed)
    assert invite_id == "inviteid"
    assert raw == "raw-token-value"


def test_hash_at_rest_is_sha256_not_raw(tmp_path):
    db = Database(tmp_path / "librarian.db")
    minted = create_household_invite(db, created_by="owner-1", actor_role="owner", role="reader")
    stored = db.get_invite(minted["invite"]["id"])
    assert stored is not None
    assert minted["token"] not in stored["token_hash"]
    raw = parse_invite_token(minted["token"])[1]
    assert stored["token_hash"] == hash_invite_token(raw)
    assert raw not in stored.values()


def test_redeem_one_transaction_and_replay_fails(tmp_path):
    db = Database(tmp_path / "librarian.db")
    minted = create_household_invite(db, created_by="owner-1", actor_role="owner", role="op")
    first = redeem_local_invite(db, raw_token=minted["token"], username="ada", password="password123")
    assert first["user"]["role"] == "op"
    assert first["user"]["display_name"] == "ada"
    with pytest.raises(ValueError, match="already been used"):
        redeem_local_invite(db, raw_token=minted["token"], username="grace", password="password123")


def test_op_cannot_invite_op(tmp_path):
    db = Database(tmp_path / "librarian.db")
    with pytest.raises(ValueError, match="Not allowed"):
        create_household_invite(db, created_by="op-1", actor_role="op", role="op")
    with pytest.raises(ValueError, match="second owner"):
        create_household_invite(db, created_by="owner-1", actor_role="owner", role="owner")


def test_concurrent_redeem_one_winner(tmp_path):
    db = Database(tmp_path / "librarian.db")
    minted = create_household_invite(db, created_by="owner-1", actor_role="owner", role="reader")
    winners = []
    errors = []

    def attempt(name: str) -> None:
        try:
            redeem_local_invite(db, raw_token=minted["token"], username=name, password="password123")
            winners.append(name)
        except ValueError as error:
            errors.append(str(error))

    threads = [threading.Thread(target=attempt, args=(f"user{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(winners) == 1
    assert len(errors) == 1
    assert db.get_user_by_display_name(winners[0]) is not None


def test_validate_and_redeem_http(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    clear_session_secret_cache()
    client = TestClient(create_app(tmp_path))
    login = client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    assert login.status_code == 200, login.text
    minted = client.post("/api/invites", json={"role": "reader"})
    assert minted.status_code == 200, minted.text
    token = minted.json()["token"]
    client.post("/api/auth/logout")
    validated = client.get("/api/invites/validate", params={"token": token})
    assert validated.status_code == 200
    assert validated.json()["invite"]["role"] == "reader"
    client.cookies.clear()
    redeemed = client.post(
        "/api/invites/redeem/local",
        json={"token": token, "username": "reader1", "password": "password123"},
    )
    assert redeemed.status_code == 200
    assert redeemed.json()["user"]["role"] == "reader"
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["display_name"] == "reader1"
