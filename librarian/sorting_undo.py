"""24-hour SQLite undo for Sorting desk batches. Never talks to SABnzbd."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Mapping, Optional, Sequence

from librarian.db import Database
from librarian.grooming_undo import snapshot_work
from librarian.repositories._base import _dumps, _loads

UNDO_TTL_SECONDS = 24 * 3600
MAX_UNDO_WORKS = 500

ACTION_LABELS = {
    "delete": "Delete group",
    "delete_group": "Delete group",
    "accept_clear": "Accept the clear ones",
    "purge_duplicates": "Purge duplicate group",
    "purge_duplicate_group": "Purge duplicate group",
    "autopilot": "Autopilot file",
}


def _label(action: str) -> str:
    key = str(action or "").strip()
    return ACTION_LABELS.get(key, key.replace("_", " ").title() or "Last tend")


def record_sorting_undo(
    db: Database,
    *,
    action: str,
    works: Sequence[Mapping[str, Any]],
    reason: str = "",
    now: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Persist a recoverable batch. Caps at 500 slips. Returns the public row."""
    snapshots: List[Dict[str, Any]] = []
    for row in works or []:
        snap = snapshot_work(row)
        if snap:
            snapshots.append(snap)
        if len(snapshots) >= MAX_UNDO_WORKS:
            break
    if not snapshots:
        return None
    moment = time.time() if now is None else float(now)
    batch_id = uuid.uuid4().hex
    action_id = str(action or "").strip() or "tend"
    payload = {
        "id": batch_id,
        "action": action_id,
        "reason": str(reason or ""),
        "label": _label(action_id),
        "created_at": moment,
        "expires_at": moment + UNDO_TTL_SECONDS,
        "restored_at": None,
        "snapshot_json": _dumps(snapshots),
    }

    def _write() -> Any:
        with db._connect() as conn:
            conn.execute(
                """
                INSERT INTO sorting_undo (
                    id, action, reason, label, created_at, expires_at, restored_at, snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"],
                    payload["action"],
                    payload["reason"],
                    payload["label"],
                    payload["created_at"],
                    payload["expires_at"],
                    None,
                    payload["snapshot_json"],
                ),
            )

    db.run_write(_write, label="record_sorting_undo")
    return public_undo(db, now=moment)


def _latest_row(db: Database) -> Optional[Dict[str, Any]]:
    with db._connect() as conn:
        row = conn.execute(
            "SELECT * FROM sorting_undo ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    from librarian.repositories._base import _row_dict

    data = _row_dict(row) or {}
    data["works"] = _loads(data.pop("snapshot_json", None), [])
    if not isinstance(data["works"], list):
        data["works"] = []
    return data


def batch_is_active(batch: Optional[Mapping[str, Any]], *, now: Optional[float] = None) -> bool:
    if not batch:
        return False
    if batch.get("restored_at"):
        return False
    works = batch.get("works") if isinstance(batch.get("works"), list) else []
    if not works:
        return False
    expires = float(batch.get("expires_at") or 0)
    return (time.time() if now is None else float(now)) < expires


def public_undo(db: Database, *, now: Optional[float] = None) -> Dict[str, Any]:
    batch = _latest_row(db)
    active = batch_is_active(batch, now=now)
    count = len(batch.get("works") or []) if active and batch else 0
    if not active or not batch:
        return {
            "available": False,
            "presence": "No recent tend to undo — the lamp keeps calm.",
            "action": "",
            "label": "",
            "count": 0,
            "expires_at": None,
        }
    label = str(batch.get("label") or "Last tend")
    if count == 1:
        presence = f"{label} can still be undone — one volume waits in the lamp's memory."
    else:
        presence = f"{label} can still be undone — {count} volumes wait in the lamp's memory."
    return {
        "available": True,
        "presence": presence,
        "action": str(batch.get("action") or ""),
        "label": label,
        "count": count,
        "expires_at": batch.get("expires_at"),
    }


def restore_sorting_undo(db: Database, *, now: Optional[float] = None) -> Dict[str, Any]:
    """Put deleted slips back. Filed slips return to needs_review. Never calls SAB."""
    moment = time.time() if now is None else float(now)
    batch = _latest_row(db)
    if not batch_is_active(batch, now=moment) or not batch:
        return {
            "ok": False,
            "restored": 0,
            "skipped": 0,
            "presence": "That undo window has closed — tend again if you need to.",
            "undo": public_undo(db, now=moment),
        }
    restored = 0
    skipped = 0
    for row in batch.get("works") or []:
        if not isinstance(row, dict):
            skipped += 1
            continue
        work_id = str(row.get("id") or "").strip()
        if not work_id:
            skipped += 1
            continue
        existing = db.get_work(work_id)
        if existing is None:
            db.upsert_work(dict(row))
            restored += 1
            continue
        if str(existing.get("review_state") or "") == "needs_review":
            skipped += 1
            continue
        db.upsert_work(
            {
                **existing,
                **{k: v for k, v in row.items() if k in existing or k in row},
                "id": work_id,
                "review_state": "needs_review",
                "review_reason": row.get("review_reason") or existing.get("review_reason"),
            }
        )
        restored += 1

    def _mark() -> Any:
        with db._connect() as conn:
            conn.execute(
                "UPDATE sorting_undo SET restored_at = ? WHERE id = ?",
                (moment, batch["id"]),
            )

    db.run_write(_mark, label="restore_sorting_undo")
    return {
        "ok": True,
        "restored": restored,
        "skipped": skipped,
        "presence": (
            "The last tend is back on the desk."
            if restored
            else "Nothing needed restoring — those volumes were already home."
        ),
        "undo": public_undo(db, now=moment),
    }


__all__ = [
    "MAX_UNDO_WORKS",
    "UNDO_TTL_SECONDS",
    "public_undo",
    "record_sorting_undo",
    "restore_sorting_undo",
]
