"""Background job poller (SAB + ingest/watch + RSS + ABS match). On-demand GET /api/queue still works."""

from __future__ import annotations

import logging
import os
import threading
from typing import Callable, Optional

from librarian.config import Settings
from librarian.db import Database
from librarian.jobs import poll_active_jobs
from librarian.sabnzbd import SABError

logger = logging.getLogger(__name__)


def poll_interval_seconds() -> float:
    raw = (os.environ.get("LIBRARIAN_POLL_SECONDS") or "30").strip()
    try:
        return max(5.0, float(raw))
    except ValueError:
        return 30.0


class JobPoller:
    def __init__(
        self,
        db: Database,
        settings_fn: Callable[[], Settings],
        *,
        interval: Optional[float] = None,
        sab=None,
    ) -> None:
        self.db = db
        self.settings_fn = settings_fn
        self.interval = interval if interval is not None else poll_interval_seconds()
        self.sab = sab
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def tick(self) -> int:
        settings = self.settings_fn()
        count = 0
        try:
            from librarian.ingest import poll_watch_folder

            count += poll_watch_folder(self.db, settings)
        except Exception:
            logger.exception("Watch poller tick failed")
        try:
            from librarian.rss import poll_rss_feeds

            count += poll_rss_feeds(self.db, settings)
        except Exception:
            logger.exception("RSS poller tick failed")
        try:
            from librarian.audiobookshelf import match_audiobooks

            match_audiobooks(self.db, settings)
        except Exception:
            logger.exception("ABS match tick failed")
        try:
            return count + poll_active_jobs(self.db, settings, sab=self.sab)
        except SABError as error:
            logger.info("SAB poll skipped: %s", error)
            return count

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.tick()
            except Exception:
                logger.exception("SAB poller tick failed")

    def start(self) -> None:
        if os.environ.get("LIBRARIAN_SKIP_APP_BOOT") == "1":
            return
        if os.environ.get("LIBRARIAN_DISABLE_POLLER") == "1":
            return
        if self.is_running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="librarian-sab-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)
        self._thread = None
