"""Scan job progress blob for UI polling (Settings → Scan the shelves)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from librarian.progress_job import ProgressJob

_JOB = ProgressJob(
    filename="scan_progress.json",
    defaults=lambda: {
        "status": "idle",
        "phase": "",
        "current_title": "",
        "current_path": "",
        "done": 0,
        "total": 0,
        "created": 0,
        "updated": 0,
        "review": 0,
        "skipped": 0,
        "errors": 0,
        "logs": [],
        "error": "",
        "source": "",
        "started_at": "",
        "finished_at": "",
        "result": None,
    },
)


def default_progress() -> Dict[str, Any]:
    return _JOB.default_progress()


def progress_path(data_dir: Path) -> Path:
    return _JOB.progress_path(data_dir)


def read_scan_progress(data_dir: Path) -> Dict[str, Any]:
    return _JOB.read(data_dir)


def write_scan_progress(data_dir: Path, payload: Mapping[str, Any]) -> Dict[str, Any]:
    return _JOB.write(data_dir, payload)


def patch_scan_progress(data_dir: Path, **fields: Any) -> Dict[str, Any]:
    return _JOB.patch(data_dir, **fields)


def append_scan_log(data_dir: Path, line: str) -> Dict[str, Any]:
    return _JOB.append_log(data_dir, line)


def begin_scan_run(
    data_dir: Path,
    *,
    source: str = "manual",
    total: int = 0,
    phase: str = "starting",
) -> Dict[str, Any]:
    return _JOB.begin(
        data_dir,
        start_log=f"Started scan ({source}).",
        total=total,
        phase=phase,
        source=source,
    )


def finish_scan_run(
    data_dir: Path,
    *,
    result: Optional[Mapping[str, Any]] = None,
    error: str = "",
) -> Dict[str, Any]:
    def _finish_log(current: Dict[str, Any], summary: Mapping[str, Any]) -> str:
        if "scanned" in summary:
            current["done"] = int(summary.get("scanned") or current.get("done") or 0)
        scanned = int(summary.get("scanned") or current.get("done") or 0)
        created = int(summary.get("created") or current.get("created") or 0)
        updated = int(summary.get("updated") or current.get("updated") or 0)
        review = int(summary.get("review") or current.get("review") or 0)
        errors = int(summary.get("errors") or current.get("errors") or 0)
        parts = [f"scanned {scanned}", f"{created} new", f"{updated} updated"]
        if review:
            parts.append(f"{review} need review")
        if errors:
            parts.append(f"{errors} failed")
        return f"Finished — {', '.join(parts)}."

    return _JOB.finish(
        data_dir,
        result=result,
        error=error,
        result_keys=("created", "updated", "review", "skipped", "errors", "done", "total"),
        clear_fields=("current_title", "current_path"),
        finish_log=None if error else _finish_log,
    )

def is_scan_running(data_dir: Path) -> bool:
    return _JOB.is_running(data_dir)


class ScanProgressReporter:
    """Callback helper passed into scan_library."""

    def __init__(self, data_dir: Path, *, source: str = "manual") -> None:
        self.data_dir = Path(data_dir)
        self.source = source

    def start(self, *, total: int, phase: str = "scanning") -> None:
        begin_scan_run(self.data_dir, source=self.source, total=total, phase=phase)

    def log(self, line: str) -> None:
        append_scan_log(self.data_dir, line)

    def tick(
        self,
        *,
        phase: str = "",
        current_title: str = "",
        current_path: str = "",
        done: Optional[int] = None,
        total: Optional[int] = None,
        created: Optional[int] = None,
        updated: Optional[int] = None,
        review: Optional[int] = None,
        skipped: Optional[int] = None,
        errors: Optional[int] = None,
        log: str = "",
    ) -> None:
        fields: Dict[str, Any] = {}
        if phase:
            fields["phase"] = phase
        if current_title is not None:
            fields["current_title"] = current_title
        if current_path is not None:
            fields["current_path"] = current_path
        if done is not None:
            fields["done"] = int(done)
        if total is not None:
            fields["total"] = int(total)
        if created is not None:
            fields["created"] = int(created)
        if updated is not None:
            fields["updated"] = int(updated)
        if review is not None:
            fields["review"] = int(review)
        if skipped is not None:
            fields["skipped"] = int(skipped)
        if errors is not None:
            fields["errors"] = int(errors)
        if fields:
            patch_scan_progress(self.data_dir, **fields)
        if log:
            append_scan_log(self.data_dir, log)

    def complete(self, result: Mapping[str, Any]) -> None:
        finish_scan_run(self.data_dir, result=result)

    def fail(self, error: str) -> None:
        finish_scan_run(self.data_dir, error=error)
