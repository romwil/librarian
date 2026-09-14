"""Local gap math: magazine YYYY-MM holes and comic issue-number holes."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Sequence

from librarian.db import Database
from librarian.kinds import KIND_COMIC, KIND_MAGAZINE

_MONTH = re.compile(r"^(?P<year>\d{4})-(?P<month>0[1-9]|1[0-2])$")
_INT = re.compile(r"^(\d+)$")


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


def local_gaps(db: Database) -> List[Dict[str, Any]]:
    rails: List[Dict[str, Any]] = []
    for kind in (KIND_MAGAZINE, KIND_COMIC):
        for name in db.series_names(kind):
            card = gaps_for_series(db, kind=kind, series_name=name)
            if card["missing"]:
                rails.append(card)
    return rails


def gap_cards(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    for row in rows:
        for missing in row.get("missing") or []:
            cards.append(
                {
                    "kind": row["kind"],
                    "series_name": row["series_name"],
                    "missing_index": missing,
                    "title": f"{row['series_name']} {missing}",
                    "provenance": "local",
                }
            )
    return cards
