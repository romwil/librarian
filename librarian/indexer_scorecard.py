"""Indexer scorecard — hosts as lanterns; mute a sick host without deleting it."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from librarian.indexers.hosts import NZBFINDER_ID, normalize_extra_indexers

SCORECARD_FILENAME = "indexer_scorecard.json"
HISTORY_LIMIT = 24

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
) -> Dict[str, Any]:
    """Append one Find probe sample for a host (lantern fuel, not a dashboard)."""
    hid = _text(host_id)
    if not hid:
        return read_scorecard(data_dir)
    with _LOCK:
        blob = read_scorecard(data_dir)
        hosts = dict(blob.get("hosts") or {})
        row = dict(hosts.get(hid) or _empty_host(hid, name=host_name))
        if host_name:
            row["name"] = _text(host_name) or row.get("name") or hid
        sample = {
            "at": utc_now(),
            "ok": bool(ok),
            "latency_ms": None if latency_ms is None else round(float(latency_ms), 1),
            "hit_count": max(0, int(hit_count or 0)),
            "error": _text(error)[:240],
            "rate_limited": bool(rate_limited),
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
        return write_scorecard(data_dir, {"hosts": hosts, "updated_at": sample["at"]})


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
    """Living lanterns for Maintain — weather + mute, never a KPI strip."""
    blob = stats if isinstance(stats, Mapping) else read_scorecard(data_dir)
    stored = blob.get("hosts") if isinstance(blob.get("hosts"), dict) else {}
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
    "configured_hosts",
    "host_is_muted",
    "is_nzbfinder_muted",
    "lantern_presence",
    "lantern_weather",
    "mute_host",
    "read_scorecard",
    "record_host_probe",
    "scorecard_path",
    "write_scorecard",
]
