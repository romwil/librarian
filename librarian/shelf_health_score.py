"""Shelf health score — living pulse + one tend action (weather, not a KPI)."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

_COUNT_WORDS = {1: "One", 2: "Two", 3: "Three"}

# One tend only — locked roots first, then extras → shells → blends.
_SIGNAL_ORDER = (
    "shelf_health",
    "extra_files",
    "unshelved_shells",
    "comic_book_blends",
)


def _count_word(n: int) -> str:
    return _COUNT_WORDS.get(n, str(n))


def _locked_tend(count: int) -> Dict[str, Any]:
    lead = _count_word(count)
    root = "root" if count == 1 else "roots"
    return {
        "id": "shelf_health",
        "kind": "shelf_health",
        "label": "Shelf health",
        "count": count,
        "presence": f"{lead} {root} locked for the lamp.",
        "href": "/maintain#maintain-shelf-health",
        "cta": "See locked roots",
    }


def _extra_tend(count: int) -> Dict[str, Any]:
    lead = _count_word(count)
    slip = "slip" if count == 1 else "slips"
    return {
        "id": "extra_files",
        "kind": "extra_files",
        "label": "Extra-files",
        "count": count,
        "presence": f"{lead} extra-files {slip} need clearing.",
        "href": "/maintain#maintain-review",
        "cta": "Clear extra-files",
    }


def _shells_tend(count: int) -> Dict[str, Any]:
    lead = _count_word(count)
    shell = "shell" if count == 1 else "shells"
    return {
        "id": "unshelved_shells",
        "kind": "unshelved_shells",
        "label": "Unshelved shells",
        "count": count,
        "presence": f"{lead} unshelved {shell} on the catalog.",
        "href": "/maintain#maintain-shells",
        "cta": "Purge shells",
    }


def _blends_tend(count: int) -> Dict[str, Any]:
    lead = _count_word(count)
    blend = "blend" if count == 1 else "blends"
    return {
        "id": "comic_book_blends",
        "kind": "comic_book_blends",
        "label": "Comic / book blends",
        "count": count,
        "presence": f"{lead} comic/book {blend} to split.",
        "href": "/maintain#maintain-split-mixed",
        "cta": "Split blends",
    }


_BUILDERS = {
    "shelf_health": _locked_tend,
    "extra_files": _extra_tend,
    "unshelved_shells": _shells_tend,
    "comic_book_blends": _blends_tend,
}


def pulse_weather(*, locked_roots: int = 0, other_signals: int = 0) -> str:
    """Weather mood for the shelves — never a numeric grade."""
    if max(0, int(locked_roots or 0)) > 0:
        return "needs_you"
    if max(0, int(other_signals or 0)) > 0:
        return "stirring"
    return "calm"


def pulse_presence(pulse: str, tend: Optional[Mapping[str, Any]] = None) -> str:
    """Soft weather line — presence, not a scoreboard."""
    mood = str(pulse or "calm").strip() or "calm"
    if mood == "calm":
        return "The shelves feel settled."
    detail = ""
    if tend:
        detail = str(tend.get("presence") or "").strip()
    if mood == "needs_you":
        return detail or "A root feels locked for the lamp."
    return detail or "A soft breeze through the stacks."


def shelf_health_score(
    *,
    locked_roots: int = 0,
    extra_files: int = 0,
    unshelved_shells: int = 0,
    comic_book_blends: int = 0,
) -> Dict[str, Any]:
    """Living pulse + exactly one tend action (or calm with none)."""
    counts = {
        "shelf_health": max(0, int(locked_roots or 0)),
        "extra_files": max(0, int(extra_files or 0)),
        "unshelved_shells": max(0, int(unshelved_shells or 0)),
        "comic_book_blends": max(0, int(comic_book_blends or 0)),
    }
    tend: Optional[Dict[str, Any]] = None
    for kind in _SIGNAL_ORDER:
        n = counts[kind]
        if n < 1:
            continue
        tend = _BUILDERS[kind](n)
        break

    other = (
        counts["extra_files"]
        + counts["unshelved_shells"]
        + counts["comic_book_blends"]
    )
    pulse = pulse_weather(locked_roots=counts["shelf_health"], other_signals=other)
    return {
        "pulse": pulse,
        "presence": pulse_presence(pulse, tend),
        "tend": tend,
        "ok": pulse == "calm",
        "signals": {
            "locked_roots": counts["shelf_health"],
            "extra_files": counts["extra_files"],
            "unshelved_shells": counts["unshelved_shells"],
            "comic_book_blends": counts["comic_book_blends"],
        },
    }


def assemble_shelf_health_score(
    *,
    shelf_health: Optional[Mapping[str, Any]] = None,
    extra_files: int = 0,
    unshelved_shells: int = 0,
    comic_book_blends: int = 0,
) -> Dict[str, Any]:
    """Build score from a permission report + backlog counts."""
    locked = 0
    if shelf_health:
        locked = int(shelf_health.get("locked_count") or 0)
    return shelf_health_score(
        locked_roots=locked,
        extra_files=extra_files,
        unshelved_shells=unshelved_shells,
        comic_book_blends=comic_book_blends,
    )


__all__ = [
    "assemble_shelf_health_score",
    "pulse_presence",
    "pulse_weather",
    "shelf_health_score",
]
