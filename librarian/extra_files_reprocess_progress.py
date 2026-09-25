"""Clear extra-files slips job progress blob for Review UI polling."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from librarian.progress_job import (
    ProgressJob,
    heartbeat_age_seconds,
    parse_utc_timestamp,
    utc_now,
)

HEARTBEAT_STALE_S = 180.0

_JOB = ProgressJob(
    filename="extra_files_reprocess_progress.json",
    defaults=lambda: {
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


def read_extra_files_reprocess_progress(data_dir: Path) -> Dict[str, Any]:
    return _JOB.read(data_dir)


def write_extra_files_reprocess_progress(data_dir: Path, payload: Mapping[str, Any]) -> Dict[str, Any]:
    return _JOB.write(data_dir, payload)


def patch_extra_files_reprocess_progress(data_dir: Path, **fields: Any) -> Dict[str, Any]:
    return _JOB.patch(data_dir, **fields)


def append_extra_files_reprocess_log(data_dir: Path, line: str) -> Dict[str, Any]:
    return _JOB.append_log(data_dir, line)


def begin_extra_files_reprocess_run(
    data_dir: Path,
    *,
    total: int = 0,
    phase: str = "starting",
) -> Dict[str, Any]:
    return _JOB.begin(
        data_dir,
        start_log="Started clearing extra_files slips.",
        total=total,
        phase=phase,
    )


def finish_extra_files_reprocess_run(
    data_dir: Path,
    *,
    result: Optional[Mapping[str, Any]] = None,
    error: str = "",
) -> Dict[str, Any]:
    def _finish_log(current: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
        shelved = int(summary.get("shelved") or current.get("shelved") or 0)
        split = int(summary.get("split") or current.get("split") or 0)
        applied = int(summary.get("applied") or current.get("applied") or 0)
        failed = int(summary.get("failed") or current.get("failed") or 0)
        done = int(summary.get("done") or current.get("done") or 0)
        parts = [f"shelved {shelved}", f"split {split}", f"applied {applied}"]
        if failed:
            parts.append(f"failed {failed}")
        return f"Finished — {', '.join(parts)} ({done} looked at)."

    return _JOB.finish(
        data_dir,
        result=result,
        error=error,
        result_keys=("shelved", "split", "applied", "failed", "still_review", "done", "total"),
        considered_as_total=True,
        finish_log=None if error else _finish_log,
    )


def is_extra_files_reprocess_running(data_dir: Path) -> bool:
    return _JOB.is_running(data_dir)


def is_extra_files_reprocess_stale(
    payload: Mapping[str, Any],
    *,
    stale_after_s: float = HEARTBEAT_STALE_S,
    now: Optional[datetime] = None,
) -> bool:
    return _JOB.is_stale(payload, stale_after_s=stale_after_s, now=now)


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
        fields: Dict[str, Any] = {"heartbeat_at": utc_now()}
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
        patch_extra_files_reprocess_progress(self.data_dir, **fields)
        if log:
            append_extra_files_reprocess_log(self.data_dir, log)

    def complete(self, result: Mapping[str, Any]) -> None:
        finish_extra_files_reprocess_run(self.data_dir, result=result)

    def fail(self, error: str) -> None:
        finish_extra_files_reprocess_run(self.data_dir, error=error)


# Re-export helpers used by tests / status endpoints.
__all__ = [
    "HEARTBEAT_STALE_S",
    "ExtraFilesReprocessProgressReporter",
    "append_extra_files_reprocess_log",
    "begin_extra_files_reprocess_run",
    "default_progress",
    "finish_extra_files_reprocess_run",
    "heartbeat_age_seconds",
    "is_extra_files_reprocess_running",
    "is_extra_files_reprocess_stale",
    "parse_utc_timestamp",
    "patch_extra_files_reprocess_progress",
    "progress_path",
    "read_extra_files_reprocess_progress",
    "write_extra_files_reprocess_progress",
]
