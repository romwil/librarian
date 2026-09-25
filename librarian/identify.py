"""Identify completed downloads. Auto-organize only when confident."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Union

from librarian.kinds import (
    ALL_KINDS,
    KIND_AUDIOBOOK,
    KIND_BOOK,
    KIND_COMIC,
    KIND_MAGAZINE,
    KIND_MUSIC,
    kind_from_newznab,
)
from librarian.review_reasons import (
    REVIEW_AUDNEXUS_AMBIGUOUS as REVIEW_AUDNEXUS_AMBIGUOUS,
)
from librarian.review_reasons import (
    REVIEW_AUDNEXUS_UNMATCHED as REVIEW_AUDNEXUS_UNMATCHED,
)
from librarian.review_reasons import (
    REVIEW_COLLISION as REVIEW_COLLISION,
)
from librarian.review_reasons import (
    REVIEW_COMICVINE_AMBIGUOUS as REVIEW_COMICVINE_AMBIGUOUS,
)
from librarian.review_reasons import (
    REVIEW_COMICVINE_UNMATCHED as REVIEW_COMICVINE_UNMATCHED,
)
from librarian.review_reasons import (
    REVIEW_CONVERT as REVIEW_CONVERT,
)
from librarian.review_reasons import (
    REVIEW_EXTRA as REVIEW_EXTRA,
)
from librarian.review_reasons import (
    REVIEW_LOW as REVIEW_LOW,
)
from librarian.review_reasons import (
    REVIEW_MISSING_FOLDER as REVIEW_MISSING_FOLDER,
)
from librarian.review_reasons import (
    REVIEW_NO_PAYLOAD as REVIEW_NO_PAYLOAD,
)
from librarian.review_reasons import (
    REVIEW_UNEXPECTED as REVIEW_UNEXPECTED,
)
from librarian.review_reasons import (
    REVIEW_UNKNOWN as REVIEW_UNKNOWN,
)
from librarian.review_reasons import (
    REVIEW_UNPACK_STUCK as REVIEW_UNPACK_STUCK,
)
from librarian.review_reasons import (
    UNPACK_STUCK as UNPACK_STUCK,
)

COMPLETE_ROOT_FALLBACKS = ("/data/usenet/complete",)

_DOT_GROUP = re.compile(r"[\.\-_]+")
_ISBN = re.compile(r"\b(?:97[89][-\s]?)?(?:\d[-\s]?){9}[\dXx]\b")
_AUDIOBOOK_HINT = re.compile(r"(?i)\baudio[\.\s_\-]*book\b|\bunabridged\b|\bm4b\b")
_DUMP_RELEASE_TOKEN = re.compile(
    r"(?i)\b("
    r"audio[\.\s_\-]*book|ebook|epub|mobi|azw3|hybrid|retail|proper|repack|"
    r"bitbook|comic|cbr|cbz|mp3|flac|m4b|unabridged|abridged|web[\.\-]?rip"
    r")\b"
)
_COMIC_HASH_YEAR = re.compile(
    r"^(?P<series>.+?)[\.\s]+(?:#|No\.?)\s*(?P<issue>\d{1,4})\s*\((?P<year>19\d{2}|20\d{2})\)(?:[\.\s].*)?$",
    re.IGNORECASE,
)
_COMIC_HASH = re.compile(
    r"^(?P<series>.+?)[\.\s]+(?:#|No\.?)\s*(?P<issue>\d{1,4})(?:[\.\s].*)?$",
    re.IGNORECASE,
)
_COMIC_VOLUME = re.compile(
    r"^(?P<series>.+?)[\.\s]+v(?:ol(?:ume)?)?\.?\s*\d+[\.\s]+(?P<issue>\d{1,4})(?:[\.\s].*)?$",
    re.IGNORECASE,
)
_COMIC_YEAR_ISSUE = re.compile(
    r"^(?P<series>.+?)[\.\s]+(?P<year>19\d{2}|20\d{2})[\.\s]+(?P<issue>\d{1,4})(?:[\.\s].*)?$",
    re.IGNORECASE,
)
_COMIC_PADDED = re.compile(
    r"^(?P<series>.+?)[\.\s]+(?P<issue>0\d{1,3}|\d{3,4})(?:[\.\s].*)?$",
    re.IGNORECASE,
)
_MAG_NO = re.compile(
    r"^(?P<title>.+?)[\.\s]+No\.?\s*(?P<num>\d+)[\.\s]+(?P<year>19\d{2}|20\d{2})",
    re.IGNORECASE,
)
_MAG_ISO = re.compile(
    r"^(?P<title>.+?)\s+(?P<year>19\d{2}|20\d{2})-(?P<month>0[1-9]|1[0-2])(?:\b.*)?$",
    re.IGNORECASE,
)
_MAG_MONTH = re.compile(
    r"^(?P<title>.+?)[\.\s]+(?P<year>19\d{2}|20\d{2})[\.\s-]+(?P<month>0?[1-9]|1[0-2])",
    re.IGNORECASE,
)
_EBOOK_GROUP = re.compile(r"[\.\s]eBook(?:-|\.)(?P<group>[A-Za-z0-9]+)", re.IGNORECASE)
_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")
_AUDIO_PART = re.compile(r"\b(?:part|cd|disc)\s*(\d+)\b", re.IGNORECASE)
# yEnc / article counters — never feed these through pathlib ( '/' is a separator ).
_PART_COUNTER = re.compile(r"[\[(]\s*\d{1,3}\s*/\s*\d{1,3}\s*[\])]")
_BARE_PART_COUNTER = re.compile(r"\b\d{1,3}\s*/\s*\d{1,3}\b")
_MUSIC_TRACK = re.compile(
    r"^(?:(?:cd|disc|disk)\s*(?P<disc>\d+)[\.\s-]+)?(?P<num>\d{1,3})[\.\s-]+(?P<title>.+)$",
    re.IGNORECASE,
)
_MBID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

MEDIA_EXTENSIONS = {
    ".epub",
    ".pdf",
    ".mobi",
    ".azw3",
    ".kepub",
    ".cbz",
    ".cbr",
    ".cbt",
    ".m4b",
    ".mp3",
    ".flac",
    ".m4a",
    ".ogg",
    ".opus",
}
# Alternate ebook encodings of one title (SAB multi-format / Calibre).
BOOK_FORMAT_EXTENSIONS = {".epub", ".pdf", ".mobi", ".azw3", ".kepub"}
# Clear ebook encodings (not PDF — PDF is comic-or-book depending on siblings).
EBOOK_FORMAT_EXTENSIONS = {".epub", ".mobi", ".azw3", ".kepub"}
COMIC_ARCHIVE_EXTENSIONS = {".cbz", ".cbr", ".cbt"}
SIDECAR_NAMES = {"metadata.opf", "comicinfo.xml", "cover.jpg", "cover.png", "nfo"}
JUNK_EXTENSIONS = {".par2", ".nzb", ".nfo", ".sfv", ".srr", ".url"}
JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
ARCHIVE_EXTENSIONS = {".rar", ".7z"}
_STEM_EXTENSIONS = MEDIA_EXTENSIONS | JUNK_EXTENSIONS | ARCHIVE_EXTENSIONS | {
    ".zip",
    ".gz",
    ".txt",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}
HOST_DATA_PREFIX = "/mnt/user/data/"
CONTAINER_DATA_PREFIX = "/data/"
DOWNLOADS_PREFIXES = (
    "/downloads/complete/",
    "/downloads/downloads/",
    "/downloads/",
)


@dataclass
class Identity:
    kind: str
    title: str
    author: str = ""
    series_name: str = ""
    series_index: str = ""
    year: Optional[int] = None
    isbn: str = ""
    asin: str = ""
    mbid: str = ""
    album: str = ""
    track_title: str = ""
    tracknumber: str = ""
    discnumber: str = ""
    recording_mbid: str = ""
    publisher: str = ""
    description: str = ""
    genre: str = ""
    narrator: str = ""
    volume_year: Optional[int] = None
    comic_format: str = ""
    comic_subtitle: str = ""
    comic_variant: str = ""
    comicvine_volume_id: Optional[int] = None
    comicvine_issue_id: Optional[int] = None
    penciller: str = ""
    inker: str = ""
    colorist: str = ""
    cover_artist: str = ""
    letterer: str = ""
    web: str = ""
    month: Optional[int] = None
    day: Optional[int] = None
    confidence: str = "low"
    rationale: str = ""
    query_terms: List[str] = field(default_factory=list)
    review_reason: Optional[str] = None
    source: str = "parse"
    match_candidates: List[Dict[str, Any]] = field(default_factory=list)
    match_confidence: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "author": self.author,
            "series_name": self.series_name,
            "series_index": self.series_index,
            "year": self.year,
            "isbn": self.isbn,
            "asin": self.asin,
            "mbid": self.mbid,
            "album": self.album,
            "track_title": self.track_title,
            "tracknumber": self.tracknumber,
            "discnumber": self.discnumber,
            "recording_mbid": self.recording_mbid,
            "publisher": self.publisher,
            "description": self.description,
            "genre": self.genre,
            "narrator": self.narrator,
            "volume_year": self.volume_year,
            "comic_format": self.comic_format,
            "comic_subtitle": self.comic_subtitle,
            "comic_variant": self.comic_variant,
            "comicvine_volume_id": self.comicvine_volume_id,
            "comicvine_issue_id": self.comicvine_issue_id,
            "penciller": self.penciller,
            "inker": self.inker,
            "colorist": self.colorist,
            "cover_artist": self.cover_artist,
            "letterer": self.letterer,
            "web": self.web,
            "month": self.month,
            "day": self.day,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "query_terms": list(self.query_terms),
            "review_reason": self.review_reason,
            "source": self.source,
            "match_candidates": list(self.match_candidates),
            "match_confidence": self.match_confidence,
        }


def tidy_title(value: str) -> str:
    text = _DOT_GROUP.sub(" ", value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def looks_like_dump_title(value: str) -> bool:
    """True for dotted Usenet dumps / release tokens that should not stay as shelf titles."""
    text = str(value or "").strip()
    if not text:
        return True
    if text.count(".") >= 3:
        return True
    if _DUMP_RELEASE_TOKEN.search(text):
        return True
    # Humanized dump: many Title Case tokens, no Author - Title separator.
    if " - " not in text and len(text) >= 48 and text.count(" ") >= 6:
        words = [w for w in text.split() if w]
        titled = sum(1 for w in words if w[:1].isupper())
        if titled >= 6 and titled >= len(words) * 0.6:
            return True
    return False


def usenet_basename(name: str) -> str:
    """Basename for Usenet subjects or real paths without splitting on [N/M] slashes."""
    text = str(name or "").strip()
    if not text:
        return ""
    normalized = text.replace("\\", "/")
    looks_like_path = (
        normalized.startswith("/")
        or bool(re.match(r"^[A-Za-z]:/", normalized))
        or "/mnt/" in normalized
        or "/data/" in normalized
        or "/downloads/" in normalized
        or "/config/" in normalized
    )
    if not looks_like_path:
        return text
    # Split on the last path slash that is not inside [] or ().
    depth = 0
    for index in range(len(normalized) - 1, -1, -1):
        char = normalized[index]
        if char in "])":
            depth += 1
        elif char in "[(":
            depth = max(0, depth - 1)
        elif char == "/" and depth == 0:
            return normalized[index + 1 :]
    return normalized


def filename_stem(name: str) -> str:
    """Strip a known extension without pathlib — Path.stem treats '/' in [6/8] as a parent path."""
    base = usenet_basename(name)
    lower = base.lower()
    for ext in sorted(_STEM_EXTENSIONS, key=len, reverse=True):
        if lower.endswith(ext):
            return base[: -len(ext)]
    if "." in base:
        head, ext = base.rsplit(".", 1)
        if ext.isalnum() and 1 <= len(ext) <= 5:
            return head
    return base


def extract_isbn(text: str) -> str:
    match = _ISBN.search(text or "")
    if not match:
        return ""
    digits = re.sub(r"[^0-9Xx]", "", match.group(0))
    return digits.upper()


def _isbn13_check_digit(core12: str) -> str:
    total = sum(int(digit) * (1 if index % 2 == 0 else 3) for index, digit in enumerate(core12))
    return str((10 - (total % 10)) % 10)


def _isbn10_check_digit(core9: str) -> str:
    total = sum(int(digit) * (10 - index) for index, digit in enumerate(core9))
    remainder = (11 - (total % 11)) % 11
    return "X" if remainder == 10 else str(remainder)


def isbn10_to_isbn13(isbn: str) -> str:
    digits = re.sub(r"[^0-9Xx]", "", isbn or "").upper()
    if len(digits) == 13 and digits.startswith(("978", "979")):
        return digits
    if len(digits) != 10:
        return ""
    body = "978" + digits[:9]
    return body + _isbn13_check_digit(body)


def isbn13_to_isbn10(isbn: str) -> str:
    digits = re.sub(r"[^0-9Xx]", "", isbn or "").upper()
    if len(digits) != 13 or not digits.startswith("978"):
        return ""
    core = digits[3:12]
    return core + _isbn10_check_digit(core)


def isbn_match_keys(*values: str) -> List[str]:
    """ISBN-10 and ISBN-13 forms for matching. Never invents a number from a title."""
    keys: List[str] = []
    seen: set[str] = set()
    for value in values:
        digits = extract_isbn(str(value or ""))
        for candidate in (digits, isbn10_to_isbn13(digits), isbn13_to_isbn10(digits)):
            if candidate and candidate not in seen:
                seen.add(candidate)
                keys.append(candidate)
    return keys


def validated_isbn(raw: str) -> str:
    """Return a check-digit-valid ISBN-10/13, else empty. Never invents digits."""
    digits = extract_isbn(raw or "")
    if not digits:
        return ""
    if len(digits) == 13 and digits.isdigit():
        if digits[-1] == _isbn13_check_digit(digits[:12]):
            return digits
        return ""
    if len(digits) == 10:
        core = digits[:9]
        if not core.isdigit():
            return ""
        if digits[-1].upper() == _isbn10_check_digit(core):
            return digits.upper()
        return ""
    return ""


def parse_usenet_name(name: str, *, category: object = None, kind: object = None) -> Identity:
    """Deterministic Usenet / folder parse. Never invents an ISBN. Filename layer is weak."""
    raw = usenet_basename(name)
    stem = filename_stem(raw)
    isbn = extract_isbn(stem)
    hinted = str(kind or "").strip().lower()
    if hinted not in ALL_KINDS:
        hinted = kind_from_newznab(category) or ""

    mag = None if hinted == KIND_COMIC else (_MAG_NO.search(stem) or _MAG_ISO.search(stem) or _MAG_MONTH.search(stem))
    if mag:
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

    comic_hint = hinted in ("", KIND_COMIC) or "comic" in stem.lower()
    if hinted != KIND_MAGAZINE and comic_hint:
        from librarian.comic_normalize import comic_identity_fields, normalize_comic_name

        tokens = normalize_comic_name(stem)
        # Keep legacy regex gate so magazine-like stems without comic markers stay out.
        legacy = (
            _COMIC_HASH_YEAR.search(stem)
            or _COMIC_VOLUME.search(stem)
            or _COMIC_YEAR_ISSUE.search(stem)
            or _COMIC_HASH.search(stem)
        )
        if legacy is None and hinted in ("", KIND_COMIC):
            padded = _COMIC_PADDED.search(stem)
            if padded and (hinted == KIND_COMIC or padded.group("issue").startswith("0")):
                legacy = padded
        if legacy is not None or (hinted == KIND_COMIC and tokens.series):
            fields = comic_identity_fields(tokens)
            series = str(fields.get("series_name") or "")
            issue = str(fields.get("series_index") or "")
            title = str(fields.get("title") or (f"{series} #{issue}" if series and issue else series))
            return Identity(
                kind=hinted or KIND_COMIC,
                title=title,
                series_name=series,
                series_index=issue,
                year=fields.get("year") if isinstance(fields.get("year"), int) else None,
                volume_year=fields.get("volume_year") if isinstance(fields.get("volume_year"), int) else None,
                comic_format=str(fields.get("comic_format") or ""),
                comic_subtitle=str(fields.get("comic_subtitle") or ""),
                comic_variant=str(fields.get("comic_variant") or ""),
                isbn=isbn,
                confidence="high" if series and issue else "low",
                rationale="comic series/issue parse",
                query_terms=[part for part in (series, issue) if part],
                source="parse",
            )

    year_match = _YEAR.search(stem)
    year = int(year_match.group(1)) if year_match else None

    def _clean_piece(value: str) -> str:
        text = _EBOOK_GROUP.sub("", value)
        text = _AUDIO_PART.sub("", text)
        text = _PART_COUNTER.sub(" ", text)
        text = _BARE_PART_COUNTER.sub(" ", text)
        text = _YEAR.sub("", text)
        text = _ISBN.sub("", text)
        return tidy_title(text)

    track = _MUSIC_TRACK.search(stem) if hinted in ("", KIND_MUSIC, KIND_AUDIOBOOK) else None
    track_title = ""
    tracknumber = ""
    discnumber = ""
    if track:
        tracknumber = str(int(track.group("num")))
        track_title = tidy_title(track.group("title"))
        if track.groupdict().get("disc"):
            discnumber = str(int(track.group("disc")))

    author = ""
    title = ""
    album = ""
    if hinted == KIND_MUSIC and " - " in stem:
        author, album = [_clean_piece(part) for part in stem.split(" - ", 1)]
        title = album
    elif " - " in stem:
        author, title = [_clean_piece(part) for part in stem.split(" - ", 1)]
    else:
        cleaned = _clean_piece(stem)
        title = cleaned
        if hinted == KIND_BOOK and " by " in cleaned.lower():
            head, tail = re.split(r"\s+by\s+", cleaned, maxsplit=1, flags=re.IGNORECASE)
            title, author = head.strip(), tail.strip()

    inferred = hinted
    if not inferred:
        if _AUDIOBOOK_HINT.search(stem):
            inferred = KIND_AUDIOBOOK
        elif any(token in stem.lower() for token in ("flac", "mp3", "vinyl", "album")):
            inferred = KIND_MUSIC
        else:
            inferred = KIND_BOOK

    if inferred == KIND_AUDIOBOOK and title:
        title = tidy_title(_AUDIO_PART.sub("", title)) or title
        title = _AUDIOBOOK_HINT.sub(" ", title)
        title = re.sub(r"\s+", " ", title).strip() or title
        from librarian.audiobook_normalize import normalize_audiobook_name

        tokens = normalize_audiobook_name(stem)
        author = tokens.author or author
        title = tokens.title or title
        year = tokens.year if tokens.year is not None else year
        series_name = tokens.series_name
        series_index = tokens.series_index
        asin = tokens.asin
        narrator = tokens.narrator
    else:
        series_name = album
        series_index = ""
        asin = ""
        narrator = ""

    high = bool(isbn and author and title) if inferred == KIND_BOOK else False
    return Identity(
        kind=inferred,
        title=title or track_title or tidy_title(stem),
        author=author,
        series_name=series_name if inferred == KIND_AUDIOBOOK else album,
        series_index=series_index if inferred == KIND_AUDIOBOOK else "",
        album=album,
        track_title=track_title,
        tracknumber=tracknumber,
        discnumber=discnumber,
        year=year,
        isbn=isbn or asin,
        asin=asin,
        narrator=narrator,
        confidence="high" if high else "low",
        rationale="indexer/parse fields" if isbn else "filename parse",
        query_terms=[part for part in (author, title, isbn or asin) if part],
        source="parse",
    )


def fill_identity_holes(identity: Identity, layer: Optional[Mapping[str, Any]]) -> Identity:
    """Copy non-empty fields from a weaker layer without overwriting stronger values."""
    if not layer:
        return identity
    fields = (
        "title",
        "author",
        "series_name",
        "series_index",
        "isbn",
        "asin",
        "mbid",
        "album",
        "track_title",
        "tracknumber",
        "discnumber",
        "recording_mbid",
        "publisher",
        "description",
        "genre",
        "narrator",
        "comic_format",
        "comic_subtitle",
        "comic_variant",
        "penciller",
        "inker",
        "colorist",
        "cover_artist",
        "letterer",
        "web",
    )
    for key in fields:
        incoming = layer.get(key)
        if incoming in (None, ""):
            continue
        current = getattr(identity, key, None)
        if current in (None, ""):
            setattr(identity, key, incoming)
    year = layer.get("year")
    if identity.year is None and str(year or "").isdigit():
        identity.year = int(year)
    volume_year = layer.get("volume_year")
    if identity.volume_year is None and str(volume_year or "").isdigit():
        identity.volume_year = int(volume_year)
    for int_key in ("comicvine_volume_id", "comicvine_issue_id", "month", "day"):
        incoming = layer.get(int_key)
        if getattr(identity, int_key, None) is None and str(incoming or "").lstrip("-").isdigit():
            setattr(identity, int_key, int(incoming))
    score = layer.get("match_confidence")
    if score is None:
        score = layer.get("match_score")
    if identity.match_confidence is None and score is not None:
        try:
            identity.match_confidence = float(score)
        except (TypeError, ValueError):
            pass
    candidates = layer.get("match_candidates")
    if candidates and not identity.match_candidates:
        identity.match_candidates = list(candidates) if isinstance(candidates, list) else []
    kind = str(layer.get("kind") or "").strip().lower()
    if kind in ALL_KINDS and identity.kind not in ALL_KINDS:
        identity.kind = kind
    if identity.album and not identity.series_name:
        identity.series_name = identity.album
    if identity.kind == KIND_MUSIC and identity.series_name and not identity.title:
        identity.title = identity.series_name
    if identity.kind in (KIND_COMIC, KIND_MAGAZINE) and identity.series_name and identity.series_index and not identity.title:
        identity.title = f"{identity.series_name} #{identity.series_index}"
    return identity


def identity_from_indexer(item: Dict[str, Any]) -> Identity:
    """Layer 1: Find sought / selected / retrieved catalog fields. Not the Usenet dump name."""
    sought = item.get("sought") if isinstance(item.get("sought"), dict) else {}
    retrieved = item.get("retrieved") if isinstance(item.get("retrieved"), dict) else {}
    selected = item.get("selected") if isinstance(item.get("selected"), dict) else {}
    requested = str(sought.get("kind") or item.get("kind") or selected.get("kind") or "").strip().lower()
    category = item.get("category") or selected.get("category") or item.get("cat")
    if requested not in ALL_KINDS:
        requested = kind_from_newznab(category) or ""
    catalog = str(
        sought.get("title")
        or sought.get("album")
        or retrieved.get("book_title")
        or retrieved.get("title")
        or retrieved.get("album")
        or item.get("book_title")
        or item.get("title")
        or item.get("album")
        or ""
    ).strip()
    series = tidy_title(
        str(sought.get("series") or retrieved.get("series") or retrieved.get("series_name") or "")
    )
    issue = str(sought.get("issue") or retrieved.get("issue") or item.get("issue") or "").strip()
    if requested == KIND_COMIC and series and issue:
        catalog = f"{series} #{str(int(issue)) if issue.isdigit() else issue}"
    author = tidy_title(
        str(
            sought.get("author")
            or sought.get("artist")
            or retrieved.get("author")
            or retrieved.get("artist")
            or item.get("author")
            or item.get("artist")
            or ""
        )
    )
    isbn_raw = sought.get("isbn") or retrieved.get("isbn") or item.get("isbn") or ""
    if requested == KIND_MUSIC:
        isbn_raw = ""
    isbn = extract_isbn(str(isbn_raw or ""))
    if requested != KIND_MUSIC and not isbn:
        isbn = extract_isbn(catalog)
    album = tidy_title(str(sought.get("album") or retrieved.get("album") or item.get("album") or ""))
    year_raw = str(sought.get("year") or retrieved.get("year") or item.get("year") or "").strip()
    identity = Identity(
        kind=requested if requested in ALL_KINDS else "",
        title=catalog,
        author=author,
        series_name=series or album,
        series_index=str(int(issue)) if issue.isdigit() else issue,
        year=int(year_raw) if year_raw.isdigit() else None,
        isbn=isbn,
        album=album,
        mbid=str(sought.get("mbid") or retrieved.get("mbid") or item.get("mbid") or "").strip(),
        confidence="low",
        rationale="indexer fields",
        query_terms=[part for part in (author, catalog, isbn, series, issue) if part],
        source="indexer",
    )
    if identity.kind == KIND_MUSIC and identity.album and not identity.title:
        identity.title = identity.album
    if identity.kind in (KIND_COMIC, KIND_MAGAZINE) and identity.series_name and identity.series_index and not identity.title:
        identity.title = f"{identity.series_name} #{identity.series_index}"
    _apply_stack_confidence(identity)
    identity.source = "indexer"
    return identity


def _apply_stack_confidence(identity: Identity) -> Identity:
    if identity.kind == KIND_BOOK and identity.isbn and identity.author and identity.title:
        identity.confidence = "high"
        identity.rationale = identity.rationale or "ISBN + author + title"
        identity.review_reason = None
    elif identity.kind == KIND_COMIC and identity.series_name and identity.series_index:
        score = identity.match_confidence
        if score is not None:
            if score >= 0.85:
                identity.confidence = "high"
                identity.rationale = identity.rationale or "comicvine match ≥0.85"
                if identity.review_reason in (
                    REVIEW_COMICVINE_AMBIGUOUS,
                    REVIEW_COMICVINE_UNMATCHED,
                    REVIEW_LOW,
                    None,
                ):
                    identity.review_reason = None
            elif score >= 0.65:
                identity.confidence = "low"
                identity.rationale = identity.rationale or "comicvine ambiguous"
                identity.review_reason = identity.review_reason or REVIEW_COMICVINE_AMBIGUOUS
            else:
                identity.confidence = "low"
                identity.rationale = identity.rationale or "comicvine unmatched"
                identity.review_reason = identity.review_reason or REVIEW_COMICVINE_UNMATCHED
        else:
            # No ComicVine key / lookup — legacy series+issue gate.
            identity.confidence = "high"
            identity.rationale = identity.rationale or "series + issue"
            identity.review_reason = None
    elif identity.kind == KIND_MAGAZINE and identity.series_name and identity.series_index:
        identity.confidence = "high"
        identity.rationale = identity.rationale or "series + issue"
        identity.review_reason = None
    elif identity.kind == KIND_MUSIC and identity.author and (identity.album or identity.series_name or identity.title):
        identity.confidence = "high"
        identity.rationale = identity.rationale or "artist + album"
        identity.review_reason = None
        if not identity.album:
            identity.album = identity.series_name or identity.title
        if not identity.series_name:
            identity.series_name = identity.album
        if not identity.title:
            identity.title = identity.album
    elif identity.kind == KIND_AUDIOBOOK and identity.asin and identity.author and identity.title:
        # ASIN-resolved identity (Audnexus). Filename author+title alone is no longer enough.
        identity.confidence = "high"
        identity.rationale = identity.rationale or "audiobook ASIN + author + title"
        identity.review_reason = None
    elif identity.kind == KIND_AUDIOBOOK and identity.author and identity.title:
        # Provisional until Audnexus scoring runs in identify_completed.
        identity.confidence = "low"
        identity.rationale = identity.rationale or "audiobook author + title (pending Audnexus)"
    else:
        identity.confidence = "low"
    return identity


def _is_junk_file(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    if "__macosx" in parts:
        return True
    name = path.name.lower()
    if name in JUNK_NAMES or name in SIDECAR_NAMES:
        return True
    suffix = path.suffix.lower()
    if suffix in JUNK_EXTENSIONS:
        return True
    if name.endswith(".par2"):
        return True
    return False


def _is_archive_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in ARCHIVE_EXTENSIONS:
        return True
    if re.match(r"^\.r\d{2}$", suffix):
        return True
    return False


# Parent dirs with this many sibling volumes look like library/ingest roots,
# not a SAB release folder — never rglob them while suggesting a better path.
_LIBRARY_ROOT_CHILD_DIRS = 32
# Cap suggestion scans so a mistaken broad candidate cannot hang Review.
_SUGGEST_PAYLOAD_MAX_FILES = 400


def list_payload_files(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    if folder.is_file():
        if _is_junk_file(folder) or _is_archive_file(folder):
            return []
        return [folder] if folder.suffix.lower() in MEDIA_EXTENSIONS else []
    found: List[Path] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        if _is_junk_file(path) or _is_archive_file(path):
            continue
        if path.suffix.lower() in MEDIA_EXTENSIONS:
            found.append(path)
    return found


def _looks_like_library_root(folder: Path) -> bool:
    """True when a folder holds many volume dirs (ingest dump / library root)."""
    if not folder.is_dir():
        return False
    try:
        child_dirs = 0
        for child in folder.iterdir():
            if not child.is_dir():
                continue
            child_dirs += 1
            if child_dirs >= _LIBRARY_ROOT_CHILD_DIRS:
                return True
    except OSError:
        return False
    return False


def _folder_has_payload_quick(folder: Path, *, max_files: int = _SUGGEST_PAYLOAD_MAX_FILES) -> bool:
    """True if readable media exists; stops early and never sorts the whole tree."""
    if not folder.exists():
        return False
    if folder.is_file():
        if _is_junk_file(folder) or _is_archive_file(folder):
            return False
        return folder.suffix.lower() in MEDIA_EXTENSIONS
    scanned = 0
    try:
        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            scanned += 1
            if scanned > max_files:
                return False
            if _is_junk_file(path) or _is_archive_file(path):
                continue
            if path.suffix.lower() in MEDIA_EXTENSIONS:
                return True
    except OSError:
        return False
    return False


def inspect_complete_folder(folder: Path) -> Dict[str, Any]:
    """Classify a SAB complete folder: payload vs leftover archives vs junk."""
    if not usable_folder(folder) or not Path(folder).exists():
        return {
            "payload": [],
            "archives": [],
            "junk": [],
            "problem": REVIEW_MISSING_FOLDER,
        }
    root = Path(folder)
    if root.is_file():
        files = [root]
    else:
        files = [path for path in sorted(root.rglob("*")) if path.is_file()]
    payload: List[Path] = []
    archives: List[Path] = []
    junk: List[Path] = []
    for path in files:
        if _is_junk_file(path):
            junk.append(path)
        elif _is_archive_file(path):
            archives.append(path)
        elif path.suffix.lower() in MEDIA_EXTENSIONS:
            payload.append(path)
        else:
            junk.append(path)
    problem: Optional[str] = None
    if payload:
        problem = None
    elif archives:
        problem = REVIEW_UNPACK_STUCK
    else:
        problem = REVIEW_NO_PAYLOAD
    return {
        "payload": payload,
        "archives": archives,
        "junk": junk,
        "problem": problem,
    }


def suggest_payload_folder(folder: Path) -> Optional[Path]:
    """Nearby folder that already has readable media (parent or nested child only)."""
    if not usable_folder(folder):
        return None
    root = Path(folder)
    candidates: List[Path] = []
    parent = root.parent if root.is_absolute() or str(root.parent) not in {"", "."} else None
    if parent is not None and parent.is_dir() and parent.name not in {"", ".", "/"}:
        # Prefer a same-named child under parent, then parent itself if it has media.
        same = parent / root.name
        if same.is_dir() and same != root:
            candidates.append(same)
        candidates.append(parent)
    if root.is_dir():
        try:
            for child in sorted(root.iterdir()):
                if child.is_dir():
                    candidates.append(child)
        except OSError:
            pass
    for candidate in _unique_paths(candidates):
        try:
            if root.exists() and candidate.resolve() == root.resolve():
                continue
        except OSError:
            pass
        # Do not suggest a broad complete/downloads root that happens to contain other albums.
        if candidate.name in {"complete", "downloads", "usenet", "data", "media"}:
            continue
        # Ingest dumps (e.g. /data/media/newlib with 1000+ volumes) must not be rglob'd.
        if _looks_like_library_root(candidate):
            continue
        if _folder_has_payload_quick(candidate):
            return candidate
    return None


def path_layout_note(folder: Path) -> str:
    """Honest note when …/complete/downloads/… looks like a double prefix but is SAB’s category layout."""
    text = str(folder or "").replace("\\", "/")
    if "/complete/downloads/" in text or text.rstrip("/").endswith("/complete/downloads"):
        return (
            "The …/complete/downloads/… path is normal: SAB’s complete root ends at …/complete, "
            "and a downloads category adds that folder under it — not a doubled map."
        )
    return ""


def diagnose_review_folder(folder: Path, complete_root: str = "") -> Dict[str, Any]:
    """Live diagnosis for a Review slip: what we checked, what’s wrong, optional better path."""
    raw = Path(folder) if usable_folder(folder) else Path()
    resolved = resolve_storage_path(raw, complete_root) if usable_folder(raw) else raw
    inspection = inspect_complete_folder(resolved)
    problem = inspection.get("problem")
    # Only hunt for a better path when this folder itself has no usable media.
    # Always-on suggest used to rglob library parents (e.g. newlib) and hang GET /api/review.
    suggested: Optional[Path] = None
    if problem:
        suggested = suggest_payload_folder(resolved)
        if suggested is None and usable_folder(raw) and resolved != raw:
            suggested = suggest_payload_folder(raw)
    payload = inspection.get("payload") or []
    archives = inspection.get("archives") or []
    junk = inspection.get("junk") or []
    par2_count = sum(1 for path in junk if Path(path).name.lower().endswith(".par2"))
    looked_for = "book (epub/pdf), comic (cbz/cbr), or audio (flac/mp3/m4a/m4b) files"
    empty_dir = False
    if problem == REVIEW_NO_PAYLOAD and resolved.exists() and resolved.is_dir():
        try:
            empty_dir = not any(resolved.iterdir())
        except OSError:
            empty_dir = False
    if problem == REVIEW_MISSING_FOLDER:
        tried = f"Looked for a complete folder at {resolved or raw or '(empty)'}."
    elif problem == REVIEW_UNPACK_STUCK:
        sidecar = f"(also {len(junk)} junk/sidecar file(s)"
        if par2_count:
            sidecar += f", including {par2_count} PAR2 recovery file(s)"
        sidecar += ")"
        tried = (
            f"Opened {resolved}. Found {len(archives)} archive file(s) and no readable media "
            f"{sidecar}."
        )
        if par2_count:
            tried += (
                " Archives may be incomplete or checksum-damaged — "
                "Repair runs par2 then unpack; Retry shelves if media appears."
            )
        else:
            tried += (
                " No PAR2 recovery files here — extract manually, fix in SABnzbd, "
                "or Request a new version."
            )
    elif problem == REVIEW_NO_PAYLOAD and empty_dir:
        tried = f"Opened {resolved}. The folder is empty."
    elif problem == REVIEW_NO_PAYLOAD:
        tried = f"Opened {resolved}. Found {len(junk)} non-media file(s) and no {looked_for}."
    else:
        tried = f"Opened {resolved}. Found {len(payload)} readable file(s) this Librarian can shelve."
    dump_meta = collection_dump_meta([Path(path) for path in payload])
    if dump_meta.get("collection_dump") and not problem:
        n = int(dump_meta.get("distinct_title_count") or 0)
        tried = (
            f"Opened {resolved}. Found {len(payload)} readable file(s) across "
            f"{n} different title name(s) — this looks like a multi-title collection dump, "
            f"not one book with leftover junk."
        )
    return {
        "path": str(resolved) if usable_folder(resolved) else str(raw or ""),
        "resolved_path": str(resolved) if usable_folder(resolved) else "",
        "problem": problem,
        "payload_count": len(payload),
        "archive_count": len(archives),
        "junk_count": len(junk),
        "par2_count": par2_count,
        "looked_for": looked_for,
        "tried": tried,
        "path_note": path_layout_note(resolved if usable_folder(resolved) else raw),
        "suggested_folder": str(suggested) if suggested is not None else None,
        "collection_dump": bool(dump_meta.get("collection_dump")),
        "distinct_title_count": int(dump_meta.get("distinct_title_count") or 0),
    }


def usable_folder(folder: Optional[Union[Path, str]]) -> bool:
    """True when a path is a real location, not empty / cwd (Path(''))."""
    text = str(folder or "").strip()
    return bool(text) and text not in {".", str(Path())}


def _complete_roots(complete_root: str) -> List[Path]:
    text = str(complete_root or "").strip()
    if text:
        return [Path(text)]
    return [Path(raw) for raw in COMPLETE_ROOT_FALLBACKS if Path(raw).is_dir()]


def _unique_paths(paths: Sequence[Path]) -> List[Path]:
    seen: List[str] = []
    unique: List[Path] = []
    for path in paths:
        key = str(path)
        if not key or key == "." or key in seen:
            continue
        seen.append(key)
        unique.append(path)
    return unique


def _storage_relatives(storage: Path, complete_root: str = "") -> List[Path]:
    """Paths relative to SAB complete_dir, without doubling a /downloads prefix."""
    text = str(storage)
    relatives: List[Path] = []
    prefixes: List[str] = []
    root_text = str(complete_root or "").rstrip("/")
    if root_text:
        prefixes.append(root_text + "/")
        if root_text.startswith(CONTAINER_DATA_PREFIX):
            prefixes.append(HOST_DATA_PREFIX + root_text[len(CONTAINER_DATA_PREFIX) :] + "/")
        if root_text.startswith(HOST_DATA_PREFIX):
            prefixes.append(CONTAINER_DATA_PREFIX + root_text[len(HOST_DATA_PREFIX) :] + "/")
    prefixes.extend(
        (
            HOST_DATA_PREFIX + "usenet/complete/",
            CONTAINER_DATA_PREFIX + "usenet/complete/",
            *DOWNLOADS_PREFIXES,
        )
    )
    for prefix in prefixes:
        if text.startswith(prefix):
            rest = text[len(prefix) :]
            if rest:
                relatives.append(Path(rest))
    parts = storage.parts[1:] if storage.is_absolute() else storage.parts
    if parts:
        relatives.append(Path(*parts))
        if len(parts) > 1:
            relatives.append(Path(*parts[1:]))
    relatives.append(Path(storage.name))
    return _unique_paths(relatives)


def _guess_relative(storage: Path, relatives: Sequence[Path]) -> Path:
    """When nothing exists yet, do not invent /downloads/downloads/... under complete_root."""
    for relative in relatives:
        parts = relative.parts
        if parts and parts[0] == "downloads":
            continue
        if str(relative) not in {"", "."}:
            return Path(relative)
    return Path(storage.name)


def resolve_storage_path(storage: Path, complete_root: str = "") -> Path:
    """Map a SAB container path (often /downloads/...) onto a directory this process can read."""
    if not usable_folder(storage):
        return storage
    if storage.exists():
        return storage
    if str(storage).startswith(HOST_DATA_PREFIX):
        rewritten = Path(CONTAINER_DATA_PREFIX + str(storage)[len(HOST_DATA_PREFIX) :])
        if rewritten.exists():
            return rewritten
    roots = _complete_roots(complete_root)
    if not roots:
        return storage
    relatives = _storage_relatives(storage, complete_root)
    candidates: List[Path] = []
    for root_path in roots:
        candidates.append(root_path / storage.name)
        for relative in relatives:
            candidates.append(root_path / relative)
    ordered = _unique_paths(candidates)
    existing = [candidate for candidate in ordered if candidate.exists()]
    if existing:
        with_payload = [candidate for candidate in existing if list_payload_files(candidate)]
        return with_payload[0] if with_payload else existing[0]
    return roots[0] / _guess_relative(storage, relatives)


def identify_completed(
    folder: Path,
    *,
    indexer_item: Optional[Dict[str, Any]] = None,
    category: object = None,
    llm_client: Any = None,
    settings: Any = None,
    catalog_lookup: Optional[Callable[[Identity], Optional[Mapping[str, Any]]]] = None,
    catalog_transport: Any = None,
) -> Dict[str, Any]:
    """Identify a completed folder via the recognition stack. Unexpected results go to Review.

    Ingest / watch-folder callers must use this same function (then organize_identified).
    Layers, strongest first: sought/selected/retrieved → embedded metadata →
    kind-specific filename parse → catalog lookup with a real key. Later layers fill holes only.
    """
    files = expand_organize_payload(folder)
    item = dict(indexer_item or {})
    if category is not None:
        item["category"] = category or item.get("category")
    sought = item.get("sought") if isinstance(item.get("sought"), dict) else {}
    sought_kind = str(sought.get("kind") or "").strip().lower()

    if indexer_item:
        identity = identity_from_indexer(item)
    else:
        identity = Identity(kind="", title="", confidence="low", source="empty")

    if not files:
        if not identity.title:
            identity = fill_identity_holes(
                identity, parse_usenet_name(folder.name, category=item.get("category"), kind=identity.kind).as_dict()
            )
        inspection = inspect_complete_folder(folder)
        problem = inspection.get("problem") or REVIEW_NO_PAYLOAD
        identity.review_reason = str(problem)
        identity.confidence = "low"
        return {"identity": identity.as_dict(), "files": [], "auto_organize": False}

    embedded = embedded_identity(folder, files, kind=identity.kind)
    if (
        str(embedded.get("kind") or "") == KIND_AUDIOBOOK
        and identity.kind == KIND_MUSIC
        and sought_kind != KIND_MUSIC
    ):
        identity.kind = KIND_AUDIOBOOK
    fill_identity_holes(identity, embedded)

    filename_layer = filename_identity(folder, files, kind=identity.kind, category=item.get("category"))
    if identity.isbn:
        filename_layer.pop("title", None)
        filename_layer.pop("author", None)
        filename_layer.pop("isbn", None)
    fill_identity_holes(identity, filename_layer)

    if identity.kind not in ALL_KINDS:
        inferred = kind_from_newznab(item.get("category")) or _kind_from_payload(files, folder)
        if inferred:
            identity.kind = inferred

    has_key = bool(extract_isbn(identity.isbn)) or bool(_MBID.match(str(identity.mbid or ""))) or bool(
        _MBID.match(str(identity.recording_mbid or ""))
    )
    if catalog_lookup is not None and has_key:
        try:
            fill_identity_holes(identity, catalog_lookup(identity) or {})
        except Exception:
            pass
    elif settings is not None:
        fill_identity_holes(identity, catalog_fill(identity, settings, transport=catalog_transport))

    if identity.kind == KIND_AUDIOBOOK and settings is not None:
        _apply_audnexus_match(identity, settings, transport=catalog_transport)

    identity.source = identity.source or "stack"
    _apply_review_gates(identity, files)

    needs_author = identity.kind in (KIND_BOOK, KIND_AUDIOBOOK) and not identity.author
    needs_llm = identity.confidence != "high" or looks_like_dump_title(identity.title) or needs_author
    if needs_llm and llm_client is not None:
        evidence = identify_evidence(folder, indexer_item, files, identity)
        try:
            from librarian.llm import merge_llm_identity

            parsed = llm_client.identify(evidence)
            identity = merge_llm_identity(identity, parsed, evidence)
        except Exception:
            pass
        else:
            files = _apply_post_llm_review(identity, folder)

    auto = identity.confidence == "high" and not identity.review_reason
    return {
        "identity": identity.as_dict(),
        "files": [str(path) for path in files],
        "auto_organize": auto,
    }


def embedded_identity(folder: Path, files: Sequence[Path], *, kind: str = "") -> Dict[str, Any]:
    """Layer 2: OPF / ComicInfo / audio tags / cheap PDF info. Does not invent identifiers."""
    from librarian.metadata import (
        read_audio_tags,
        read_cbz_comicinfo,
        read_epub_opf,
        read_folder_metadata,
        read_pdf_info,
    )

    merged: Dict[str, Any] = {}
    sidecar = read_folder_metadata(Path(folder)) if Path(folder).is_dir() else {}
    merged.update(sidecar)
    hinted = str(kind or "").strip().lower()
    for path in files:
        suffix = path.suffix.lower()
        layer: Dict[str, Any] = {}
        if suffix == ".epub":
            layer = read_epub_opf(path)
        elif suffix == ".cbz":
            layer = read_cbz_comicinfo(path)
        elif suffix == ".pdf":
            layer = read_pdf_info(path)
        elif suffix in {".flac", ".mp3", ".m4a", ".m4b", ".ogg", ".opus", ".mp4", ".aac"}:
            layer = read_audio_tags(path)
        for key, value in layer.items():
            if value in (None, "") or merged.get(key) not in (None, ""):
                continue
            merged[key] = value
        if hinted in (KIND_MUSIC, KIND_AUDIOBOOK, "") and layer.get("album") and not merged.get("album"):
            merged["album"] = layer["album"]
    return merged


def filename_identity(
    folder: Path,
    files: Sequence[Path],
    *,
    kind: str = "",
    category: object = None,
) -> Dict[str, Any]:
    """Layer 3: conservative kind-specific folder/filename parse. Weak titles only fill holes."""
    names: List[str] = [Path(folder).name]
    if files:
        names.append(files[0].stem)
        names.append(files[0].name)
        if len(files) == 1 and files[0].parent != Path(folder):
            names.append(files[0].parent.name)
    merged: Dict[str, Any] = {}
    skip = {"confidence", "rationale", "source", "query_terms", "review_reason", "kind"}
    for name in names:
        parsed = parse_usenet_name(name, category=category, kind=kind)
        data = parsed.as_dict()
        if kind == KIND_BOOK and not data.get("isbn"):
            # Author - Title.epub is a weak title only when nothing else exists.
            data = {key: data.get(key) for key in ("title", "author", "year", "isbn") if data.get(key)}
        for key, value in data.items():
            if key in skip or value in (None, "", [], "low"):
                continue
            if merged.get(key) in (None, ""):
                merged[key] = value
    return merged


def catalog_fill(identity: Identity, settings: Any, *, transport: Any = None) -> Dict[str, Any]:
    """Layer 4: Hardcover/OL by ISBN, MusicBrainz by MBID or artist+album, Comic Vine if keyed.

    Fail closed on HTTP errors. Never writes an ISBN from a title-only match. Never invents an MBID.
    Audiobooks use Audnexus (see ``_apply_audnexus_match``) — not Hardcover/Open Library.
    """
    kind = identity.kind
    if kind == KIND_AUDIOBOOK:
        return {}
    if kind in (KIND_BOOK, KIND_MAGAZINE) and identity.isbn:
        if identity.title and identity.author:
            return {}
        return _catalog_isbn(identity, settings, transport=transport)
    if kind == KIND_MUSIC:
        return _catalog_music(identity, settings, transport=transport)
    if kind == KIND_COMIC:
        return _catalog_comic(identity, settings, transport=transport)
    return {}


def _apply_audnexus_match(identity: Identity, settings: Any, *, transport: Any = None) -> None:
    """Score Audnexus candidates for audiobooks. Sets review bands; no remux until resolved."""
    if identity.kind != KIND_AUDIOBOOK or settings is None:
        return
    try:
        from librarian.audnexus import (
            AudnexusError,
            client_from_settings,
            identity_from_candidate,
            match_audiobook_tokens,
        )
    except Exception:
        return
    tokens = {
        "title": identity.title,
        "author": identity.author,
        "asin": identity.asin or identity.isbn,
        "narrator": identity.narrator,
        "series_name": identity.series_name,
        "series_index": identity.series_index,
        "year": identity.year,
    }
    client = client_from_settings(settings, transport=transport)
    try:
        matched = match_audiobook_tokens(tokens, client=client)
    except AudnexusError:
        if not identity.review_reason:
            identity.review_reason = REVIEW_AUDNEXUS_UNMATCHED
            identity.confidence = "low"
        return
    finally:
        client.close()

    candidates = list(matched.get("candidates") or [])
    identity.match_candidates = candidates[:8]
    identity.match_confidence = float(matched.get("score") or 0)
    reason = matched.get("review_reason")
    best = matched.get("best")
    if reason is None and best:
        filled = identity_from_candidate(best)
        fill_identity_holes(identity, filled)
        # Strong fields from authority win for title/author/asin once auto-matched.
        for key in ("title", "author", "asin", "series_name", "series_index", "description", "narrator"):
            value = filled.get(key)
            if value not in (None, ""):
                setattr(identity, key, value)
        if filled.get("year") is not None:
            identity.year = filled["year"]
        identity.isbn = identity.asin or identity.isbn
        identity.confidence = "high"
        identity.rationale = "Audnexus ASIN match"
        identity.review_reason = None
        identity.source = "audnexus"
        return
    identity.confidence = "low"
    identity.review_reason = reason or REVIEW_AUDNEXUS_UNMATCHED
    if best and not identity.asin:
        # Surface best guess into the Review form without auto-filing.
        hint = identity_from_candidate(best)
        if not identity.title and hint.get("title"):
            identity.title = str(hint["title"])
        if not identity.author and hint.get("author"):
            identity.author = str(hint["author"])


def _catalog_isbn(identity: Identity, settings: Any, *, transport: Any = None) -> Dict[str, Any]:
    isbn = extract_isbn(identity.isbn)
    if not isbn:
        return {}
    merged: Dict[str, Any] = {}
    try:
        from librarian.hardcover import HardcoverClient, HardcoverError

        token = str(getattr(settings, "hardcover_api_token", "") or "").strip()
        if token:
            client = HardcoverClient(token, transport=transport)
            try:
                merged = dict(client.lookup_by_isbn(isbn) or {})
            except HardcoverError:
                merged = {}
            finally:
                client.close()
    except Exception:
        merged = {}
    if not merged.get("title") or not merged.get("author"):
        try:
            from librarian.openlibrary import OpenLibraryClient

            client = OpenLibraryClient(transport=transport)
            try:
                found = client.lookup_by_isbn(isbn) or {}
            finally:
                client.close()
            for key, value in found.items():
                if value not in (None, "") and merged.get(key) in (None, ""):
                    merged[key] = value
        except Exception:
            pass
    merged.pop("isbn", None)
    return merged


def _catalog_music(identity: Identity, settings: Any, *, transport: Any = None) -> Dict[str, Any]:
    mbid = str(identity.mbid or "").strip()
    recording = str(identity.recording_mbid or "").strip()
    if mbid and not _MBID.match(mbid):
        mbid = ""
    if recording and not _MBID.match(recording):
        recording = ""
    if not mbid and not recording:
        return {}
    try:
        from librarian.musicbrainz import MusicBrainzClient, MusicBrainzError

        client = MusicBrainzClient(transport=transport, min_interval=0)
        try:
            found = client.lookup_release(
                artist=identity.author,
                album=identity.album or identity.series_name or identity.title,
                mbid=mbid,
                recording_mbid=recording,
            )
        except MusicBrainzError:
            found = {}
        finally:
            client.close()
    except Exception:
        return {}
    found.pop("isbn", None)
    return found or {}


def _catalog_comic(identity: Identity, settings: Any, *, transport: Any = None) -> Dict[str, Any]:
    key = str(getattr(settings, "comicvine_api_key", "") or "").strip()
    if not key or not (identity.series_name and identity.series_index):
        return {}
    try:
        import os

        from librarian.comicvine import ComicVineClient, ComicVineError

        cache_path = Path(os.environ.get("DATA_DIR", "/config")) / "comicvine-cache.db"
        client = ComicVineClient(
            key,
            transport=transport,
            cache_path=cache_path,
            rate_limit=transport is None,
        )
        try:
            matched = client.match_issue(
                identity.series_name,
                identity.series_index,
                volume_year=identity.volume_year,
                cover_year=identity.year,
            )
        except ComicVineError:
            return {
                "match_confidence": 0.0,
                "match_candidates": [],
                "review_reason": REVIEW_COMICVINE_UNMATCHED,
            }
        finally:
            client.close()
    except Exception:
        return {}

    best = matched.get("best") if isinstance(matched.get("best"), dict) else {}
    score = float(matched.get("match_score") or 0)
    candidates = list(matched.get("candidates") or [])
    out: Dict[str, Any] = {
        "match_confidence": score,
        "match_candidates": candidates,
    }
    if best:
        for key_name in (
            "title",
            "author",
            "year",
            "publisher",
            "description",
            "web",
            "penciller",
            "inker",
            "colorist",
            "cover_artist",
            "letterer",
            "month",
            "day",
        ):
            if best.get(key_name) not in (None, ""):
                out[key_name] = best[key_name]
        if best.get("volume_year") not in (None, ""):
            out["volume_year"] = best["volume_year"]
        if best.get("volume_id") not in (None, ""):
            out["comicvine_volume_id"] = best["volume_id"]
        if best.get("issue_id") not in (None, ""):
            out["comicvine_issue_id"] = best["issue_id"]
        if best.get("series_name"):
            out["series_name"] = best["series_name"]
        if best.get("series_index"):
            out["series_index"] = best["series_index"]

    band = str(matched.get("band") or "low")
    if band == "high":
        out["confidence"] = "high"
        out["rationale"] = "comicvine match ≥0.85"
    elif band == "mid":
        out["confidence"] = "low"
        out["review_reason"] = REVIEW_COMICVINE_AMBIGUOUS
        out["rationale"] = "comicvine ambiguous volume"
    else:
        out["confidence"] = "low"
        out["review_reason"] = REVIEW_COMICVINE_UNMATCHED
        out["rationale"] = "comicvine unmatched"
    return out


def _kind_from_payload(files: Sequence[Path], folder: Path) -> str:
    suffixes = {path.suffix.lower() for path in files}
    names = " ".join([folder.name, *(path.name for path in files)]).lower()
    # Comic archives win only when no clear ebook encodings share the payload.
    # Mixed comic+ebook is handled by partition/split — never blend as comic.
    if suffixes & COMIC_ARCHIVE_EXTENSIONS and not (suffixes & EBOOK_FORMAT_EXTENSIONS):
        return KIND_COMIC
    if suffixes & {".m4b"} or _AUDIOBOOK_HINT.search(names):
        return KIND_AUDIOBOOK
    if suffixes & {".flac", ".mp3", ".m4a", ".ogg", ".opus"} and ".epub" not in suffixes:
        return KIND_MUSIC
    if suffixes & EBOOK_FORMAT_EXTENSIONS:
        return KIND_BOOK
    if suffixes == {".pdf"}:
        return KIND_BOOK
    if suffixes & COMIC_ARCHIVE_EXTENSIONS:
        return KIND_COMIC
    return ""


def is_mixed_comic_ebook_payload(files: Sequence[Path]) -> bool:
    """True when a volume holds both comic archives and clear ebook encodings.

    Those are separate works (comic adaptation vs prose book), never alternate
    formats of one title. PDF alone does not trigger this — PDF+cbz stays comic.
    """
    suffixes = {path.suffix.lower() for path in files}
    return bool(suffixes & COMIC_ARCHIVE_EXTENSIONS) and bool(suffixes & EBOOK_FORMAT_EXTENSIONS)


def partition_comic_ebook_files(files: Sequence[Path]) -> Dict[str, List[Path]]:
    """Split media into comic archives vs ebook encodings (PDF follows ebooks when mixed)."""
    comics: List[Path] = []
    ebooks: List[Path] = []
    pdfs: List[Path] = []
    other: List[Path] = []
    for path in files:
        suffix = path.suffix.lower()
        if suffix in COMIC_ARCHIVE_EXTENSIONS:
            comics.append(path)
        elif suffix in EBOOK_FORMAT_EXTENSIONS:
            ebooks.append(path)
        elif suffix == ".pdf":
            pdfs.append(path)
        else:
            other.append(path)
    if comics and ebooks:
        return {"comic": comics, "book": ebooks + pdfs, "other": other}
    if comics:
        return {"comic": comics + pdfs, "book": [], "other": other + ebooks}
    return {"comic": [], "book": ebooks + pdfs, "other": other}


def ingest_targets_for_mixed_payload(files: Sequence[Path]) -> List[Path]:
    """Paths to enqueue when a leaf folder mixed comics with ebooks.

    Each comic archive is its own volume. Ebook encodings that share a
    normalized stem stay one volume (representative file; siblings expand later).
    """
    parts = partition_comic_ebook_files(files)
    targets: List[Path] = list(parts.get("comic") or [])
    book_groups: Dict[str, List[Path]] = {}
    for path in parts.get("book") or []:
        key = _normalized_payload_stem(path) or path.stem.lower()
        book_groups.setdefault(key, []).append(path)
    for group in book_groups.values():
        ordered = sorted(group, key=lambda item: item.name.lower())
        targets.append(ordered[0])
    targets.extend(parts.get("other") or [])
    return targets


def ingest_targets_for_multi_title_payload(files: Sequence[Path]) -> List[Path]:
    """One ingest target per distinct title stem in a flat multi-book dump.

    NYT / Usenet Fiction folders often hold dozens of ``Title - Author.epub``
    siblings. Clear-extra and ingest must not treat that as one volume — pick a
    representative file per stem; ``expand_organize_payload`` pulls same-stem
    multi-format siblings later.
    """
    groups: Dict[str, List[Path]] = {}
    for path in files:
        key = _normalized_payload_stem(path) or path.stem.lower()
        groups.setdefault(key, []).append(path)
    targets: List[Path] = []
    for key in sorted(groups.keys()):
        ordered = sorted(
            groups[key],
            key=lambda item: (
                0 if item.suffix.lower() == ".epub" else 1,
                item.name.lower(),
            ),
        )
        targets.append(ordered[0])
    return targets


def match_payload_files_to_identity(
    files: Sequence[Path],
    identity: Mapping[str, Any],
) -> List[Path]:
    """Return media files in ``files`` that belong to the confirmed Review identity.

    Used when Apply peels one volume out of a multi-title dump (extra_files).
    Matches ISBN-in-name, normalized title stem, or title substring in the stem;
    then expands to same-stem multi-format siblings.
    """
    title = tidy_title(str(identity.get("title") or ""))
    isbn = extract_isbn(str(identity.get("isbn") or "")) or ""
    title_norm = _normalized_payload_stem(Path(f"{title}.epub")) if title else ""
    title_l = title.lower()
    hits: List[Path] = []
    for path in files:
        stem_norm = _normalized_payload_stem(path)
        name_digits = re.sub(r"[^0-9]", "", path.name)
        if isbn and isbn in name_digits:
            hits.append(path)
            continue
        if title_norm and stem_norm == title_norm:
            hits.append(path)
            continue
        if title_l and title_l in path.stem.lower():
            hits.append(path)
    if not hits:
        return []
    stems = {_normalized_payload_stem(path) for path in hits}
    stems.discard("")
    return sorted(
        [path for path in files if _normalized_payload_stem(path) in stems],
        key=lambda item: item.name.lower(),
    )


def unexpected_extra_files(files: Sequence[Path]) -> bool:
    """Public: folder looks like multiple distinct works (not one multi-format book)."""
    return _unexpected_extra_files(files)


def collection_dump_meta(files: Sequence[Path]) -> Dict[str, Any]:
    """Household signal: flat/multi-stem dump vs one book with alternate formats.

    NYT Fiction / Usenet collection folders have many distinct title stems. That is
    not "extra junk beside one download" — Clear / ingest should expand per title.
    Mixed comic+ebook is a different repair path and is not flagged here.
    """
    payload = [Path(path) for path in files]
    if is_mixed_comic_ebook_payload(payload):
        return {"collection_dump": False, "distinct_title_count": 0}
    if not _unexpected_extra_files(payload):
        return {"collection_dump": False, "distinct_title_count": 0}
    stems = {_normalized_payload_stem(path) for path in payload}
    stems.discard("")
    count = len(stems)
    return {"collection_dump": count >= 2, "distinct_title_count": count}


def expand_organize_payload(target: Path) -> List[Path]:
    """Media files for identify/organize.

    When the target is a single ebook file, include same-stem ebook siblings in
    the same folder (Calibre multi-format) but never comic archives — so a mass
    import that split a mixed folder still shelves epub+azw3 as one book.
    """
    if target.is_file():
        if _is_junk_file(target) or _is_archive_file(target):
            return []
        suffix = target.suffix.lower()
        if suffix not in MEDIA_EXTENSIONS:
            return []
        if suffix in EBOOK_FORMAT_EXTENSIONS or suffix == ".pdf":
            stem = _normalized_payload_stem(target)
            siblings: List[Path] = []
            try:
                for child in target.parent.iterdir():
                    if not child.is_file():
                        continue
                    child_suffix = child.suffix.lower()
                    if child_suffix not in EBOOK_FORMAT_EXTENSIONS and child_suffix != ".pdf":
                        continue
                    if _normalized_payload_stem(child) != stem:
                        continue
                    siblings.append(child)
            except OSError:
                return [target]
            return sorted(siblings or [target], key=lambda item: item.name.lower())
        return [target]
    return list_payload_files(target)


def _apply_review_gates(identity: Identity, files: Sequence[Path]) -> None:
    if is_mixed_comic_ebook_payload(files):
        identity.review_reason = REVIEW_EXTRA
        identity.confidence = "low"
        return
    extra = _unexpected_extra_files(files)
    if extra and identity.kind not in (KIND_MUSIC, KIND_AUDIOBOOK, KIND_MAGAZINE):
        identity.review_reason = REVIEW_EXTRA
        identity.confidence = "low"
        return

    if identity.kind not in ALL_KINDS:
        identity.review_reason = identity.review_reason or REVIEW_UNEXPECTED
        identity.confidence = "low"
        return

    _apply_stack_confidence(identity)

    if identity.kind == KIND_BOOK:
        suffixes = {path.suffix.lower() for path in files}
        if suffixes == {".pdf"}:
            identity.review_reason = identity.review_reason or REVIEW_CONVERT
            identity.confidence = "low"
        if identity.confidence != "high" or not (identity.isbn and identity.author and identity.title):
            if not identity.review_reason:
                identity.review_reason = REVIEW_LOW if identity.title else REVIEW_UNKNOWN
                identity.confidence = "low"
                identity.isbn = extract_isbn(identity.isbn)

    if identity.kind in (KIND_COMIC, KIND_MAGAZINE):
        if not (identity.series_name and identity.series_index):
            identity.review_reason = identity.review_reason or REVIEW_UNKNOWN
            identity.confidence = "low"
        suffixes = {path.suffix.lower() for path in files}
        # Final shelf is CBZ only — CBR and PDF comics must remux before auto-organize.
        if identity.kind == KIND_COMIC:
            has_cbz = ".cbz" in suffixes
            needs_cbz = (".cbr" in suffixes or ".pdf" in suffixes) and not has_cbz
            if needs_cbz:
                identity.review_reason = identity.review_reason or REVIEW_CONVERT
                identity.confidence = "low"
            if identity.review_reason in (REVIEW_COMICVINE_AMBIGUOUS, REVIEW_COMICVINE_UNMATCHED):
                identity.confidence = "low"

    if identity.kind == KIND_AUDIOBOOK and not (identity.author and identity.title):
        identity.review_reason = identity.review_reason or REVIEW_UNKNOWN
        identity.confidence = "low"
    elif identity.kind == KIND_AUDIOBOOK and identity.review_reason in (
        REVIEW_AUDNEXUS_AMBIGUOUS,
        REVIEW_AUDNEXUS_UNMATCHED,
    ):
        identity.confidence = "low"
    elif identity.kind == KIND_AUDIOBOOK and identity.confidence != "high":
        identity.review_reason = identity.review_reason or (
            REVIEW_AUDNEXUS_UNMATCHED if not identity.asin else REVIEW_LOW
        )
        identity.confidence = "low"
    if identity.kind == KIND_MUSIC and identity.confidence != "high":
        identity.review_reason = identity.review_reason or (REVIEW_LOW if identity.title else REVIEW_UNKNOWN)
        identity.confidence = "low"

    if identity.kind == KIND_BOOK and identity.confidence != "high":
        identity.isbn = extract_isbn(identity.isbn)


def _normalized_payload_stem(path: Path) -> str:
    """Collapse Calibre/Usenet name noise so epub+mobi of one title match."""
    stem = path.stem
    # Calibre: "Title - Author"
    if " - " in stem:
        stem = stem.split(" - ", 1)[0]
    text = stem.lower().replace(".", " ").replace("_", " ")
    text = re.sub(r"[^a-z0-9\s]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _compatible_alternate_formats(files: Sequence[Path]) -> bool:
    """True when every media file is an alternate ebook encoding of one title."""
    if len(files) <= 1:
        return True
    suffixes = {path.suffix.lower() for path in files}
    if not suffixes or not suffixes <= BOOK_FORMAT_EXTENSIONS:
        return False
    stems = {_normalized_payload_stem(path) for path in files}
    stems.discard("")
    return len(stems) == 1


def _unexpected_extra_files(files: Sequence[Path]) -> bool:
    """True when the folder looks like multiple distinct works (not one multi-format book)."""
    if len(files) <= 1:
        return False
    if all(
        _AUDIO_PART.search(path.name) or path.suffix.lower() in {".mp3", ".m4b", ".flac"} for path in files
    ):
        return False
    if _compatible_alternate_formats(files):
        return False
    return True


def _apply_post_llm_review(identity: Identity, folder: Path) -> List[Path]:
    """Folder hygiene after a successful LLM identity. Keep true multi-work extras in Review."""
    files = expand_organize_payload(folder)
    if is_mixed_comic_ebook_payload(files):
        identity.review_reason = REVIEW_EXTRA
        identity.confidence = "low"
        return files
    extra = _unexpected_extra_files(files)
    if extra and identity.kind not in (KIND_MUSIC, KIND_AUDIOBOOK, KIND_MAGAZINE):
        identity.review_reason = REVIEW_EXTRA
        identity.confidence = "low"
    if identity.kind == KIND_BOOK:
        suffixes = {path.suffix.lower() for path in files}
        if suffixes == {".pdf"}:
            identity.review_reason = identity.review_reason or REVIEW_CONVERT
            identity.confidence = "low"
        elif (
            identity.isbn
            and identity.author
            and identity.title
            and identity.confidence == "high"
            and identity.review_reason != REVIEW_EXTRA
        ):
            identity.review_reason = None
    if identity.kind in (KIND_COMIC, KIND_MAGAZINE) and identity.series_name and identity.series_index:
        suffixes = {path.suffix.lower() for path in files}
        # Final shelf is CBZ only — CBR and PDF comics must remux before auto-organize.
        if identity.kind == KIND_COMIC:
            has_cbz = ".cbz" in suffixes
            needs_cbz = (".cbr" in suffixes or ".pdf" in suffixes) and not has_cbz
            if needs_cbz:
                identity.review_reason = identity.review_reason or REVIEW_CONVERT
                identity.confidence = "low"
            elif identity.confidence == "high" and identity.review_reason not in (
                REVIEW_EXTRA,
                REVIEW_COMICVINE_AMBIGUOUS,
                REVIEW_COMICVINE_UNMATCHED,
            ):
                identity.review_reason = None
        elif identity.confidence == "high" and identity.review_reason != REVIEW_EXTRA:
            identity.review_reason = None
    return files


def identify_evidence(
    folder: Path,
    indexer_item: Optional[Dict[str, Any]],
    files: Sequence[Path],
    identity: Identity,
) -> str:
    item = indexer_item or {}
    sought = item.get("sought") if isinstance(item.get("sought"), dict) else {}
    names = ", ".join(path.name for path in files)
    return (
        f"folder: {folder.name}\n"
        f"files: {names}\n"
        f"sought_kind: {sought.get('kind') or item.get('kind') or ''}\n"
        f"sought_title: {sought.get('title') or item.get('title') or ''}\n"
        f"sought_author: {sought.get('author') or item.get('author') or ''}\n"
        f"sought_isbn: {sought.get('isbn') or item.get('isbn') or ''}\n"
        f"indexer_title: {item.get('title') or ''}\n"
        f"indexer_author: {item.get('author') or ''}\n"
        f"indexer_isbn: {item.get('isbn') or ''}\n"
        f"parsed_title: {identity.title}\n"
        f"parsed_author: {identity.author}\n"
        f"parsed_kind: {identity.kind}\n"
        f"parsed_isbn: {identity.isbn}\n"
        f"parsed_series: {identity.series_name} {identity.series_index}\n"
    )


def safe_path_part(value: str, fallback: str = "Unknown") -> str:
    text = tidy_title(value) or fallback
    text = re.sub(r"[/\\:]+", " - ", text).strip(" .")
    return text or fallback


def dest_layout(identity: Dict[str, Any], settings: Any, *, filename: str, source: Optional[Path] = None) -> Path:
    kind = identity.get("kind")
    title = safe_path_part(str(identity.get("title") or "Untitled"))
    author = safe_path_part(str(identity.get("author") or ""), fallback="Unknown Author")
    series = safe_path_part(str(identity.get("series_name") or title))
    index = safe_path_part(str(identity.get("series_index") or identity.get("year") or "000"), fallback="000")
    suffix = Path(filename).suffix.lower()

    if kind == KIND_BOOK:
        dest_name = f"{title}.epub" if suffix == ".epub" else Path(filename).name
        return Path(settings.books_root) / author / title / dest_name
    if kind == KIND_MAGAZINE:
        return Path(settings.magazines_root) / series / index / Path(filename).name
    if kind == KIND_COMIC:
        publisher = safe_path_part(str(identity.get("publisher") or ""), fallback="Unknown Publisher")
        volume_year = identity.get("volume_year")
        vol = str(int(volume_year)) if str(volume_year or "").isdigit() else ""
        series_folder = f"{series} ({vol})" if vol else series
        year = identity.get("year")
        year_bit = f" ({int(year)})" if str(year or "").isdigit() else ""
        fmt = str(identity.get("comic_format") or "").lower()
        subtitle = safe_path_part(str(identity.get("comic_subtitle") or ""))
        issue = str(identity.get("series_index") or index)
        if fmt in ("tpb", "omnibus", "compendium", "hc", "gn", "oneshot") or (
            not issue and subtitle
        ):
            label = subtitle or title
            if vol:
                dest_name = f"{series} - {label}{year_bit}.cbz"
            else:
                dest_name = f"{series} - {label}{year_bit}.cbz"
        else:
            if vol:
                dest_name = f"{series} v{vol} #{issue}{year_bit}.cbz"
            else:
                dest_name = f"{series} #{issue}{year_bit}.cbz"
        if suffix != ".cbz":
            dest_name = Path(filename).name
        return Path(settings.comics_root) / publisher / series_folder / dest_name
    if kind == KIND_AUDIOBOOK:
        year_val = identity.get("year")
        year_bit = f" ({year_val})" if year_val not in (None, "") else ""
        series = str(identity.get("series_name") or "").strip()
        index = str(identity.get("series_index") or "").strip()
        # Prefer canonical Title.m4b when shelving a remuxed book; otherwise keep source name.
        if suffix == ".m4b" or str(identity.get("asin") or "").strip():
            dest_name = f"{title}.m4b"
        else:
            dest_name = Path(filename).name
        root = Path(settings.audiobooks_root)
        if series:
            index_label = f"{index} - {title}{year_bit}" if index else f"{title}{year_bit}"
            return root / author / series / index_label / dest_name
        return root / author / f"{title}{year_bit}" / dest_name
    if kind == KIND_MUSIC:
        dest_name = _music_track_filename(identity, filename=filename, source=source)
        existing = existing_album_folder(identity, settings)
        if existing is not None:
            album_folder = existing
        else:
            album = safe_path_part(str(identity.get("series_name") or identity.get("album") or title))
            album_folder = Path(settings.incoming_music_root) / author / album
        disc = _music_discnumber(identity, source=source)
        if disc:
            album_folder = album_folder / f"Disc {disc}"
        return album_folder / dest_name
    raise ValueError(f"unsupported kind {kind}")


def existing_album_folder(identity: Mapping[str, Any], settings: Any) -> Optional[Path]:
    """Join an album that already exists under incoming_music_root or music_root."""
    artist = safe_path_part(str(identity.get("author") or ""), fallback="Unknown Author")
    album = safe_path_part(
        str(identity.get("series_name") or identity.get("album") or identity.get("title") or "")
    )
    if not album:
        return None
    for attr in ("incoming_music_root", "music_root"):
        root = Path(str(getattr(settings, attr, "") or "").strip())
        if not root:
            continue
        candidate = root / artist / album
        if candidate.is_dir():
            return candidate
        artist_dir = root / artist
        if artist_dir.is_dir():
            wanted = album.casefold()
            try:
                for child in artist_dir.iterdir():
                    if child.is_dir() and child.name.casefold() == wanted:
                        return child
            except OSError:
                continue
    return None


def music_state_for_folder(settings: Any, folder: Path) -> str:
    text = Path(folder)
    try:
        text.resolve().relative_to(Path(settings.music_root).resolve())
        return "promoted"
    except (ValueError, OSError):
        return "incoming"


def _safe_source_filename(filename: str) -> str:
    """Keep the source name; only strip separators and trailing dots (not Usenet tidy)."""
    name = usenet_basename(filename)
    stem = filename_stem(name).replace("/", "-").replace("\\", "-")
    stem = re.sub(r"[:]+", " - ", stem).strip(" .")
    suffix = ""
    lower = name.lower()
    for ext in sorted(_STEM_EXTENSIONS, key=len, reverse=True):
        if lower.endswith(ext):
            suffix = name[len(name) - len(ext) :]
            break
    if not suffix and "." in name:
        maybe = name.rsplit(".", 1)[-1]
        if maybe.isalnum() and 1 <= len(maybe) <= 5:
            suffix = f".{maybe}"
    if not stem:
        return name or "track"
    return f"{stem}{suffix}"


def _music_track_filename(_identity: Mapping[str, Any], *, filename: str, source: Optional[Path]) -> str:
    """Original filename unless embedded track number + title tags exist (`NN - Title.ext`)."""
    # Folder/parse identity must not invent a dump-named track file.
    tags: Dict[str, Any] = {}
    if source is not None:
        try:
            from librarian.metadata import read_audio_tags

            tags = read_audio_tags(Path(source))
        except Exception:
            tags = {}
    track_title = str(tags.get("track_title") or "").strip()
    number = str(tags.get("tracknumber") or "").strip()
    if track_title and number.isdigit():
        name = safe_path_part(track_title)
        return f"{int(number):02d} - {name}{Path(filename).suffix}"
    return _safe_source_filename(filename)


def _music_discnumber(identity: Mapping[str, Any], *, source: Optional[Path]) -> str:
    """Disc folder segment when a trustworthy discnumber tag (or identity) is present."""
    raw = str(identity.get("discnumber") or "").strip()
    if not raw and source is not None:
        try:
            from librarian.metadata import read_audio_tags

            tags = read_audio_tags(Path(source))
            raw = str(tags.get("discnumber") or "").strip()
        except Exception:
            raw = ""
    if not raw or not raw.isdigit():
        return ""
    number = int(raw)
    return str(number) if number >= 1 else ""


def expected_payload_ok(kind: str, files: Sequence[Path]) -> Optional[str]:
    if not files:
        return REVIEW_NO_PAYLOAD
    suffixes = {path.suffix.lower() for path in files}
    if kind == KIND_COMIC and ".cbr" in suffixes and ".cbz" not in suffixes:
        return REVIEW_CONVERT
    if kind == KIND_BOOK and suffixes == {".pdf"}:
        return REVIEW_CONVERT
    return None
