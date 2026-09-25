"""Purge-duplicate Review slips job progress blob for UI polling."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from librarian.progress_job import ProgressJob, heartbeat_age_seconds, parse_utc_timestamp, utc_now

HEARTBEAT_STALE_S = 300.0

_JOB = ProgressJob(
    filename="purge_duplicates_progress.json",
    defaults=lambda: {
        "status": "idle",
        "phase": "",
        "current_title": "",
        "done": 0,
        "total": 0,
        "purged": 0,
        "shelf_twins": 0,
        "slip_twins": 0,
        "kept": 0,
        "failed": 0,
        "logs": [],
        "error": "",
        "started_at": "",
        "heartbeat_at": "",
        "finished_at": "",
        "result": None,
    },
    heartbeat=True,
    heartbeat_stale_s=HEARTBEAT_STALE_S,
)


def default_progress() -> Dict[str, Any]:
    return _JOB.default_progress()


def progress_path(data_dir: Path) -> Path:
    return _JOB.progress_path(data_dir)


def read_purge_duplicates_progress(data_dir: Path) -> Dict[str, Any]:
    return _JOB.read(data_dir)


def write_purge_duplicates_progress(data_dir: Path, payload: Mapping[str, Any]) -> Dict[str, Any]:
    return _JOB.write(data_dir, payload)


def patch_purge_duplicates_progress(data_dir: Path, **fields: Any) -> Dict[str, Any]:
    return _JOB.patch(data_dir, **fields)


def append_purge_duplicates_log(data_dir: Path, line: str) -> Dict[str, Any]:
    return _JOB.append_log(data_dir, line)


def begin_purge_duplicates_run(
    data_dir: Path,
    *,
    total: int = 0,
    phase: str = "starting",
) -> Dict[str, Any]:
    return _JOB.begin(
        data_dir,
        start_log="Started purging redundant Review slips.",
        total=total,
        phase=phase,
    )


def finish_purge_duplicates_run(
    data_dir: Path,
    *,
    result: Optional[Mapping[str, Any]] = None,
    error: str = "",
) -> Dict[str, Any]:
    def _finish_log(current: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
        purged = int(summary.get("purged") or current.get("purged") or 0)
        shelf = int(summary.get("shelf_twins") or current.get("shelf_twins") or 0)
        slip = int(summary.get("slip_twins") or current.get("slip_twins") or 0)
        kept = int(summary.get("kept") or current.get("kept") or 0)
        failed = int(summary.get("failed") or current.get("failed") or 0)
        done = int(summary.get("done") or current.get("done") or 0)
        parts = [f"purged {purged}", f"shelf twins {shelf}", f"slip twins {slip}", f"kept {kept}"]
        if failed:
            parts.append(f"failed {failed}")
        return f"Finished — {', '.join(parts)} ({done} looked at)."

    return _JOB.finish(
        data_dir,
        result=result,
        error=error,
        result_keys=("purged", "shelf_twins", "slip_twins", "kept", "failed", "done", "total"),
        considered_as_total=True,
        finish_log=None if error else _finish_log,
    )


def is_purge_duplicates_running(data_dir: Path) -> bool:
    return _JOB.is_running(data_dir)


def is_purge_duplicates_stale(
    payload: Mapping[str, Any],
    *,
    stale_after_s: float = HEARTBEAT_STALE_S,
    now: Optional[datetime] = None,
) -> bool:
    return _JOB.is_stale(payload, stale_after_s=stale_after_s, now=now)


class PurgeDuplicatesProgressReporter:
    """Callback helper passed into purge_duplicate_reviews."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)

    def start(self, *, total: int, phase: str = "starting") -> None:
        begin_purge_duplicates_run(self.data_dir, total=total, phase=phase)

    def log(self, line: str) -> None:
        append_purge_duplicates_log(self.data_dir, line)

    def tick(
        self,
        *,
        phase: str = "",
        current_title: str = "",
        done: Optional[int] = None,
        total: Optional[int] = None,
        purged: Optional[int] = None,
        shelf_twins: Optional[int] = None,
        slip_twins: Optional[int] = None,
        kept: Optional[int] = None,
        failed: Optional[int] = None,
        log: str = "",
    ) -> None:
        fields: Dict[str, Any] = {"heartbeat_at": utc_now()}
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
        if shelf_twins is not None:
            fields["shelf_twins"] = int(shelf_twins)
        if slip_twins is not None:
            fields["slip_twins"] = int(slip_twins)
        if kept is not None:
            fields["kept"] = int(kept)
        if failed is not None:
            fields["failed"] = int(failed)
        patch_purge_duplicates_progress(self.data_dir, **fields)
        if log:
            append_purge_duplicates_log(self.data_dir, log)

    def complete(self, result: Mapping[str, Any]) -> None:
        finish_purge_duplicates_run(self.data_dir, result=result)

    def fail(self, error: str) -> None:
        finish_purge_duplicates_run(self.data_dir, error=error)


__all__ = [
    "HEARTBEAT_STALE_S",
    "PurgeDuplicatesProgressReporter",
    "append_purge_duplicates_log",
    "begin_purge_duplicates_run",
    "default_progress",
    "finish_purge_duplicates_run",
    "heartbeat_age_seconds",
    "is_purge_duplicates_running",
    "is_purge_duplicates_stale",
    "parse_utc_timestamp",
    "patch_purge_duplicates_progress",
    "progress_path",
    "read_purge_duplicates_progress",
    "write_purge_duplicates_progress",
]
