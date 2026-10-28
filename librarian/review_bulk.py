"""Holds desk group actions: one motion for a whole pile, by the server's effective reason.

Actions:

- ``delete``: the owner's deliberate discard. Removes the slip, its catalog and job
  records, and dismisses its Wanted request. The completed-download folder and its
  files stay on disk.
- ``accept_clear``: shelve the path-clear Author/Title books in the pile.
- ``purge_duplicates``: only on a duplicate pile. Dismisses exact-fingerprint twins;
  different bytes and unreadable folders stay. ``dry_run`` reports the evidence first.

Every mutation goes through the database write serializer (``Database.run_write``).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from librarian.config import Settings
from librarian.db import Database
from librarian.duplicate_gate import EVIDENCE_EXACT, start_slip_cooldown
from librarian.review_reasons import (
    DUPLICATE_REVIEW_REASONS,
    REVIEW_MISSING_FOLDER,
    REVIEW_NO_PAYLOAD,
    REVIEW_UNPACK_STUCK,
)

logger = logging.getLogger(__name__)

ACTION_DELETE = "delete"
ACTION_ACCEPT_CLEAR = "accept_clear"
ACTION_PURGE_DUPLICATES = "purge_duplicates"
BULK_ACTIONS = frozenset({ACTION_DELETE, ACTION_ACCEPT_CLEAR, ACTION_PURGE_DUPLICATES})

READY_TO_FILE = "ready_to_file"
BULK_SLIP_LIMIT = 20000
_DIAGNOSIS_REASONS = frozenset({"", REVIEW_UNPACK_STUCK, REVIEW_MISSING_FOLDER, REVIEW_NO_PAYLOAD, READY_TO_FILE})


class BulkError(ValueError):
    """Caller-facing bulk validation error."""


def effective_review_reason(
    work: Mapping[str, Any],
    diagnosis: Optional[Mapping[str, Any]] = None,
    suggestion: Optional[Mapping[str, Any]] = None,
) -> str:
    """The pile a slip belongs to. Same rules the Holds desk groups by."""
    problem = str((diagnosis or {}).get("problem") or "")
    stored = str(work.get("review_reason") or "")
    if problem == REVIEW_UNPACK_STUCK:
        return REVIEW_UNPACK_STUCK
    if problem == REVIEW_MISSING_FOLDER and stored in ("", REVIEW_NO_PAYLOAD):
        return REVIEW_MISSING_FOLDER
    if problem == REVIEW_NO_PAYLOAD and stored in ("", REVIEW_NO_PAYLOAD):
        return REVIEW_NO_PAYLOAD
    if not stored and not problem and str((suggestion or {}).get("outcome") or "") == "trusted":
        return READY_TO_FILE
    return stored or problem or ""


def _diagnose(work: Mapping[str, Any], settings: Settings) -> Dict[str, Any]:
    from librarian.identify import diagnose_review_folder

    folder = str(work.get("folder_path") or "")
    try:
        return dict(diagnose_review_folder(Path(folder), settings.complete_root))
    except OSError:
        return {}


def slips_in_group(
    db: Database,
    settings: Settings,
    *,
    reason: str,
    work_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Slips whose effective reason is ``reason``. Selected ids outside the pile are skipped."""
    key = str(reason or "").strip()
    chosen = [str(w).strip() for w in (work_ids or []) if str(w or "").strip()]
    if chosen:
        rows = [db.get_work(work_id) for work_id in dict.fromkeys(chosen)]
        candidates = [row for row in rows if row]
        missing = len(chosen) - len(candidates)
    elif key in _DIAGNOSIS_REASONS:
        candidates = db.list_works(review_state="needs_review", limit=BULK_SLIP_LIMIT)
        missing = 0
    else:
        candidates = db.list_works(
            review_state="needs_review", review_reason=key, limit=BULK_SLIP_LIMIT
        )
        missing = 0
    suggestions = db.get_review_suggestions([str(row.get("id") or "") for row in candidates])
    members: List[Dict[str, Any]] = []
    outside = 0
    for row in candidates:
        if str(row.get("review_state") or "") != "needs_review":
            outside += 1
            continue
        effective = effective_review_reason(
            row, _diagnose(row, settings), suggestions.get(str(row.get("id") or ""))
        )
        if effective != key:
            outside += 1
            continue
        members.append(row)
    return {"works": members, "outside": outside, "missing": missing}


def _wanted_ids_for_slip(db: Database, work_id: str, jobs: Sequence[Mapping[str, Any]]) -> List[str]:
    found: List[str] = []
    for job in jobs:
        row = db.get_wanted_by_job(str(job.get("id") or ""))
        if row is not None:
            found.append(str(row["id"]))
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        linked = str((payload or {}).get("wanted_id") or "").strip()
        if linked:
            found.append(linked)
    by_work = db.get_open_wanted_by_work(work_id)
    if by_work is not None:
        found.append(str(by_work["id"]))
    return list(dict.fromkeys(found))


def _record_undo(data_dir: Any, action: str, removed: List[Dict[str, Any]]) -> bool:
    if not removed or data_dir is None:
        return False
    try:
        from librarian.grooming_undo import record_grooming_batch

        record_grooming_batch(Path(data_dir), action=action, works=removed)
        return True
    except Exception:  # noqa: BLE001 — undo must never break a bulk action
        logger.exception("Could not record grooming undo for %s", action)
        return False


def _delete_group(
    db: Database,
    works: List[Dict[str, Any]],
    *,
    data_dir: Any,
) -> Dict[str, Any]:
    changed = 0
    wanted_dismissed = 0
    failures: List[Dict[str, Any]] = []
    removed: List[Dict[str, Any]] = []
    for work in works:
        work_id = str(work.get("id") or "")
        try:
            jobs = db.jobs_for_work(work_id)
            wanted_ids = _wanted_ids_for_slip(db, work_id, jobs)
            ok = db.discard_review_slip(
                work_id,
                dismiss_wanted_ids=wanted_ids,
                job_ids=[str(job.get("id") or "") for job in jobs if job.get("id")],
                detail={"action": "delete_group", "title": work.get("title")},
            )
            if not ok:
                failures.append({"id": work_id, "title": work.get("title"), "error": "Already gone"})
                continue
            start_slip_cooldown(db, work.get("folder_path"), reason="delete_group")
            removed.append(dict(work))
            changed += 1
            wanted_dismissed += len(wanted_ids)
        except Exception as error:  # noqa: BLE001 — keep going; report the partial failure
            logger.exception("Delete group failed for %s", work_id)
            failures.append({"id": work_id, "title": work.get("title"), "error": str(error)})
    undo = _record_undo(data_dir, "delete_group", removed)
    return {
        "changed": changed,
        "failed": len(failures),
        "failures": failures[:20],
        "wanted_dismissed": wanted_dismissed,
        "undo_recorded": undo,
    }


def _purge_duplicate_group(
    db: Database,
    settings: Settings,
    works: List[Dict[str, Any]],
    *,
    dry_run: bool,
    data_dir: Any,
) -> Dict[str, Any]:
    from librarian.purge_duplicates import duplicate_evidence

    evidence = duplicate_evidence(db, settings, works)
    counts = evidence["counts"]
    out: Dict[str, Any] = {
        "evidence": counts,
        "works_evidence": evidence["works"],
        "purgeable": int(counts.get(EVIDENCE_EXACT) or 0),
        "unassessable": int(counts.get("unassessable") or 0),
    }
    if dry_run:
        out.update({"changed": 0, "failed": 0, "failures": []})
        return out
    changed = 0
    failures: List[Dict[str, Any]] = []
    removed: List[Dict[str, Any]] = []
    for work in works:
        work_id = str(work.get("id") or "")
        row = evidence["works"].get(work_id) or {}
        if row.get("evidence") != EVIDENCE_EXACT:
            if row.get("evidence") == "unassessable":
                logger.info(
                    "Purge duplicate group kept %s: no readable media to fingerprint at %s",
                    work_id,
                    work.get("folder_path") or "no folder",
                )
            continue
        try:
            fresh = db.get_work(work_id)
            if fresh is None or str(fresh.get("review_state") or "") != "needs_review":
                continue
            db.delete_work(work_id)
            start_slip_cooldown(db, fresh.get("folder_path"), reason="purge_duplicates")
            removed.append(dict(fresh))
            changed += 1
        except Exception as error:  # noqa: BLE001
            logger.exception("Purge duplicate group failed for %s", work_id)
            failures.append({"id": work_id, "title": work.get("title"), "error": str(error)})
    out.update(
        {
            "changed": changed,
            "failed": len(failures),
            "failures": failures[:20],
            "undo_recorded": _record_undo(data_dir, "purge_duplicate_group", removed),
        }
    )
    return out


def bulk_by_reason(
    db: Database,
    settings: Settings,
    *,
    reason: str,
    action: str,
    work_ids: Optional[Sequence[str]] = None,
    dry_run: bool = False,
    data_dir: Any = None,
) -> Dict[str, Any]:
    """Run one allow-listed action on a pile. Returns examined/changed/skipped/reasons."""
    act = str(action or "").strip()
    key = str(reason or "").strip()
    if act not in BULK_ACTIONS:
        raise BulkError("Unknown group action")
    if act == ACTION_PURGE_DUPLICATES and key not in DUPLICATE_REVIEW_REASONS:
        raise BulkError("Purge duplicate group only runs on the duplicate pile")
    if dry_run and act != ACTION_PURGE_DUPLICATES:
        raise BulkError("Only Purge duplicate group has a preview")
    group = slips_in_group(db, settings, reason=key, work_ids=work_ids)
    works: List[Dict[str, Any]] = group["works"]
    skip_reasons: Dict[str, int] = {}
    if group["outside"]:
        skip_reasons["not_in_group"] = int(group["outside"])
    if group["missing"]:
        skip_reasons["not_found"] = int(group["missing"])
    examined = len(works) + int(group["outside"]) + int(group["missing"])
    detail: Dict[str, Any]
    if act == ACTION_DELETE:
        detail = _delete_group(db, works, data_dir=data_dir)
    elif act == ACTION_ACCEPT_CLEAR:
        from librarian.slip_gate import accept_path_clear_slips

        accepted = accept_path_clear_slips(db, reason=key, works=works)
        detail = {"changed": int(accepted.get("accepted") or 0), "failed": 0, "failures": []}
        kept = int(accepted.get("kept") or 0)
        if kept:
            skip_reasons["not_path_clear"] = kept
    else:
        detail = _purge_duplicate_group(db, settings, works, dry_run=dry_run, data_dir=data_dir)
        if not dry_run:
            others = len(works) - int(detail["changed"]) - int(detail["failed"])
            if detail.get("unassessable"):
                skip_reasons["unassessable"] = int(detail["unassessable"])
            not_exact = others - int(detail.get("unassessable") or 0)
            if not_exact > 0:
                skip_reasons["not_exact_fingerprint"] = not_exact
    if detail.get("failed"):
        skip_reasons["failed"] = int(detail["failed"])
    changed = int(detail.get("changed") or 0)
    return {
        "action": act,
        "reason": key,
        "dry_run": bool(dry_run),
        "examined": examined,
        "changed": changed,
        "skipped": max(0, examined - changed),
        "reasons": skip_reasons,
        **{k: v for k, v in detail.items() if k != "changed"},
    }


__all__ = [
    "ACTION_ACCEPT_CLEAR",
    "ACTION_DELETE",
    "ACTION_PURGE_DUPLICATES",
    "BULK_ACTIONS",
    "BulkError",
    "READY_TO_FILE",
    "bulk_by_reason",
    "effective_review_reason",
    "slips_in_group",
]
