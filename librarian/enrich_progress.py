"""Enrich job progress blob for UI polling (Settings + trickle)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from librarian.progress_job import ProgressJob

_JOB = ProgressJob(
    filename="enrich_progress.json",
    defaults=lambda: {
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
    },
)


def default_progress() -> Dict[str, Any]:
    return _JOB.default_progress()


def progress_path(data_dir: Path) -> Path:
    return _JOB.progress_path(data_dir)


def read_enrich_progress(data_dir: Path) -> Dict[str, Any]:
    return _JOB.read(data_dir)


def write_enrich_progress(data_dir: Path, payload: Mapping[str, Any]) -> Dict[str, Any]:
    return _JOB.write(data_dir, payload)


def patch_enrich_progress(data_dir: Path, **fields: Any) -> Dict[str, Any]:
    return _JOB.patch(data_dir, **fields)


def append_enrich_log(data_dir: Path, line: str) -> Dict[str, Any]:
    return _JOB.append_log(data_dir, line)


def begin_enrich_run(
    data_dir: Path,
    *,
    source: str,
    total: int = 0,
    phase: str = "starting",
) -> Dict[str, Any]:
    return _JOB.begin(
        data_dir,
        start_log=f"Started enrich ({source}).",
        total=total,
        phase=phase,
        source=source,
    )


def finish_enrich_run(
    data_dir: Path,
    *,
    result: Optional[Mapping[str, Any]] = None,
    error: str = "",
) -> Dict[str, Any]:
    def _finish_log(current: Dict[str, Any], summary: Mapping[str, Any]) -> str:
        if "scanned" in summary:
            current["done"] = int(summary.get("scanned") or current.get("done") or 0)
        updated = int(summary.get("updated") or current.get("updated") or 0)
        scanned = int(summary.get("scanned") or current.get("done") or 0)
        return f"Finished — enriched {updated} of {scanned}."

    return _JOB.finish(
        data_dir,
        result=result,
        error=error,
        result_keys=("updated", "skipped"),
        clear_fields=("current_title",),
        finish_log=None if error else _finish_log,
    )

def is_enrich_running(data_dir: Path) -> bool:
    return _JOB.is_running(data_dir)


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
