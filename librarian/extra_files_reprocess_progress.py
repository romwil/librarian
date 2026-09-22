"""Clear extra-files slips job progress blob for Review UI polling."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

MAX_LOG_LINES = 40

_lock = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_progress() -> Dict[str, Any]:
    return {
        "status": "idle",
        "phase": "",
        "current_title": "",
        "done": 0,
        "total": 0,
        "shelved": 0,
        "split": 0,
        "applied": 0,
        "failed": 0,
        "still_review": 0,
        "logs": [],
        "error": "",
        "started_at": "",
        "finished_at": "",
        "result": None,
    }


def progress_path(data_dir: Path) -> Path:
    return Path(data_dir) / "extra_files_reprocess_progress.json"


def _read_unlocked(data_dir: Path) -> Dict[str, Any]:
    """Read progress JSON. Caller must hold ``_lock``."""
    path = progress_path(data_dir)
    if not path.is_file():
        return default_progress()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_progress()
    if not isinstance(raw, dict):
        return default_progress()
    base = default_progress()
    base.update(raw)
    logs = base.get("logs") or []
    if not isinstance(logs, list):
        logs = []
    base["logs"] = [str(line) for line in logs][-MAX_LOG_LINES:]
    return base


def _write_unlocked(data_dir: Path, payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Write progress JSON. Caller must hold ``_lock``."""
    path = progress_path(data_dir)
    merged = default_progress()
    merged.update(dict(payload))
    logs = merged.get("logs") or []
    if not isinstance(logs, list):
        logs = []
    merged["logs"] = [str(line) for line in logs][-MAX_LOG_LINES:]
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(merged, indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8")
    return merged


def read_extra_files_reprocess_progress(data_dir: Path) -> Dict[str, Any]:
    with _lock:
        return _read_unlocked(data_dir)


def write_extra_files_reprocess_progress(data_dir: Path, payload: Mapping[str, Any]) -> Dict[str, Any]:
    with _lock:
        return _write_unlocked(data_dir, payload)


def patch_extra_files_reprocess_progress(data_dir: Path, **fields: Any) -> Dict[str, Any]:
    with _lock:
        current = _read_unlocked(data_dir)
        current.update(fields)
        return _write_unlocked(data_dir, current)


def append_extra_files_reprocess_log(data_dir: Path, line: str) -> Dict[str, Any]:
    text = str(line or "").strip()
    if not text:
        return read_extra_files_reprocess_progress(data_dir)
    with _lock:
        current = _read_unlocked(data_dir)
        logs: List[str] = list(current.get("logs") or [])
        logs.append(text)
        current["logs"] = logs[-MAX_LOG_LINES:]
        return _write_unlocked(data_dir, current)


def begin_extra_files_reprocess_run(
    data_dir: Path,
    *,
    total: int = 0,
    phase: str = "starting",
) -> Dict[str, Any]:
    payload = default_progress()
    payload.update(
        {
            "status": "running",
            "phase": phase,
            "total": max(0, int(total)),
            "started_at": _utc_now(),
            "logs": ["Started clearing extra_files slips."],
        }
    )
    return write_extra_files_reprocess_progress(data_dir, payload)


def finish_extra_files_reprocess_run(
    data_dir: Path,
    *,
    result: Optional[Mapping[str, Any]] = None,
    error: str = "",
) -> Dict[str, Any]:
    with _lock:
        current = _read_unlocked(data_dir)
        if error:
            current["status"] = "failed"
            current["phase"] = "failed"
            current["error"] = str(error)
            logs = list(current.get("logs") or [])
            logs.append(f"Failed: {error}")
            current["logs"] = logs[-MAX_LOG_LINES:]
        else:
            current["status"] = "completed"
            current["phase"] = "done"
            current["error"] = ""
            current["current_title"] = ""
            summary = dict(result or {})
            current["result"] = summary
            for key in ("shelved", "split", "applied", "failed", "still_review", "done", "total"):
                if key in summary:
                    current[key] = int(summary.get(key) or 0)
            if "considered" in summary and "total" not in summary:
                current["total"] = int(summary.get("considered") or current.get("total") or 0)
            logs = list(current.get("logs") or [])
            shelved = int(summary.get("shelved") or current.get("shelved") or 0)
            split = int(summary.get("split") or current.get("split") or 0)
            applied = int(summary.get("applied") or current.get("applied") or 0)
            failed = int(summary.get("failed") or current.get("failed") or 0)
            done = int(summary.get("done") or current.get("done") or 0)
            parts = [f"shelved {shelved}", f"split {split}", f"applied {applied}"]
            if failed:
                parts.append(f"failed {failed}")
            logs.append(f"Finished — {', '.join(parts)} ({done} looked at).")
            current["logs"] = logs[-MAX_LOG_LINES:]
        current["finished_at"] = _utc_now()
        return _write_unlocked(data_dir, current)


def is_extra_files_reprocess_running(data_dir: Path) -> bool:
    return str(read_extra_files_reprocess_progress(data_dir).get("status") or "") == "running"


class ExtraFilesReprocessProgressReporter:
    """Callback helper passed into reprocess_extra_files_reviews."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)

    def start(self, *, total: int, phase: str = "starting") -> None:
        begin_extra_files_reprocess_run(self.data_dir, total=total, phase=phase)

    def log(self, line: str) -> None:
        append_extra_files_reprocess_log(self.data_dir, line)

    def tick(
        self,
        *,
        phase: str = "",
        current_title: str = "",
        done: Optional[int] = None,
        total: Optional[int] = None,
        shelved: Optional[int] = None,
        split: Optional[int] = None,
        applied: Optional[int] = None,
        failed: Optional[int] = None,
        still_review: Optional[int] = None,
        log: str = "",
    ) -> None:
        fields: Dict[str, Any] = {}
        if phase:
            fields["phase"] = phase
        if current_title is not None:
            fields["current_title"] = current_title
        if done is not None:
            fields["done"] = int(done)
        if total is not None:
            fields["total"] = int(total)
        if shelved is not None:
            fields["shelved"] = int(shelved)
        if split is not None:
            fields["split"] = int(split)
        if applied is not None:
            fields["applied"] = int(applied)
        if failed is not None:
            fields["failed"] = int(failed)
        if still_review is not None:
            fields["still_review"] = int(still_review)
        if fields:
            patch_extra_files_reprocess_progress(self.data_dir, **fields)
        if log:
            append_extra_files_reprocess_log(self.data_dir, log)

    def complete(self, result: Mapping[str, Any]) -> None:
        finish_extra_files_reprocess_run(self.data_dir, result=result)

    def fail(self, error: str) -> None:
        finish_extra_files_reprocess_run(self.data_dir, error=error)
