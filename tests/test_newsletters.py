"""Value-based tests for personalized library newsletter editions."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from librarian.config import MailSettings, Settings, save_settings
from librarian.mail import MailSendResult
from librarian.notifications import (
    build_member_edition,
    deliver_editions,
    edition_due,
    get_kind_pref,
    merge_notification_prefs,
    normalize_newsletter_timing,
)
from librarian.notifications.prefs import get_newsletter_last_edition_at


def _seed_work(db, *, title: str, author: str = "Frank Herbert", genre: str = "Science Fiction"):
    work = db.upsert_work(
        {
            "kind": "book",
            "title": title,
            "author": author,
            "genre": genre,
            "year": 1965,
        }
    )
    db.add_file(
        {
            "work_id": work["id"],
            "path": f"/library/{work['id']}.epub",
            "filename": f"{title}.epub",
            "kind": "book",
            "size": 1024,
        }
    )
    return db.get_work(work["id"])


def test_newsletter_timing_normalization():
    assert normalize_newsletter_timing("monthly_digest") == "monthly"
    assert normalize_newsletter_timing("week") == "weekly"
    assert normalize_newsletter_timing("realtime") == "weekly"


def test_build_edition_uses_tastes_and_recent(tmp_path):
    from librarian.db import Database

    db = Database(tmp_path / "librarian.db")
    user = db.create_local_user(
        user_id="u-reader",
        display_name="Ada",
        role="reader",
        password_hash="x",
    )
    dune = _seed_work(db, title="Dune")
    _seed_work(db, title="Children of Dune", author="Frank Herbert", genre="Science Fiction")
    db.add_favorite(user["id"], dune["id"])
    db.upsert_progress(user_id=user["id"], work_id=dune["id"], position="ch-2", fraction=0.2)

    prefs = db.set_user_prefs(
        user["id"],
        prefs=merge_notification_prefs(
            db.get_user_prefs(user["id"]),
            kinds={"newsletter": {"enabled": True, "channels": ["inbox"], "timing": "weekly"}},
        ),
    )
    edition = build_member_edition(db, user=user, user_prefs=prefs)
    assert "Ada" in edition["subject"]
    assert "Herbert" in edition["blurb"] or "Science Fiction" in edition["blurb"]
    assert any(p["title"] == "Children of Dune" or p["title"] == "Dune" for p in edition["picks"])
    assert "lamp" in edition["body"].lower() or "Hall" in edition["body"]


def test_deliver_editions_opt_in_inbox_no_force_email(tmp_path, monkeypatch):
    from librarian.db import Database

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    db = Database(tmp_path / "librarian.db")
    user = db.create_local_user(
        user_id="u-owner",
        display_name="Owner",
        role="owner",
        password_hash="x",
    )
    _seed_work(db, title="The Left Hand of Darkness", author="Ursula K. Le Guin", genre="Science Fiction")
    settings = Settings(
        mail=MailSettings(
            enabled=True,
            provider="resend",
            from_email="hall@example.com",
            resend_api_key="re_test",
        )
    )
    # Opt in inbox only — email must not send.
    db.set_user_prefs(
        user["id"],
        prefs=merge_notification_prefs(
            db.get_user_prefs(user["id"]),
            notification_email="owner@example.com",
            kinds={"newsletter": {"enabled": True, "channels": ["inbox"], "timing": "weekly"}},
        ),
    )
    with patch("librarian.notifications.service.send_mail") as mock_send:
        result = deliver_editions(db, settings, user_ids=[user["id"]], force=True)
    mock_send.assert_not_called()
    assert result["delivered"] == 1
    assert result["emailed"] == 0
    assert db.count_unread_notifications(user["id"]) == 1
    assert get_newsletter_last_edition_at(db.get_user_prefs(user["id"])) is not None

    # Not due again until cadence (force=False).
    assert edition_due(db.get_user_prefs(user["id"]), force=False) is False
    again = deliver_editions(db, settings, user_ids=[user["id"]], force=False)
    assert again["delivered"] == 0
    assert again["skipped_not_due"] == 1


def test_deliver_editions_email_when_opted_in(tmp_path):
    from librarian.db import Database

    db = Database(tmp_path / "librarian.db")
    user = db.create_local_user(
        user_id="u-mail",
        display_name="Mailer",
        role="owner",
        password_hash="x",
    )
    _seed_work(db, title="Neuromancer", author="William Gibson", genre="Cyberpunk")
    settings = Settings(
        mail=MailSettings(
            enabled=True,
            provider="resend",
            from_email="hall@example.com",
            resend_api_key="re_test",
        )
    )
    db.set_user_prefs(
        user["id"],
        prefs=merge_notification_prefs(
            db.get_user_prefs(user["id"]),
            notification_email="mailer@example.com",
            kinds={
                "newsletter": {
                    "enabled": True,
                    "channels": ["inbox", "email"],
                    "timing": "monthly",
                }
            },
        ),
    )
    assert get_kind_pref(db.get_user_prefs(user["id"]), "newsletter")["timing"] == "monthly"
    with patch(
        "librarian.notifications.service.send_mail",
        return_value=MailSendResult(ok=True, provider="resend", message_id="n1"),
    ) as mock_send:
        result = deliver_editions(db, settings, user_ids=[user["id"]], force=True)
    assert result["delivered"] == 1
    assert result["emailed"] == 1
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args.kwargs
    assert "Mailer" in str(call_kwargs.get("subject") or "")
    assert call_kwargs.get("to_email") == "mailer@example.com"


def test_skipped_when_opted_out(tmp_path):
    from librarian.db import Database

    db = Database(tmp_path / "librarian.db")
    user = db.create_local_user(
        user_id="u-out",
        display_name="Out",
        role="reader",
        password_hash="x",
    )
    result = deliver_editions(db, Settings(), user_ids=[user["id"]], force=True)
    assert result["skipped_opt_out"] == 1
    assert result["delivered"] == 0


def test_newsletters_api_push(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    save_settings(
        tmp_path,
        Settings(
            mail=MailSettings(
                enabled=True,
                provider="resend",
                from_email="hall@example.com",
                resend_api_key="re_live",
            )
        ),
    )
    from librarian.db import Database
    from librarian.web.app import create_app

    client = TestClient(create_app())
    assert (
        client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"}).status_code
        == 200
    )
    me = client.get("/api/auth/me").json()
    owner_id = me["user"]["id"]
    # Re-open same DB the app uses.
    app_db = Database(tmp_path / "librarian.db")
    _seed_work(app_db, title="Kindred", author="Octavia E. Butler", genre="Science Fiction")
    put = client.put(
        "/api/notifications/prefs",
        json={
            "notification_email": "owner@example.com",
            "kinds": {
                "newsletter": {
                    "enabled": True,
                    "channels": ["inbox", "email"],
                    "timing": "weekly",
                }
            },
        },
    )
    assert put.status_code == 200, put.text
    assert put.json()["kinds"]["newsletter"]["timing"] == "weekly"

    with patch(
        "librarian.notifications.service.send_mail",
        return_value=MailSendResult(ok=True, provider="resend", message_id="push1"),
    ):
        pushed = client.post("/api/newsletters/push", json={"scope": "self", "force": True})
    assert pushed.status_code == 200, pushed.text
    body = pushed.json()
    assert body["ok"] is True
    assert body["delivered"] == 1
    assert body["emailed"] == 1

    inbox = client.get("/api/notifications?kind=newsletter&unread_only=1")
    assert inbox.status_code == 200
    assert inbox.json()["unread_count"] >= 1
    assert any(row["kind"] == "newsletter" for row in inbox.json()["items"])

    # Cadence run without force should skip not-due.
    due = client.post("/api/newsletters/run")
    assert due.status_code == 200
    assert due.json()["skipped_not_due"] >= 1 or due.json()["delivered"] == 0

    assert owner_id
