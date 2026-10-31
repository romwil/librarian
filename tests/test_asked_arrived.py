"""Asked → arrived loop. Never queues SABnzbd."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.notifications.loop import complete_asked_loop, notify_asked_confirm
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.wanted import STATUS_ARRIVED, add_wanted
from librarian.web.app import create_app


def _client(tmp_path, monkeypatch, **fields):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    monkeypatch.setattr("librarian.config.load_dotenv", lambda path=None: None)
    save_settings(tmp_path, Settings(llm_api_key="", **fields))
    clear_session_secret_cache()
    clear_rate_limits()
    return TestClient(create_app(tmp_path))


def _login(client, username="owner", password="password123"):
    resp = client.post("/api/auth/local/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["user"]


def _reader(client):
    minted = client.post("/api/invites", json={"role": "reader"})
    token = minted.json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    redeemed = client.post(
        "/api/invites/redeem/local",
        json={"token": token, "username": "reader1", "password": "password123"},
    )
    assert redeemed.status_code == 200
    return redeemed.json()["user"]


def test_reader_search_ask_tracks_without_sab(tmp_path, monkeypatch):
    from librarian.sabnzbd import SABClient

    def boom(*_args, **_kwargs):
        raise AssertionError("SABnzbd was called before a person confirmed the slip")

    monkeypatch.setattr(SABClient, "addfile", boom)
    client = _client(tmp_path, monkeypatch)
    _login(client)
    reader = _reader(client)
    resp = client.post(
        "/api/search/ask",
        json={"q": "Kindred", "title": "Kindred", "author": "Octavia Butler", "kind": "audiobook"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["searched"] is False
    assert body["item"]["status"] == "wanted"
    assert body["job"]["status"] == "asked"
    db = Database(tmp_path / "librarian.db")
    try:
        jobs = db.list_jobs_for_user(reader["id"])
        assert len(jobs) == 1
        assert jobs[0]["payload"]["source"] == "ask"
        assert not jobs[0].get("indexer_guid")
        notes = db.list_notifications_for_user(reader["id"])
        assert notes == [] or all(n.get("kind") != "asked_confirm" for n in notes)
        card = client.get("/api/library-card").json()
        assert card["asks"][0]["title"] == "Kindred"
        assert card["asks"][0]["label"] == "Looking"
    finally:
        db.close()


def test_asked_confirm_notifies_keepers_not_the_reader(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    owner = _login(client)
    reader = _reader(client)
    db = Database(tmp_path / "librarian.db")
    try:
        results = notify_asked_confirm(
            db,
            Settings(),
            title="Kindred",
            from_user_id=reader["id"],
            related_id="wanted-1",
        )
        assert results
        owner_notes = db.list_notifications_for_user(owner["id"])
        kinds = {row["kind"] for row in owner_notes}
        assert "asked_confirm" in kinds
        reader_notes = db.list_notifications_for_user(reader["id"])
        assert all(row["kind"] != "asked_confirm" for row in reader_notes)
        again = notify_asked_confirm(
            db,
            Settings(),
            title="Kindred",
            from_user_id=reader["id"],
            related_id="wanted-1",
        )
        assert again == [] or all(item.get("skipped") for item in again)
    finally:
        db.close()


def test_organized_job_marks_wanted_arrived_and_notifies_reader(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    reader = _reader(client)
    db = Database(tmp_path / "librarian.db")
    try:
        row = add_wanted(db, {"title": "Kindred", "kind": "audiobook", "author": "Octavia Butler"})
        work = db.upsert_work({"kind": "audiobook", "title": "Kindred", "author": "Octavia Butler"})
        job = db.create_job(
            {
                "status": "organized",
                "title": "Kindred",
                "kind": "audiobook",
                "requested_by": reader["id"],
                "work_id": work["id"],
                "payload": {"wanted_id": row["id"], "source": "wanted"},
            }
        )
        complete_asked_loop(db, Settings(), job)
        arrived = db.get_wanted(row["id"])
        assert arrived["status"] == STATUS_ARRIVED
        notes = db.list_notifications_for_user(reader["id"])
        assert any(row["kind"] == "arrived" for row in notes)
    finally:
        db.close()


def test_owner_own_grab_does_not_ping_arrived(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    owner = _login(client)
    db = Database(tmp_path / "librarian.db")
    try:
        work = db.upsert_work({"kind": "book", "title": "Dune", "author": "Frank Herbert"})
        job = db.create_job(
            {
                "status": "organized",
                "title": "Dune",
                "kind": "book",
                "requested_by": owner["id"],
                "work_id": work["id"],
                "payload": {"source": "request"},
            }
        )
        complete_asked_loop(db, Settings(), job)
        notes = db.list_notifications_for_user(owner["id"])
        assert all(row["kind"] != "arrived" for row in notes)
    finally:
        db.close()


def test_quiet_hours_parks_realtime_email(tmp_path, monkeypatch):
    from librarian.config import MailSettings

    client = _client(
        tmp_path,
        monkeypatch,
        quiet_hours_enabled=True,
        quiet_hours_start="00:00",
        quiet_hours_end="23:59",
        mail=MailSettings(
            enabled=True,
            provider="resend",
            from_email="hall@example.com",
            resend_api_key="re_test",
        ),
    )
    owner = _login(client)
    reader = _reader(client)
    db = Database(tmp_path / "librarian.db")
    try:
        db.set_user_prefs(
            owner["id"],
            prefs={
                "notifications": {
                    "email": "owner@example.com",
                    "kinds": {
                        "asked_confirm": {
                            "enabled": True,
                            "channels": ["inbox", "email"],
                            "timing": "realtime",
                        }
                    },
                }
            },
        )
        monkeypatch.setattr("librarian.delight.in_quiet_hours", lambda *_a, **_k: True)
        with patch("librarian.notifications.service.send_mail") as send:
            notify_asked_confirm(
                db,
                Settings(
                    quiet_hours_enabled=True,
                    quiet_hours_start="00:00",
                    quiet_hours_end="23:59",
                    mail=MailSettings(
                        enabled=True,
                        provider="resend",
                        from_email="hall@example.com",
                        resend_api_key="re_test",
                    ),
                ),
                title="Kindred",
                from_user_id=reader["id"],
                related_id="wanted-quiet",
            )
            send.assert_not_called()
        notes = db.list_notifications_for_user(owner["id"])
        assert any(row["kind"] == "asked_confirm" for row in notes)
    finally:
        db.close()
