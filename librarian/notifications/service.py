"""Notification fan-out: inbox rows + optional email (opt-in only)."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Sequence

from librarian.mail import MailSendError, mail_configured, send_mail
from librarian.notifications.kinds import CHANNEL_SET, normalize_kind, normalize_timing
from librarian.notifications.prefs import get_kind_pref, resolve_notification_email

logger = logging.getLogger(__name__)


def notification_channel_offerings(settings: Any) -> List[Dict[str, Any]]:
    """Describe channels for Settings → Notifications."""
    mail_ok = mail_configured(settings)
    return [
        {
            "id": "inbox",
            "label": "In-app inbox",
            "requires_owner": False,
            "available": True,
            "help": "Always available inside Librarian.",
        },
        {
            "id": "email",
            "label": "Email",
            "requires_owner": True,
            "available": mail_ok,
            "help": "Requires the owner to configure Settings → Mail (SMTP or Resend), and your opt-in plus address.",
        },
    ]


def user_wants_channel(user_prefs: Dict[str, Any], *, kind: str, channel: str) -> bool:
    cleaned_kind = normalize_kind(kind)
    cleaned_channel = str(channel or "").strip().lower()
    if cleaned_channel not in CHANNEL_SET:
        return False
    pref = get_kind_pref(user_prefs, cleaned_kind)
    if not pref.get("enabled"):
        return False
    return cleaned_channel in (pref.get("channels") or [])


def enqueue_digest_item(
    db: Any,
    *,
    user_id: str,
    kind: str,
    title: str,
    body: Optional[str],
    payload: Optional[Dict[str, Any]],
    related_id: Optional[str],
    period: str,
) -> Dict[str, Any]:
    """Park an item for daily/weekly email digest flush."""
    cleaned_period = normalize_timing(period, default="daily")
    if cleaned_period == "realtime":
        cleaned_period = "daily"
    return db.enqueue_notification_digest(
        digest_id=str(uuid.uuid4()),
        user_id=user_id,
        kind=kind,
        title=title,
        body=body,
        payload=payload,
        related_id=related_id,
        period=cleaned_period,
    )


def deliver_notification(
    db: Any,
    settings: Any,
    *,
    user_id: str,
    kind: str,
    title: str,
    body: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    from_user_id: Optional[str] = None,
    related_id: Optional[str] = None,
    email_subject: Optional[str] = None,
    force_inbox: bool = False,
    force_email: bool = False,
) -> Dict[str, Any]:
    """Create an inbox notification and optionally email the member.

    Email is never forced by product paths (force_email is for tests / owner tools).
    Timing: realtime emails send now; daily/weekly emails queue for digest flush.
    Inbox delivery is always immediate when the inbox channel is on.
    """
    cleaned_kind = normalize_kind(kind)
    user = db.get_user(user_id)
    if user is None:
        raise ValueError(f"User not found: {user_id}")
    user_prefs = db.get_user_prefs(user_id)
    pref = get_kind_pref(user_prefs, cleaned_kind)

    result: Dict[str, Any] = {
        "notification": None,
        "emailed": False,
        "email_error": None,
        "queued_digest": None,
        "skipped": False,
    }

    if not pref.get("enabled") and not force_inbox and not force_email:
        result["skipped"] = True
        return result

    wants_inbox = force_inbox or user_wants_channel(user_prefs, kind=cleaned_kind, channel="inbox")
    wants_email = force_email or user_wants_channel(user_prefs, kind=cleaned_kind, channel="email")
    timing = str(pref.get("timing") or "realtime")

    if wants_inbox:
        result["notification"] = db.create_notification(
            notification_id=str(uuid.uuid4()),
            user_id=user_id,
            kind=cleaned_kind,
            title=title,
            body=body,
            payload=payload,
            from_user_id=from_user_id,
            related_id=related_id,
        )

    if wants_email and mail_configured(settings):
        to_email = resolve_notification_email(user_prefs, user)
        if to_email:
            if timing == "realtime" or force_email:
                try:
                    send_mail(
                        settings,
                        to_email=to_email,
                        subject=email_subject or title,
                        body_text=body or title,
                    )
                    result["emailed"] = True
                except MailSendError as exc:
                    logger.warning("Notification email failed for %s: %s", user_id, exc)
                    result["email_error"] = str(exc)
            else:
                result["queued_digest"] = enqueue_digest_item(
                    db,
                    user_id=user_id,
                    kind=cleaned_kind,
                    title=title,
                    body=body,
                    payload=payload,
                    related_id=related_id,
                    period=timing,
                )
    return result


def fan_out_notifications(
    db: Any,
    settings: Any,
    *,
    user_ids: Sequence[str],
    kind: str,
    title: str,
    body: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    email_subject: Optional[str] = None,
    **extra: Any,
) -> List[Dict[str, Any]]:
    delivered: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for raw_id in user_ids:
        uid = str(raw_id or "").strip()
        if not uid or uid in seen:
            continue
        seen.add(uid)
        try:
            delivered.append(
                deliver_notification(
                    db,
                    settings,
                    user_id=uid,
                    kind=kind,
                    title=title,
                    body=body,
                    payload=payload,
                    email_subject=email_subject,
                    **extra,
                )
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to deliver %s notification to %s", kind, uid)
    return delivered


def flush_email_digests(
    db: Any,
    settings: Any,
    *,
    period: str,
) -> Dict[str, Any]:
    """Send one digest email per user for queued daily/weekly items."""
    cleaned_period = normalize_timing(period, default="daily")
    if cleaned_period == "realtime":
        return {"period": cleaned_period, "users": 0, "sent": 0, "errors": 0}
    if not mail_configured(settings):
        return {"period": cleaned_period, "users": 0, "sent": 0, "errors": 0, "mail_configured": False}

    pending = db.list_pending_notification_digests(period=cleaned_period)
    by_user: Dict[str, List[Dict[str, Any]]] = {}
    for row in pending:
        by_user.setdefault(str(row["user_id"]), []).append(row)

    sent = 0
    errors = 0
    for user_id, items in by_user.items():
        user_prefs = db.get_user_prefs(user_id)
        user = db.get_user(user_id)
        to_email = resolve_notification_email(user_prefs, user)
        if not to_email:
            continue
        lines = []
        for item in items:
            title = str(item.get("title") or "").strip() or "Notice"
            body = str(item.get("body") or "").strip()
            lines.append(f"• {title}" + (f" — {body}" if body else ""))
        subject = (
            "Your daily note from the library"
            if cleaned_period == "daily"
            else "Your weekly note from the library"
        )
        body_text = "\n".join(lines) if lines else "Nothing new this period."
        try:
            send_mail(settings, to_email=to_email, subject=subject, body_text=body_text)
            db.mark_notification_digests_sent([str(i["id"]) for i in items])
            sent += 1
        except MailSendError as exc:
            logger.warning("Digest email failed for %s: %s", user_id, exc)
            errors += 1
    return {
        "period": cleaned_period,
        "users": len(by_user),
        "sent": sent,
        "errors": errors,
        "mail_configured": True,
    }
