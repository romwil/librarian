"""Usenet / dump comic filename normalization (scene scrub → tokens).

See docs/superpowers/specs/2026-09-19-comic-parsing-matrix.md.
Does not call ComicVine; identify wires authority matching separately.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from librarian.identify import tidy_title

# Ripper / scene groups (trailing).
_GROUP = re.compile(
    r"(?i)[\.\s_\-]+("
    r"minutemen|megan|empire|dcp|glorith|zone[\.\-_]?empire|digital[\.\-_]?empire|"
    r"thp|dcs|glorth|darkhorse[\.\-_]?empire|comicbook[\.\-_]?empire|"
    r"ebook[\.\-_][a-z0-9]+"
    r")$"
)

# Scan / quality / archive noise (anywhere as whole tokens).
_NOISE_TOKEN = re.compile(
    r"(?i)(?:^|[\.\s_\-])("
    r"c2c|no[\.\-_]?ads|digital|hd[\.\-_]?webrip|webrip|repack|proper|retail|hybrid|"
    r"cbz|cbr|pdf|hd"
    r")(?=$|[\.\s_\-])"
)

_VARIANT = re.compile(
    r"(?i)(?:^|[\.\s_\-])("
    r"cvr[\.\s_\-]?[a-z0-9]+|cover[\.\s_\-]?[a-z0-9]+|foc|2nd[\.\s_\-]?print|3rd[\.\s_\-]?print|"
    r"variant|virgin[\.\s_\-]?cover"
    r")(?=$|[\.\s_\-])"
)

_FORMAT = re.compile(
    r"(?i)(?:^|[\.\s_\-])(tpb|omnibus|compendium|hardcover|hard[\.\-_]?cover|hc|gn|one[\.\-_]?shot|os)(?=$|[\.\s_\-])"
)

_ANNUAL = re.compile(r"(?i)(?:^|[\.\s_\-])(annual|ann)(?=$|[\.\s_\-])")

_HASH_YEAR = re.compile(
    r"(?i)^(?P<series>.+?)[\.\s_\-]+(?:#|no\.?)\s*(?P<issue>\d{1,4}(?:\.\d+)?)[\.\s_\-]*"
    r"\((?P<year>19\d{2}|20\d{2})\)(?:[\.\s_\-].*)?$"
)
_HASH = re.compile(
    r"(?i)^(?P<series>.+?)[\.\s_\-]+(?:#|no\.?)\s*(?P<issue>\d{1,4}(?:\.\d+)?)(?:[\.\s_\-].*)?$"
)
_YEAR_ISSUE = re.compile(
    r"(?i)^(?P<series>.+?)[\.\s_\-]+(?P<year>19\d{2}|20\d{2})[\.\s_\-]+(?P<issue>\d{1,4}(?:\.\d+)?)(?:[\.\s_\-].*)?$"
)
_VOLUME_ISSUE = re.compile(
    r"(?i)^(?P<series>.+?)[\.\s_\-]+v(?:ol(?:ume)?)?\.?\s*(?P<volnum>\d+)[\.\s_\-]+"
    r"(?P<issue>\d{1,4}(?:\.\d+)?)(?:[\.\s_\-].*)?$"
)
_PADDED = re.compile(
    r"(?i)^(?P<series>.+?)[\.\s_\-]+(?P<issue>0\d{1,3}|\d{3,4})(?:[\.\s_\-].*)?$"
)
_ANNUAL_ISSUE = re.compile(
    r"(?i)^(?P<series>.+?)[\.\s_\-]+(?:annual|ann)(?:[\.\s_\-]+(?P<ayear>19\d{2}|20\d{2}))?"
    r"[\.\s_\-]+(?P<issue>\d{1,4})(?:[\.\s_\-].*)?$"
)
_PAREN_YEAR = re.compile(r"\((?P<year>19\d{2}|20\d{2})\)")
_BARE_YEAR = re.compile(r"(?:^|[\.\s_\-])(?P<year>19\d{2}|20\d{2})(?:$|[\.\s_\-])")
_SUBTITLE_AFTER_VOL = re.compile(
    r"(?i)^(?P<series>.+?)[\.\s_\-]+vol(?:ume)?\.?\s*(?P<volnum>\d+)[\.\s_\-]+"
    r"(?P<subtitle>.+?)(?:[\.\s_\-]+\((?P<year>19\d{2}|20\d{2})\))?(?:[\.\s_\-]+(?P<fmt>tpb|omnibus|compendium|hc|gn))?$"
)


@dataclass
class ComicTokens:
    series: str = ""
    volume_year: Optional[int] = None
    issue: str = ""
    year: Optional[int] = None
    variant: str = ""
    annual: bool = False
    format: str = ""  # tpb / gn / compendium / hc / oneshot / ""
    subtitle: str = ""
    volume_number: Optional[int] = None
    raw: str = ""
    scrubbed: str = ""
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _norm_issue(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    if "." in text:
        whole, frac = text.split(".", 1)
        if whole.isdigit() and frac.isdigit():
            return f"{int(whole)}.{frac}"
        return text
    if text.isdigit():
        return str(int(text))
    return text


def scrub_comic_stem(stem: str) -> tuple[str, List[str], str, str]:
    """Strip noise/groups/variants. Returns (scrubbed, notes, variant, format)."""
    text = str(stem or "").strip()
    notes: List[str] = []
    variant = ""
    fmt = ""

    group = _GROUP.search(text)
    if group:
        notes.append(f"group:{group.group(1)}")
        text = text[: group.start()].rstrip(".-_ ")

    for match in list(_VARIANT.finditer(text)):
        variant = re.sub(r"[\.\-_]+", " ", match.group(1)).strip()
        notes.append(f"variant:{variant}")
    text = _VARIANT.sub(" ", text)

    for match in list(_FORMAT.finditer(text)):
        fmt = match.group(1).lower().replace(".", "").replace("-", "").replace("_", "")
        if fmt in ("hardcover", "hardcover"):
            fmt = "hc"
        if fmt in ("oneshot",):
            fmt = "oneshot"
        notes.append(f"format:{fmt}")
    text = _FORMAT.sub(" ", text)

    text = _NOISE_TOKEN.sub(" ", text)
    text = re.sub(r"[\.\s_\-]{2,}", ".", text).strip(".-_ ")
    return text, notes, variant, fmt


def normalize_comic_name(name: str) -> ComicTokens:
    """Parse a Usenet / folder / file stem into comic tokens."""
    raw = str(name or "").strip()
    # Drop extension-like suffix if present.
    stem = re.sub(r"(?i)\.(cbz|cbr|cbt|pdf)$", "", raw)
    scrubbed, notes, variant, fmt = scrub_comic_stem(stem)
    tokens = ComicTokens(raw=raw, scrubbed=scrubbed, variant=variant, format=fmt, notes=list(notes))

    annual_hit = _ANNUAL.search(scrubbed)
    if annual_hit:
        tokens.annual = True

    match = _ANNUAL_ISSUE.search(scrubbed)
    if match:
        tokens.series = tidy_title(match.group("series"))
        tokens.issue = f"Annual {_norm_issue(match.group('issue'))}"
        if match.group("ayear"):
            tokens.year = int(match.group("ayear"))
        tokens.annual = True
        return tokens

    if fmt in ("tpb", "omnibus", "compendium", "hc", "gn", "oneshot") or not re.search(
        r"(?i)(?:#|no\.?)\s*\d", scrubbed
    ):
        sub = _SUBTITLE_AFTER_VOL.search(scrubbed)
        if sub and (fmt or "vol" in scrubbed.lower()):
            tokens.series = tidy_title(sub.group("series"))
            tokens.volume_number = int(sub.group("volnum"))
            tokens.subtitle = tidy_title(sub.group("subtitle"))
            if sub.group("year"):
                tokens.year = int(sub.group("year"))
            if sub.group("fmt"):
                tokens.format = sub.group("fmt").lower()
            return tokens

    for pattern, kind in (
        (_HASH_YEAR, "hash_year"),
        (_YEAR_ISSUE, "year_issue"),
        (_VOLUME_ISSUE, "volume_issue"),
        (_HASH, "hash"),
        (_PADDED, "padded"),
    ):
        hit = pattern.search(scrubbed)
        if not hit:
            continue
        tokens.series = tidy_title(hit.group("series"))
        tokens.issue = _norm_issue(hit.group("issue"))
        if "year" in hit.groupdict() and hit.groupdict().get("year"):
            year = int(hit.group("year"))
            tokens.year = year
            if kind == "year_issue":
                # Bare YYYY before issue is treated as volume start year (Saga.2012.001).
                tokens.volume_year = year
        if kind == "volume_issue" and hit.groupdict().get("volnum"):
            tokens.volume_number = int(hit.group("volnum"))
        # Paren year may still appear after hash-only matches.
        if tokens.year is None:
            paren = _PAREN_YEAR.search(scrubbed)
            if paren:
                tokens.year = int(paren.group("year"))
        return tokens

    # Fallback: series + optional years only (GN / titled dump).
    series = scrubbed
    paren = _PAREN_YEAR.search(series)
    if paren:
        tokens.year = int(paren.group("year"))
        series = (series[: paren.start()] + series[paren.end() :]).strip(".-_ ")
    else:
        bare = _BARE_YEAR.search(series)
        if bare:
            tokens.year = int(bare.group("year"))
            tokens.volume_year = tokens.year
            series = (series[: bare.start()] + series[bare.end() :]).strip(".-_ ")
    series = _ANNUAL.sub(" ", series)
    series = re.sub(r"[\.\s_\-]{2,}", ".", series).strip(".-_ ")
    tokens.series = tidy_title(series) if series else tidy_title(scrubbed)
    if tokens.annual and not tokens.issue:
        tokens.issue = "Annual 1"
    return tokens


def comic_identity_fields(tokens: ComicTokens) -> Dict[str, Any]:
    """Map tokens into Identity-compatible fields (additive keys included)."""
    series = tokens.series
    issue = tokens.issue
    title = ""
    if series and issue:
        title = f"{series} #{issue}" if not str(issue).lower().startswith("annual") else f"{series} {issue}"
    elif series and tokens.subtitle:
        title = f"{series} - {tokens.subtitle}"
    elif series:
        title = series
    out: Dict[str, Any] = {
        "kind": "comic",
        "series_name": series,
        "series_index": issue,
        "title": title,
        "year": tokens.year,
        "publisher": "",
        "volume_year": tokens.volume_year,
        "comic_format": tokens.format,
        "comic_subtitle": tokens.subtitle,
        "comic_variant": tokens.variant,
        "comic_volume_number": tokens.volume_number,
        "source": "comic_normalize",
        "rationale": "comic scene normalize",
    }
    return out
