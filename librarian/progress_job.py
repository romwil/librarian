"""Shared JSON progress blob kit for long-running Librarian jobs.

``make_job`` owns defaults, start/finish copy, and the reporter callback
shape for each kind. Thin ``*_progress.py`` modules re-export that API so
existing imports keep working. This module also owns the thread-safe
read/patch/write/log/begin/finish machinery and optional heartbeat stale
detection.
"""

from __future__ import annotations

import json
import os
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
        # Atomic replace so a crash mid-write cannot tear the JSON blob
        # (readers would reset to defaults and falsely idle a running job).
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text + "\n", encoding="utf-8")
        os.replace(tmp, path)
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
        is_running: Callable[[], bool],
        begin: Callable[[], None],
        target: Callable[[], None],
        name: str,
    ) -> bool:
        """Begin + start a daemon thread when idle. Return True if kicked off.

        ``is_running`` is evaluated under ``self.lock`` together with thread
        creation so concurrent kickoffs cannot both begin. A live worker is
        always refused (including when progress briefly reads idle). A progress
        blob that still says running with no live thread (lamp restart orphan)
        is reclaimed via ``begin``.
        """
        with self.lock:
            # Evaluate progress under the same lock as thread creation so two
            # concurrent POSTs cannot both see idle and both begin.
            running = is_running()
            live = self.alive()
            # Historical gate: running and live. Also refuse when live alone so
            # a False progress read cannot short-circuit past the thread check.
            if running and live:
                return False
            if live:
                return False
            begin()
            thread = threading.Thread(target=target, name=name, daemon=True)
            self.thread["thread"] = thread
            thread.start()
            return True


def _copy_defaults(template: Mapping[str, Any]) -> Dict[str, Any]:
    copied: Dict[str, Any] = {}
    for key, value in template.items():
        if isinstance(value, list):
            copied[key] = list(value)
        elif isinstance(value, dict):
            copied[key] = dict(value)
        else:
            copied[key] = value
    return copied


def _require_keywords(label: str, kwargs: Mapping[str, Any], required: Sequence[str], allowed: Sequence[str]) -> None:
    missing = [name for name in required if name not in kwargs]
    if missing:
        raise TypeError(f"{label}() missing 1 required keyword-only argument: '{missing[0]}'")
    unknown = [name for name in kwargs if name not in allowed]
    if unknown:
        raise TypeError(f"{label}() got an unexpected keyword argument '{unknown[0]}'")


def _enrich_finish_log(current: Dict[str, Any], summary: Mapping[str, Any]) -> str:
    if "scanned" in summary:
        current["done"] = int(summary.get("scanned") or current.get("done") or 0)
    updated = int(summary.get("updated") or current.get("updated") or 0)
    scanned = int(summary.get("scanned") or current.get("done") or 0)
    return f"Finished — enriched {updated} of {scanned}."


def _ingest_finish_log(current: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
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


def _scan_finish_log(current: Dict[str, Any], summary: Mapping[str, Any]) -> str:
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


def _counted_finish_log(
    labels: Sequence[tuple[str, str]],
    *,
    always: Sequence[str],
) -> FinishLogFn:
    def _finish(current: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
        parts: List[str] = []
        for key, label in labels:
            value = int(summary.get(key) or current.get(key) or 0)
            if key in always or value:
                parts.append(f"{label} {value}")
        done = int(summary.get("done") or current.get("done") or 0)
        return f"Finished — {', '.join(parts)} ({done} looked at)."

    return _finish


class JobApi:
    """Public progress surface for one job kind. Thin modules re-export these callables."""

    def __init__(self, spec: "JobSpec") -> None:
        self.spec = spec
        self.heartbeat_stale_s = float(spec.heartbeat_stale_s)
        self.job = ProgressJob(
            filename=spec.filename,
            defaults=lambda template=spec.defaults: _copy_defaults(template),
            heartbeat=spec.heartbeat,
            heartbeat_stale_s=spec.heartbeat_stale_s,
        )
        self.reporter = self._build_reporter()

    def default_progress(self) -> Dict[str, Any]:
        return self.job.default_progress()

    def progress_path(self, data_dir: Path) -> Path:
        return self.job.progress_path(data_dir)

    def read(self, data_dir: Path) -> Dict[str, Any]:
        return self.job.read(data_dir)

    def write(self, data_dir: Path, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self.job.write(data_dir, payload)

    def patch(self, data_dir: Path, **fields: Any) -> Dict[str, Any]:
        return self.job.patch(data_dir, **fields)

    def append_log(self, data_dir: Path, line: str) -> Dict[str, Any]:
        return self.job.append_log(data_dir, line)

    def begin(self, data_dir: Path, **kwargs: Any) -> Dict[str, Any]:
        phase = kwargs.pop("phase", self.spec.begin_phase)
        total = kwargs.pop("total", 0)
        _require_keywords("begin", kwargs, self.spec.begin_required, self.spec.begin_allowed)
        return self.job.begin(
            data_dir,
            start_log=self.spec.start_log(kwargs),
            total=int(total or 0),
            phase=str(phase),
            **self.spec.begin_extra(kwargs),
        )

    def finish(
        self,
        data_dir: Path,
        *,
        result: Optional[Mapping[str, Any]] = None,
        error: str = "",
    ) -> Dict[str, Any]:
        return self.job.finish(
            data_dir,
            result=result,
            error=error,
            result_keys=self.spec.result_keys,
            considered_as_total=self.spec.considered_as_total,
            clear_fields=self.spec.clear_fields,
            finish_log=None if error else self.spec.finish_log,
        )

    def is_running(self, data_dir: Path) -> bool:
        return self.job.is_running(data_dir)

    def is_stale(
        self,
        payload: Mapping[str, Any],
        *,
        stale_after_s: Optional[float] = None,
        now: Optional[datetime] = None,
    ) -> bool:
        limit = self.heartbeat_stale_s if stale_after_s is None else stale_after_s
        return self.job.is_stale(payload, stale_after_s=limit, now=now)

    def _build_reporter(self) -> type:
        spec = self.spec
        api = self

        class Reporter:
            def __init__(self, data_dir: Path, **kwargs: Any) -> None:
                _require_keywords(
                    "__init__",
                    kwargs,
                    spec.init_required,
                    spec.init_allowed,
                )
                self.data_dir = Path(data_dir)
                self._begin_kwargs: Dict[str, Any] = {}
                for name in spec.init_allowed:
                    value = kwargs.get(name, spec.init_defaults.get(name))
                    setattr(self, name, value)
                    self._begin_kwargs[name] = value

            def start(self, *, total: int, phase: Optional[str] = None) -> None:
                chosen = spec.start_phase if phase is None else phase
                api.begin(self.data_dir, total=total, phase=chosen, **self._begin_kwargs)

            def log(self, line: str) -> None:
                api.append_log(self.data_dir, line)

            def tick(self, *, phase: str = "", log: str = "", **raw: Any) -> None:
                _require_keywords(
                    "tick",
                    raw,
                    (),
                    (*spec.text_fields, *spec.counters),
                )
                fields: Dict[str, Any] = {}
                if spec.force_heartbeat_on_tick:
                    fields["heartbeat_at"] = utc_now()
                if phase:
                    fields["phase"] = phase
                for name in spec.text_fields:
                    value = raw.get(name, "")
                    if value is not None:
                        fields[name] = value
                for name in spec.counters:
                    if name in raw and raw[name] is not None:
                        fields[name] = int(raw[name])
                if fields:
                    api.patch(self.data_dir, **fields)
                if log:
                    api.append_log(self.data_dir, log)

            def complete(self, result: Mapping[str, Any]) -> None:
                api.finish(self.data_dir, result=result)

            def fail(self, error: str) -> None:
                api.finish(self.data_dir, error=error)

        if spec.reporter_finish_alias:

            def finish(self: Reporter, result: Mapping[str, Any]) -> None:
                self.complete(result)

            Reporter.finish = finish  # type: ignore[attr-defined]

        Reporter.__name__ = spec.reporter_name
        Reporter.__qualname__ = spec.reporter_name
        Reporter.__doc__ = spec.reporter_doc
        return Reporter


class JobSpec:
    def __init__(
        self,
        *,
        filename: str,
        defaults: Mapping[str, Any],
        start_log: Callable[[Mapping[str, Any]], str],
        begin_extra: Callable[[Mapping[str, Any]], Dict[str, Any]],
        finish_log: FinishLogFn,
        result_keys: Sequence[str],
        reporter_name: str,
        reporter_doc: str,
        begin_required: Sequence[str] = (),
        begin_allowed: Sequence[str] = (),
        begin_phase: str = "starting",
        start_phase: str = "starting",
        init_required: Sequence[str] = (),
        init_allowed: Sequence[str] = (),
        init_defaults: Optional[Mapping[str, Any]] = None,
        clear_fields: Sequence[str] = ("current_title",),
        text_fields: Sequence[str] = ("current_title",),
        counters: Sequence[str] = (),
        considered_as_total: bool = False,
        heartbeat: bool = False,
        heartbeat_stale_s: float = 300.0,
        force_heartbeat_on_tick: bool = False,
        reporter_finish_alias: bool = False,
    ) -> None:
        self.filename = filename
        self.defaults = dict(defaults)
        self.start_log = start_log
        self.begin_extra = begin_extra
        self.finish_log = finish_log
        self.result_keys = tuple(result_keys)
        self.reporter_name = reporter_name
        self.reporter_doc = reporter_doc
        self.begin_required = tuple(begin_required)
        self.begin_allowed = tuple(begin_allowed)
        self.begin_phase = begin_phase
        self.start_phase = start_phase
        self.init_required = tuple(init_required)
        self.init_allowed = tuple(init_allowed)
        self.init_defaults = dict(init_defaults or {})
        self.clear_fields = tuple(clear_fields)
        self.text_fields = tuple(text_fields)
        self.counters = tuple(counters)
        self.considered_as_total = considered_as_total
        self.heartbeat = heartbeat
        self.heartbeat_stale_s = float(heartbeat_stale_s)
        self.force_heartbeat_on_tick = force_heartbeat_on_tick
        self.reporter_finish_alias = reporter_finish_alias


def _idle(**counts: int) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "status": "idle",
        "phase": "",
        "current_title": "",
        "done": 0,
        "total": 0,
        "logs": [],
        "error": "",
        "started_at": "",
        "finished_at": "",
        "result": None,
    }
    payload.update(counts)
    return payload


def _passthrough(fields: Sequence[str]) -> Callable[[Mapping[str, Any]], Dict[str, Any]]:
    def _extra(kwargs: Mapping[str, Any]) -> Dict[str, Any]:
        return {name: kwargs[name] for name in fields}

    return _extra


def _static_log(line: str) -> Callable[[Mapping[str, Any]], str]:
    def _log(_kwargs: Mapping[str, Any]) -> str:
        return line

    return _log


_JOBS: Dict[str, JobSpec] = {
    "enrich": JobSpec(
        filename="enrich_progress.json",
        defaults={
            **_idle(updated=0, skipped=0, errors=0),
            "source": "",
        },
        start_log=lambda kwargs: f"Started enrich ({kwargs['source']}).",
        begin_extra=_passthrough(("source",)),
        begin_required=("source",),
        begin_allowed=("source",),
        start_phase="scanning",
        init_required=("source",),
        init_allowed=("source",),
        finish_log=_enrich_finish_log,
        result_keys=("updated", "skipped"),
        counters=("done", "total", "updated", "skipped", "errors"),
        reporter_name="EnrichProgressReporter",
        reporter_doc="Callback helper passed into enrich_library / enrich_backlog_batch.",
    ),
    "ingest": JobSpec(
        filename="ingest_progress.json",
        defaults={
            **_idle(
                seen=0,
                shelved=0,
                review=0,
                skipped=0,
                duplicates=0,
                errors=0,
                volumes_found=0,
                files_found=0,
            ),
            "current_path": "",
            "source_path": "",
        },
        start_log=lambda kwargs: f"Started shelving from {kwargs.get('source_path') or 'disk'}.",
        begin_extra=lambda kwargs: {"source_path": str(kwargs.get("source_path") or "")},
        begin_required=("source_path",),
        begin_allowed=("source_path",),
        begin_phase="scanning",
        start_phase="scanning",
        init_allowed=("source_path",),
        init_defaults={"source_path": ""},
        finish_log=_ingest_finish_log,
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
        text_fields=("current_path", "current_title"),
        counters=(
            "done",
            "total",
            "shelved",
            "review",
            "skipped",
            "duplicates",
            "errors",
            "seen",
            "volumes_found",
            "files_found",
        ),
        reporter_name="IngestProgressReporter",
        reporter_doc="Callback helper passed into run_ingest_paths.",
    ),
    "scan": JobSpec(
        filename="scan_progress.json",
        defaults={
            **_idle(created=0, updated=0, review=0, skipped=0, errors=0),
            "current_path": "",
            "source": "",
        },
        start_log=lambda kwargs: f"Started scan ({kwargs.get('source', 'manual')}).",
        begin_extra=lambda kwargs: {"source": kwargs.get("source", "manual")},
        begin_allowed=("source",),
        start_phase="scanning",
        init_allowed=("source",),
        init_defaults={"source": "manual"},
        finish_log=_scan_finish_log,
        result_keys=("created", "updated", "review", "skipped", "errors", "done", "total"),
        clear_fields=("current_title", "current_path"),
        text_fields=("current_title", "current_path"),
        counters=("done", "total", "created", "updated", "review", "skipped", "errors"),
        reporter_name="ScanProgressReporter",
        reporter_doc="Callback helper passed into scan_library.",
    ),
    "extra_files_reprocess": JobSpec(
        filename="extra_files_reprocess_progress.json",
        defaults={
            **_idle(shelved=0, split=0, applied=0, failed=0, still_review=0),
            "heartbeat_at": "",
        },
        start_log=_static_log("Started clearing extra_files slips."),
        begin_extra=lambda _kwargs: {},
        finish_log=_counted_finish_log(
            (("shelved", "shelved"), ("split", "split"), ("applied", "applied"), ("failed", "failed")),
            always=("shelved", "split", "applied"),
        ),
        result_keys=("shelved", "split", "applied", "failed", "still_review", "done", "total"),
        counters=("done", "total", "shelved", "split", "applied", "failed", "still_review"),
        considered_as_total=True,
        heartbeat=True,
        heartbeat_stale_s=180.0,
        force_heartbeat_on_tick=True,
        reporter_name="ExtraFilesReprocessProgressReporter",
        reporter_doc="Callback helper passed into reprocess_extra_files_reviews.",
    ),
    "purge_duplicates": JobSpec(
        filename="purge_duplicates_progress.json",
        defaults={
            **_idle(purged=0, shelf_twins=0, slip_twins=0, kept=0, failed=0),
            "heartbeat_at": "",
        },
        start_log=_static_log("Started purging redundant Review slips."),
        begin_extra=lambda _kwargs: {},
        finish_log=_counted_finish_log(
            (
                ("purged", "purged"),
                ("shelf_twins", "shelf twins"),
                ("slip_twins", "slip twins"),
                ("kept", "kept"),
                ("failed", "failed"),
            ),
            always=("purged", "shelf_twins", "slip_twins", "kept"),
        ),
        result_keys=("purged", "shelf_twins", "slip_twins", "kept", "failed", "done", "total"),
        counters=("done", "total", "purged", "shelf_twins", "slip_twins", "kept", "failed"),
        considered_as_total=True,
        heartbeat=True,
        force_heartbeat_on_tick=True,
        reporter_name="PurgeDuplicatesProgressReporter",
        reporter_doc="Callback helper passed into purge_duplicate_reviews.",
    ),
    "purge_shells": JobSpec(
        filename="purge_shells_progress.json",
        defaults={
            **_idle(purged=0, kept=0, failed=0),
            "heartbeat_at": "",
        },
        start_log=_static_log("Started purging catalog shells with no media on disk."),
        begin_extra=lambda _kwargs: {},
        finish_log=_counted_finish_log(
            (("purged", "purged"), ("kept", "kept"), ("failed", "failed")),
            always=("purged", "kept"),
        ),
        result_keys=("purged", "kept", "failed", "done", "total"),
        counters=("done", "total", "purged", "kept", "failed"),
        considered_as_total=True,
        heartbeat=True,
        force_heartbeat_on_tick=True,
        reporter_name="PurgeShellsProgressReporter",
        reporter_doc="Callback helper passed into purge_shell_works.",
    ),
    "split_mixed_kinds": JobSpec(
        filename="split_mixed_kinds_progress.json",
        defaults={
            **_idle(split=0, failed=0),
            "heartbeat_at": "",
        },
        start_log=_static_log("Started splitting comic+ebook blends."),
        begin_extra=lambda _kwargs: {},
        finish_log=_counted_finish_log(
            (("split", "split"), ("failed", "failed")),
            always=("split",),
        ),
        result_keys=("split", "failed", "done", "total"),
        counters=("done", "total", "split", "failed"),
        considered_as_total=True,
        heartbeat=True,
        force_heartbeat_on_tick=True,
        reporter_finish_alias=True,
        reporter_name="SplitMixedKindsProgressReporter",
        reporter_doc="Callback helper passed into split_mixed_kind_works.",
    ),
}


def make_job(kind: str) -> JobApi:
    """Build the progress API for a known job kind.

    Kinds: enrich, ingest, scan, extra_files_reprocess, purge_duplicates,
    purge_shells, split_mixed_kinds. Each call returns a fresh API object;
    import modules should call this once and re-export the methods.
    """
    try:
        spec = _JOBS[kind]
    except KeyError as error:
        known = ", ".join(sorted(_JOBS))
        raise ValueError(f"Unknown progress job kind {kind!r}. Known: {known}") from error
    return JobApi(spec)
