"""Value-based tests for mail transport + Settings mail retain/mask/test."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from librarian.config import (
    MailSettings,
    Settings,
    mask_settings,
    merge_secret_fields,
    save_settings,
)
from librarian.mail import MailSendError, MailSendResult, mail_configured, send_mail
from librarian.mail.transport import RESEND_API_URL


def test_mail_configured_requires_provider_and_from():
    assert mail_configured(MailSettings()) is False
    assert (
        mail_configured(MailSettings(enabled=True, provider="smtp", smtp_host="smtp.example")) is False
    )
    assert (
        mail_configured(
            MailSettings(
                enabled=True,
                provider="smtp",
                smtp_host="smtp.example",
                from_email="hall@example.com",
            )
        )
        is True
    )
    assert (
        mail_configured(
            MailSettings(
                enabled=True,
                provider="resend",
                resend_api_key="re_test",
                from_email="hall@example.com",
            )
        )
        is True
    )
    assert (
        mail_configured(
            Settings(
                mail=MailSettings(
                    enabled=True,
                    provider="resend",
                    resend_api_key="re_test",
                    from_email="hall@example.com",
                )
            )
        )
        is True
    )


def test_mask_settings_masks_mail_secrets():
    masked = mask_settings(
        Settings(
            mail=MailSettings(
                enabled=True,
                provider="resend",
                from_email="hall@example.com",
                resend_api_key="re_secret",
                smtp_password="smtp-secret",
            )
        )
    )
    mail = masked["mail"]
    assert mail["resend_api_key"] == ""
    assert mail["resend_api_key_set"] is True
    assert mail["smtp_password"] == ""
    assert mail["smtp_password_set"] is True
    assert mail["from_email"] == "hall@example.com"
    assert mail["configured"] is True
    assert "re_secret" not in str(masked)
    assert "smtp-secret" not in str(masked)


def test_merge_secret_fields_retains_blank_mail_secrets():
    existing = Settings(
        mail=MailSettings(
            enabled=True,
            provider="smtp",
            from_email="hall@example.com",
            smtp_host="smtp.example",
            smtp_password="keep-me",
            resend_api_key="keep-resend",
        )
    )
    merged = merge_secret_fields(
        {
            "mail": {
                "enabled": True,
                "provider": "smtp",
                "from_email": "hall@example.com",
                "smtp_host": "smtp.example",
                "smtp_password": "",
                "resend_api_key": "",
            }
        },
        existing,
    )
    assert merged["mail"]["smtp_password"] == "keep-me"
    assert merged["mail"]["resend_api_key"] == "keep-resend"


def test_send_mail_smtp_uses_starttls(monkeypatch):
    mail = MailSettings(
        enabled=True,
        provider="smtp",
        from_email="hall@example.com",
        from_name="Librarian",
        smtp_host="smtp.example",
        smtp_port=587,
        smtp_username="user",
        smtp_password="pass",
        smtp_use_tls=True,
    )
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.__exit__.return_value = False

    with patch("librarian.mail.transport.smtplib.SMTP", return_value=smtp) as smtp_cls:
        result = send_mail(
            mail,
            to_email="reader@example.com",
            subject="Hello",
            body_text="Body line",
        )
    smtp_cls.assert_called_once_with("smtp.example", 587, timeout=30)
    smtp.ehlo.assert_called()
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("user", "pass")
    smtp.send_message.assert_called_once()
    assert result.ok is True
    assert result.provider == "smtp"


def test_send_mail_resend_posts_api(monkeypatch):
    mail = MailSettings(
        enabled=True,
        provider="resend",
        from_email="hall@example.com",
        resend_api_key="re_test_key",
        subject_prefix="[Librarian]",
    )

    class FakeResponse:
        status_code = 200
        text = '{"id":"msg_1"}'

        def json(self):
            return {"id": "msg_1"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.timeout = kwargs.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            assert url == RESEND_API_URL
            assert headers["Authorization"] == "Bearer re_test_key"
            assert json["to"] == ["reader@example.com"]
            assert "[Librarian]" in json["subject"]
            return FakeResponse()

    with patch("librarian.mail.transport.httpx.Client", FakeClient):
        result = send_mail(
            mail,
            to_email="reader@example.com",
            subject="Hello",
            body_text="Body",
        )
    assert result == MailSendResult(ok=True, provider="resend", message_id="msg_1", detail="sent")


def test_send_mail_rejects_unconfigured():
    try:
        send_mail(MailSettings(), to_email="a@b.co", subject="x", body_text="y")
        raise AssertionError("expected MailSendError")
    except MailSendError as exc:
        assert "not configured" in str(exc).lower()


def test_mail_env_seeds_blank_json(tmp_path, monkeypatch):
    monkeypatch.setenv("MAIL_RESEND_API_KEY", "from-env")
    monkeypatch.setenv("MAIL_FROM_EMAIL", "env@example.com")
    monkeypatch.setenv("MAIL_PROVIDER", "resend")
    monkeypatch.setenv("MAIL_ENABLED", "true")
    from librarian.config import load_merged_settings

    # No settings.json yet — env seeds first boot.
    settings = load_merged_settings(tmp_path)
    assert settings.mail.resend_api_key == "from-env"
    assert settings.mail.from_email == "env@example.com"
    assert settings.mail.provider == "resend"
    assert settings.mail.enabled is True


def test_mail_blank_secret_takes_env_when_json_blank(tmp_path, monkeypatch):
    monkeypatch.setenv("MAIL_RESEND_API_KEY", "from-env")
    from librarian.config import load_merged_settings

    save_settings(
        tmp_path,
        Settings(
            mail=MailSettings(
                enabled=True,
                provider="resend",
                from_email="hall@example.com",
                resend_api_key="",
            )
        ),
    )
    settings = load_merged_settings(tmp_path)
    assert settings.mail.resend_api_key == "from-env"


def test_mail_saved_secret_beats_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MAIL_RESEND_API_KEY", "from-env")
    from librarian.config import load_merged_settings

    save_settings(
        tmp_path,
        Settings(
            mail=MailSettings(
                enabled=True,
                provider="resend",
                from_email="hall@example.com",
                resend_api_key="from-json",
            )
        ),
    )
    settings = load_merged_settings(tmp_path)
    assert settings.mail.resend_api_key == "from-json"


def test_settings_mail_api_mask_and_test(tmp_path, monkeypatch):
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
    from fastapi.testclient import TestClient

    from librarian.web.app import create_app

    client = TestClient(create_app())
    assert (
        client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"}).status_code
        == 200
    )
    got = client.get("/api/settings")
    assert got.status_code == 200
    mail = got.json()["settings"]["mail"]
    assert mail["resend_api_key"] == ""
    assert mail["resend_api_key_set"] is True
    assert mail["from_email"] == "hall@example.com"

    put = client.put(
        "/api/settings",
        json={
            "mail": {
                "enabled": True,
                "provider": "resend",
                "from_email": "hall@example.com",
                "resend_api_key": "",
            }
        },
    )
    assert put.status_code == 200
    assert put.json()["settings"]["mail"]["resend_api_key_set"] is True

    with patch(
        "librarian.mail.send_mail",
        return_value=MailSendResult(ok=True, provider="resend", message_id="msg_1"),
    ) as mock_send:
        resp = client.post("/api/settings/mail/test", json={"to_email": "owner@example.com"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["provider"] == "resend"
    assert body["to_email"] == "owner@example.com"
    mock_send.assert_called_once()

    bad = client.post("/api/settings/mail/test", json={})
    assert bad.status_code == 400
