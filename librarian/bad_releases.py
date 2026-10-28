"""Send a recoverable bad download back to Wanted instead of the Holds desk.

A release that unpacked to nothing (``no_payload``) or failed its conversion twice
(``convert_failed``) is not an identity question. ``release_bad_wanted`` records the
release id as bad so search never picks it again, clears the Wanted row's job, and
puts it back on the normal retry clock. The completed-download folder stays on disk.

Without a Wanted row or a release id there is nothing to send back and nothing for
the owner to decide. The slip is dismissed. The download folder stays on disk, and
no Wanted row is invented.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Mapping, Optional

from librarian.db import Database, safe_release_guid
from librarian.progress_job import BackgroundJobSlot, ProgressJob, utc_now
from librarian.review_reasons import REVIEW_CONVERT, REVIEW_NO_PAYLOAD

logger = logging.getLogger(__name__)

BAD_RELEASE_REASONS = frozenset({REVIEW_NO_PAYLOAD, REVIEW_CONVERT})
NEEDS_OWNER_ACTION = "needs_owner"
NEEDS_OWNER_NOTE = (
    "Needs owner decision — no Wanted request or release id to send this back for another "
    "release. Request a new version or Delete it."
)
UNRETURNABLE_NOTE = (
    "Nothing to send back to Wanted, so this slip was not kept. "
    "The download folder is still on disk."
)
DISMISS_BAD_SLIP = "dismiss_bad_slip"

MIGRATION_NAME = "bad_release_slips_dismiss_unreturnable_v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _payload(job: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    raw = (job or {}).get("payload")
    return dict(raw) if isinstance(raw, dict) else {}


def _selected(payload: Mapping[str, Any]) -> Dict[str, Any]:
    raw = payload.get("selected")
    return dict(raw) if isinstance(raw, dict) else {}


def release_context(
    db: Database,
    *,
    job_id: Optional[str] = None,
    work_id: Optional[str] = None,
    guid: Optional[str] = None,
    host_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Find the job, Wanted row, release id, and indexer host for a bad download."""
    job = db.get_job(job_id) if job_id else None
    work = db.get_work(work_id) if work_id else None
    if job is None and work_id:
        jobs = db.jobs_for_work(work_id)
        job = jobs[0] if jobs else None
    payload = _payload(job)
    selected = _selected(payload)
    found_guid = safe_release_guid(
        guid
        or (job or {}).get("indexer_guid")
        or payload.get("guid")
        or selected.get("guid")
        or (work or {}).get("indexer_guid")
    )
    found_host = _text(host_id or selected.get("host_id") or payload.get("host_id"))
    wanted = None
    if job is not None:
        wanted = db.get_wanted_by_job(str(job.get("id") or ""))
    if wanted is None and _text(payload.get("wanted_id")):
        wanted = db.get_wanted(_text(payload.get("wanted_id")))
    if wanted is None and work_id:
        wanted = db.get_open_wanted_by_work(work_id)
    if wanted is not None and wanted.get("status") == "dismissed":
        wanted = None
    return {
        "job": job,
        "work": work,
        "wanted": wanted,
        "guid": found_guid,
        "host_id": found_host,
    }


def _clear_unreturnable_slip(
    db: Database,
    *,
    work_id: Optional[str],
    job_id: Optional[str],
    guid: str,
    reason: str,
    missing: str,
    now: float,
) -> Dict[str, Any]:
    """Drop a bad-download slip the desk cannot act on. Does not touch the folder or Wanted."""
    wid = _text(work_id)
    dismissed = bool(wid) and db.delete_work(wid)
    if dismissed:
        db.record_review_audit(
            DISMISS_BAD_SLIP,
            work_id=wid,
            job_id=job_id,
            guid=guid or None,
            reason=reason,
            detail={"missing": missing},
            now=now,
        )
    return {
        "released": False,
        "dismissed": dismissed,
        "needs_owner": False,
        "missing": missing,
        "guid": guid,
        "wanted_id": None,
        "note": UNRETURNABLE_NOTE,
    }


def release_bad_wanted(
    db: Database,
    *,
    reason: str,
    job_id: Optional[str] = None,
    work_id: Optional[str] = None,
    guid: Optional[str] = None,
    host_id: Optional[str] = None,
    remove_slip: bool = False,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """One shared transition: mark the release bad and return the Wanted row to the retry clock.

    Links the Wanted row by job first, then by work. With ``remove_slip`` the slip and its
    job records go in the same write. When there is no Wanted row or no release id, the
    slip is dismissed instead. Never touches files on disk and never inserts a Wanted row.
    """
    if reason not in BAD_RELEASE_REASONS:
        raise ValueError(f"Not a bad-release reason: {reason}")
    moment = time.time() if now is None else float(now)
    ctx = release_context(db, job_id=job_id, work_id=work_id, guid=guid, host_id=host_id)
    job = ctx["job"]
    wanted = ctx["wanted"]
    found_guid = ctx["guid"]
    resolved_job_id = _text((job or {}).get("id")) or _text(job_id) or None
    missing = ""
    if not found_guid:
        missing = "guid"
    elif wanted is None:
        missing = "wanted"
    if missing:
        if found_guid:
            db.record_bad_indexer_release(
                host_id=ctx["host_id"], guid=found_guid, reason=reason, now=moment
            )
        return _clear_unreturnable_slip(
            db,
            work_id=work_id,
            job_id=resolved_job_id,
            guid=found_guid,
            reason=reason,
            missing=missing,
            now=moment,
        )
    assert wanted is not None
    updated = db.apply_bad_release(
        host_id=ctx["host_id"],
        guid=found_guid,
        wanted_id=str(wanted["id"]),
        reason=reason,
        job_id=resolved_job_id,
        work_id=work_id,
        remove_slip=remove_slip,
        now=moment,
        detail={"title": _text((ctx["work"] or job or {}).get("title"))},
    )
    if updated is None:
        db.record_bad_indexer_release(
            host_id=ctx["host_id"], guid=found_guid, reason=reason, now=moment
        )
        return _clear_unreturnable_slip(
            db,
            work_id=work_id,
            job_id=resolved_job_id,
            guid=found_guid,
            reason=reason,
            missing="wanted",
            now=moment,
        )
    logger.info(
        "Bad release %s (%s) sent Wanted %s back to search", found_guid, reason, updated.get("id")
    )
    return {
        "released": True,
        "dismissed": False,
        "needs_owner": False,
        "missing": "",
        "guid": found_guid,
        "wanted_id": updated.get("id"),
        "next_search_at": updated.get("next_search_at"),
        "note": "Bad release — back on Wanted for another release.",
    }


# --- one-time migration: existing no_payload / convert_failed slips -------------

_MIGRATION_PROGRESS = ProgressJob(
    filename="bad_release_migration_progress.json",
    defaults=lambda: {
        "status": "idle",
        "phase": "",
        "done": 0,
        "total": 0,
        "returned": 0,
        "dismissed": 0,
        "left_on_desk": 0,
        "failed": 0,
        "current_title": "",
        "logs": [],
        "error": "",
        "started_at": "",
        "finished_at": "",
    },
)


def read_migration_progress(data_dir: Any) -> Dict[str, Any]:
    return _MIGRATION_PROGRESS.read(data_dir)


def migrate_bad_release_slips(
    db: Database,
    *,
    data_dir: Any = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Send existing no_payload/convert_failed slips back to Wanted. Runs once, idempotent.

    A slip that cannot go back — no Wanted row, or no release id — is dismissed.
    The download folder stays on disk. Nothing is left on the desk for the owner.
    """
    done = db.get_migration(MIGRATION_NAME)
    if done is not None:
        return {**dict(done.get("report") or {}), "already_done": True}
    moment = time.time() if now is None else float(now)
    slips = [
        row
        for reason in sorted(BAD_RELEASE_REASONS)
        for row in db.list_works(review_state="needs_review", review_reason=reason, limit=100000)
    ]
    total = len(slips)
    returned = 0
    dismissed = 0
    left = 0
    failed = 0
    if data_dir is not None:
        _MIGRATION_PROGRESS.write(
            data_dir,
            {
                "status": "running",
                "phase": "returning",
                "total": total,
                "started_at": utc_now(),
                "logs": [
                    f"Returning {total} bad-download slips to Wanted. "
                    "Slips that cannot go back are cleared from the desk."
                ],
            },
        )
    for index, slip in enumerate(slips, start=1):
        title = _text(slip.get("title")) or _text(slip.get("id"))
        try:
            result = release_bad_wanted(
                db,
                reason=_text(slip.get("review_reason")),
                work_id=_text(slip.get("id")),
                remove_slip=True,
                now=moment,
            )
            if result["released"]:
                returned += 1
            elif result.get("dismissed"):
                dismissed += 1
            else:
                left += 1
        except Exception as error:  # noqa: BLE001 — keep going through the backlog
            failed += 1
            logger.exception("Bad-release migration failed for %s", slip.get("id"))
            if data_dir is not None:
                _MIGRATION_PROGRESS.append_log(data_dir, f"Failed — {title}: {error}")
        if data_dir is not None:
            _MIGRATION_PROGRESS.patch(
                data_dir,
                done=index,
                returned=returned,
                dismissed=dismissed,
                left_on_desk=left,
                failed=failed,
                current_title=title,
            )
    report = {
        "total": total,
        "returned": returned,
        "dismissed": dismissed,
        "left_on_desk": left,
        "failed": failed,
    }
    if failed == 0:
        db.mark_migration(MIGRATION_NAME, report, now=moment)
    if data_dir is not None:
        _MIGRATION_PROGRESS.patch(
            data_dir,
            status="completed",
            phase="done",
            current_title="",
            finished_at=utc_now(),
        )
        _MIGRATION_PROGRESS.append_log(
            data_dir,
            f"Finished — {returned} back on Wanted, {dismissed} cleared from the desk, {left} left.",
        )
    return report


_MIGRATION_SLOT = BackgroundJobSlot()


def start_bad_release_migration(db: Database, data_dir: Any) -> bool:
    """Kick the one-time migration on a daemon thread at boot. No-op once it has run."""
    if db.get_migration(MIGRATION_NAME) is not None:
        return False

    def _run() -> None:
        try:
            migrate_bad_release_slips(db, data_dir=data_dir)
        except Exception as error:  # noqa: BLE001 — boot must not die on a migration
            logger.exception("Bad-release migration crashed")
            _MIGRATION_PROGRESS.patch(data_dir, status="failed", phase="failed", error=str(error))

    return _MIGRATION_SLOT.start_if_idle(
        is_running=lambda: False,
        begin=lambda: None,
        target=_run,
        name="librarian-bad-release-migration",
    )


__all__ = [
    "BAD_RELEASE_REASONS",
    "MIGRATION_NAME",
    "DISMISS_BAD_SLIP",
    "NEEDS_OWNER_ACTION",
    "NEEDS_OWNER_NOTE",
    "UNRETURNABLE_NOTE",
    "migrate_bad_release_slips",
    "read_migration_progress",
    "release_bad_wanted",
    "release_context",
    "start_bad_release_migration",
]
