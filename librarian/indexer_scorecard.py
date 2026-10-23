"""Indexer scorecard — hosts as lanterns; mute a sick host without deleting it."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from librarian.indexers.hosts import NZBFINDER_ID, normalize_extra_indexers
from librarian.indexers.kind_map import EXTRA_KINDS
from librarian.kinds import ALL_KINDS

SCORECARD_FILENAME = "indexer_scorecard.json"
CATALOG_DB_FILENAME = "librarian.db"
HISTORY_LIMIT = 24
SQLITE_BUSY_TIMEOUT_MS = 30000

HOUSEHOLD_STAT_KINDS = ALL_KINDS
EXTRA_STAT_KINDS = EXTRA_KINDS
KNOWN_STAT_KINDS = frozenset(HOUSEHOLD_STAT_KINDS + EXTRA_STAT_KINDS)

KIND_LABELS = {
    "book": "Books",
    "magazine": "Magazines",
    "comic": "Comics",
    "audiobook": "Audiobooks",
    "music": "Music",
    "movie": "Movies",
    "tv": "TV",
    "xxx": "XXX",
    "": "Any",
}

# Lantern weather — never a latency KPI strip.
LANTERN_BRIGHT = "bright"
LANTERN_DIM = "dim"
LANTERN_DARK = "dark"
LANTERN_MUTED = "muted"
LANTERN_IDLE = "idle"

_LOCK = threading.Lock()


def _text(value: Any) -> str:
    return str(value or "").strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def scorecard_path(data_dir: Path) -> Path:
    return Path(data_dir) / SCORECARD_FILENAME


def catalog_db_path(data_dir: Path) -> Path:
    return Path(data_dir) / CATALOG_DB_FILENAME


def normalize_stat_kind(kind: Any) -> Optional[str]:
    """Known media kinds, or empty for untyped Finds. Unknown names are dropped."""
    key = _text(kind).lower()
    if key in KNOWN_STAT_KINDS:
        return key
    if not key:
        return ""
    return None


def kind_stat_label(kind: str) -> str:
    key = normalize_stat_kind(kind)
    if key is None:
        return KIND_LABELS[""]
    return KIND_LABELS.get(key, KIND_LABELS[""])


def match_rate(hits: int, empty: int) -> Optional[float]:
    """Hits over spoken Finds (hits + empty). Errors stay a reliability note."""
    spoken = max(0, int(hits or 0)) + max(0, int(empty or 0))
    if spoken < 1:
        return None
    return round(int(hits or 0) / spoken, 4)


def _empty_kind_row(kind: str = "") -> Dict[str, Any]:
    return {
        "kind": kind,
        "label": kind_stat_label(kind),
        "searches": 0,
        "hits": 0,
        "empty": 0,
        "errors": 0,
        "rate_limited": 0,
        "match_rate": None,
        "last_spoken_at": "",
        "last_hit_at": "",
    }


def _connect_stats(data_dir: Path) -> sqlite3.Connection:
    path = catalog_db_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS indexer_kind_stats (
            host_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            searches INTEGER NOT NULL DEFAULT 0,
            hits INTEGER NOT NULL DEFAULT 0,
            empty INTEGER NOT NULL DEFAULT 0,
            errors INTEGER NOT NULL DEFAULT 0,
            rate_limited INTEGER NOT NULL DEFAULT 0,
            last_spoken_at TEXT,
            last_hit_at TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (host_id, kind)
        )
        """
    )
    return conn


def _int_row(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _kind_row_from_sql(row: sqlite3.Row) -> Optional[Dict[str, Any]]:
    kind = normalize_stat_kind(row["kind"])
    if kind is None:
        return None
    hits = _int_row(row["hits"])
    empty = _int_row(row["empty"])
    return {
        "kind": kind,
        "label": kind_stat_label(kind),
        "searches": _int_row(row["searches"]),
        "hits": hits,
        "empty": empty,
        "errors": _int_row(row["errors"]),
        "rate_limited": _int_row(row["rate_limited"]),
        "match_rate": match_rate(hits, empty),
        "last_spoken_at": _text(row["last_spoken_at"]),
        "last_hit_at": _text(row["last_hit_at"]),
    }


def _record_kind_stat(
    data_dir: Path,
    *,
    host_id: str,
    kind: str,
    ok: bool,
    hit_count: int,
    rate_limited: bool,
    at: str,
) -> None:
    hid = _text(host_id)
    if not hid:
        return
    stored_kind = normalize_stat_kind(kind)
    if stored_kind is None:
        stored_kind = ""
    spoke_hit = bool(ok) and int(hit_count or 0) > 0
    spoke_empty = bool(ok) and not spoke_hit
    errored = not bool(ok)
    conn = _connect_stats(data_dir)
    try:
        conn.execute(
            """
            INSERT INTO indexer_kind_stats (
                host_id, kind, searches, hits, empty, errors, rate_limited,
                last_spoken_at, last_hit_at, updated_at
            )
            VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(host_id, kind) DO UPDATE SET
                searches = searches + 1,
                hits = hits + excluded.hits,
                empty = empty + excluded.empty,
                errors = errors + excluded.errors,
                rate_limited = rate_limited + excluded.rate_limited,
                last_spoken_at = excluded.last_spoken_at,
                last_hit_at = COALESCE(excluded.last_hit_at, last_hit_at),
                updated_at = excluded.updated_at
            """,
            (
                hid,
                stored_kind,
                1 if spoke_hit else 0,
                1 if spoke_empty else 0,
                1 if errored else 0,
                1 if rate_limited else 0,
                at,
                at if spoke_hit else None,
                at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def load_kind_stats(data_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Per-host kind rows from SQLite. Missing catalog is an empty map."""
    path = catalog_db_path(data_dir)
    if not path.exists():
        return {}
    conn = _connect_stats(data_dir)
    try:
        rows = conn.execute(
            """
            SELECT host_id, kind, searches, hits, empty, errors, rate_limited,
                   last_spoken_at, last_hit_at
            FROM indexer_kind_stats
            ORDER BY host_id, kind
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()
    out: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        hid = _text(row["host_id"])
        parsed = _kind_row_from_sql(row)
        if not hid or parsed is None:
            continue
        out.setdefault(hid, []).append(parsed)
    return out


def summarize_host_stats(
    kind_rows: Optional[Sequence[Mapping[str, Any]]] = None,
    *,
    extra: bool = False,
) -> Dict[str, Any]:
    """Roll kind counters into a compact BI payload (match rate by media type)."""
    allowed = set(HOUSEHOLD_STAT_KINDS) | {""}
    if extra:
        allowed.update(EXTRA_STAT_KINDS)
    by_kind: Dict[str, Dict[str, Any]] = {}
    for raw in kind_rows or []:
        if not isinstance(raw, Mapping):
            continue
        kind = normalize_stat_kind(raw.get("kind"))
        if kind is None or kind not in allowed:
            continue
        row = by_kind.setdefault(kind, _empty_kind_row(kind))
        row["searches"] += _int_row(raw.get("searches"))
        row["hits"] += _int_row(raw.get("hits"))
        row["empty"] += _int_row(raw.get("empty"))
        row["errors"] += _int_row(raw.get("errors"))
        row["rate_limited"] += _int_row(raw.get("rate_limited"))
        spoken_at = _text(raw.get("last_spoken_at"))
        hit_at = _text(raw.get("last_hit_at"))
        if spoken_at > _text(row.get("last_spoken_at")):
            row["last_spoken_at"] = spoken_at
        if hit_at > _text(row.get("last_hit_at")):
            row["last_hit_at"] = hit_at
    order = list(HOUSEHOLD_STAT_KINDS)
    if extra:
        order.extend(EXTRA_STAT_KINDS)
    order.append("")
    kinds: List[Dict[str, Any]] = []
    searches = hits = empty = errors = rate_limited = 0
    last_spoken = ""
    last_hit = ""
    for kind in order:
        row = by_kind.get(kind)
        if not row or int(row.get("searches") or 0) < 1:
            continue
        row["match_rate"] = match_rate(int(row["hits"]), int(row["empty"]))
        kinds.append(row)
        searches += int(row["searches"])
        hits += int(row["hits"])
        empty += int(row["empty"])
        errors += int(row["errors"])
        rate_limited += int(row["rate_limited"])
        if _text(row.get("last_spoken_at")) > last_spoken:
            last_spoken = _text(row.get("last_spoken_at"))
        if _text(row.get("last_hit_at")) > last_hit:
            last_hit = _text(row.get("last_hit_at"))
    return {
        "searches": searches,
        "hits": hits,
        "empty": empty,
        "errors": errors,
        "rate_limited": rate_limited,
        "match_rate": match_rate(hits, empty),
        "last_spoken_at": last_spoken,
        "last_hit_at": last_hit,
        "by_kind": kinds,
    }


def _empty_host(host_id: str, *, name: str = "") -> Dict[str, Any]:
    return {
        "id": host_id,
        "name": name or host_id,
        "samples": [],
        "last_ok_at": "",
        "last_error_at": "",
        "last_error": "",
        "last_latency_ms": None,
        "last_hit_count": None,
        "ok_count": 0,
        "error_count": 0,
        "empty_count": 0,
        "rate_limited_count": 0,
    }


def _default_blob() -> Dict[str, Any]:
    return {"hosts": {}, "updated_at": ""}


def read_scorecard(data_dir: Path) -> Dict[str, Any]:
    path = scorecard_path(data_dir)
    if not path.exists():
        return _default_blob()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_blob()
    if not isinstance(raw, dict):
        return _default_blob()
    hosts = raw.get("hosts")
    if not isinstance(hosts, dict):
        hosts = {}
    cleaned: Dict[str, Any] = {}
    for key, row in hosts.items():
        if not isinstance(row, dict):
            continue
        host_id = _text(row.get("id") or key) or _text(key)
        if not host_id:
            continue
        base = _empty_host(host_id, name=_text(row.get("name")) or host_id)
        samples = row.get("samples") if isinstance(row.get("samples"), list) else []
        base.update(
            {
                "samples": [dict(s) for s in samples[-HISTORY_LIMIT:] if isinstance(s, dict)],
                "last_ok_at": _text(row.get("last_ok_at")),
                "last_error_at": _text(row.get("last_error_at")),
                "last_error": _text(row.get("last_error")),
                "last_latency_ms": row.get("last_latency_ms"),
                "last_hit_count": row.get("last_hit_count"),
                "ok_count": max(0, int(row.get("ok_count") or 0)),
                "error_count": max(0, int(row.get("error_count") or 0)),
                "empty_count": max(0, int(row.get("empty_count") or 0)),
                "rate_limited_count": max(0, int(row.get("rate_limited_count") or 0)),
            }
        )
        cleaned[host_id] = base
    return {"hosts": cleaned, "updated_at": _text(raw.get("updated_at"))}


def write_scorecard(data_dir: Path, payload: Mapping[str, Any]) -> Dict[str, Any]:
    path = scorecard_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = {
        "hosts": dict(payload.get("hosts") or {}),
        "updated_at": _text(payload.get("updated_at")) or utc_now(),
    }
    path.write_text(json.dumps(blob, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return blob


def record_host_probe(
    data_dir: Path,
    *,
    host_id: str,
    host_name: str = "",
    ok: bool,
    latency_ms: Optional[float] = None,
    hit_count: int = 0,
    error: str = "",
    rate_limited: bool = False,
    kind: str = "",
) -> Dict[str, Any]:
    """Append one Find probe sample for a host (lantern fuel + by-kind stats)."""
    hid = _text(host_id)
    if not hid:
        return read_scorecard(data_dir)
    at = utc_now()
    with _LOCK:
        blob = read_scorecard(data_dir)
        hosts = dict(blob.get("hosts") or {})
        row = dict(hosts.get(hid) or _empty_host(hid, name=host_name))
        if host_name:
            row["name"] = _text(host_name) or row.get("name") or hid
        sample = {
            "at": at,
            "ok": bool(ok),
            "latency_ms": None if latency_ms is None else round(float(latency_ms), 1),
            "hit_count": max(0, int(hit_count or 0)),
            "error": _text(error)[:240],
            "rate_limited": bool(rate_limited),
            "kind": normalize_stat_kind(kind) or "",
        }
        samples = list(row.get("samples") or [])
        samples.append(sample)
        row["samples"] = samples[-HISTORY_LIMIT:]
        row["last_latency_ms"] = sample["latency_ms"]
        row["last_hit_count"] = sample["hit_count"]
        if ok:
            row["ok_count"] = int(row.get("ok_count") or 0) + 1
            row["last_ok_at"] = sample["at"]
            row["last_error"] = ""
            if sample["hit_count"] < 1:
                row["empty_count"] = int(row.get("empty_count") or 0) + 1
        else:
            row["error_count"] = int(row.get("error_count") or 0) + 1
            row["last_error_at"] = sample["at"]
            row["last_error"] = sample["error"] or "host failed"
            if rate_limited:
                row["rate_limited_count"] = int(row.get("rate_limited_count") or 0) + 1
        hosts[hid] = row
        blob = write_scorecard(data_dir, {"hosts": hosts, "updated_at": sample["at"]})
    try:
        _record_kind_stat(
            data_dir,
            host_id=hid,
            kind=kind,
            ok=ok,
            hit_count=hit_count,
            rate_limited=rate_limited,
            at=at,
        )
    except Exception:  # noqa: BLE001 — kind stats must never break lantern weather
        pass
    return blob


def lantern_weather(
    *,
    muted: bool = False,
    configured: bool = True,
    ok_count: int = 0,
    error_count: int = 0,
    empty_count: int = 0,
    rate_limited_count: int = 0,
    last_ok_at: str = "",
    last_error: str = "",
) -> str:
    """Lantern mood from recent health — never a numeric grade."""
    if muted:
        return LANTERN_MUTED
    if not configured:
        return LANTERN_IDLE
    errors = max(0, int(error_count or 0))
    oks = max(0, int(ok_count or 0))
    empties = max(0, int(empty_count or 0))
    limited = max(0, int(rate_limited_count or 0))
    if errors + oks < 1:
        return LANTERN_IDLE
    if last_error or (errors > 0 and errors >= oks):
        return LANTERN_DARK
    if limited > 0 or (empties > 0 and empties >= max(1, oks // 2)):
        return LANTERN_DIM
    if oks > 0 and _text(last_ok_at):
        return LANTERN_BRIGHT
    return LANTERN_IDLE


def lantern_presence(weather: str, *, name: str = "", last_error: str = "") -> str:
    """Soft lantern line — presence, not a scoreboard."""
    mood = _text(weather) or LANTERN_IDLE
    host = _text(name) or "This host"
    if mood == LANTERN_MUTED:
        return f"{host} rests muted — Find skips it until you unmute."
    if mood == LANTERN_DARK:
        err = _text(last_error)
        if err:
            return f"{host} dimmed out — {err}"
        return f"{host} went dark on the last Find."
    if mood == LANTERN_DIM:
        return f"{host} flickers — empty pages or a soft rate limit."
    if mood == LANTERN_BRIGHT:
        return f"{host} burns steady."
    return f"{host} has not spoken yet."


def is_nzbfinder_muted(settings: Any) -> bool:
    return bool(getattr(settings, "nzbfinder_muted", False))


def host_is_muted(settings: Any, host_id: str) -> bool:
    hid = _text(host_id) or NZBFINDER_ID
    if hid == NZBFINDER_ID:
        return is_nzbfinder_muted(settings)
    for row in normalize_extra_indexers(getattr(settings, "extra_indexers", [])):
        if row.get("id") == hid:
            return not bool(row.get("enabled", True))
    return False


def configured_hosts(settings: Any) -> List[Dict[str, Any]]:
    """All known hosts (including muted) for the Maintain lantern row."""
    out: List[Dict[str, Any]] = []
    nzb_url = _text(getattr(settings, "nzbfinder_url", ""))
    nzb_token = _text(getattr(settings, "nzbfinder_api_token", ""))
    out.append(
        {
            "id": NZBFINDER_ID,
            "name": "NZBFinder",
            "url": nzb_url,
            "configured": bool(nzb_url and nzb_token),
            "muted": is_nzbfinder_muted(settings),
            "primary": True,
        }
    )
    for row in normalize_extra_indexers(getattr(settings, "extra_indexers", [])):
        out.append(
            {
                "id": row["id"],
                "name": row["name"],
                "url": row["url"],
                "configured": bool(row.get("url") and row.get("api_token")),
                "muted": not bool(row.get("enabled", True)),
                "primary": False,
            }
        )
    return out


def assemble_indexer_scorecard(
    data_dir: Path,
    settings: Any,
    *,
    stats: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Living lanterns for Maintain — weather + mute, plus match rate by kind."""
    blob = stats if isinstance(stats, Mapping) else read_scorecard(data_dir)
    stored = blob.get("hosts") if isinstance(blob.get("hosts"), dict) else {}
    extra = bool(getattr(settings, "show_extra_categories", False))
    kind_stats = load_kind_stats(data_dir)
    lanterns: List[Dict[str, Any]] = []
    sick = 0
    muted_n = 0
    for host in configured_hosts(settings):
        row = stored.get(host["id"]) if isinstance(stored.get(host["id"]), dict) else {}
        weather = lantern_weather(
            muted=bool(host.get("muted")),
            configured=bool(host.get("configured")),
            ok_count=int(row.get("ok_count") or 0) if row else 0,
            error_count=int(row.get("error_count") or 0) if row else 0,
            empty_count=int(row.get("empty_count") or 0) if row else 0,
            rate_limited_count=int(row.get("rate_limited_count") or 0) if row else 0,
            last_ok_at=_text(row.get("last_ok_at")) if row else "",
            last_error=_text(row.get("last_error")) if row else "",
        )
        if weather == LANTERN_MUTED:
            muted_n += 1
        elif weather == LANTERN_DARK:
            sick += 1
        presence = lantern_presence(
            weather,
            name=_text(host.get("name")),
            last_error=_text(row.get("last_error")) if row else "",
        )
        lanterns.append(
            {
                "id": host["id"],
                "name": host["name"],
                "primary": bool(host.get("primary")),
                "configured": bool(host.get("configured")),
                "muted": bool(host.get("muted")),
                "weather": weather,
                "presence": presence,
                "last_ok_at": _text(row.get("last_ok_at")) if row else "",
                "last_error": _text(row.get("last_error")) if row else "",
                "last_latency_ms": row.get("last_latency_ms") if row else None,
                "can_mute": bool(host.get("configured")),
                "stats": summarize_host_stats(kind_stats.get(host["id"]) or [], extra=extra),
            }
        )
    if sick > 0:
        desk = "A lantern needs tending — mute a sick host without deleting it."
    elif muted_n > 0:
        desk = "Some lanterns rest muted. Unmute when the host recovers."
    elif any(row["weather"] == LANTERN_BRIGHT for row in lanterns):
        desk = "The Find lanterns burn steady."
    else:
        desk = "Lanterns wait for the next Find beyond the shelves."
    return {
        "presence": desk,
        "lanterns": lanterns,
        "updated_at": _text(blob.get("updated_at")),
        "ok": sick < 1,
        "show_extra_categories": extra,
    }


def mute_host(settings: Any, host_id: str, *, muted: bool = True) -> Any:
    """Toggle mute on a host. NZBFinder uses nzbfinder_muted; extras use enabled."""
    from librarian.config import Settings

    hid = _text(host_id) or NZBFINDER_ID
    if not isinstance(settings, Settings):
        raise TypeError("settings must be Settings")
    if hid == NZBFINDER_ID:
        settings.nzbfinder_muted = bool(muted)
        return settings
    extras = normalize_extra_indexers(getattr(settings, "extra_indexers", []))
    found = False
    next_rows: List[Dict[str, Any]] = []
    for row in extras:
        if row["id"] == hid:
            found = True
            next_rows.append({**row, "enabled": not bool(muted)})
        else:
            next_rows.append(row)
    if not found:
        raise KeyError(hid)
    settings.extra_indexers = next_rows
    return settings


__all__ = [
    "LANTERN_BRIGHT",
    "LANTERN_DARK",
    "LANTERN_DIM",
    "LANTERN_IDLE",
    "LANTERN_MUTED",
    "assemble_indexer_scorecard",
    "catalog_db_path",
    "configured_hosts",
    "host_is_muted",
    "is_nzbfinder_muted",
    "kind_stat_label",
    "lantern_presence",
    "lantern_weather",
    "load_kind_stats",
    "match_rate",
    "mute_host",
    "normalize_stat_kind",
    "read_scorecard",
    "record_host_probe",
    "scorecard_path",
    "summarize_host_stats",
    "write_scorecard",
]
