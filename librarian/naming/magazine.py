"""Magazine issue rules: ``Title No.10 2026``, ``Title 2026-09``, ``Title.2026.09``."""

from __future__ import annotations

import re
from typing import Optional

from librarian.kinds import KIND_COMIC, KIND_MAGAZINE
from librarian.naming.identity import Identity
from librarian.naming.tokens import tidy_title

MAG_NO = re.compile(
    r"^(?P<title>.+?)[\.\s]+No\.?\s*(?P<num>\d+)[\.\s]+(?P<year>19\d{2}|20\d{2})",
    re.IGNORECASE,
)
MAG_ISO = re.compile(
    r"^(?P<title>.+?)\s+(?P<year>19\d{2}|20\d{2})-(?P<month>0[1-9]|1[0-2])(?:\b.*)?$",
    re.IGNORECASE,
)
MAG_MONTH = re.compile(
    r"^(?P<title>.+?)[\.\s]+(?P<year>19\d{2}|20\d{2})[\.\s-]+(?P<month>0?[1-9]|1[0-2])",
    re.IGNORECASE,
)


def parse_magazine(stem: str, *, hinted: str, isbn: str) -> Optional[Identity]:
    """Magazine issue identity, or None when the stem has no issue shape (or is a comic)."""
    if hinted == KIND_COMIC:
        return None
    mag = MAG_NO.search(stem) or MAG_ISO.search(stem) or MAG_MONTH.search(stem)
    if not mag:
        return None
    title = tidy_title(mag.group("title"))
    year = int(mag.group("year"))
    if mag.groupdict().get("num"):
        num = int(mag.group("num"))
        index = f"{year}-{num:02d}" if 1 <= num <= 12 else f"{year}-{num}"
    else:
        index = f"{year}-{int(mag.group('month')):02d}"
    return Identity(
        kind=hinted or KIND_MAGAZINE,
        title=title,
        series_name=title,
        series_index=index,
        year=year,
        isbn=isbn,
        confidence="high" if (hinted in ("", KIND_MAGAZINE) and title and index) else "low",
        rationale="magazine issue parse",
        query_terms=[title, index],
        source="parse",
    )
