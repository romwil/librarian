"""Daily indexer host budget. Wanted gets at most half.

Household totals only — never a per-reader ledger. A 429 halves the remaining
Wanted allowance for that host until midnight UTC. Interactive Find still runs
until the full host budget is gone.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Mapping, Optional

PROVIDER_INDEXER = "indexer"
PURPOSE_WANTED = "wanted"
PURPOSE_INTERACTIVE = "interactive"

# Cross-exam / 3.3: 500 calls/day/host; Wanted ≤ half.
INDEXER_DAILY_CALL_BUDGET = 500
WANTED_BUDGET_SHARE = 0.5


class WantedBudgetExhausted(Exception):
    """No host has Wanted budget left. Not a miss; the row stays due."""


def utc_day(now: Optional[float] = None) -> str:
    if now is None:
        moment = datetime.now(timezone.utc)
    else:
        moment = datetime.fromtimestamp(float(now), tz=timezone.utc)
    return moment.date().isoformat()


def remaining_ticks_today(now: float, interval_seconds: float = 3600.0) -> int:
    moment = datetime.fromtimestamp(float(now), tz=timezone.utc)
    end = datetime(moment.year, moment.month, moment.day, tzinfo=timezone.utc) + timedelta(days=1)
    left = max(0.0, (end - moment).total_seconds())
    step = max(1.0, float(interval_seconds))
    return max(1, int(math.ceil(left / step)))


def daily_host_budget(settings: Any = None) -> int:
    raw = getattr(settings, "indexer_daily_call_budget", None) if settings is not None else None
    try:
        value = int(raw) if raw is not None else INDEXER_DAILY_CALL_BUDGET
    except (TypeError, ValueError):
        value = INDEXER_DAILY_CALL_BUDGET
    return max(1, value)


def daily_wanted_budget(settings: Any = None) -> int:
    return max(1, daily_host_budget(settings) // 2)


def _fetch(
    db: Any,
    host_id: str,
    *,
    now: Optional[float] = None,
    purpose: Optional[str] = None,
) -> list:
    day = utc_day(now)
    host = str(host_id or "").strip() or "nzbfinder"
    conn = db._connect()
    try:
        if purpose is None:
            rows = conn.execute(
                """
                SELECT purpose, calls, errors, rate_limited, wanted_cap
                FROM provider_calls
                WHERE day = ? AND provider = ? AND host = ?
                """,
                (day, PROVIDER_INDEXER, host),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT purpose, calls, errors, rate_limited, wanted_cap
                FROM provider_calls
                WHERE day = ? AND provider = ? AND host = ? AND purpose = ?
                """,
                (day, PROVIDER_INDEXER, host, purpose),
            ).fetchall()
        return list(rows or [])
    finally:
        conn.close()


def _int(row: Any, key: str, default: int = 0) -> int:
    try:
        return int(row[key] if row[key] is not None else default)
    except (TypeError, ValueError, KeyError, IndexError):
        return default


def total_calls(db: Any, host_id: str, *, now: Optional[float] = None) -> int:
    return sum(_int(row, "calls") for row in _fetch(db, host_id, now=now))


def wanted_calls(db: Any, host_id: str, *, now: Optional[float] = None) -> int:
    return sum(_int(row, "calls") for row in _fetch(db, host_id, now=now, purpose=PURPOSE_WANTED))


def current_wanted_cap(
    db: Any,
    host_id: str,
    *,
    now: Optional[float] = None,
    settings: Any = None,
) -> int:
    default = daily_wanted_budget(settings)
    for row in _fetch(db, host_id, now=now, purpose=PURPOSE_WANTED):
        cap = row["wanted_cap"] if row["wanted_cap"] is not None else None
        if cap is not None:
            try:
                return max(0, int(cap))
            except (TypeError, ValueError):
                return default
    return default


def remaining_host(
    db: Any,
    host_id: str,
    *,
    now: Optional[float] = None,
    settings: Any = None,
) -> int:
    return max(0, daily_host_budget(settings) - total_calls(db, host_id, now=now))


def remaining_wanted(
    db: Any,
    host_id: str,
    *,
    now: Optional[float] = None,
    settings: Any = None,
) -> int:
    cap = current_wanted_cap(db, host_id, now=now, settings=settings)
    used = wanted_calls(db, host_id, now=now)
    return max(0, min(cap - used, remaining_host(db, host_id, now=now, settings=settings)))


def wanted_tick_allowance(
    db: Any,
    host_id: str,
    *,
    now: float,
    interval_seconds: float = 3600.0,
    settings: Any = None,
) -> int:
    remaining = remaining_wanted(db, host_id, now=now, settings=settings)
    if remaining <= 0:
        return 0
    ticks = remaining_ticks_today(now, interval_seconds)
    return max(1, int(math.ceil(remaining / ticks)))


def allow_call(
    db: Any,
    host_id: str,
    purpose: str,
    *,
    now: Optional[float] = None,
    settings: Any = None,
) -> bool:
    if remaining_host(db, host_id, now=now, settings=settings) <= 0:
        return False
    if purpose == PURPOSE_WANTED:
        return remaining_wanted(db, host_id, now=now, settings=settings) > 0
    return True


def record_call(
    db: Any,
    host_id: str,
    purpose: str,
    *,
    now: Optional[float] = None,
    calls: int = 1,
    errors: int = 0,
    rate_limited: int = 0,
) -> None:
    day = utc_day(now)
    host = str(host_id or "").strip() or "nzbfinder"
    kind = str(purpose or PURPOSE_INTERACTIVE).strip() or PURPOSE_INTERACTIVE
    add_calls = max(0, int(calls))
    add_errors = max(0, int(errors))
    add_limited = max(0, int(rate_limited))
    if add_calls == 0 and add_errors == 0 and add_limited == 0:
        return

    def _write() -> None:
        conn = db._connect()
        try:
            conn.execute(
                """
                INSERT INTO provider_calls (
                    day, provider, host, purpose, calls, errors, rate_limited
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(day, provider, host, purpose) DO UPDATE SET
                    calls = calls + excluded.calls,
                    errors = errors + excluded.errors,
                    rate_limited = rate_limited + excluded.rate_limited
                """,
                (day, PROVIDER_INDEXER, host, kind, add_calls, add_errors, add_limited),
            )
            conn.commit()
        finally:
            conn.close()

    db.run_write(_write, label="provider_calls")


def halt_wanted_on_429(
    db: Any,
    host_id: str,
    *,
    now: Optional[float] = None,
    settings: Any = None,
) -> int:
    """Halve remaining Wanted allowance for this UTC day. Returns the new cap."""
    used = wanted_calls(db, host_id, now=now)
    cap = current_wanted_cap(db, host_id, now=now, settings=settings)
    remaining = max(0, cap - used)
    new_cap = used + remaining // 2
    day = utc_day(now)
    host = str(host_id or "").strip() or "nzbfinder"

    def _write() -> None:
        conn = db._connect()
        try:
            conn.execute(
                """
                INSERT INTO provider_calls (
                    day, provider, host, purpose, calls, errors, rate_limited, wanted_cap
                ) VALUES (?, ?, ?, ?, 0, 0, 0, ?)
                ON CONFLICT(day, provider, host, purpose) DO UPDATE SET
                    wanted_cap = excluded.wanted_cap
                """,
                (day, PROVIDER_INDEXER, host, PURPOSE_WANTED, new_cap),
            )
            conn.commit()
        finally:
            conn.close()

    db.run_write(_write, label="wanted_cap")
    return new_cap


def any_wanted_open(
    db: Any,
    hosts: Iterable[Mapping[str, Any]],
    *,
    now: Optional[float] = None,
    settings: Any = None,
    started: Optional[Mapping[str, int]] = None,
    allowance: Optional[Mapping[str, int]] = None,
) -> bool:
    """True when at least one host still has Wanted room this tick."""
    for host in hosts:
        host_id = str(host.get("id") or "").strip() or "nzbfinder"
        if remaining_wanted(db, host_id, now=now, settings=settings) <= 0:
            continue
        if started is not None and allowance is not None:
            used_this_tick = wanted_calls(db, host_id, now=now) - int(started.get(host_id, 0))
            if used_this_tick >= int(allowance.get(host_id, 0)):
                continue
        return True
    return False


def household_totals(
    db: Any,
    hosts: Iterable[Mapping[str, Any]],
    *,
    now: Optional[float] = None,
    settings: Any = None,
) -> Dict[str, Any]:
    """Maintain payload: per-host household counts, never a user id."""
    day = utc_day(now)
    rows: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for host in hosts:
        host_id = str(host.get("id") or "").strip()
        if not host_id or host_id in seen:
            continue
        seen.add(host_id)
        call_rows = _fetch(db, host_id, now=now)
        calls = sum(_int(row, "calls") for row in call_rows)
        errors = sum(_int(row, "errors") for row in call_rows)
        limited = sum(_int(row, "rate_limited") for row in call_rows)
        wanted = sum(_int(row, "calls") for row in call_rows if str(row["purpose"]) == PURPOSE_WANTED)
        rows.append(
            {
                "id": host_id,
                "name": str(host.get("name") or host_id),
                "calls": calls,
                "wanted_calls": wanted,
                "errors": errors,
                "rate_limited": limited,
                "budget": daily_host_budget(settings),
                "wanted_budget": current_wanted_cap(db, host_id, now=now, settings=settings),
            }
        )
    return {"day": day, "hosts": rows}
