"""Usenet / dump scene scrub for audiobook identity tokens."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from librarian.identify import tidy_title

# B0… Audible ASINs, or 10-char ASIN-like tokens tagged as asin/audible.
_ASIN_B0 = re.compile(r"\b(B0[A-Z0-9]{8})\b", re.IGNORECASE)
_ASIN_TAGGED = re.compile(
    r"(?i)\b(?:asin|audible)\s*[:\-]?\s*([A-Z0-9]{10})\b"
)
_ASIN_LEADING = re.compile(r"^(B0[A-Z0-9]{8})\b\s*[-–—:]\s*", re.IGNORECASE)

_YEAR = re.compile(r"\((19\d{2}|20\d{2})\)|\b(19\d{2}|20\d{2})\b")
_PART_COUNTER = re.compile(r"[\[(]\s*\d{1,3}\s*/\s*\d{1,3}\s*[\])]")
_BARE_PART = re.compile(r"\b\d{1,3}\s*/\s*\d{1,3}\b")
_DISC_PART = re.compile(
    r"(?i)\b(?:part|cd|disc|disk)\s*(?:of\s*)?\d+(?:\s*(?:of|/)\s*\d+)?\b"
)
_BITRATE = re.compile(r"(?i)\b\d{2,3}\s?k(?:bps|b/?s)?\b|\bvbr\b|\bcbr\b")
_GROUP_TAIL = re.compile(r"(?i)\s*-\s*[A-Z][A-Z0-9]{1,23}$")
_RELEASE_GROUP = re.compile(
    r"(?i)\b(?:audiobook|ebook|mp3|m4b|flac)\-[A-Za-z0-9]{2,24}\b"
)
_AUTHOR_TITLE_SEP = re.compile(r"(?:\s+-\s+|[\.]+-[\.]+|\s+-[\.]+|[\.]+-\s+)")
_INITIALS = re.compile(r"\b(?:[A-Za-z]\.){1,4}")
_NOISE_WORD = re.compile(
    r"(?i)\b(?:"
    r"audio[\.\s_\-]*book|audiobook|unabridged|abridged|retail|proper|repack|"
    r"web[\.\-]?rip|m4b|mp3|flac|m4a|aac|ogg|opus|nfo|sample|proof|par2"
    r")\b"
)
_NARRATED_BY = re.compile(
    r"(?i)(?:\(|\[)\s*(?:narrated\s+by|read\s+by|narrator\s*:)\s*"
    r"(?P<who>[^)\]]{2,})(?:\)|\])"
)
_NARRATED_INLINE = re.compile(
    r"(?i)\b(?:narrated\s+by|read\s+by|narrator\s*:)\s+(?P<who>[A-Za-z][A-Za-z .'-]{1,60})"
)
_SERIES_BOOK = re.compile(
    r"(?i)^(?P<series>.+?)\s+(?:book|bk)\s*(?P<num>\d{1,2})\s+(?P<title>.+)$"
)
_SERIES_HASH = re.compile(
    r"(?i)^(?P<series>.+?)\s+#\s*(?P<num>\d{1,2})\s+(?P<title>.+)$"
)
_AUTHOR_TITLE = re.compile(r"\s+-\s+")


@dataclass
class AudiobookTokens:
    author: str = ""
    title: str = ""
    narrator: str = ""
    series_name: str = ""
    series_index: str = ""
    year: Optional[int] = None
    asin: str = ""
    raw: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def extract_asin(text: str) -> str:
    """Return a plausible Audible ASIN from text. Never invents one."""
    raw = text or ""
    tagged = _ASIN_TAGGED.search(raw)
    if tagged:
        return tagged.group(1).upper()
    hit = _ASIN_B0.search(raw)
    if hit:
        return hit.group(1).upper()
    leading = _ASIN_LEADING.match(raw.strip())
    if leading:
        return leading.group(1).upper()
    return ""


def _scrub_noise(text: str) -> str:
    cleaned = _PART_COUNTER.sub(" ", text or "")
    cleaned = _BARE_PART.sub(" ", cleaned)
    cleaned = _DISC_PART.sub(" ", cleaned)
    cleaned = _BITRATE.sub(" ", cleaned)
    cleaned = _RELEASE_GROUP.sub(" ", cleaned)
    cleaned = _NOISE_WORD.sub(" ", cleaned)
    cleaned = _GROUP_TAIL.sub("", cleaned)
    cleaned = re.sub(r"[\[\]()]+", " ", cleaned)
    # Keep Author - Title separators; do not collapse spaced hyphens.
    cleaned = re.sub(r"(?<!\s)-(?!\s)", " ", cleaned)
    # Preserve initials (N.K. / E.) while turning other dots into spaces.
    held: list[str] = []

    def _hold(match: re.Match[str]) -> str:
        held.append(match.group(0))
        return f"\x00{len(held) - 1}\x00"

    cleaned = _INITIALS.sub(_hold, cleaned)
    cleaned = re.sub(r"\.+", " ", cleaned)
    cleaned = re.sub(r"_+", " ", cleaned)
    for index, token in enumerate(held):
        cleaned = cleaned.replace(f"\x00{index}\x00", token)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned


def _pull_narrator(text: str) -> tuple[str, str]:
    match = _NARRATED_BY.search(text)
    if match is None:
        match = _NARRATED_INLINE.search(text)
    if not match:
        return text, ""
    narrator = tidy_title(match.group("who")).strip(" .,-")
    remainder = tidy_title(text[: match.start()] + " " + text[match.end() :])
    # Restore Author - Title if tidy collapsed the hyphen.
    remainder = re.sub(r"\s+-\s+", " - ", remainder)
    if " - " not in remainder and match.start() > 0:
        # Re-read from original left of match which still has delimiters.
        left = text[: match.start()]
        left = re.sub(r"[\.\s_]*-[\.\s_]*", " - ", left)
        left = re.sub(r"[\.\_]+", " ", left)
        left = re.sub(r"\s+", " ", left).strip(" .")
        right = text[match.end() :]
        right = re.sub(r"[\.\_]+", " ", right)
        right = re.sub(r"\s+", " ", right).strip(" .")
        remainder = tidy_title(f"{left} {right}".strip())
        if " - " not in remainder and " - " in left:
            remainder = f"{left} {right}".strip()
            remainder = re.sub(r"\s+", " ", remainder).strip()
    return remainder, narrator


def _pull_year(text: str) -> tuple[str, Optional[int]]:
    match = _YEAR.search(text or "")
    if not match:
        return text, None
    year = int(match.group(1) or match.group(2))
    # Avoid tidy_title here — it collapses Author - Title hyphens.
    remainder = _YEAR.sub(" ", text, count=1)
    remainder = re.sub(r"[\[\]()]+", " ", remainder)
    remainder = re.sub(r"\s+", " ", remainder).strip(" .")
    return remainder, year


def _pull_series(title: str) -> tuple[str, str, str]:
    for pattern in (_SERIES_BOOK, _SERIES_HASH):
        match = pattern.match(title)
        if match:
            return (
                tidy_title(match.group("title")),
                tidy_title(match.group("series")),
                str(int(match.group("num"))),
            )
    return title, "", ""


def normalize_audiobook_name(name: str) -> AudiobookTokens:
    """Parse a Usenet / folder / file name into audiobook tokens."""
    raw = (name or "").strip()
    # Drop extension-ish suffixes for stems that still include them.
    stem = re.sub(r"\.(m4b|mp3|flac|m4a|aac|ogg|opus)$", "", raw, flags=re.IGNORECASE)
    asin = extract_asin(stem)
    work = stem
    if asin:
        work = _ASIN_TAGGED.sub(" ", work)
        work = _ASIN_B0.sub(" ", work)
        work = _ASIN_LEADING.sub("", work.strip())
        work = re.sub(r"^[\s\-–—:]+", "", work).strip()

    # Preserve Author - Title (Usenet `.-.` / spaced hyphen). Do not touch Audiobook-GROUP.
    work = _AUTHOR_TITLE_SEP.sub(" - ", work)

    work, narrator = _pull_narrator(work)
    work, year = _pull_year(work)
    work = _scrub_noise(work)

    author = ""
    title = work
    # Leading "ASIN - Title - Author" (after ASIN strip → "Title - Author").
    asin_led = bool(asin and _ASIN_LEADING.match(stem.strip()))
    parts = [p.strip() for p in _AUTHOR_TITLE.split(work) if p.strip()]
    if asin_led and len(parts) >= 2:
        title = parts[0]
        author = parts[-1]
        if len(parts) > 2:
            title = " - ".join(parts[:-1]).strip()
    elif len(parts) >= 2:
        author, title = parts[0], " - ".join(parts[1:]).strip()

    # Soft-tidy without collapsing spaced hyphens already consumed.
    # Keep mid-name initials (E.) — golden fixtures expect "Raymond E. Feist".
    author = re.sub(r"\s+", " ", author).strip(" .")
    title = re.sub(r"\s+", " ", title).strip(" .")
    title, series_name, series_index = _pull_series(title)

    return AudiobookTokens(
        author=author,
        title=title or re.sub(r"\s+", " ", _scrub_noise(stem)).strip(" .") or "Untitled",
        narrator=narrator,
        series_name=series_name,
        series_index=series_index,
        year=year,
        asin=asin,
        raw=raw,
    )


def tokens_for_identity(name: str) -> Dict[str, Any]:
    """Dict suitable for fill_identity_holes / Identity fields."""
    tokens = normalize_audiobook_name(name)
    payload = tokens.as_dict()
    payload.pop("raw", None)
    return payload
