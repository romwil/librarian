"""Quiet ingest map — stems, twins, and kinds before the lamp shelves a dump.

Read-only inventory. Never identifies over the network, never upserts works,
never moves files. Extends the 0.4.7 pre-scan into a human beat.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from librarian.file_identity import payload_media_files
from librarian.identify import _kind_from_payload
from librarian.ingest import (
    _title_for_path,
    inventory_ingest_paths,
)

# Cap rows so a Calibre dump stays a map, not a spreadsheet.
PREVIEW_VOLUME_CAP = 36

_KIND_LABELS = {
    "book": "Book",
    "comic": "Comic",
    "magazine": "Magazine",
    "audiobook": "Audiobook",
    "music": "Music",
}

_COUNT_WORDS = {
    1: "One",
    2: "Two",
    3: "Three",
    4: "Four",
    5: "Five",
    6: "Six",
    7: "Seven",
    8: "Eight",
    9: "Nine",
    10: "Ten",
    11: "Eleven",
    12: "Twelve",
}

_TWIN_WORDS = {
    1: "one twin",
    2: "two twins",
    3: "three twins",
}


def kind_label(kind: str) -> str:
    key = str(kind or "").strip().lower()
    if not key:
        return "Unknown"
    return _KIND_LABELS.get(key, key.replace("_", " ").title())


def _count_word(n: int) -> str:
    return _COUNT_WORDS.get(n, str(n))


def ingest_preview_presence(
    *,
    volumes_found: int,
    twins: int,
    kinds: Optional[Mapping[str, int]] = None,
) -> str:
    """Warm invitation — never a KPI strip."""
    n = max(0, int(volumes_found or 0))
    twin_n = max(0, int(twins or 0))
    if n < 1:
        return "Nothing to shelve here — empty or only junk."

    lead = _count_word(n)
    volume = "volume" if n == 1 else "volumes"
    base = f"{lead} {volume} wait on the map"
    if n == 1:
        base = "One volume waits on the map"

    if twin_n:
        twin_phrase = _TWIN_WORDS.get(twin_n, f"{twin_n} twins")
        base = f"{base} — {twin_phrase} to set aside"

    kind_note = _soft_kind_note(kinds or {})
    if kind_note:
        return f"{base}. {kind_note}"
    return f"{base}."


def _soft_kind_note(kinds: Mapping[str, int]) -> str:
    """One soft sentence about mix — never a scoreboard."""
    ranked = sorted(
        ((str(k), int(v or 0)) for k, v in kinds.items() if k and int(v or 0) > 0),
        key=lambda pair: (-pair[1], pair[0]),
    )
    if not ranked:
        return ""
    if len(ranked) == 1:
        label = kind_label(ranked[0][0]).lower()
        if ranked[0][1] == 1:
            return f"Looks like a {label}."
        return f"Mostly {label}s."
    top = kind_label(ranked[0][0]).lower()
    second = kind_label(ranked[1][0]).lower()
    if ranked[0][1] >= ranked[1][1] * 2:
        return f"Mostly {top}s, with a {second} among them."
    return f"A mix of {top}s and {second}s."


def _volume_row(
    target: Path,
    *,
    twin: bool,
    index: int,
) -> Dict[str, Any]:
    media = payload_media_files(target)
    kind = ""
    if media:
        kind = str(_kind_from_payload(media, target) or "")
    stem = _title_for_path(target)
    role = "twin" if twin else ("empty" if not media else "ready")
    return {
        "id": f"vol-{index}",
        "stem": stem,
        "kind": kind,
        "kind_label": kind_label(kind),
        "path": str(target),
        "files": len(media),
        "twin": twin,
        "role": role,
        "breathing": twin,
    }


def build_ingest_preview(roots: Sequence[Path]) -> Dict[str, Any]:
    """Map what Add would shelve — inventory only, no apply."""
    paths = [Path(p) for p in roots if p is not None]
    if not paths:
        return {
            "path": "",
            "volumes_found": 0,
            "files_found": 0,
            "twins": 0,
            "kinds": {},
            "volumes": [],
            "truncated": False,
            "empty": True,
            "presence": ingest_preview_presence(volumes_found=0, twins=0),
        }

    inventory = inventory_ingest_paths(paths)
    targets: List[Path] = list(inventory.get("targets") or [])
    duplicate_indexes = set(inventory.get("duplicate_indexes") or set())
    volumes_found = int(inventory.get("volumes_found") or len(targets))
    files_found = int(inventory.get("files_found") or 0)
    twins = len(duplicate_indexes)

    kinds: Dict[str, int] = {}
    volumes: List[Dict[str, Any]] = []
    truncated = False

    for index, target in enumerate(targets):
        twin = index in duplicate_indexes
        row = _volume_row(target, twin=twin, index=index)
        kind_key = str(row.get("kind") or "")
        if kind_key:
            kinds[kind_key] = kinds.get(kind_key, 0) + 1
        if len(volumes) < PREVIEW_VOLUME_CAP:
            volumes.append(row)
        else:
            truncated = True

    # Empty / junk-only dumps: inventory still yields the folder as a target.
    no_media = files_found < 1
    if no_media:
        volumes = []
        truncated = False
        volumes_found = 0
        twins = 0
        kinds = {}

    presence = ingest_preview_presence(
        volumes_found=volumes_found,
        twins=twins,
        kinds=kinds,
    )
    return {
        "path": str(paths[0]),
        "volumes_found": volumes_found,
        "files_found": files_found,
        "twins": twins,
        "kinds": kinds,
        "volumes": volumes,
        "truncated": truncated,
        "empty": no_media or volumes_found < 1,
        "presence": presence,
    }


def preview_for_path(path: Path) -> Dict[str, Any]:
    """Single-path convenience for the HTTP route."""
    return build_ingest_preview([path])
