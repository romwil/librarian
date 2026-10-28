"""Background poller.

SABnzbd stays on the short cadence (``LIBRARIAN_POLL_SECONDS``, default 30s,
or the ``interval`` passed to ``JobPoller``). Enrich, RSS, the audiobook
sweep, and wanted search each wait on a longer interval so a slow enrich
cannot hold the next download poll. Watch-folder ingest stays on the short
thread, after the download poll. One step's failure is recorded on that
step and the others still run.
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
DEFAULT_WANTED_POLL_SECONDS = 120.0

SAB_POLL_ENV = "LIBRARIAN_POLL_SECONDS"
ENRICH_POLL_ENV = "LIBRARIAN_ENRICH_POLL_SECONDS"
RSS_POLL_ENV = "LIBRARIAN_RSS_POLL_SECONDS"
SWEEP_POLL_ENV = "LIBRARIAN_SWEEP_POLL_SECONDS"
WANTED_POLL_ENV = "LIBRARIAN_WANTED_POLL_SECONDS"

# Housekeeping shares one thread. Enrich is last so a long trickle does not
# delay RSS, the sweep, or wanted search that were already due.
_BACKGROUND_STEPS = ("rss", "repair", "abs", "sweep", "owned", "wanted", "enrich")
_STATUS_ORDER = (
    "sab",
    "enrich",
    "rss",
    "sweep",
    "wanted",
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
        _Step("owned", "Owned slips", short, False),
        _Step(
            "wanted",
            "Wanted search",
            _env_seconds(WANTED_POLL_ENV, DEFAULT_WANTED_POLL_SECONDS),
            True,
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
        with self._lock:
            steps = []
            for step_id in _STATUS_ORDER:
                step = self._by_id[step_id]
                steps.append(
                    {
                        "id": step.id,
                        "label": step.label,
                        "interval_seconds": step.interval,
                        "last_run": self._last_run[step.id],
                        "last_error": self._last_error[step.id],
                    }
                )
        return {"steps": steps}

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
        try:
            produced = int(self._runners[name](self.settings_fn()) or 0)
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

    def _run_sweep(self, _settings: Settings) -> int:
        from librarian.wanted_sweep import sweep_wanted_audiobooks

        sweep_wanted_audiobooks(self.db)
        return 0

    def _run_owned(self, _settings: Settings) -> int:
        from librarian.owned_slip import sweep_owned_slips

        sweep_owned_slips(self.db)
        return 0

    def _run_wanted(self, settings: Settings) -> int:
        from librarian.wanted_search import poll_wanted

        return int(poll_wanted(self.db, settings) or 0)

    def _run_enrich(self, settings: Settings) -> int:
        from librarian.enrich import enrich_backlog_batch
        from librarian.enrich_progress import EnrichProgressReporter, read_enrich_progress

        current = read_enrich_progress(self.data_dir)
        if current.get("status") == "running" and current.get("source") == "manual":
            logger.debug("Enrich trickle skipped — manual enrich is running")
            return 0
        reporter = EnrichProgressReporter(self.data_dir, source="trickle")
        result = enrich_backlog_batch(
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
                    if self._due(name):
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
        for thread in (self._sab_thread, self._steps_thread):
            if thread is not None:
                thread.join(timeout=2)
        self._sab_thread = None
        self._steps_thread = None
        with self._lock:
            self._started = False
