"""Shared JSON progress blob kit for long-running Librarian jobs.

Each job kind keeps a thin ``*_progress.py`` wrapper that owns defaults,
start/finish copy, and the reporter callback shape. This module owns the
thread-safe read/patch/write/log/begin/finish machinery and optional
heartbeat stale detection.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

MAX_LOG_LINES = 40

DefaultsFactory = Callable[[], Dict[str, Any]]
FinishLogFn = Callable[[Mapping[str, Any], Mapping[str, Any]], str]


def utc_now() -> str:
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


def heartbeat_age_seconds(
    payload: Mapping[str, Any],
    *,
    now: Optional[datetime] = None,
) -> Optional[float]:
    """Seconds since last heartbeat (or started_at). None when timestamps missing."""
    stamp = parse_utc_timestamp(payload.get("heartbeat_at")) or parse_utc_timestamp(
        payload.get("started_at")
    )
    if stamp is None:
        return None
    current = now or datetime.now(timezone.utc)
    return max(0.0, (current - stamp).total_seconds())


def is_stale_running(
    payload: Mapping[str, Any],
    *,
    stale_after_s: float,
    now: Optional[datetime] = None,
) -> bool:
    if str(payload.get("status") or "") != "running":
        return False
    age = heartbeat_age_seconds(payload, now=now)
    if age is None:
        return False
    return age >= max(1.0, float(stale_after_s))


class ProgressJob:
    """Thread-safe JSON progress file for one job kind."""

    def __init__(
        self,
        *,
        filename: str,
        defaults: DefaultsFactory,
        max_log_lines: int = MAX_LOG_LINES,
        heartbeat: bool = False,
        heartbeat_stale_s: float = 300.0,
    ) -> None:
        self.filename = str(filename)
        self._defaults = defaults
        self.max_log_lines = max(1, int(max_log_lines))
        self.heartbeat = bool(heartbeat)
        self.heartbeat_stale_s = float(heartbeat_stale_s)
        self._lock = threading.Lock()

    def default_progress(self) -> Dict[str, Any]:
        return dict(self._defaults())

    def progress_path(self, data_dir: Path) -> Path:
        return Path(data_dir) / self.filename

    def _trim_logs(self, logs: Any) -> List[str]:
        if not isinstance(logs, list):
            return []
        return [str(line) for line in logs][-self.max_log_lines :]

    def _read_unlocked(self, data_dir: Path) -> Dict[str, Any]:
        path = self.progress_path(data_dir)
        if not path.is_file():
            return self.default_progress()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self.default_progress()
        if not isinstance(raw, dict):
            return self.default_progress()
        base = self.default_progress()
        base.update(raw)
        base["logs"] = self._trim_logs(base.get("logs"))
        return base

    def _write_unlocked(self, data_dir: Path, payload: Mapping[str, Any]) -> Dict[str, Any]:
        path = self.progress_path(data_dir)
        merged = self.default_progress()
        merged.update(dict(payload))
        merged["logs"] = self._trim_logs(merged.get("logs"))
        if (
            self.heartbeat
            and str(merged.get("status") or "") == "running"
            and not str(merged.get("heartbeat_at") or "").strip()
        ):
            merged["heartbeat_at"] = utc_now()
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(merged, indent=2, sort_keys=True)
        path.write_text(text + "\n", encoding="utf-8")
        return merged

    def read(self, data_dir: Path) -> Dict[str, Any]:
        with self._lock:
            return self._read_unlocked(data_dir)

    def write(self, data_dir: Path, payload: Mapping[str, Any]) -> Dict[str, Any]:
        with self._lock:
            return self._write_unlocked(data_dir, payload)

    def patch(self, data_dir: Path, **fields: Any) -> Dict[str, Any]:
        with self._lock:
            current = self._read_unlocked(data_dir)
            current.update(fields)
            if (
                self.heartbeat
                and str(current.get("status") or "") == "running"
                and "heartbeat_at" not in fields
            ):
                current["heartbeat_at"] = utc_now()
            return self._write_unlocked(data_dir, current)

    def append_log(self, data_dir: Path, line: str) -> Dict[str, Any]:
        text = str(line or "").strip()
        if not text:
            return self.read(data_dir)
        with self._lock:
            current = self._read_unlocked(data_dir)
            logs: List[str] = list(current.get("logs") or [])
            logs.append(text)
            current["logs"] = logs[-self.max_log_lines :]
            return self._write_unlocked(data_dir, current)

    def begin(
        self,
        data_dir: Path,
        *,
        start_log: str,
        total: int = 0,
        phase: str = "starting",
        **extra: Any,
    ) -> Dict[str, Any]:
        started = utc_now()
        payload = self.default_progress()
        payload.update(
            {
                "status": "running",
                "phase": phase,
                "total": max(0, int(total)),
                "started_at": started,
                "logs": [str(start_log)],
            }
        )
        if self.heartbeat:
            payload["heartbeat_at"] = started
        payload.update(extra)
        return self.write(data_dir, payload)

    def finish(
        self,
        data_dir: Path,
        *,
        result: Optional[Mapping[str, Any]] = None,
        error: str = "",
        result_keys: Sequence[str] = (),
        considered_as_total: bool = False,
        clear_fields: Sequence[str] = ("current_title",),
        finish_log: Optional[FinishLogFn] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            current = self._read_unlocked(data_dir)
            if error:
                current["status"] = "failed"
                current["phase"] = "failed"
                current["error"] = str(error)
                logs = list(current.get("logs") or [])
                logs.append(f"Failed: {error}")
                current["logs"] = logs[-self.max_log_lines :]
            else:
                current["status"] = "completed"
                current["phase"] = "done"
                current["error"] = ""
                for field in clear_fields:
                    current[field] = ""
                summary = dict(result or {})
                current["result"] = summary
                for key in result_keys:
                    if key in summary:
                        current[key] = int(summary.get(key) or 0)
                if considered_as_total and "considered" in summary and "total" not in summary:
                    current["total"] = int(summary.get("considered") or current.get("total") or 0)
                if finish_log is not None:
                    logs = list(current.get("logs") or [])
                    line = finish_log(current, summary)
                    if line:
                        logs.append(str(line))
                    current["logs"] = logs[-self.max_log_lines :]
            current["finished_at"] = utc_now()
            return self._write_unlocked(data_dir, current)

    def is_running(self, data_dir: Path) -> bool:
        return str(self.read(data_dir).get("status") or "") == "running"

    def is_stale(
        self,
        payload: Mapping[str, Any],
        *,
        stale_after_s: Optional[float] = None,
        now: Optional[datetime] = None,
    ) -> bool:
        if not self.heartbeat:
            return False
        return is_stale_running(
            payload,
            stale_after_s=self.heartbeat_stale_s if stale_after_s is None else stale_after_s,
            now=now,
        )


class BackgroundJobSlot:
    """One lock + daemon thread holder for create_app kickoff endpoints."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.thread: Dict[str, Optional[threading.Thread]] = {"thread": None}

    def alive(self) -> bool:
        live = self.thread.get("thread")
        return live is not None and live.is_alive()

    def start_if_idle(
        self,
        *,
        already_running: bool,
        begin: Callable[[], None],
        target: Callable[[], None],
        name: str,
    ) -> bool:
        """Begin + start a daemon thread when idle. Return True if kicked off."""
        with self.lock:
            if already_running and self.alive():
                return False
            begin()
            thread = threading.Thread(target=target, name=name, daemon=True)
            self.thread["thread"] = thread
            thread.start()
            return True
