"""Ask → confirm → arrived producers. Never queues SABnzbd."""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional

from librarian.delight import in_quiet_hours
from librarian.notifications.service import fan_out_notifications

logger = logging.getLogger(__name__)

_SYSTEM_REQUESTERS = frozenset({"wanted", "rss", "watch", "ingest", "owner", "sweep"})


def keeper_user_ids(db: Any) -> list[str]:
    """Owner and ops who confirm Asked slips."""
    out: list[str] = []
    for row in db.list_users() or []:
        role = str(row.get("role") or "").strip().lower()
        uid = str(row.get("id") or "").strip()
        if uid and role in {"owner", "op"}:
            out.append(uid)
    return out


def requester_user_id(db: Any, raw: Any) -> str:
    """A real household member id, or empty when the asker is a system source."""
    uid = str(raw or "").strip()
    if not uid or uid.lower() in _SYSTEM_REQUESTERS:
        return ""
    user = db.get_user(uid)
    if user is None:
        return ""
    return str(user.get("id") or uid)


def display_name_for(db: Any, user_id: str) -> str:
    user = db.get_user(user_id)
    if not user:
        return "A reader"
    return str(user.get("display_name") or user.get("username") or "A reader").strip() or "A reader"


def asker_for_wanted(db: Any, wanted_id: str) -> str:
    """Find the household member who filed this Wanted row, if we stored a job."""
    wid = str(wanted_id or "").strip()
    if not wid:
        return ""
    for job in db.list_jobs(limit=200):
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        if str(payload.get("wanted_id") or "").strip() != wid:
            continue
        uid = requester_user_id(db, job.get("requested_by"))
        if uid:
            return uid
    return ""


def notify_asked_confirm(
    db: Any,
    settings: Any,
    *,
    title: str,
    from_user_id: str,
    related_id: str,
    path: str = "/queue",
) -> list:
    """Tell keepers a reader asked. Skip when the asker is a keeper acting alone."""
    asker = requester_user_id(db, from_user_id)
    if not asker:
        return []
    keepers = [uid for uid in keeper_user_ids(db) if uid != asker]
    if not keepers:
        return []
    name = display_name_for(db, asker)
    book = str(title or "").strip() or "a title"
    return fan_out_notifications(
        db,
        settings,
        user_ids=keepers,
        kind="asked_confirm",
        title=f"{name} asked for {book}",
        body=f"{name} asked the house for {book}. Confirm on Downloads before anything is fetched.",
        payload={"path": path, "wanted_id": related_id},
        from_user_id=asker,
        related_id=related_id,
    )


def notify_job_arrived(db: Any, settings: Any, job: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Tell the requester the volume is on the shelf. Skip the confirmer's own grab."""
    work_id = str(job.get("work_id") or "").strip()
    if not work_id:
        return None
    asker = requester_user_id(db, job.get("requested_by"))
    if not asker:
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        asker = asker_for_wanted(db, str(payload.get("wanted_id") or ""))
    if not asker:
        return None
    user = db.get_user(asker)
    role = str((user or {}).get("role") or "").strip().lower()
    if role in {"owner", "op"}:
        return None
    title = str(job.get("title") or "").strip() or "Your request"
    results = fan_out_notifications(
        db,
        settings,
        user_ids=[asker],
        kind="arrived",
        title=f"{title} is on the shelf",
        body=f"{title} is on the shelves — open it when you are ready.",
        payload={"path": f"/works/{work_id}", "work_id": work_id},
        related_id=str(job.get("id") or work_id),
    )
    return results[0] if results else None


def complete_asked_loop(db: Any, settings: Any, job: Mapping[str, Any]) -> None:
    """Mark the Wanted row arrived and notify the requester. Never SAB."""
    from librarian.wanted import mark_wanted_arrived

    try:
        notify_job_arrived(db, settings, job)
    except Exception:  # noqa: BLE001
        logger.exception("arrived notice failed for job %s", job.get("id"))
    try:
        mark_wanted_arrived(db, job)
    except Exception:  # noqa: BLE001
        logger.exception("wanted arrived mark failed for job %s", job.get("id"))


def flush_notice_scheduler(db: Any, settings: Any) -> Dict[str, Any]:
    """Hourly notices tick: flush daily digests. Quiet hours do not send email."""
    from librarian.notifications.service import flush_email_digests

    if in_quiet_hours(settings):
        return {"period": "daily", "users": 0, "sent": 0, "errors": 0, "quiet_hours": True}
    return flush_email_digests(db, settings, period="daily")
