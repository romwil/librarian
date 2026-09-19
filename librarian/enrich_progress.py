"""Enrich job progress blob for UI polling (Settings + trickle)."""

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
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "logs": [],
        "error": "",
        "source": "",
        "started_at": "",
        "finished_at": "",
        "result": None,
    }


def progress_path(data_dir: Path) -> Path:
    return Path(data_dir) / "enrich_progress.json"


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


def read_enrich_progress(data_dir: Path) -> Dict[str, Any]:
    with _lock:
        return _read_unlocked(data_dir)


def write_enrich_progress(data_dir: Path, payload: Mapping[str, Any]) -> Dict[str, Any]:
    with _lock:
        return _write_unlocked(data_dir, payload)


def patch_enrich_progress(data_dir: Path, **fields: Any) -> Dict[str, Any]:
    with _lock:
        current = _read_unlocked(data_dir)
        current.update(fields)
        return _write_unlocked(data_dir, current)


def append_enrich_log(data_dir: Path, line: str) -> Dict[str, Any]:
    text = str(line or "").strip()
    if not text:
        return read_enrich_progress(data_dir)
    with _lock:
        current = _read_unlocked(data_dir)
        logs: List[str] = list(current.get("logs") or [])
        logs.append(text)
        current["logs"] = logs[-MAX_LOG_LINES:]
        return _write_unlocked(data_dir, current)


def begin_enrich_run(
    data_dir: Path,
    *,
    source: str,
    total: int = 0,
    phase: str = "starting",
) -> Dict[str, Any]:
    payload = default_progress()
    payload.update(
        {
            "status": "running",
            "phase": phase,
            "source": source,
            "total": max(0, int(total)),
            "started_at": _utc_now(),
            "logs": [f"Started enrich ({source})."],
        }
    )
    return write_enrich_progress(data_dir, payload)


def finish_enrich_run(
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
            if "updated" in summary:
                current["updated"] = int(summary.get("updated") or 0)
            if "skipped" in summary:
                current["skipped"] = int(summary.get("skipped") or 0)
            if "scanned" in summary:
                current["done"] = int(summary.get("scanned") or current.get("done") or 0)
            logs = list(current.get("logs") or [])
            updated = int(summary.get("updated") or current.get("updated") or 0)
            scanned = int(summary.get("scanned") or current.get("done") or 0)
            logs.append(f"Finished — enriched {updated} of {scanned}.")
            current["logs"] = logs[-MAX_LOG_LINES:]
        current["finished_at"] = _utc_now()
        return _write_unlocked(data_dir, current)


def is_enrich_running(data_dir: Path) -> bool:
    return str(read_enrich_progress(data_dir).get("status") or "") == "running"


class EnrichProgressReporter:
    """Callback helper passed into enrich_library / enrich_backlog_batch."""

    def __init__(self, data_dir: Path, *, source: str) -> None:
        self.data_dir = Path(data_dir)
        self.source = source

    def start(self, *, total: int, phase: str = "scanning") -> None:
        begin_enrich_run(self.data_dir, source=self.source, total=total, phase=phase)

    def log(self, line: str) -> None:
        append_enrich_log(self.data_dir, line)

    def tick(
        self,
        *,
        phase: str = "",
        current_title: str = "",
        done: Optional[int] = None,
        total: Optional[int] = None,
        updated: Optional[int] = None,
        skipped: Optional[int] = None,
        errors: Optional[int] = None,
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
        if updated is not None:
            fields["updated"] = int(updated)
        if skipped is not None:
            fields["skipped"] = int(skipped)
        if errors is not None:
            fields["errors"] = int(errors)
        if fields:
            patch_enrich_progress(self.data_dir, **fields)
        if log:
            append_enrich_log(self.data_dir, log)

    def complete(self, result: Mapping[str, Any]) -> None:
        finish_enrich_run(self.data_dir, result=result)

    def fail(self, error: str) -> None:
        finish_enrich_run(self.data_dir, error=error)
