"""Ingest job progress blob for UI polling (Add to the shelves)."""

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
        "current_path": "",
        "current_title": "",
        "done": 0,
        "total": 0,
        "seen": 0,
        "shelved": 0,
        "review": 0,
        "skipped": 0,
        "duplicates": 0,
        "errors": 0,
        "volumes_found": 0,
        "files_found": 0,
        "logs": [],
        "error": "",
        "source_path": "",
        "started_at": "",
        "finished_at": "",
        "result": None,
    }


def progress_path(data_dir: Path) -> Path:
    return Path(data_dir) / "ingest_progress.json"


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


def read_ingest_progress(data_dir: Path) -> Dict[str, Any]:
    with _lock:
        return _read_unlocked(data_dir)


def write_ingest_progress(data_dir: Path, payload: Mapping[str, Any]) -> Dict[str, Any]:
    with _lock:
        return _write_unlocked(data_dir, payload)


def patch_ingest_progress(data_dir: Path, **fields: Any) -> Dict[str, Any]:
    with _lock:
        current = _read_unlocked(data_dir)
        current.update(fields)
        return _write_unlocked(data_dir, current)


def append_ingest_log(data_dir: Path, line: str) -> Dict[str, Any]:
    text = str(line or "").strip()
    if not text:
        return read_ingest_progress(data_dir)
    with _lock:
        current = _read_unlocked(data_dir)
        logs: List[str] = list(current.get("logs") or [])
        logs.append(text)
        current["logs"] = logs[-MAX_LOG_LINES:]
        return _write_unlocked(data_dir, current)


def begin_ingest_run(
    data_dir: Path,
    *,
    source_path: str,
    total: int = 0,
    phase: str = "scanning",
) -> Dict[str, Any]:
    payload = default_progress()
    payload.update(
        {
            "status": "running",
            "phase": phase,
            "source_path": str(source_path or ""),
            "total": max(0, int(total)),
            "started_at": _utc_now(),
            "logs": [f"Started shelving from {source_path or 'disk'}."],
        }
    )
    return write_ingest_progress(data_dir, payload)


def finish_ingest_run(
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
            current["current_path"] = ""
            current["current_title"] = ""
            summary = dict(result or {})
            current["result"] = summary
            for key in (
                "shelved",
                "review",
                "skipped",
                "duplicates",
                "errors",
                "done",
                "total",
                "seen",
                "volumes_found",
                "files_found",
            ):
                if key in summary:
                    current[key] = int(summary.get(key) or 0)
            logs = list(current.get("logs") or [])
            shelved = int(summary.get("shelved") or current.get("shelved") or 0)
            review = int(summary.get("review") or current.get("review") or 0)
            skipped = int(summary.get("skipped") or current.get("skipped") or 0)
            duplicates = int(summary.get("duplicates") or current.get("duplicates") or 0)
            seen = int(summary.get("seen") or summary.get("done") or current.get("seen") or 0)
            parts = [f"seen {seen}", f"added {shelved}"]
            if duplicates:
                parts.append(f"ignored duplicates {duplicates}")
            if review:
                parts.append(f"needs you {review}")
            if skipped:
                parts.append(f"skipped {skipped}")
            errors = int(summary.get("errors") or current.get("errors") or 0)
            if errors:
                parts.append(f"failed {errors}")
            logs.append(f"Finished — {', '.join(parts)}.")
            current["logs"] = logs[-MAX_LOG_LINES:]
        current["finished_at"] = _utc_now()
        return _write_unlocked(data_dir, current)


def is_ingest_running(data_dir: Path) -> bool:
    return str(read_ingest_progress(data_dir).get("status") or "") == "running"


class IngestProgressReporter:
    """Callback helper passed into run_ingest_paths."""

    def __init__(self, data_dir: Path, *, source_path: str = "") -> None:
        self.data_dir = Path(data_dir)
        self.source_path = str(source_path or "")

    def start(self, *, total: int, phase: str = "scanning") -> None:
        begin_ingest_run(
            self.data_dir,
            source_path=self.source_path,
            total=total,
            phase=phase,
        )

    def log(self, line: str) -> None:
        append_ingest_log(self.data_dir, line)

    def tick(
        self,
        *,
        phase: str = "",
        current_path: str = "",
        current_title: str = "",
        done: Optional[int] = None,
        total: Optional[int] = None,
        shelved: Optional[int] = None,
        review: Optional[int] = None,
        skipped: Optional[int] = None,
        duplicates: Optional[int] = None,
        errors: Optional[int] = None,
        seen: Optional[int] = None,
        volumes_found: Optional[int] = None,
        files_found: Optional[int] = None,
        log: str = "",
    ) -> None:
        fields: Dict[str, Any] = {}
        if phase:
            fields["phase"] = phase
        if current_path is not None:
            fields["current_path"] = current_path
        if current_title is not None:
            fields["current_title"] = current_title
        if done is not None:
            fields["done"] = int(done)
        if total is not None:
            fields["total"] = int(total)
        if shelved is not None:
            fields["shelved"] = int(shelved)
        if review is not None:
            fields["review"] = int(review)
        if skipped is not None:
            fields["skipped"] = int(skipped)
        if duplicates is not None:
            fields["duplicates"] = int(duplicates)
        if errors is not None:
            fields["errors"] = int(errors)
        if seen is not None:
            fields["seen"] = int(seen)
        if volumes_found is not None:
            fields["volumes_found"] = int(volumes_found)
        if files_found is not None:
            fields["files_found"] = int(files_found)
        if fields:
            patch_ingest_progress(self.data_dir, **fields)
        if log:
            append_ingest_log(self.data_dir, log)

    def complete(self, result: Mapping[str, Any]) -> None:
        finish_ingest_run(self.data_dir, result=result)

    def fail(self, error: str) -> None:
        finish_ingest_run(self.data_dir, error=error)
