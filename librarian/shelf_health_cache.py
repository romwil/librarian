"""Process-local SWR cache for Maintain shelf-health snapshots.

Permission probes and comic/book blend classification can take tens of seconds
on a large catalog. Maintain must paint immediately: serve the last snapshot
(or a warming skeleton) and refresh off-request.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from librarian.config import Settings
from librarian.db import Database
from librarian.review_reasons import REVIEW_EXTRA
from librarian.shelf_health import CHOWN_COMMAND, CHOWN_TIP, shelf_permission_report
from librarian.shelf_health_score import assemble_shelf_health_score
from librarian.split_mixed_kinds import count_mixed_kind_works

logger = logging.getLogger("librarian.shelf_health_cache")

# PERF-002: refresh at most every ~15 minutes; keep hard window generous so a
# stale paint always has weather to show while a background rebuild runs.
SOFT_TTL_SECONDS = 15 * 60.0
HARD_TTL_SECONDS = 6 * 60 * 60.0

Payload = Dict[str, Any]


class _Entry:
    __slots__ = ("payload", "built_at", "epoch")

    def __init__(self, payload: Payload, built_at: float, epoch: int) -> None:
        self.payload = payload
        self.built_at = built_at
        self.epoch = epoch


_lock = threading.Lock()
_entry: Optional[_Entry] = None
_epoch = 0
_inflight: Optional[threading.Event] = None


def clear_shelf_health_cache() -> None:
    """Test helper — drop memory state."""
    global _entry, _epoch, _inflight
    with _lock:
        _entry = None
        _epoch = 0
        _inflight = None


def invalidate_shelf_health_cache() -> None:
    """Mark the snapshot soft-stale so the next read refreshes behind paint."""
    global _epoch
    with _lock:
        _epoch += 1


def wait_shelf_health_idle(timeout: float = 5.0) -> bool:
    """Test helper — wait for an in-flight background build."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with _lock:
            event = _inflight
        if event is None:
            return True
        event.wait(max(0.0, deadline - time.monotonic()))
    return False


def _iso(ts: Optional[float]) -> Optional[str]:
    if ts is None or ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def warming_shelf_health_skeleton() -> Payload:
    """Honest empty paint while the first snapshot is still computing."""
    score = assemble_shelf_health_score(
        shelf_health={"locked_count": 0},
        extra_files=0,
        unshelved_shells=0,
        comic_book_blends=0,
    )
    return {
        "roots": [],
        "locked_count": 0,
        "ok": True,
        "chown_tip": CHOWN_TIP,
        "chown_command": CHOWN_COMMAND,
        "puid": "",
        "pgid": "",
        "score": score,
        "generated_at": None,
        "stale": False,
        "refreshing": True,
        "cached": False,
    }


def build_shelf_health_snapshot(db: Database, settings: Settings) -> Payload:
    """Synchronously compose permission report + backlog counts + score."""
    report = shelf_permission_report(settings)
    extra = db.count_works(review_state="needs_review", review_reason=REVIEW_EXTRA)
    shells = db.count_shell_works()
    blends = count_mixed_kind_works(db)
    score = assemble_shelf_health_score(
        shelf_health=report,
        extra_files=extra,
        unshelved_shells=shells,
        comic_book_blends=blends,
    )
    built_at = time.time()
    return {
        **report,
        "score": score,
        "generated_at": _iso(built_at),
        "stale": False,
        "refreshing": False,
        "cached": False,
    }


def _annotate(payload: Payload, *, state: str, built_at: Optional[float]) -> Payload:
    out = dict(payload)
    if built_at is not None:
        out["generated_at"] = _iso(built_at)
    elif "generated_at" not in out:
        out["generated_at"] = None
    if state == "fresh":
        out["cached"] = True
        out["stale"] = False
        out["refreshing"] = False
    elif state == "stale":
        out["cached"] = True
        out["stale"] = True
        out["refreshing"] = True
    else:  # warming
        out["cached"] = False
        out["stale"] = False
        out["refreshing"] = True
    return out


def _lookup() -> Optional[tuple[_Entry, bool]]:
    now = time.time()
    with _lock:
        if _entry is None:
            return None
        age = now - _entry.built_at
        if age >= HARD_TTL_SECONDS:
            return None
        fresh = age < SOFT_TTL_SECONDS and _entry.epoch == _epoch
        return _entry, fresh


def _store(payload: Payload, *, built_at: Optional[float] = None, epoch: Optional[int] = None) -> _Entry:
    global _entry
    entry = _Entry(
        payload=payload,
        built_at=time.time() if built_at is None else built_at,
        epoch=_epoch if epoch is None else epoch,
    )
    with _lock:
        _entry = entry
    return entry


def _schedule(builder: Callable[[], Payload]) -> Optional[threading.Event]:
    """Single-flight background rebuild. Returns the event only for the starter."""
    global _inflight
    with _lock:
        if _inflight is not None:
            return None
        done = threading.Event()
        _inflight = done
        epoch_at_start = _epoch

    def _run() -> None:
        global _inflight
        try:
            payload = builder()
            if not isinstance(payload, dict):
                raise TypeError("shelf-health builder must return a dict")
            # Persist without cache flags; annotate at serve time.
            clean = dict(payload)
            clean.pop("cached", None)
            clean.pop("stale", None)
            clean.pop("refreshing", None)
            built = time.time()
            clean["generated_at"] = _iso(built)
            _store(clean, built_at=built, epoch=epoch_at_start)
        except Exception:  # noqa: BLE001 — never crash the worker
            logger.exception("shelf-health background refresh failed")
        finally:
            with _lock:
                _inflight = None
            done.set()

    threading.Thread(target=_run, name="librarian-shelf-health", daemon=True).start()
    return done


def get_shelf_health_snapshot(
    db: Database,
    settings: Settings,
    *,
    cold_wait: float = 0.0,
    builder: Optional[Callable[[], Payload]] = None,
) -> Payload:
    """Return the best available shelf-health payload without blocking on recompute.

    ``cold_wait`` may briefly wait on a *first* cold miss (tests / tiny catalogs).
    Production routes should keep ``cold_wait=0`` so Maintain never times out.
    """
    compute = builder or (lambda: build_shelf_health_snapshot(db, settings))

    hit = _lookup()
    if hit is not None:
        entry, fresh = hit
        if fresh:
            return _annotate(entry.payload, state="fresh", built_at=entry.built_at)
        _schedule(compute)
        return _annotate(entry.payload, state="stale", built_at=entry.built_at)

    done = _schedule(compute)
    if done is not None and cold_wait > 0:
        done.wait(cold_wait)
        hit = _lookup()
        if hit is not None:
            return _annotate(hit[0].payload, state="fresh", built_at=hit[0].built_at)

    return _annotate(warming_shelf_health_skeleton(), state="warming", built_at=None)


def refresh_shelf_health_snapshot(
    db: Database,
    settings: Settings,
    *,
    builder: Optional[Callable[[], Payload]] = None,
) -> Payload:
    """Synchronous rebuild (tests / explicit refresh)."""
    compute = builder or (lambda: build_shelf_health_snapshot(db, settings))
    payload = compute()
    clean = dict(payload)
    clean.pop("cached", None)
    clean.pop("stale", None)
    clean.pop("refreshing", None)
    built = time.time()
    clean["generated_at"] = _iso(built)
    entry = _store(clean, built_at=built)
    return _annotate(entry.payload, state="fresh", built_at=entry.built_at)


__all__ = [
    "HARD_TTL_SECONDS",
    "SOFT_TTL_SECONDS",
    "build_shelf_health_snapshot",
    "clear_shelf_health_cache",
    "get_shelf_health_snapshot",
    "invalidate_shelf_health_cache",
    "refresh_shelf_health_snapshot",
    "wait_shelf_health_idle",
    "warming_shelf_health_skeleton",
]
