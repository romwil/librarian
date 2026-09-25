"""Outbound mail transport (SMTP + Resend) for Librarian notifications."""

from __future__ import annotations

from librarian.mail.transport import MailSendError, MailSendResult, mail_configured, send_mail

__all__ = [
    "MailSendError",
    "MailSendResult",
    "mail_configured",
    "send_mail",
]
