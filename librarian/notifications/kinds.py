"""Librarian notification kinds, channels, and default prefs.

Voice: household library — slips, Requests, Needs you, lamp digests.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# Kind ids are stable API tokens (snake_case). Labels are member-facing.
NOTIFICATION_KINDS: Tuple[str, ...] = (
    "asked_confirm",
    "arrived",
    "needs_you",
    "quiet_hours_wake",
    "newsletter",
    "someone_finished",
    "shelf_health",
)

NOTIFICATION_KIND_SET = frozenset(NOTIFICATION_KINDS)

CHANNELS: Tuple[str, ...] = ("inbox", "email")
CHANNEL_SET = frozenset(CHANNELS)

TIMINGS: Tuple[str, ...] = ("realtime", "daily", "weekly")
TIMING_SET = frozenset(TIMINGS)

# Catalog for Settings → Notifications (order matches NOTIFICATION_KINDS).
KIND_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "asked_confirm",
        "label": "Asked slip needs confirm",
        "help": "When a Request needs you to confirm before the house acts.",
        "default": {"enabled": True, "channels": ["inbox"], "timing": "realtime"},
    },
    {
        "id": "arrived",
        "label": "Arrived (your Request)",
        "help": "When something you asked for lands on the shelf.",
        "default": {"enabled": True, "channels": ["inbox"], "timing": "realtime"},
    },
    {
        "id": "needs_you",
        "label": "Needs you (Review)",
        "help": "When Review slips are waiting for a calm sort.",
        "default": {"enabled": True, "channels": ["inbox"], "timing": "realtime"},
    },
    {
        "id": "quiet_hours_wake",
        "label": "Quiet hours wake",
        "help": "A short warm digest when quiet hours end and parked slips stir.",
        "default": {"enabled": True, "channels": ["inbox"], "timing": "daily"},
    },
    {
        "id": "newsletter",
        "label": "Library newsletter",
        "help": "Weekly or monthly letter about recent arrivals (edition lands in a later release).",
        "default": {"enabled": False, "channels": ["inbox", "email"], "timing": "weekly"},
    },
    {
        "id": "someone_finished",
        "label": "Someone finished",
        "help": "A quiet household whisper when someone finishes a title.",
        "default": {"enabled": True, "channels": ["inbox"], "timing": "realtime"},
    },
    {
        "id": "shelf_health",
        "label": "Shelf health",
        "help": "Shells, blends, and permission locks that need a tend.",
        "default": {"enabled": True, "channels": ["inbox"], "timing": "daily"},
    },
]

KIND_DEFAULTS: Dict[str, Dict[str, Any]] = {
    str(row["id"]): dict(row["default"]) for row in KIND_CATALOG
}


def normalize_kind(raw: Any) -> str:
    cleaned = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if cleaned not in NOTIFICATION_KIND_SET:
        raise ValueError(f"Unsupported notification kind: {raw}")
    return cleaned


def normalize_timing(raw: Any, *, default: str = "realtime") -> str:
    cleaned = str(raw or default).strip().lower()
    if cleaned in {"real_time", "real-time", "immediate"}:
        cleaned = "realtime"
    if cleaned in {"daily_digest", "day"}:
        cleaned = "daily"
    if cleaned in {"weekly_digest", "week"}:
        cleaned = "weekly"
    if cleaned not in TIMING_SET:
        return default if default in TIMING_SET else "realtime"
    return cleaned


def normalize_channels(raw: Any, *, default: List[str] | None = None) -> List[str]:
    fallback = list(default or ["inbox"])
    if raw is None:
        return [c for c in fallback if c in CHANNEL_SET] or ["inbox"]
    if isinstance(raw, str):
        parts = [p.strip().lower() for p in raw.replace(";", ",").split(",") if p.strip()]
    elif isinstance(raw, (list, tuple, set)):
        parts = [str(p).strip().lower() for p in raw if str(p).strip()]
    else:
        return [c for c in fallback if c in CHANNEL_SET] or ["inbox"]
    # Preserve order, drop unknowns/dupes.
    seen: set[str] = set()
    out: List[str] = []
    for part in parts:
        alias = "inbox" if part in {"in_app", "in-app", "app"} else part
        if alias not in CHANNEL_SET or alias in seen:
            continue
        seen.add(alias)
        out.append(alias)
    return out or ([c for c in fallback if c in CHANNEL_SET] or ["inbox"])


def normalize_kind_pref(kind: str, raw: Any = None) -> Dict[str, Any]:
    """Merge one kind pref with catalog defaults."""
    cleaned = normalize_kind(kind)
    base = dict(KIND_DEFAULTS[cleaned])
    if not isinstance(raw, dict):
        return {
            "enabled": bool(base["enabled"]),
            "channels": list(base["channels"]),
            "timing": str(base["timing"]),
        }
    enabled = raw.get("enabled")
    if enabled is None:
        enabled = base["enabled"]
    return {
        "enabled": bool(enabled),
        "channels": normalize_channels(raw.get("channels"), default=list(base["channels"])),
        "timing": normalize_timing(raw.get("timing"), default=str(base["timing"])),
    }
