"""On-box House pulse: household aggregates, never a third-party SDK.

North star (volumes with real progress this week) is suppressed when fewer
than three members are on the box. Operational counters always show.
``metrics_daily`` has no user, IP, query, title, or work-id column.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from librarian import __version__
from librarian.db import Database
from librarian.web.status import last_backup_at

WEEK_SECONDS = 7 * 24 * 60 * 60
MEMBER_SUPPRESS_BELOW = 3
METRICS_KEEP_DAYS = 400

# Fixed enums. Unknown increment names become ``other``.
METRIC_SET = frozenset(
    {
        "asks_filed",
        "confirms_waiting",
        "confirm_download",
        "arrived",
        "search_run",
        "volumes_progress",
        "isbn_auto_file",
        "isbn_auto_file_undo",
        "other",
    }
)
SEARCH_DIM_SET = frozenset(
    {
        "beyond:hits",
        "beyond:zero",
        "beyond:error",
        "beyond:skipped",
        "beyond:calls",
        "",
    }
)
# confirm_download dims: ``{kind}:{ask-age bucket}`` — never titles or queries.
CONFIRM_KIND_SET = frozenset(
    {"book", "magazine", "comic", "audiobook", "music", "other", ""}
)
ASK_AGE_BUCKETS = ("lt1m", "lt1h", "lt1d", "gt1d")

FORBIDDEN_COLUMNS = frozenset(
    {
        "user",
        "user_id",
        "userid",
        "ip",
        "query",
        "title",
        "work_id",
        "workid",
        "path",
        "email",
        "ua",
        "user_agent",
    }
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def utc_day(*, now: Optional[float] = None) -> str:
    if now is None:
        moment = datetime.now(timezone.utc)
    else:
        moment = datetime.fromtimestamp(float(now), tz=timezone.utc)
    return moment.date().isoformat()


def normalize_metric(raw: Any) -> str:
    cleaned = _text(raw).lower().replace("-", "_")
    if cleaned in METRIC_SET:
        return cleaned
    return "other"


def ask_age_bucket(age_ms: int) -> str:
    """Bucket ask→confirm latency for on-box pulse (no free text)."""
    ms = max(0, int(age_ms or 0))
    if ms < 60_000:
        return "lt1m"
    if ms < 3_600_000:
        return "lt1h"
    if ms < 86_400_000:
        return "lt1d"
    return "gt1d"


def normalize_dim(metric: str, raw: Any) -> str:
    cleaned = _text(raw).lower()
    if metric == "search_run":
        return cleaned if cleaned in SEARCH_DIM_SET else "other"
    if metric == "confirm_download":
        # Accept ``kind:bucket`` or a bare kind.
        if ":" in cleaned:
            kind, _, bucket = cleaned.partition(":")
            kind_key = kind if kind in CONFIRM_KIND_SET else "other"
            bucket_key = bucket if bucket in ASK_AGE_BUCKETS else "lt1h"
            return f"{kind_key}:{bucket_key}"
        if cleaned in CONFIRM_KIND_SET:
            return f"{cleaned or 'other'}:lt1h"
        return "other:lt1h"
    return ""


def metrics_columns(db: Database) -> List[str]:
    with db._connect() as conn:
        rows = conn.execute("PRAGMA table_info(metrics_daily)").fetchall()
    return [str(row[1] if not hasattr(row, "keys") else row["name"]) for row in rows]


def increment(
    db: Database,
    metric: str,
    *,
    dim: str = "",
    count: int = 1,
    sum_ms: int = 0,
    now: Optional[float] = None,
    version: Optional[str] = None,
) -> None:
    """Add to today's household counter. Never stores a member id."""
    day = utc_day(now=now)
    key = normalize_metric(metric)
    dim_key = normalize_dim(key, dim)
    n = max(0, int(count or 0))
    ms = max(0, int(sum_ms or 0))
    if n == 0 and ms == 0:
        return
    ver = _text(version) or __version__

    def _write() -> None:
        with db._connect() as conn:
            conn.execute(
                """
                INSERT INTO metrics_daily (day, version, metric, dim, count, sum_ms)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(day, version, metric, dim) DO UPDATE SET
                    count = count + excluded.count,
                    sum_ms = sum_ms + excluded.sum_ms
                """,
                (day, ver, key, dim_key, n, ms),
            )

    db.run_write(_write, label="metrics_daily")


def set_metric(
    db: Database,
    metric: str,
    *,
    dim: str = "",
    count: int = 0,
    sum_ms: int = 0,
    now: Optional[float] = None,
    version: Optional[str] = None,
) -> None:
    """Replace today's household counter (daily snapshot, not an event increment)."""
    day = utc_day(now=now)
    key = normalize_metric(metric)
    dim_key = normalize_dim(key, dim)
    ver = _text(version) or __version__

    def _write() -> None:
        with db._connect() as conn:
            conn.execute(
                """
                INSERT INTO metrics_daily (day, version, metric, dim, count, sum_ms)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(day, version, metric, dim) DO UPDATE SET
                    count = excluded.count,
                    sum_ms = excluded.sum_ms
                """,
                (day, ver, key, dim_key, max(0, int(count or 0)), max(0, int(sum_ms or 0))),
            )

    db.run_write(_write, label="metrics_daily_set")


def _int_row(row: Any, index: int = 0) -> int:
    if row is None:
        return 0
    try:
        if hasattr(row, "keys"):
            return max(0, int(list(row)[index] or 0))
        return max(0, int(row[index] or 0))
    except (TypeError, ValueError, IndexError):
        return 0


def _member_count(conn: Any) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM users WHERE COALESCE(disabled, 0) = 0"
    ).fetchone()
    return _int_row(row)


def _volumes_progress(conn: Any, since: float) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT 1 FROM progress
            WHERE fraction > 0 AND updated_at >= ?
            GROUP BY user_id, work_id
        )
        """,
        (since,),
    ).fetchone()
    return _int_row(row)


def _asks_filed(conn: Any, since: float) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM wanted WHERE created_at >= ?",
        (since,),
    ).fetchone()
    return _int_row(row)


def _confirms_waiting(conn: Any) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE status = 'asked'"
    ).fetchone()
    return _int_row(row)


def _arrived(conn: Any, since: float) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM wanted WHERE status = 'arrived' AND updated_at >= ?",
        (since,),
    ).fetchone()
    return _int_row(row)


def _beyond_week(conn: Any, since_day: str) -> Dict[str, int]:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(calls), 0), COALESCE(SUM(errors), 0)
        FROM provider_calls
        WHERE provider = 'indexer' AND day >= ?
        """,
        (since_day,),
    ).fetchone()
    return {"calls": _int_row(row, 0), "errors": _int_row(row, 1)}


def _confirm_download_week(conn: Any, since_day: str) -> Dict[str, int]:
    """Household confirm_download rollup for the pulse card (count + latency ms)."""
    row = conn.execute(
        """
        SELECT COALESCE(SUM(count), 0), COALESCE(SUM(sum_ms), 0)
        FROM metrics_daily
        WHERE metric = 'confirm_download' AND day >= ?
        """,
        (since_day,),
    ).fetchone()
    return {"count": _int_row(row, 0), "sum_ms": _int_row(row, 1)}


def _metric_week_count(conn: Any, metric: str, since_day: str) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(count), 0)
        FROM metrics_daily
        WHERE metric = ? AND day >= ?
        """,
        (metric, since_day),
    ).fetchone()
    return _int_row(row, 0)


def _weather(
    *,
    beyond_rate: Optional[float],
    confirms_waiting: int,
    snapshot_age_hours: Optional[float],
) -> str:
    if snapshot_age_hours is not None and snapshot_age_hours > 36:
        return "act"
    if beyond_rate is not None and beyond_rate > 0.15:
        return "act"
    if confirms_waiting > 0:
        return "watch"
    if beyond_rate is not None and beyond_rate > 0.05:
        return "watch"
    return "steady"


def _age_hours(stamp: Optional[str], *, now: Optional[float] = None) -> Optional[float]:
    if not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    moment = datetime.fromtimestamp(now if now is not None else time.time(), tz=timezone.utc)
    return max(0.0, (moment - parsed.astimezone(timezone.utc)).total_seconds() / 3600.0)


def assemble_pulse(
    db: Database,
    *,
    data_dir: Optional[Path] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Owner-only household totals. Member-derived figures hide under n < 3."""
    moment = float(now if now is not None else time.time())
    since = moment - WEEK_SECONDS
    since_day = utc_day(now=since)
    with db._connect() as conn:
        members = _member_count(conn)
        volumes = _volumes_progress(conn, since)
        asks = _asks_filed(conn, since)
        waiting = _confirms_waiting(conn)
        landed = _arrived(conn, since)
        beyond = _beyond_week(conn, since_day)
        confirms = _confirm_download_week(conn, since_day)
        isbn_filed = _metric_week_count(conn, "isbn_auto_file", since_day)
        isbn_undo = _metric_week_count(conn, "isbn_auto_file_undo", since_day)
    calls = int(beyond["calls"])
    errors = int(beyond["errors"])
    rate = (errors / calls) if calls else None
    confirm_n = int(confirms["count"])
    confirm_ms = int(confirms["sum_ms"])
    confirm_avg = int(confirm_ms / confirm_n) if confirm_n else None
    backup_stamp = last_backup_at(Path(data_dir)) if data_dir is not None else None
    age = _age_hours(backup_stamp, now=moment)
    suppressed = members < MEMBER_SUPPRESS_BELOW
    return {
        "north_star": {
            "label": "Volumes read or listened this week",
            "value": None if suppressed else volumes,
            "display": "fewer than 3" if suppressed else str(volumes),
            "suppressed": suppressed,
            "member_count": members,
            "threshold": MEMBER_SUPPRESS_BELOW,
        },
        "asks_filed": {"label": "Asks filed this week", "value": asks, "window": "7d"},
        "confirms_waiting": {"label": "Confirms waiting", "value": waiting},
        "confirm_download": {
            "label": "Confirms this week",
            "value": confirm_n,
            "sum_ms": confirm_ms,
            "avg_ms": confirm_avg,
            "display": (
                "No confirms this week"
                if confirm_n == 0
                else (
                    f"{confirm_n}"
                    if confirm_avg is None
                    else f"{confirm_n} · ~{confirm_avg} ms"
                )
            ),
            "window": "7d",
        },
        "arrived": {"label": "Arrived this week", "value": landed, "window": "7d"},
        "beyond_error_rate": {
            "label": "Beyond search errors this week",
            "value": rate,
            "errors": errors,
            "calls": calls,
            "display": "No beyond searches this week" if calls == 0 else f"{errors} of {calls}",
        },
        "isbn_auto_file": {
            "label": "ISBN auto-filed this week",
            "value": isbn_filed,
            "window": "7d",
        },
        "isbn_auto_file_undo": {
            "label": "ISBN auto-file undos (mis-shelve signal)",
            "value": isbn_undo,
            "window": "7d",
        },
        "snapshot_age": {
            "label": "Last backup",
            "last_backup": backup_stamp,
            "age_hours": age,
            "display": "No backup yet" if backup_stamp is None else backup_stamp,
        },
        "weather": _weather(
            beyond_rate=rate,
            confirms_waiting=waiting,
            snapshot_age_hours=age,
        ),
        "analytics_hosts": 0,
    }


def snapshot_pulse(
    db: Database,
    *,
    data_dir: Optional[Path] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Write today's derived totals into metrics_daily (household only)."""
    payload = assemble_pulse(db, data_dir=data_dir, now=now)
    north = payload["north_star"]
    set_metric(
        db,
        "volumes_progress",
        count=int(north.get("value") or 0) if not north.get("suppressed") else 0,
        now=now,
    )
    set_metric(db, "asks_filed", count=int(payload["asks_filed"]["value"] or 0), now=now)
    set_metric(
        db,
        "confirms_waiting",
        count=int(payload["confirms_waiting"]["value"] or 0),
        now=now,
    )
    set_metric(db, "arrived", count=int(payload["arrived"]["value"] or 0), now=now)
    beyond = payload["beyond_error_rate"]
    set_metric(db, "search_run", dim="beyond:calls", count=int(beyond["calls"] or 0), now=now)
    set_metric(db, "search_run", dim="beyond:error", count=int(beyond["errors"] or 0), now=now)
    return payload


def purge_metrics(db: Database, *, keep_days: int = METRICS_KEEP_DAYS, now: Optional[float] = None) -> int:
    cutoff = utc_day(now=(now if now is not None else time.time()) - keep_days * 86400)

    def _write() -> int:
        with db._connect() as conn:
            cur = conn.execute("DELETE FROM metrics_daily WHERE day < ?", (cutoff,))
            return int(cur.rowcount or 0)

    return int(db.run_write(_write, label="purge_metrics") or 0)


__all__ = [
    "ASK_AGE_BUCKETS",
    "FORBIDDEN_COLUMNS",
    "MEMBER_SUPPRESS_BELOW",
    "METRIC_SET",
    "METRICS_KEEP_DAYS",
    "ask_age_bucket",
    "assemble_pulse",
    "increment",
    "set_metric",
    "metrics_columns",
    "normalize_dim",
    "normalize_metric",
    "purge_metrics",
    "snapshot_pulse",
    "utc_day",
]
