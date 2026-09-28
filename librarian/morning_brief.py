"""Owner Maintain morning desk — tend ranking, not a KPI strip."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

MORNING_BRIEF_LIMIT = 3

_COUNT_WORDS = {1: "One", 2: "Two", 3: "Three"}
_TEND_WORDS = {2: "two", 3: "three"}

# Priority after stuck jobs: locked roots → Holds → extras → shells → blends.
_SIGNAL_ORDER = (
    "shelf_health",
    "holds_desk",
    "extra_files",
    "unshelved_shells",
    "comic_book_blends",
)


def _count_word(n: int) -> str:
    return _COUNT_WORDS.get(n, str(n))


def morning_tend_presence(count: int) -> str:
    """Invitation to tend — never a KPI strip."""
    n = max(0, int(count or 0))
    if n < 1:
        return "The shelves are quiet this morning."
    if n == 1:
        return "Tend this one."
    word = _TEND_WORDS.get(n)
    if word:
        return f"Tend these {word}."
    return "Tend these few."


def _stuck_job_item(job: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    job_id = str(job.get("id") or "").strip()
    label = str(job.get("label") or "").strip()
    if not job_id or not label:
        return None
    return {
        "id": f"stuck:{job_id}",
        "kind": "stuck_job",
        "label": label,
        "count": 0,
        "presence": str(job.get("detail") or "Still working — the lamp will finish.").strip(),
        "href": str(job.get("href") or "").strip(),
        "cta": str(job.get("cta") or "Watch the dock").strip(),
        "breathing": True,
    }


def _shelf_health_item(count: int) -> Dict[str, Any]:
    lead = _count_word(count)
    root = "root" if count == 1 else "roots"
    return {
        "id": "shelf_health",
        "kind": "shelf_health",
        "label": "Shelf health",
        "count": count,
        "presence": f"{lead} {root} locked for the lamp.",
        "href": "/maintain#maintain-shelf-health",
        "cta": "Check Shelf health",
        "breathing": False,
    }


def _holds_desk_item(count: int) -> Dict[str, Any]:
    lead = _count_word(count)
    slip = "slip" if count == 1 else "slips"
    return {
        "id": "holds_desk",
        "kind": "holds_desk",
        "label": "Holds desk",
        "count": count,
        "presence": f"{lead} {slip} wait at the Holds desk.",
        "href": "/review",
        "cta": "Open Holds desk",
        "breathing": False,
    }


def _extra_files_item(count: int) -> Dict[str, Any]:
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
        "breathing": False,
    }


def _shells_item(count: int) -> Dict[str, Any]:
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
        "breathing": False,
    }


def _blends_item(count: int) -> Dict[str, Any]:
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
        "breathing": False,
    }


_BUILDERS = {
    "shelf_health": _shelf_health_item,
    "holds_desk": _holds_desk_item,
    "extra_files": _extra_files_item,
    "unshelved_shells": _shells_item,
    "comic_book_blends": _blends_item,
}


def morning_brief(
    *,
    stuck_jobs: Sequence[Mapping[str, Any]] = (),
    locked_roots: int = 0,
    holds_desk_slips: int = 0,
    extra_files: int = 0,
    unshelved_shells: int = 0,
    comic_book_blends: int = 0,
    limit: int = MORNING_BRIEF_LIMIT,
) -> Dict[str, Any]:
    """Rank at most ``limit`` tend items for the Maintain morning desk.

    Priority (highest first): stuck jobs breathing → locked shelf roots →
    Holds desk slips → extra-files → unshelved shells → comic/book blends.
    Quiet empty when nothing needs tending — never a KPI strip.
    """
    cap = max(0, int(limit))
    items: List[Dict[str, Any]] = []
    quiet = {
        "items": [],
        "empty": True,
        "presence": morning_tend_presence(0),
        "title": "Morning shelf brief",
        "lede": "Nothing asking for your hand.",
    }
    if cap < 1:
        return quiet

    for raw in stuck_jobs or []:
        if len(items) >= cap:
            break
        row = _stuck_job_item(raw)
        if row:
            items.append(row)

    counts: Mapping[str, int] = {
        "shelf_health": max(0, int(locked_roots or 0)),
        "holds_desk": max(0, int(holds_desk_slips or 0)),
        "extra_files": max(0, int(extra_files or 0)),
        "unshelved_shells": max(0, int(unshelved_shells or 0)),
        "comic_book_blends": max(0, int(comic_book_blends or 0)),
    }
    for kind in _SIGNAL_ORDER:
        if len(items) >= cap:
            break
        n = counts[kind]
        if n < 1:
            continue
        items.append(_BUILDERS[kind](n))

    if not items:
        return quiet
    return {
        "items": items,
        "empty": False,
        "presence": morning_tend_presence(len(items)),
        "title": "Morning shelf brief",
        "lede": "A desk in morning light — tend these, not a scoreboard.",
    }


def assemble_morning_brief(
    *,
    shelf_health: Optional[Mapping[str, Any]] = None,
    stuck_jobs: Sequence[Mapping[str, Any]] = (),
    holds_desk_slips: int = 0,
    extra_files: int = 0,
    unshelved_shells: int = 0,
    comic_book_blends: int = 0,
    limit: int = MORNING_BRIEF_LIMIT,
) -> Dict[str, Any]:
    """Build a morning brief from a shelf-health report + backlog counts."""
    locked = 0
    if shelf_health:
        locked = int(shelf_health.get("locked_count") or 0)
    return morning_brief(
        stuck_jobs=stuck_jobs,
        locked_roots=locked,
        holds_desk_slips=holds_desk_slips,
        extra_files=extra_files,
        unshelved_shells=unshelved_shells,
        comic_book_blends=comic_book_blends,
        limit=limit,
    )


__all__ = [
    "MORNING_BRIEF_LIMIT",
    "assemble_morning_brief",
    "morning_brief",
    "morning_tend_presence",
]
