"""Value-based tests for notification prefs, inbox, and email opt-in."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from librarian.config import MailSettings, Settings, save_settings
from librarian.mail import MailSendResult
from librarian.notifications import (
    NOTIFICATION_KINDS,
    deliver_notification,
    flush_email_digests,
    get_kind_pref,
    merge_notification_prefs,
    normalize_kind,
    notification_channel_offerings,
    user_wants_channel,
)
from librarian.notifications.kinds import normalize_channels, normalize_timing


def test_kind_and_channel_normalization():
    assert normalize_kind("Asked-Confirm") == "asked_confirm"
    assert normalize_timing("daily_digest") == "daily"
    assert normalize_channels(["email", "inbox", "pager"]) == ["email", "inbox"]
    assert normalize_channels(None) == ["inbox"]


def test_default_prefs_and_merge(tmp_path):
    from librarian.db import Database

    db = Database(tmp_path / "librarian.db")
    user = db.create_local_user(
        user_id="u-reader",
        display_name="reader",
        role="reader",
        password_hash="x",
    )
    prefs = db.get_user_prefs(user["id"])
    arrived = get_kind_pref(prefs, "arrived")
    assert arrived["enabled"] is True
    assert "inbox" in arrived["channels"]
    newsletter = get_kind_pref(prefs, "newsletter")
    assert newsletter["enabled"] is False

    nested = merge_notification_prefs(
        prefs,
        notification_email="reader@example.com",
        kinds={
            "arrived": {"enabled": True, "channels": ["inbox", "email"], "timing": "realtime"},
            "newsletter": {"enabled": True, "channels": ["email"], "timing": "weekly"},
        },
    )
    saved = db.set_user_prefs(user["id"], prefs=nested)
    assert get_kind_pref(saved, "newsletter")["enabled"] is True
    assert user_wants_channel(saved, kind="arrived", channel="email") is True
    assert user_wants_channel(saved, kind="needs_you", channel="email") is False


def test_deliver_inbox_and_email_opt_in(tmp_path, monkeypatch):
    from librarian.db import Database

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    db = Database(tmp_path / "librarian.db")
    user = db.create_local_user(
        user_id="u-owner",
        display_name="owner",
        role="owner",
        password_hash="x",
    )
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
            notification_email="owner@example.com",
            kinds={"arrived": {"enabled": True, "channels": ["inbox", "email"], "timing": "realtime"}},
        ),
    )

    with patch(
        "librarian.notifications.service.send_mail",
        return_value=MailSendResult(ok=True, provider="resend", message_id="m1"),
    ) as mock_send:
        result = deliver_notification(
            db,
            settings,
            user_id=user["id"],
            kind="arrived",
            title="Dune arrived",
            body="Your Request is on the shelf.",
        )
    assert result["notification"] is not None
    assert result["emailed"] is True
    mock_send.assert_called_once()
    assert db.count_unread_notifications(user["id"]) == 1

    # No email when channel not opted in.
    with patch("librarian.notifications.service.send_mail") as mock_send2:
        deliver_notification(
            db,
            settings,
            user_id=user["id"],
            kind="needs_you",
            title="Review needs you",
        )
    mock_send2.assert_not_called()


def test_daily_timing_queues_email_digest(tmp_path):
    from librarian.db import Database

    db = Database(tmp_path / "librarian.db")
    user = db.create_local_user(
        user_id="u-owner-digest",
        display_name="owner",
        role="owner",
        password_hash="x",
    )
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
            notification_email="owner@example.com",
            kinds={
                "shelf_health": {
                    "enabled": True,
                    "channels": ["inbox", "email"],
                    "timing": "daily",
                }
            },
        ),
    )
    with patch("librarian.notifications.service.send_mail") as mock_send:
        result = deliver_notification(
            db,
            settings,
            user_id=user["id"],
            kind="shelf_health",
            title="Shells need a tend",
            body="Three empty shells on the shelf.",
        )
    mock_send.assert_not_called()
    assert result["notification"] is not None  # inbox still immediate
    assert result["queued_digest"] is not None

    with patch(
        "librarian.notifications.service.send_mail",
        return_value=MailSendResult(ok=True, provider="resend", message_id="d1"),
    ) as mock_digest:
        flushed = flush_email_digests(db, settings, period="daily")
    assert flushed["sent"] == 1
    mock_digest.assert_called_once()


def test_channel_offerings_flag_mail():
    offerings = {row["id"]: row for row in notification_channel_offerings(Settings())}
    assert offerings["inbox"]["available"] is True
    assert offerings["email"]["available"] is False
    assert offerings["email"]["requires_owner"] is True
    configured = notification_channel_offerings(
        Settings(
            mail=MailSettings(
                enabled=True,
                provider="smtp",
                smtp_host="smtp.example",
                from_email="hall@example.com",
            )
        )
    )
    assert {row["id"]: row for row in configured}["email"]["available"] is True


def test_notifications_api_inbox_and_prefs(tmp_path, monkeypatch):
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
    from librarian.web.app import create_app

    client = TestClient(create_app())
    assert (
        client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"}).status_code
        == 200
    )

    features = client.get("/api/features")
    assert features.status_code == 200
    assert features.json()["notifications"]["mail_configured"] is True

    prefs = client.get("/api/notifications/prefs")
    assert prefs.status_code == 200
    body = prefs.json()
    assert set(body["kinds"]) == set(NOTIFICATION_KINDS)
    assert body["mail_configured"] is True

    put = client.put(
        "/api/notifications/prefs",
        json={
            "notification_email": "owner@example.com",
            "kinds": {
                "arrived": {"enabled": True, "channels": ["inbox", "email"], "timing": "realtime"},
            },
        },
    )
    assert put.status_code == 200, put.text
    assert put.json()["notification_email"] == "owner@example.com"
    assert put.json()["kinds"]["arrived"]["channels"] == ["inbox", "email"]

    test = client.post(
        "/api/notifications/test",
        json={"kind": "arrived", "title": "Test notice", "body": "Desk check."},
    )
    assert test.status_code == 200, test.text
    assert test.json()["notification"]["title"] == "Test notice"

    listed = client.get("/api/notifications?unread_only=1")
    assert listed.status_code == 200
    assert listed.json()["unread_count"] >= 1
    assert any(row["title"] == "Test notice" for row in listed.json()["items"])

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["inbox_unread"] >= 1

    seen = client.post("/api/notifications/seen", json={"all_unread": True})
    assert seen.status_code == 200
    assert seen.json()["unread_count"] == 0

    bad_email = client.put("/api/notifications/prefs", json={"notification_email": "not-an-email"})
    assert bad_email.status_code == 400
