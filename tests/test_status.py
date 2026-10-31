from unittest import mock

from fastapi.testclient import TestClient

from librarian import __version__
from librarian.db import Database
from librarian.web.app import create_app
from librarian.web.status import is_ready, last_backup_at, notes_tip_from_image, owner_status


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    return TestClient(create_app(tmp_path))


def test_status_requires_owner(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.cookies.clear()
    assert client.get("/api/status").status_code == 401

    login = client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    assert login.status_code == 200
    minted = client.post("/api/invites", json={"role": "reader"})
    token = minted.json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    redeemed = client.post(
        "/api/invites/redeem/local",
        json={"token": token, "username": "reader1", "password": "password123"},
    )
    assert redeemed.status_code == 200
    assert client.get("/api/status").status_code == 403


def test_owner_status_notes_from_image_not_data_dir(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    decoy = tmp_path / "frontend" / "dist"
    decoy.mkdir(parents=True)
    (decoy / "release-notes.json").write_text(
        '{"releases":[{"version":"0.0.0"}]}', encoding="utf-8"
    )
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    body = client.get("/api/status").json()
    assert body["version"] == __version__
    assert "rev" in body
    assert "built_at" in body
    assert "last_backup" in body
    assert "poller_alive" in body
    assert isinstance(body["poller_alive"], bool)
    # DATA_DIR decoy must not win — notes come from the image / package tree.
    image_tip = notes_tip_from_image()
    assert body["notes_version"] == image_tip
    assert body["notes_match"] is (image_tip == __version__)
    assert body["notes_version"] != "0.0.0"


def test_owner_status_notes_match_true_when_image_matches(tmp_path):
    db = Database(tmp_path / "librarian.db")
    with mock.patch("librarian.web.status.notes_tip_from_image", return_value=__version__):
        with mock.patch("librarian.web.status.read_build_info", return_value="0.6.2 built 2026-10-31T04:00:00Z rev abc"):
            payload = owner_status(db=db, poller=None, data_dir=tmp_path)
    assert payload["notes_match"] is True
    assert payload["notes_version"] == __version__
    assert payload["rev"] == "abc"
    assert payload["built_at"] == "2026-10-31T04:00:00Z"
    assert payload["poller_alive"] is False
    assert payload["last_backup"] is None
    db.close()


def test_last_backup_reads_backups_dir_not_backup_module(tmp_path):
    backups = tmp_path / "backups"
    backups.mkdir()
    snapshot = backups / "librarian-20261031.db"
    snapshot.write_bytes(b"sqlite")
    stamp = last_backup_at(tmp_path)
    assert stamp is not None
    assert stamp.endswith("Z")
    assert last_backup_at(tmp_path / "missing") is None


def test_is_ready_needs_select_one_and_live_poller(tmp_path):
    db = Database(tmp_path / "librarian.db")

    class Dead:
        is_running = False

    class Alive:
        is_running = True

    assert is_ready(db=db, poller=None) is False
    assert is_ready(db=db, poller=Dead()) is False
    assert is_ready(db=db, poller=Alive()) is True
    db.close()


def test_notes_tip_from_image_uses_frontend_public_file(tmp_path):
    notes = tmp_path / "release-notes.json"
    notes.write_text('{"releases":[{"version":"9.9.9"}]}', encoding="utf-8")
    with mock.patch("librarian.web.status.frontend_public_file", return_value=notes):
        assert notes_tip_from_image() == "9.9.9"
    with mock.patch("librarian.web.status.frontend_public_file", return_value=None):
        assert notes_tip_from_image() == ""
