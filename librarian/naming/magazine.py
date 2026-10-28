"""Magazine issue rules: ``Title No.10 2026``, ``Title 2026-09``, ``Title.2026.09``.

Also the cover (first page, CBZ or PDF) and the publication+issue-date match key used
by enrich to recognize "the same issue" without any external magazine API.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

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


def _masthead_match_key(value: Any) -> str:
    """Accent/case-insensitive masthead key — deferred import avoids a naming/identity cycle."""
    from librarian.identity.titles import title_match_key

    return title_match_key(value)


def magazine_match_key(masthead: Any, issue_index: Any) -> str:
    """Publication + issue-date key. Empty unless both the masthead and issue resolve."""
    base = _masthead_match_key(masthead)
    issue = str(issue_index or "").strip().lower()
    if not base or not issue:
        return ""
    return f"{base}::{issue}"


def magazine_identity_matches(work: Mapping[str, Any], parsed: Identity) -> bool:
    """True when a fresh filename re-parse names the same publication and issue as *work*.

    This is the magazine stand-in for a strong identifier match: there is no external
    magazine API, so a correction is only trusted when the masthead and the issue
    (month/year or number) it re-derives agree with what is already on the shelf.
    """
    work_key = magazine_match_key(
        work.get("series_name") or work.get("title"), work.get("series_index")
    )
    parsed_key = magazine_match_key(parsed.series_name or parsed.title, parsed.series_index)
    return bool(work_key and parsed_key and work_key == parsed_key)


def extract_magazine_cover(
    folder: Path,
    *,
    files: Optional[Sequence[Path]] = None,
    runner: Any = None,
) -> Optional[Path]:
    """Write cover.jpg from the first page — CBZ page one, else a rasterized PDF page one.

    No external API. Fail-soft: missing tools or unreadable files simply skip.
    """
    from librarian.convert import run_tool as default_runner
    from librarian.convert import which_pdftoppm
    from librarian.covers import MIN_IMAGE_BYTES, cover_from_cbz

    folder = Path(folder)
    if not folder.is_dir():
        return None
    dest = folder / "cover.jpg"
    try:
        if dest.is_file() and dest.stat().st_size >= MIN_IMAGE_BYTES:
            return dest
    except OSError:
        return None

    try:
        candidates = list(files) if files is not None else sorted(folder.glob("*"))
    except OSError:
        candidates = []

    for cbz in sorted(Path(p) for p in candidates if Path(p).suffix.lower() == ".cbz"):
        written = cover_from_cbz(cbz, dest)
        if written is not None:
            return written

    pdf_paths = sorted(Path(p) for p in candidates if Path(p).suffix.lower() == ".pdf")
    tool = which_pdftoppm()
    if not tool or not pdf_paths:
        return None
    pdf = pdf_paths[0]
    run = runner or default_runner
    prefix = folder / f".librarian-magazine-cover-{pdf.stem}"
    try:
        result = run(
            [tool, "-jpeg", "-f", "1", "-l", "1", "-r", "150", str(pdf), str(prefix)],
            cwd=folder,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if getattr(result, "returncode", 1) != 0:
        return None
    try:
        produced = sorted(folder.glob(f"{prefix.name}*.jpg"))
    except OSError:
        produced = []
    if not produced:
        return None
    try:
        dest.write_bytes(produced[0].read_bytes())
    except OSError:
        return None
    finally:
        for page in produced:
            page.unlink(missing_ok=True)
    return dest
