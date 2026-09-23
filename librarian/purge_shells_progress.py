"""Shell-works purge job progress blob for UI polling."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

MAX_LOG_LINES = 40
# Fingerprinting thousands of slips can take a while; heartbeat while scanning.
HEARTBEAT_STALE_S = 300.0

_lock = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc_timestamp(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
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


def heartbeat_age_seconds(payload: Mapping[str, Any], *, now: Optional[datetime] = None) -> Optional[float]:
    stamp = parse_utc_timestamp(payload.get("heartbeat_at")) or parse_utc_timestamp(payload.get("started_at"))
    if stamp is None:
        return None
    current = now or datetime.now(timezone.utc)
    return max(0.0, (current - stamp).total_seconds())


def is_purge_shells_stale(
    payload: Mapping[str, Any],
    *,
    stale_after_s: float = HEARTBEAT_STALE_S,
    now: Optional[datetime] = None,
) -> bool:
    if str(payload.get("status") or "") != "running":
        return False
    age = heartbeat_age_seconds(payload, now=now)
    if age is None:
        return False
    return age >= max(1.0, float(stale_after_s))


def default_progress() -> Dict[str, Any]:
    return {
        "status": "idle",
        "phase": "",
        "current_title": "",
        "done": 0,
        "total": 0,
        "purged": 0,
        "kept": 0,
        "failed": 0,
        "logs": [],
        "error": "",
        "started_at": "",
        "heartbeat_at": "",
        "finished_at": "",
        "result": None,
    }


def progress_path(data_dir: Path) -> Path:
    return Path(data_dir) / "purge_shells_progress.json"


def _read_unlocked(data_dir: Path) -> Dict[str, Any]:
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
    path = progress_path(data_dir)
    merged = default_progress()
    merged.update(dict(payload))
    logs = merged.get("logs") or []
    if not isinstance(logs, list):
        logs = []
    merged["logs"] = [str(line) for line in logs][-MAX_LOG_LINES:]
    if str(merged.get("status") or "") == "running" and not str(merged.get("heartbeat_at") or "").strip():
        merged["heartbeat_at"] = _utc_now()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(merged, indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8")
    return merged


def read_purge_shells_progress(data_dir: Path) -> Dict[str, Any]:
    with _lock:
        return _read_unlocked(data_dir)


def write_purge_shells_progress(data_dir: Path, payload: Mapping[str, Any]) -> Dict[str, Any]:
    with _lock:
        return _write_unlocked(data_dir, payload)


def patch_purge_shells_progress(data_dir: Path, **fields: Any) -> Dict[str, Any]:
    with _lock:
        current = _read_unlocked(data_dir)
        current.update(fields)
        if str(current.get("status") or "") == "running" and "heartbeat_at" not in fields:
            current["heartbeat_at"] = _utc_now()
        return _write_unlocked(data_dir, current)


def append_purge_shells_log(data_dir: Path, line: str) -> Dict[str, Any]:
    text = str(line or "").strip()
    if not text:
        return read_purge_shells_progress(data_dir)
    with _lock:
        current = _read_unlocked(data_dir)
        logs: List[str] = list(current.get("logs") or [])
        logs.append(text)
        current["logs"] = logs[-MAX_LOG_LINES:]
        return _write_unlocked(data_dir, current)


def begin_purge_shells_run(
    data_dir: Path,
    *,
    total: int = 0,
    phase: str = "starting",
) -> Dict[str, Any]:
    started = _utc_now()
    payload = default_progress()
    payload.update(
        {
            "status": "running",
            "phase": phase,
            "total": max(0, int(total)),
            "started_at": started,
            "heartbeat_at": started,
            "logs": ["Started purging catalog shells with no media on disk."],
        }
    )
    return write_purge_shells_progress(data_dir, payload)


def finish_purge_shells_run(
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
            for key in ("purged", "kept", "failed", "done", "total"):
                if key in summary:
                    current[key] = int(summary.get(key) or 0)
            if "considered" in summary and "total" not in summary:
                current["total"] = int(summary.get("considered") or current.get("total") or 0)
            logs = list(current.get("logs") or [])
            purged = int(summary.get("purged") or current.get("purged") or 0)
            kept = int(summary.get("kept") or current.get("kept") or 0)
            failed = int(summary.get("failed") or current.get("failed") or 0)
            done = int(summary.get("done") or current.get("done") or 0)
            parts = [f"purged {purged}", f"kept {kept}"]
            if failed:
                parts.append(f"failed {failed}")
            logs.append(f"Finished — {', '.join(parts)} ({done} looked at).")
            current["logs"] = logs[-MAX_LOG_LINES:]
        current["finished_at"] = _utc_now()
        return _write_unlocked(data_dir, current)


def is_purge_shells_running(data_dir: Path) -> bool:
    return str(read_purge_shells_progress(data_dir).get("status") or "") == "running"


class PurgeShellsProgressReporter:
    """Callback helper passed into purge_shell_works."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)

    def start(self, *, total: int, phase: str = "starting") -> None:
        begin_purge_shells_run(self.data_dir, total=total, phase=phase)

    def log(self, line: str) -> None:
        append_purge_shells_log(self.data_dir, line)

    def tick(
        self,
        *,
        phase: str = "",
        current_title: str = "",
        done: Optional[int] = None,
        total: Optional[int] = None,
        purged: Optional[int] = None,
        kept: Optional[int] = None,
        failed: Optional[int] = None,
        log: str = "",
    ) -> None:
        fields: Dict[str, Any] = {"heartbeat_at": _utc_now()}
        if phase:
            fields["phase"] = phase
        if current_title is not None:
            fields["current_title"] = current_title
        if done is not None:
            fields["done"] = int(done)
        if total is not None:
            fields["total"] = int(total)
        if purged is not None:
            fields["purged"] = int(purged)
        if kept is not None:
            fields["kept"] = int(kept)
        if failed is not None:
            fields["failed"] = int(failed)
        patch_purge_shells_progress(self.data_dir, **fields)
        if log:
            append_purge_shells_log(self.data_dir, log)

    def complete(self, result: Mapping[str, Any]) -> None:
        finish_purge_shells_run(self.data_dir, result=result)

    def fail(self, error: str) -> None:
        finish_purge_shells_run(self.data_dir, error=error)
