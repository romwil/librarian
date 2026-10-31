"""Nightly personal-data retention (PRIV-014). Household box, not a warehouse."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from librarian.db import Database
from librarian.pulse import METRICS_KEEP_DAYS, purge_metrics, snapshot_pulse

logger = logging.getLogger(__name__)

SEEN_NOTICE_DAYS = 30
UNSEEN_NOTICE_DAYS = 180
DIGEST_SENT_DAYS = 7
INVITE_CLOSED_DAYS = 30
JOB_TERMINAL_DAYS = 180
AUDIT_DAYS = 365
LISTS_CACHE_DAYS = 7
SESSIONS_REVOKED_DAYS = 30

TERMINAL_JOB_STATUSES = ("organized", "failed", "skipped", "cancelled")
CLOSED_INVITE_STATUSES = ("expired", "revoked", "redeemed")


def _cutoff(days: int, *, now: float) -> float:
    return float(now) - (days * 86400)


def _int_rowcount(cur: Any) -> int:
    try:
        return max(0, int(cur.rowcount or 0))
    except (TypeError, ValueError):
        return 0


def _purge_lists_cache(data_dir: Optional[Path], *, now: float) -> int:
    if data_dir is None:
        return 0
    folder = Path(data_dir) / "lists-cache"
    if not folder.is_dir():
        return 0
    cutoff = now - (LISTS_CACHE_DAYS * 86400)
    removed = 0
    try:
        entries = list(folder.iterdir())
    except OSError:
        return 0
    for path in entries:
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def run_retention(
    db: Database,
    *,
    data_dir: Optional[Path] = None,
    now: Optional[float] = None,
) -> Dict[str, int]:
    """Delete or strip aged personal rows. Open jobs stay. Metrics keep 400 days."""
    moment = float(now if now is not None else time.time())
    counts: Dict[str, int] = {}

    def _write() -> Dict[str, int]:
        out: Dict[str, int] = {}
        with db._connect() as conn:
            cur = conn.execute(
                """
                DELETE FROM user_notifications
                WHERE (seen_at IS NOT NULL AND seen_at < ?)
                   OR (seen_at IS NULL AND created_at < ?)
                """,
                (_cutoff(SEEN_NOTICE_DAYS, now=moment), _cutoff(UNSEEN_NOTICE_DAYS, now=moment)),
            )
            out["notifications"] = _int_rowcount(cur)
            cur = conn.execute(
                """
                DELETE FROM notification_digest_queue
                WHERE sent_at IS NOT NULL AND sent_at < ?
                """,
                (_cutoff(DIGEST_SENT_DAYS, now=moment),),
            )
            out["digests"] = _int_rowcount(cur)
            cur = conn.execute(
                """
                DELETE FROM invites
                WHERE status IN (?, ?, ?)
                  AND COALESCE(redeemed_at, expires_at, created_at) < ?
                """,
                (*CLOSED_INVITE_STATUSES, _cutoff(INVITE_CLOSED_DAYS, now=moment)),
            )
            out["invites"] = _int_rowcount(cur)
            cur = conn.execute(
                """
                UPDATE jobs
                SET requested_by = NULL, payload_json = NULL
                WHERE status IN (?, ?, ?, ?)
                  AND updated_at < ?
                  AND (requested_by IS NOT NULL OR payload_json IS NOT NULL)
                """,
                (*TERMINAL_JOB_STATUSES, _cutoff(JOB_TERMINAL_DAYS, now=moment)),
            )
            out["jobs_stripped"] = _int_rowcount(cur)
            cur = conn.execute(
                "DELETE FROM review_audit WHERE created_at < ?",
                (_cutoff(AUDIT_DAYS, now=moment),),
            )
            out["review_audit"] = _int_rowcount(cur)
            cur = conn.execute(
                """
                DELETE FROM sessions
                WHERE revoked_at IS NOT NULL AND revoked_at < ?
                """,
                (_cutoff(SESSIONS_REVOKED_DAYS, now=moment),),
            )
            out["sessions"] = _int_rowcount(cur)
        return out

    counts.update(db.run_write(_write, label="retention") or {})
    counts["metrics"] = purge_metrics(db, keep_days=METRICS_KEEP_DAYS, now=moment)
    counts["lists_cache"] = _purge_lists_cache(data_dir, now=moment)
    try:
        snapshot_pulse(db, data_dir=data_dir, now=moment)
        counts["pulse_snapshot"] = 1
    except Exception:
        logger.exception("House pulse snapshot failed")
        counts["pulse_snapshot"] = 0
    return counts


__all__ = [
    "AUDIT_DAYS",
    "INVITE_CLOSED_DAYS",
    "JOB_TERMINAL_DAYS",
    "SEEN_NOTICE_DAYS",
    "UNSEEN_NOTICE_DAYS",
    "run_retention",
]
