"""Background poller.

SABnzbd stays on the short cadence (``LIBRARIAN_POLL_SECONDS``, default 30s,
or the ``interval`` passed to ``JobPoller``). Enrich, RSS, the audiobook
sweep, wanted search, and New & noted each wait on a longer interval so a
slow enrich cannot hold the next download poll. Watch-folder ingest stays on
the short thread, after the download poll. One step's failure is recorded on
that step and the others still run.

Wanted search is one hourly pass over every due row. It walks on its own thread
so a long pass does not hold the other steps, and a second pass never starts
while one is still walking. Rows the audiobook sweep just created are searched
right away. Nightly backup stays on this housekeeping thread.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional

from librarian.config import Settings
from librarian.db import Database
from librarian.jobs import poll_active_jobs
from librarian.progress_job import utc_now
from librarian.sabnzbd import SABError

logger = logging.getLogger(__name__)

_MIN_POLL_SECONDS = 5.0
_ENRICH_BATCH = 3
_ERROR_LIMIT = 500

DEFAULT_SAB_POLL_SECONDS = 30.0
# Matches the old enrich trickle: every 10 ticks of the 30s poll.
DEFAULT_ENRICH_POLL_SECONDS = 300.0
DEFAULT_RSS_POLL_SECONDS = 300.0
DEFAULT_SWEEP_POLL_SECONDS = 900.0
DEFAULT_WANTED_POLL_SECONDS = 3600.0
DEFAULT_OWNED_POLL_SECONDS = 300.0
DEFAULT_NOTED_POLL_SECONDS = 21600.0
# Hourly look; a snapshot is only taken when today's is missing (nightly in effect).
DEFAULT_BACKUP_POLL_SECONDS = 3600.0

SAB_POLL_ENV = "LIBRARIAN_POLL_SECONDS"
ENRICH_POLL_ENV = "LIBRARIAN_ENRICH_POLL_SECONDS"
RSS_POLL_ENV = "LIBRARIAN_RSS_POLL_SECONDS"
SWEEP_POLL_ENV = "LIBRARIAN_SWEEP_POLL_SECONDS"
WANTED_POLL_ENV = "LIBRARIAN_WANTED_POLL_SECONDS"
OWNED_POLL_ENV = "LIBRARIAN_OWNED_POLL_SECONDS"
NOTED_POLL_ENV = "LIBRARIAN_NOTED_POLL_SECONDS"
BACKUP_POLL_ENV = "LIBRARIAN_BACKUP_POLL_SECONDS"

# Housekeeping shares one thread. Enrich is last so a long trickle does not
# delay RSS, the sweep, wanted search, or New & noted that were already due.
_BACKGROUND_STEPS = ("rss", "repair", "abs", "sweep", "owned", "wanted", "noted", "backup", "enrich")
_STATUS_ORDER = (
    "sab",
    "enrich",
    "rss",
    "sweep",
    "wanted",
    "noted",
    "backup",
    "watch",
    "repair",
    "abs",
    "owned",
)

_FAILURE_LOG = {
    "watch": "Watch poller tick failed",
    "rss": "RSS poller tick failed",
    "repair": "Review soft-repair tick failed",
    "abs": "ABS match tick failed",
    "sweep": "Wanted sweep tick failed",
    "owned": "Owned slip sweep tick failed",
    "wanted": "Wanted search tick failed",
    "noted": "New & noted refresh failed",
    "backup": "Nightly backup failed",
    "enrich": "Enrich backlog tick failed",
    "sab": "SAB poller tick failed",
}


def poll_interval_seconds() -> float:
    return _env_seconds(SAB_POLL_ENV, DEFAULT_SAB_POLL_SECONDS)


def _env_seconds(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(_MIN_POLL_SECONDS, float(raw))
    except ValueError:
        return default


def _error_text(error: BaseException) -> str:
    message = str(error).strip() or type(error).__name__
    if len(message) > _ERROR_LIMIT:
        return message[:_ERROR_LIMIT]
    return message


@dataclass(frozen=True)
class _Step:
    id: str
    label: str
    interval: float
    counted: bool


def _build_steps(short: float) -> tuple[_Step, ...]:
    """Tick order. Downloads stay last so a caller of ``tick`` still shelves first."""
    return (
        _Step("watch", "Watch folder", short, True),
        _Step("rss", "RSS", _env_seconds(RSS_POLL_ENV, DEFAULT_RSS_POLL_SECONDS), True),
        _Step("repair", "Holds repair", short, True),
        _Step("abs", "Audiobookshelf", short, False),
        _Step(
            "sweep",
            "Audiobook sweep",
            _env_seconds(SWEEP_POLL_ENV, DEFAULT_SWEEP_POLL_SECONDS),
            False,
        ),
        _Step(
            "owned",
            "Owned slips",
            _env_seconds(OWNED_POLL_ENV, DEFAULT_OWNED_POLL_SECONDS),
            False,
        ),
        _Step(
            "wanted",
            "Wanted search",
            _env_seconds(WANTED_POLL_ENV, DEFAULT_WANTED_POLL_SECONDS),
            True,
        ),
        _Step(
            "noted",
            "New & noted",
            _env_seconds(NOTED_POLL_ENV, DEFAULT_NOTED_POLL_SECONDS),
            False,
        ),
        _Step(
            "backup",
            "Nightly backup",
            _env_seconds(BACKUP_POLL_ENV, DEFAULT_BACKUP_POLL_SECONDS),
            False,
        ),
        _Step(
            "enrich",
            "Enrich",
            _env_seconds(ENRICH_POLL_ENV, DEFAULT_ENRICH_POLL_SECONDS),
            True,
        ),
        _Step("sab", "Downloads", short, True),
    )


class JobPoller:
    def __init__(
        self,
        db: Database,
        settings_fn: Callable[[], Settings],
        *,
        interval: Optional[float] = None,
        sab=None,
        data_dir: Optional[Path] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.db = db
        self.settings_fn = settings_fn
        self.interval = interval if interval is not None else poll_interval_seconds()
        self.sab = sab
        self.data_dir = (
            Path(data_dir) if data_dir is not None else Path(os.environ.get("DATA_DIR", "/config"))
        )
        self._clock = clock or time.monotonic
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._sab_thread: Optional[threading.Thread] = None
        self._steps_thread: Optional[threading.Thread] = None
        self._wanted_thread: Optional[threading.Thread] = None
        self._queued_thread: Optional[threading.Thread] = None
        self._started = False
        self._steps = _build_steps(self.interval)
        self._by_id = {step.id: step for step in self._steps}
        self._runners: Dict[str, Callable[[Settings], int]] = {
            "watch": self._run_watch,
            "rss": self._run_rss,
            "repair": self._run_repair,
            "abs": self._run_abs,
            "sweep": self._run_sweep,
            "owned": self._run_owned,
            "wanted": self._run_wanted,
            "noted": self._run_noted,
            "backup": self._run_backup,
            "enrich": self._run_enrich,
            "sab": self._run_sab,
        }
        now = self._clock()
        # Enrich waits out its first interval so boot and a single tick() do not
        # trickle. Every other step is due immediately; the download thread still
        # sleeps one short interval before its first poll.
        self._next_due = {
            step.id: now + step.interval if step.id == "enrich" else now for step in self._steps
        }
        self._last_run: Dict[str, Optional[str]] = {step.id: None for step in self._steps}
        self._last_error: Dict[str, Optional[str]] = {step.id: None for step in self._steps}

    @property
    def is_running(self) -> bool:
        sab = self._sab_thread
        steps = self._steps_thread
        return bool(
            (sab is not None and sab.is_alive()) or (steps is not None and steps.is_alive())
        )

    def step_status(self) -> Dict[str, object]:
        """Last run and last error for Maintain. One entry per scheduled step."""
        try:
            settings = self.settings_fn()
        except Exception:
            settings = None
        with self._lock:
            steps = []
            for step_id in _STATUS_ORDER:
                step = self._by_id[step_id]
                enabled = True if settings is None else self._step_enabled(step.id, settings)
                entry = {
                    "id": step.id,
                    "label": step.label,
                    "interval_seconds": step.interval,
                    "last_run": self._last_run[step.id],
                    "last_error": self._last_error[step.id],
                    "state": "ok" if enabled else "off",
                }
                if not enabled:
                    entry["off_reason"] = self._off_reason(step.id)
                steps.append(entry)
        return {"steps": steps}

    def _step_enabled(self, name: str, settings: Settings) -> bool:
        """Skip unconfigured work. Owned only runs when a file-less slip exists."""
        if name == "watch":
            return bool(getattr(settings, "watch_enabled", False)) and bool(
                str(getattr(settings, "watch_root", "") or "").strip()
            )
        if name == "abs":
            return bool(str(getattr(settings, "audiobookshelf_url", "") or "").strip()) and bool(
                str(getattr(settings, "audiobookshelf_api_token", "") or "").strip()
            )
        if name == "sab":
            return bool(str(getattr(settings, "sabnzbd_api_key", "") or "").strip())
        if name == "wanted":
            from librarian.indexers.hosts import enabled_hosts

            return bool(enabled_hosts(settings))
        if name == "owned":
            return bool(self.db.has_fileless_slips())
        return True

    def _off_reason(self, name: str) -> str:
        if name == "owned":
            return "Off: nothing to do"
        return "Off: not configured"

    def _defer(self, name: str) -> None:
        """Advance next_due without stamping last_run (disabled / idle steps)."""
        with self._lock:
            self._next_due[name] = self._clock() + self._by_id[name].interval

    def tick(self) -> int:
        """Run every step that is due, in shelf order. Failures stay on that step."""
        count = 0
        for step in self._steps:
            if not self._due(step.id):
                continue
            count += self._run_step(step.id)
        return count

    def _due(self, name: str) -> bool:
        with self._lock:
            return self._clock() >= self._next_due[name]

    def _mark(self, name: str, *, error: Optional[str]) -> None:
        with self._lock:
            self._next_due[name] = self._clock() + self._by_id[name].interval
            self._last_run[name] = utc_now()
            self._last_error[name] = error

    def _delay_until_next(self, names: tuple[str, ...]) -> float:
        moment = self._clock()
        with self._lock:
            remaining = [self._next_due[name] - moment for name in names]
        if not remaining:
            return self.interval
        return max(0.0, min(remaining))

    def _run_step(self, name: str) -> int:
        spec = self._by_id[name]
        settings = self.settings_fn()
        if not self._step_enabled(name, settings):
            self._defer(name)
            return 0
        try:
            produced = int(self._runners[name](settings) or 0)
        except SABError as error:
            self._mark(name, error=_error_text(error))
            if name == "sab":
                logger.info("SAB poll skipped: %s", error)
            else:
                logger.exception(_FAILURE_LOG[name])
            return 0
        except Exception as error:
            self._mark(name, error=_error_text(error))
            logger.exception(_FAILURE_LOG[name])
            return 0
        self._mark(name, error=None)
        if not spec.counted:
            return 0
        return produced

    def _run_watch(self, settings: Settings) -> int:
        from librarian.ingest import poll_watch_folder

        return int(poll_watch_folder(self.db, settings) or 0)

    def _run_rss(self, settings: Settings) -> int:
        from librarian.rss import poll_rss_feeds

        return int(poll_rss_feeds(self.db, settings) or 0)

    def _run_repair(self, settings: Settings) -> int:
        from librarian.organize import soft_repair_review_reasons

        return int(soft_repair_review_reasons(self.db, settings) or 0)

    def _run_abs(self, settings: Settings) -> int:
        from librarian.audiobookshelf import match_audiobooks

        match_audiobooks(self.db, settings)
        return 0

    def _run_sweep(self, settings: Settings) -> int:
        from librarian.wanted_sweep import sweep_wanted_audiobooks

        created: list[str] = []
        sweep_wanted_audiobooks(self.db, created_ids=created)
        if created:
            self._search_queued(settings, created)
        return 0

    def _search_queued(self, settings: Settings, ids: list[str]) -> None:
        """Search just-created rows now. Off the steps thread once the poller runs."""
        from librarian.wanted_search import search_queued_wanted

        def _search() -> None:
            try:
                search_queued_wanted(self.db, settings, ids)
            except Exception:
                logger.exception("Wanted search for new rows failed")

        if not self._started:
            _search()
            return
        thread = threading.Thread(target=_search, name="librarian-wanted-new", daemon=True)
        self._queued_thread = thread
        thread.start()

    def _start_wanted_pass(self) -> None:
        """Start the hourly pass on its own thread unless one is still walking."""
        try:
            settings = self.settings_fn()
        except Exception:
            settings = None
        if settings is None or not self._step_enabled("wanted", settings):
            self._defer("wanted")
            return
        with self._lock:
            running = self._wanted_thread
            if running is not None and running.is_alive():
                return
            self._next_due["wanted"] = self._clock() + self._by_id["wanted"].interval
            thread = threading.Thread(
                target=self._run_step,
                args=("wanted",),
                name="librarian-wanted-pass",
                daemon=True,
            )
            self._wanted_thread = thread
        thread.start()

    def _run_owned(self, _settings: Settings) -> int:
        from librarian.owned_slip import sweep_owned_slips

        sweep_owned_slips(self.db)
        return 0

    def _run_wanted(self, settings: Settings) -> int:
        from librarian.wanted_search import poll_wanted

        return int(poll_wanted(self.db, settings, should_stop=self._stop.is_set) or 0)

    def _run_noted(self, settings: Settings) -> int:
        from librarian.noted import run_noted_refresh

        # Current lists only. Dated NYT lists already in the cache stay put.
        run_noted_refresh(self.db, settings, data_dir=self.data_dir)
        return 0

    def _run_backup(self, _settings: Settings) -> int:
        from librarian.backup import backup_dir_for, backup_due, run_backup

        target = backup_dir_for(self.data_dir)
        if backup_due(target):
            run_backup(self.db.path, target)
        return 0

    def _run_enrich(self, settings: Settings) -> int:
        from librarian.enrich import enrich_corrections_backlog_batch
        from librarian.enrich_progress import EnrichProgressReporter, read_enrich_progress

        current = read_enrich_progress(self.data_dir)
        if current.get("status") == "running" and current.get("source") == "manual":
            logger.debug("Enrich trickle skipped — manual enrich is running")
            return 0
        reporter = EnrichProgressReporter(self.data_dir, source="trickle")
        # Identifiers, strong-match corrections, ISBN backfill, Audnexus ASIN/narrator,
        # and magazine masthead/issue/cover corrections all run on this one backlog.
        result = enrich_corrections_backlog_batch(
            self.db,
            settings,
            data_dir=self.data_dir,
            limit=_ENRICH_BATCH,
            pause_seconds=0.5,
            progress=reporter,
        )
        return int(result.get("enriched") or 0)

    def _run_sab(self, settings: Settings) -> int:
        return int(poll_active_jobs(self.db, settings, sab=self.sab) or 0)

    def _loop(self) -> None:
        """Short cadence: downloads, then the watch folder. Never enrich."""
        while not self._stop.wait(self.interval):
            try:
                if self._due("sab"):
                    self._run_step("sab")
                if self._due("watch"):
                    self._run_step("watch")
            except Exception:
                logger.exception("SAB poller tick failed")

    def _steps_loop(self) -> None:
        """Longer cadences. A slow enrich stays on this thread."""
        while not self._stop.is_set():
            try:
                for name in _BACKGROUND_STEPS:
                    if self._stop.is_set():
                        return
                    if not self._due(name):
                        continue
                    if name == "wanted":
                        self._start_wanted_pass()
                    else:
                        self._run_step(name)
            except Exception:
                logger.exception("Poller housekeeping tick failed")
            delay = self._delay_until_next(_BACKGROUND_STEPS)
            if delay <= 0:
                delay = self.interval if self.interval > 0 else _MIN_POLL_SECONDS
            if self._stop.wait(delay):
                return

    def start(self) -> None:
        if os.environ.get("LIBRARIAN_SKIP_APP_BOOT") == "1":
            return
        if os.environ.get("LIBRARIAN_DISABLE_POLLER") == "1":
            return
        with self._lock:
            if self._started:
                return
            self._started = True
            self._stop.clear()
        self._sab_thread = threading.Thread(
            target=self._loop, name="librarian-sab-poller", daemon=True
        )
        self._steps_thread = threading.Thread(
            target=self._steps_loop, name="librarian-poller-steps", daemon=True
        )
        self._sab_thread.start()
        self._steps_thread.start()

    def stop(self) -> None:
        self._stop.set()
        for thread in (
            self._sab_thread,
            self._steps_thread,
            self._wanted_thread,
            self._queued_thread,
        ):
            if thread is not None:
                thread.join(timeout=2)
        self._sab_thread = None
        self._steps_thread = None
        self._wanted_thread = None
        self._queued_thread = None
        with self._lock:
            self._started = False
