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

COMPLETE_ROOT_FALLBACKS = ("/data/usenet/complete",)

REVIEW_UNKNOWN = "unknown_identity"
REVIEW_LOW = "low_confidence"
REVIEW_UNEXPECTED = "unexpected_kind"
REVIEW_NO_PAYLOAD = "no_payload"
REVIEW_UNPACK_STUCK = "unpack_stuck"
REVIEW_EXTRA = "extra_files"
REVIEW_CONVERT = "convert_failed"
REVIEW_COLLISION = "collision"
REVIEW_MISSING_FOLDER = "missing_folder"

_DOT_GROUP = re.compile(r"[\.\-_]+")
_ISBN = re.compile(r"\b(?:97[89][-\s]?)?(?:\d[-\s]?){9}[\dXx]\b")
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
SIDECAR_NAMES = {"metadata.opf", "comicinfo.xml", "cover.jpg", "cover.png", "nfo"}
JUNK_EXTENSIONS = {".par2", ".nzb", ".nfo", ".sfv", ".srr", ".url"}
JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
ARCHIVE_EXTENSIONS = {".rar", ".7z"}
UNPACK_STUCK = REVIEW_UNPACK_STUCK  # jobs / ingest compare against this name
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
    mbid: str = ""
    album: str = ""
    track_title: str = ""
    tracknumber: str = ""
    discnumber: str = ""
    recording_mbid: str = ""
    publisher: str = ""
    description: str = ""
    genre: str = ""
    confidence: str = "low"
    rationale: str = ""
    query_terms: List[str] = field(default_factory=list)
    review_reason: Optional[str] = None
    source: str = "parse"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "author": self.author,
            "series_name": self.series_name,
            "series_index": self.series_index,
            "year": self.year,
            "isbn": self.isbn,
            "mbid": self.mbid,
            "album": self.album,
            "track_title": self.track_title,
            "tracknumber": self.tracknumber,
            "discnumber": self.discnumber,
            "recording_mbid": self.recording_mbid,
            "publisher": self.publisher,
            "description": self.description,
            "genre": self.genre,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "query_terms": list(self.query_terms),
            "review_reason": self.review_reason,
            "source": self.source,
        }


def tidy_title(value: str) -> str:
    text = _DOT_GROUP.sub(" ", value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


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


def parse_usenet_name(name: str, *, category: object = None, kind: object = None) -> Identity:
    """Deterministic Usenet / folder parse. Never invents an ISBN. Filename layer is weak."""
    raw = Path(name).name
    stem = Path(raw).stem
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

    comic = None
    if hinted != KIND_MAGAZINE:
        comic = (
            _COMIC_HASH_YEAR.search(stem)
            or _COMIC_VOLUME.search(stem)
            or _COMIC_YEAR_ISSUE.search(stem)
            or _COMIC_HASH.search(stem)
        )
        if comic is None and hinted in ("", KIND_COMIC):
            padded = _COMIC_PADDED.search(stem)
            if padded and (hinted == KIND_COMIC or padded.group("issue").startswith("0")):
                comic = padded
    if comic and (hinted in ("", KIND_COMIC) or "comic" in stem.lower()):
        series = tidy_title(comic.group("series"))
        issue = str(int(comic.group("issue")))
        year = int(comic.group("year")) if "year" in comic.groupdict() and comic.groupdict().get("year") else None
        return Identity(
            kind=hinted or KIND_COMIC,
            title=f"{series} #{issue}",
            series_name=series,
            series_index=issue,
            year=year,
            isbn=isbn,
            confidence="high" if series and issue else "low",
            rationale="comic series/issue parse",
            query_terms=[series, issue],
            source="parse",
        )

    year_match = _YEAR.search(stem)
    year = int(year_match.group(1)) if year_match else None

    def _clean_piece(value: str) -> str:
        text = _EBOOK_GROUP.sub("", value)
        text = _AUDIO_PART.sub("", text)
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
        if any(token in stem.lower() for token in ("m4b", "audiobook", "unabridged")):
            inferred = KIND_AUDIOBOOK
        elif any(token in stem.lower() for token in ("flac", "mp3", "vinyl", "album")):
            inferred = KIND_MUSIC
        else:
            inferred = KIND_BOOK

    if inferred == KIND_AUDIOBOOK and title:
        title = tidy_title(_AUDIO_PART.sub("", title)) or title

    high = bool(isbn and author and title) if inferred == KIND_BOOK else False
    return Identity(
        kind=inferred,
        title=title or track_title or tidy_title(stem),
        author=author,
        series_name=album,
        album=album,
        track_title=track_title,
        tracknumber=tracknumber,
        discnumber=discnumber,
        year=year,
        isbn=isbn,
        confidence="high" if high else "low",
        rationale="indexer/parse fields" if isbn else "filename parse",
        query_terms=[part for part in (author, title, isbn) if part],
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
        "mbid",
        "album",
        "track_title",
        "tracknumber",
        "discnumber",
        "recording_mbid",
        "publisher",
        "description",
        "genre",
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
    elif identity.kind in (KIND_COMIC, KIND_MAGAZINE) and identity.series_name and identity.series_index:
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
    elif identity.kind == KIND_AUDIOBOOK and identity.author and identity.title:
        identity.confidence = "high"
        identity.rationale = identity.rationale or "audiobook author + title"
        identity.review_reason = None
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
        if candidate.name in {"complete", "downloads", "usenet", "data"}:
            continue
        if list_payload_files(candidate):
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
    suggested = suggest_payload_folder(resolved)
    if problem and suggested is None and usable_folder(raw) and resolved != raw:
        suggested = suggest_payload_folder(raw)
    payload = inspection.get("payload") or []
    archives = inspection.get("archives") or []
    junk = inspection.get("junk") or []
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
        tried = (
            f"Opened {resolved}. Found {len(archives)} archive file(s) and no readable media "
            f"(also {len(junk)} junk/sidecar file(s))."
        )
    elif problem == REVIEW_NO_PAYLOAD and empty_dir:
        tried = f"Opened {resolved}. The folder is empty."
    elif problem == REVIEW_NO_PAYLOAD:
        tried = f"Opened {resolved}. Found {len(junk)} non-media file(s) and no {looked_for}."
    else:
        tried = f"Opened {resolved}. Found {len(payload)} readable file(s) this Librarian can shelve."
    return {
        "path": str(resolved) if usable_folder(resolved) else str(raw or ""),
        "resolved_path": str(resolved) if usable_folder(resolved) else "",
        "problem": problem,
        "payload_count": len(payload),
        "archive_count": len(archives),
        "junk_count": len(junk),
        "looked_for": looked_for,
        "tried": tried,
        "path_note": path_layout_note(resolved if usable_folder(resolved) else raw),
        "suggested_folder": str(suggested) if suggested is not None else None,
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
    files = list_payload_files(folder)
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
        if problem == REVIEW_MISSING_FOLDER:
            problem = REVIEW_NO_PAYLOAD
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

    identity.source = identity.source or "stack"
    _apply_review_gates(identity, files)

    if identity.confidence != "high" and llm_client is not None:
        evidence = _identify_evidence(folder, indexer_item, files, identity)
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
    """
    kind = identity.kind
    if kind in (KIND_BOOK, KIND_MAGAZINE, KIND_AUDIOBOOK) and identity.isbn:
        if identity.title and identity.author:
            return {}
        return _catalog_isbn(identity, settings, transport=transport)
    if kind == KIND_MUSIC:
        return _catalog_music(identity, settings, transport=transport)
    if kind == KIND_COMIC:
        return _catalog_comic(identity, settings, transport=transport)
    return {}


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
    if identity.year is not None and identity.author:
        return {}
    try:
        from librarian.comicvine import ComicVineClient, ComicVineError

        client = ComicVineClient(key, transport=transport)
        try:
            issues = client.series_issues(identity.series_name)
        except ComicVineError:
            issues = []
        finally:
            client.close()
    except Exception:
        return {}
    want = str(identity.series_index)
    for row in issues:
        if str(row.get("series_index") or "") != want:
            continue
        out = {key: row[key] for key in ("title", "author", "year", "publisher") if row.get(key) not in (None, "")}
        out.pop("isbn", None)
        return out
    return {}


def _kind_from_payload(files: Sequence[Path], folder: Path) -> str:
    suffixes = {path.suffix.lower() for path in files}
    names = " ".join([folder.name, *(path.name for path in files)]).lower()
    if suffixes & {".cbz", ".cbr", ".cbt"}:
        return KIND_COMIC
    if suffixes & {".m4b"} or "audiobook" in names:
        return KIND_AUDIOBOOK
    if suffixes & {".flac", ".mp3", ".m4a", ".ogg", ".opus"} and ".epub" not in suffixes:
        return KIND_MUSIC
    if suffixes & {".epub", ".mobi", ".azw3", ".kepub"}:
        return KIND_BOOK
    if suffixes == {".pdf"}:
        return KIND_BOOK
    return ""


def _apply_review_gates(identity: Identity, files: Sequence[Path]) -> None:
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
        if identity.kind == KIND_COMIC and suffixes & {".cbr", ".pdf"} and ".cbz" not in suffixes:
            identity.review_reason = identity.review_reason or REVIEW_CONVERT
            identity.confidence = "low"

    if identity.kind == KIND_AUDIOBOOK and not (identity.author and identity.title):
        identity.review_reason = identity.review_reason or REVIEW_UNKNOWN
        identity.confidence = "low"

    if identity.kind == KIND_MUSIC and identity.confidence != "high":
        identity.review_reason = identity.review_reason or (REVIEW_LOW if identity.title else REVIEW_UNKNOWN)
        identity.confidence = "low"

    if identity.kind == KIND_BOOK and identity.confidence != "high":
        identity.isbn = extract_isbn(identity.isbn)


def _unexpected_extra_files(files: Sequence[Path]) -> bool:
    return len(files) > 1 and not all(
        _AUDIO_PART.search(path.name) or path.suffix.lower() in {".mp3", ".m4b", ".flac"} for path in files
    )


def _apply_post_llm_review(identity: Identity, folder: Path) -> List[Path]:
    """Folder hygiene after a successful LLM identity. Never auto-organize extra files."""
    files = list_payload_files(folder)
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
        if identity.kind == KIND_COMIC and suffixes & {".cbr", ".pdf"} and ".cbz" not in suffixes:
            identity.review_reason = identity.review_reason or REVIEW_CONVERT
            identity.confidence = "low"
        elif identity.confidence == "high" and identity.review_reason != REVIEW_EXTRA:
            identity.review_reason = None
    return files


def _identify_evidence(
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
        dest_name = f"{series} #{identity.get('series_index') or index}.cbz" if suffix == ".cbz" else Path(filename).name
        return Path(settings.comics_root) / series / index / dest_name
    if kind == KIND_AUDIOBOOK:
        dest_name = Path(filename).name
        return Path(settings.audiobooks_root) / author / title / dest_name
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
    name = Path(filename).name
    stem = Path(name).stem.replace("/", "-").replace("\\", "-")
    stem = re.sub(r"[:]+", " - ", stem).strip(" .")
    suffix = Path(name).suffix
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
    if kind == KIND_COMIC and suffixes & {".cbr", ".pdf"} and ".cbz" not in suffixes:
        return REVIEW_CONVERT
    if kind == KIND_BOOK and suffixes == {".pdf"}:
        return REVIEW_CONVERT
    return None
