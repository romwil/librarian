"""Safe undo for grooming — last Clear/Purge/Skip batch, metadata only, timed window."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

UNDO_FILENAME = "grooming_undo.json"
UNDO_TTL_HOURS = 4
MAX_SNAPSHOTS = 200

_LOCK = threading.Lock()

ACTION_LABELS = {
    "skip": "Skip",
    "purge_shells": "Purge shells",
    "purge_duplicates": "Purge twins",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def utc_now_iso() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def parse_utc(value: Any) -> Optional[datetime]:
    text = _text(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def undo_path(data_dir: Path) -> Path:
    return Path(data_dir) / UNDO_FILENAME


def _empty_batch() -> Dict[str, Any]:
    return {
        "action": "",
        "label": "",
        "at": "",
        "expires_at": "",
        "works": [],
        "restored_at": "",
    }


def snapshot_work(work: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """Metadata-only catalog snapshot (no media bytes)."""
    if not work:
        return None
    work_id = _text(work.get("id"))
    if not work_id:
        return None
    # Keep a lean allowlist so undo never rehydrates secrets or giant blobs.
    keys = (
        "id",
        "kind",
        "title",
        "author",
        "series_name",
        "series_index",
        "year",
        "isbn",
        "folder_path",
        "cover_path",
        "review_state",
        "review_reason",
        "music_state",
        "description",
        "llm_blurb",
        "cloth",
        "indexer_guid",
        "created_at",
        "updated_at",
    )
    out = {key: work.get(key) for key in keys if key in work}
    out["id"] = work_id
    return out


def read_undo(data_dir: Path) -> Dict[str, Any]:
    path = undo_path(data_dir)
    if not path.exists():
        return _empty_batch()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_batch()
    if not isinstance(raw, dict):
        return _empty_batch()
    works = raw.get("works") if isinstance(raw.get("works"), list) else []
    return {
        "action": _text(raw.get("action")),
        "label": _text(raw.get("label")),
        "at": _text(raw.get("at")),
        "expires_at": _text(raw.get("expires_at")),
        "works": [dict(row) for row in works if isinstance(row, dict)][:MAX_SNAPSHOTS],
        "restored_at": _text(raw.get("restored_at")),
    }


def write_undo(data_dir: Path, payload: Mapping[str, Any]) -> Dict[str, Any]:
    path = undo_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = {
        "action": _text(payload.get("action")),
        "label": _text(payload.get("label")),
        "at": _text(payload.get("at")) or utc_now_iso(),
        "expires_at": _text(payload.get("expires_at")),
        "works": list(payload.get("works") or [])[:MAX_SNAPSHOTS],
        "restored_at": _text(payload.get("restored_at")),
    }
    path.write_text(json.dumps(blob, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return blob


def record_grooming_batch(
    data_dir: Path,
    *,
    action: str,
    works: Sequence[Mapping[str, Any]],
    ttl_hours: float = UNDO_TTL_HOURS,
) -> Dict[str, Any]:
    """Replace the recoverable batch with this tend (one undo window at a time)."""
    snapshots: List[Dict[str, Any]] = []
    for row in works or []:
        snap = snapshot_work(row)
        if snap:
            snapshots.append(snap)
        if len(snapshots) >= MAX_SNAPSHOTS:
            break
    if not snapshots:
        return read_undo(data_dir)
    now = utc_now()
    expires = now + timedelta(hours=max(0.25, float(ttl_hours or UNDO_TTL_HOURS)))
    action_id = _text(action) or "groom"
    label = ACTION_LABELS.get(action_id, action_id.replace("_", " ").title())
    with _LOCK:
        return write_undo(
            data_dir,
            {
                "action": action_id,
                "label": label,
                "at": now.isoformat().replace("+00:00", "Z"),
                "expires_at": expires.isoformat().replace("+00:00", "Z"),
                "works": snapshots,
                "restored_at": "",
            },
        )


def batch_is_active(batch: Optional[Mapping[str, Any]], *, now: Optional[datetime] = None) -> bool:
    if not batch:
        return False
    if _text(batch.get("restored_at")):
        return False
    works = batch.get("works") if isinstance(batch.get("works"), list) else []
    if not works:
        return False
    expires = parse_utc(batch.get("expires_at"))
    if expires is None:
        return False
    current = now or utc_now()
    return current < expires


def undo_presence(batch: Optional[Mapping[str, Any]] = None) -> str:
    """Warm confidence line — never a KPI of deleted counts alone."""
    if not batch_is_active(batch):
        return "No recent tend to undo — the lamp keeps calm."
    label = _text(batch.get("label")) or "Last tend"
    n = len(batch.get("works") or [])
    if n == 1:
        return f"{label} can still be undone — one volume waits in the lamp’s memory."
    return f"{label} can still be undone — {n} volumes wait in the lamp’s memory."


def assemble_grooming_undo(data_dir: Path) -> Dict[str, Any]:
    batch = read_undo(data_dir)
    active = batch_is_active(batch)
    return {
        "available": active,
        "presence": undo_presence(batch if active else None),
        "action": _text(batch.get("action")) if active else "",
        "label": _text(batch.get("label")) if active else "",
        "at": _text(batch.get("at")) if active else "",
        "expires_at": _text(batch.get("expires_at")) if active else "",
        "count": len(batch.get("works") or []) if active else 0,
    }


def restore_grooming_batch(db: Any, data_dir: Path) -> Dict[str, Any]:
    """Restore the last metadata-only batch. Fail closed when expired or empty."""
    with _LOCK:
        batch = read_undo(data_dir)
        if not batch_is_active(batch):
            return {
                "ok": False,
                "restored": 0,
                "skipped": 0,
                "presence": "That undo window has closed — tend again if you need to.",
                "undo": assemble_grooming_undo(data_dir),
            }
        restored = 0
        skipped = 0
        for row in batch.get("works") or []:
            if not isinstance(row, dict):
                skipped += 1
                continue
            work_id = _text(row.get("id"))
            if not work_id:
                skipped += 1
                continue
            if db.get_work(work_id) is not None:
                skipped += 1
                continue
            db.upsert_work(dict(row))
            restored += 1
        batch["restored_at"] = utc_now_iso()
        write_undo(data_dir, batch)
    return {
        "ok": True,
        "restored": restored,
        "skipped": skipped,
        "presence": (
            "The last tend is back on the desk."
            if restored
            else "Nothing needed restoring — those volumes were already home."
        ),
        "undo": assemble_grooming_undo(data_dir),
    }


__all__ = [
    "UNDO_TTL_HOURS",
    "assemble_grooming_undo",
    "batch_is_active",
    "read_undo",
    "record_grooming_batch",
    "restore_grooming_batch",
    "snapshot_work",
    "undo_presence",
    "write_undo",
]
