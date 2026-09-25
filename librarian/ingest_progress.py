"""Ingest job progress blob for UI polling (Add to the shelves)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from librarian.progress_job import ProgressJob

_JOB = ProgressJob(
    filename="ingest_progress.json",
    defaults=lambda: {
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
    },
)


def default_progress() -> Dict[str, Any]:
    return _JOB.default_progress()


def progress_path(data_dir: Path) -> Path:
    return _JOB.progress_path(data_dir)


def read_ingest_progress(data_dir: Path) -> Dict[str, Any]:
    return _JOB.read(data_dir)


def write_ingest_progress(data_dir: Path, payload: Mapping[str, Any]) -> Dict[str, Any]:
    return _JOB.write(data_dir, payload)


def patch_ingest_progress(data_dir: Path, **fields: Any) -> Dict[str, Any]:
    return _JOB.patch(data_dir, **fields)


def append_ingest_log(data_dir: Path, line: str) -> Dict[str, Any]:
    return _JOB.append_log(data_dir, line)


def begin_ingest_run(
    data_dir: Path,
    *,
    source_path: str,
    total: int = 0,
    phase: str = "scanning",
) -> Dict[str, Any]:
    return _JOB.begin(
        data_dir,
        start_log=f"Started shelving from {source_path or 'disk'}.",
        total=total,
        phase=phase,
        source_path=str(source_path or ""),
    )


def finish_ingest_run(
    data_dir: Path,
    *,
    result: Optional[Mapping[str, Any]] = None,
    error: str = "",
) -> Dict[str, Any]:
    def _finish_log(current: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
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
        return f"Finished — {', '.join(parts)}."

    return _JOB.finish(
        data_dir,
        result=result,
        error=error,
        result_keys=(
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
        ),
        clear_fields=("current_path", "current_title"),
        finish_log=None if error else _finish_log,
    )


def is_ingest_running(data_dir: Path) -> bool:
    return _JOB.is_running(data_dir)


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
