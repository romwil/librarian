"""Local gap math: magazine YYYY-MM, comic issues, audiobook parts, music tracks."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Sequence

from librarian.db import Database
from librarian.kinds import KIND_AUDIOBOOK, KIND_COMIC, KIND_MAGAZINE, KIND_MUSIC

_MONTH = re.compile(r"^(?P<year>\d{4})-(?P<month>0[1-9]|1[0-2])$")
_INT = re.compile(r"^(\d+)$")
_AUDIO_PART = re.compile(r"\b(?:part|cd|disc)\s*(\d+)\b", re.IGNORECASE)
_TRACK = re.compile(r"^(?:(?:track|tr|t)[\s._-]*)?(\d{1,2})\b", re.IGNORECASE)


def magazine_month_holes(indexes: Sequence[str]) -> List[str]:
    """Return missing YYYY-MM values strictly between the owned min and max."""
    owned: List[tuple[int, int]] = []
    for raw in indexes:
        match = _MONTH.match(str(raw or "").strip())
        if not match:
            continue
        owned.append((int(match.group("year")), int(match.group("month"))))
    if len(owned) < 2:
        return []
    owned = sorted(set(owned))
    start_y, start_m = owned[0]
    end_y, end_m = owned[-1]
    have = set(owned)
    missing: List[str] = []
    year, month = start_y, start_m
    while (year, month) <= (end_y, end_m):
        if (year, month) not in have:
            missing.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            month = 1
            year += 1
    return missing


def comic_issue_holes(indexes: Sequence[object]) -> List[str]:
    """Return missing integer issue numbers between owned min and max."""
    return integer_holes(indexes)


def integer_holes(indexes: Sequence[object]) -> List[str]:
    owned: List[int] = []
    for raw in indexes:
        text = str(raw or "").strip()
        match = _INT.match(text)
        if not match:
            continue
        owned.append(int(match.group(1)))
    if len(owned) < 2:
        return []
    low, high = min(owned), max(owned)
    have = set(owned)
    return [str(n) for n in range(low, high + 1) if n not in have]


def audiobook_part_holes(filenames: Sequence[str]) -> List[str]:
    """Missing part/cd/disc numbers between owned min and max."""
    parts = []
    for name in filenames:
        match = _AUDIO_PART.search(str(name or ""))
        if match:
            parts.append(match.group(1))
    return integer_holes(parts)


def music_track_holes(filenames: Sequence[str]) -> List[str]:
    """Missing leading track numbers on an owned album."""
    tracks = []
    for name in filenames:
        stem = str(name or "")
        match = _TRACK.match(stem)
        if match:
            tracks.append(str(int(match.group(1))))
    return integer_holes(tracks)


def gaps_for_series(
    db: Database,
    *,
    kind: str,
    series_name: str,
) -> Dict[str, Any]:
    works = db.works_for_series(kind=kind, series_name=series_name)
    indexes = [str(work.get("series_index") or "") for work in works]
    if kind == KIND_MAGAZINE:
        missing = magazine_month_holes(indexes)
    elif kind == KIND_COMIC:
        missing = comic_issue_holes(indexes)
    else:
        missing = []
    return {
        "kind": kind,
        "series_name": series_name,
        "owned": [work["id"] for work in works],
        "owned_indexes": indexes,
        "missing": missing,
    }


def _file_gaps(db: Database, kind: str, hole_fn, label: str) -> List[Dict[str, Any]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    work_ids: dict[str, list[str]] = defaultdict(list)
    for row in db.files_named_for_kind(kind):
        key = str(row.get("series_name") or row.get("work_title") or "").strip()
        if not key:
            continue
        grouped[key].append(str(row.get("filename") or ""))
        work_id = str(row.get("work_id") or row.get("work_pk") or "")
        if work_id and work_id not in work_ids[key]:
            work_ids[key].append(work_id)
    rails: List[Dict[str, Any]] = []
    for name, filenames in grouped.items():
        missing = hole_fn(filenames)
        if missing:
            rails.append(
                {
                    "kind": kind,
                    "series_name": name,
                    "owned": work_ids[name],
                    "owned_indexes": filenames,
                    "missing": missing,
                    "provenance": "local",
                    "gap_type": label,
                }
            )
    return rails


def local_gaps(db: Database) -> List[Dict[str, Any]]:
    rails: List[Dict[str, Any]] = []
    for kind in (KIND_MAGAZINE, KIND_COMIC):
        for name in db.series_names(kind):
            card = gaps_for_series(db, kind=kind, series_name=name)
            if card["missing"]:
                rails.append(card)
    rails.extend(_file_gaps(db, KIND_AUDIOBOOK, audiobook_part_holes, "audiobook_parts"))
    rails.extend(_file_gaps(db, KIND_MUSIC, music_track_holes, "music_tracks"))
    return rails


def gap_cards(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    for row in rows:
        for missing in row.get("missing") or []:
            card = {
                "kind": row["kind"],
                "series_name": row["series_name"],
                "missing_index": missing,
                "title": f"{row['series_name']} {missing}",
                "provenance": row.get("provenance") or "local",
            }
            if row.get("gap_type"):
                card["gap_type"] = row["gap_type"]
            cards.append(card)
    return cards
