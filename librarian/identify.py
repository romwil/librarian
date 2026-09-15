"""Identify completed downloads. Auto-organize only when confident."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from librarian.kinds import (
    KIND_AUDIOBOOK,
    KIND_BOOK,
    KIND_COMIC,
    KIND_MAGAZINE,
    KIND_MUSIC,
    kind_from_newznab,
)

REVIEW_UNKNOWN = "unknown_identity"
REVIEW_LOW = "low_confidence"
REVIEW_UNEXPECTED = "unexpected_kind"
REVIEW_NO_PAYLOAD = "no_payload"
REVIEW_EXTRA = "extra_files"
REVIEW_CONVERT = "convert_failed"
REVIEW_COLLISION = "collision"

_DOT_GROUP = re.compile(r"[\.\-_]+")
_ISBN = re.compile(r"\b(?:97[89][-\s]?)?(?:\d[-\s]?){9}[\dXx]\b")
_COMIC_HASH = re.compile(
    r"^(?P<series>.+?)[\.\s]+(?:#|No\.?)\s*(?P<issue>\d{1,4})(?:[\.\s].*)?$",
    re.IGNORECASE,
)
_COMIC_YEAR_ISSUE = re.compile(
    r"^(?P<series>.+?)[\.\s]+(?P<year>19\d{2}|20\d{2})[\.\s]+(?P<issue>\d{1,4})(?:[\.\s].*)?$",
    re.IGNORECASE,
)
_MAG_NO = re.compile(
    r"^(?P<title>.+?)[\.\s]+No\.?\s*(?P<num>\d+)[\.\s]+(?P<year>19\d{2}|20\d{2})",
    re.IGNORECASE,
)
_MAG_MONTH = re.compile(
    r"^(?P<title>.+?)[\.\s]+(?P<year>19\d{2}|20\d{2})[\.\s-]+(?P<month>0?[1-9]|1[0-2])",
    re.IGNORECASE,
)
_EBOOK_GROUP = re.compile(r"[\.\s]eBook(?:-|\.)(?P<group>[A-Za-z0-9]+)", re.IGNORECASE)
_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")
_AUDIO_PART = re.compile(r"\b(?:part|cd|disc)\s*(\d+)\b", re.IGNORECASE)

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


@dataclass
class Identity:
    kind: str
    title: str
    author: str = ""
    series_name: str = ""
    series_index: str = ""
    year: Optional[int] = None
    isbn: str = ""
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


def parse_usenet_name(name: str, *, category: object = None) -> Identity:
    """Deterministic Usenet / folder parse. Never invents an ISBN."""
    raw = Path(name).name
    stem = Path(raw).stem
    isbn = extract_isbn(stem)
    kind = kind_from_newznab(category) or ""

    mag = _MAG_NO.search(stem) or _MAG_MONTH.search(stem)
    if mag:
        title = tidy_title(mag.group("title"))
        year = int(mag.group("year"))
        if mag.groupdict().get("num"):
            num = int(mag.group("num"))
            index = f"{year}-{num:02d}" if 1 <= num <= 12 else f"{year}-{num}"
        else:
            index = f"{year}-{int(mag.group('month')):02d}"
        return Identity(
            kind=kind or KIND_MAGAZINE,
            title=title,
            series_name=title,
            series_index=index,
            year=year,
            isbn=isbn,
            confidence="high" if (kind in ("", KIND_MAGAZINE) and title and index) else "low",
            rationale="magazine issue parse",
            query_terms=[title, index],
            source="parse",
        )

    comic = _COMIC_YEAR_ISSUE.search(stem) or _COMIC_HASH.search(stem)
    if comic and (kind in ("", KIND_COMIC) or "comic" in stem.lower()):
        series = tidy_title(comic.group("series"))
        issue = str(int(comic.group("issue")))
        year = int(comic.group("year")) if "year" in comic.groupdict() and comic.groupdict().get("year") else None
        return Identity(
            kind=kind or KIND_COMIC,
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
        text = _YEAR.sub("", text)
        text = _ISBN.sub("", text)
        return tidy_title(text)

    author = ""
    title = ""
    if " - " in stem:
        author, title = [_clean_piece(part) for part in stem.split(" - ", 1)]
    else:
        cleaned = _clean_piece(stem)
        title = cleaned
        if kind == KIND_BOOK and " by " in cleaned.lower():
            head, tail = re.split(r"\s+by\s+", cleaned, maxsplit=1, flags=re.IGNORECASE)
            title, author = head.strip(), tail.strip()

    inferred = kind
    if not inferred:
        if any(token in stem.lower() for token in ("m4b", "audiobook", "unabridged")):
            inferred = KIND_AUDIOBOOK
        elif any(token in stem.lower() for token in ("flac", "mp3", "vinyl", "album")):
            inferred = KIND_MUSIC
        else:
            inferred = KIND_BOOK

    high = bool(isbn and author and title) if inferred == KIND_BOOK else bool(title)
    return Identity(
        kind=inferred,
        title=title or tidy_title(stem),
        author=author,
        year=year,
        isbn=isbn,
        confidence="high" if high else "low",
        rationale="indexer/parse fields" if isbn else "filename parse",
        query_terms=[part for part in (author, title, isbn) if part],
        source="parse",
    )


def identity_from_indexer(item: Dict[str, Any]) -> Identity:
    title = tidy_title(str(item.get("title") or item.get("book_title") or ""))
    author = tidy_title(str(item.get("author") or ""))
    isbn = extract_isbn(str(item.get("isbn") or item.get("title") or ""))
    category = item.get("category") or item.get("cat")
    parsed = parse_usenet_name(str(item.get("name") or item.get("title") or ""), category=category)
    if not parsed.isbn:
        parsed.isbn = isbn
    if author:
        parsed.author = author
    if title and not parsed.series_name:
        parsed.title = title
    if parsed.kind in (KIND_BOOK,) and parsed.isbn and parsed.author and parsed.title:
        parsed.confidence = "high"
        parsed.rationale = "indexer ISBN + author + title"
    elif parsed.kind in (KIND_COMIC, KIND_MAGAZINE) and parsed.series_name and parsed.series_index:
        parsed.confidence = "high"
        parsed.rationale = "indexer series + issue"
    parsed.source = "indexer"
    return parsed


def list_payload_files(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    if folder.is_file():
        return [folder] if folder.suffix.lower() in MEDIA_EXTENSIONS else []
    found: List[Path] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        if path.name.lower() in SIDECAR_NAMES:
            continue
        if path.suffix.lower() in MEDIA_EXTENSIONS:
            found.append(path)
    return found


def usable_folder(folder: Optional[Union[Path, str]]) -> bool:
    """True when a path is a real location, not empty / cwd (Path(''))."""
    text = str(folder or "").strip()
    return bool(text) and text not in {".", str(Path())}


def resolve_storage_path(storage: Path, complete_root: str = "") -> Path:
    """Map a SAB container path (often /downloads/...) onto a directory this process can read."""
    if not usable_folder(storage):
        return storage
    if storage.exists():
        return storage
    root = str(complete_root or "").strip()
    if not root:
        return storage
    root_path = Path(root)
    parts = storage.parts[1:] if storage.parts and storage.parts[0] == "/" else storage.parts
    if not parts:
        return storage
    without_mount = Path(*parts[1:]) if len(parts) > 1 else Path(parts[0])
    candidates = [root_path / without_mount, root_path / Path(*parts), root_path / storage.name]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def identify_completed(
    folder: Path,
    *,
    indexer_item: Optional[Dict[str, Any]] = None,
    category: object = None,
    llm_client: Any = None,
) -> Dict[str, Any]:
    """Identify a completed SAB folder. Unexpected results go to Review."""
    files = list_payload_files(folder)
    if not files:
        identity = identity_from_indexer(indexer_item or {"title": folder.name, "category": category})
        identity.review_reason = REVIEW_NO_PAYLOAD
        identity.confidence = "low"
        return {"identity": identity.as_dict(), "files": [], "auto_organize": False}

    extra = _unexpected_extra_files(files)
    if indexer_item:
        identity = identity_from_indexer({**indexer_item, "category": category or indexer_item.get("category")})
    else:
        identity = parse_usenet_name(folder.name, category=category)

    if extra and identity.kind not in (KIND_MUSIC, KIND_AUDIOBOOK, KIND_MAGAZINE):
        identity.review_reason = REVIEW_EXTRA
        identity.confidence = "low"

    if identity.kind not in (KIND_BOOK, KIND_MAGAZINE, KIND_COMIC, KIND_AUDIOBOOK, KIND_MUSIC):
        identity.review_reason = identity.review_reason or REVIEW_UNEXPECTED
        identity.confidence = "low"

    if identity.kind == KIND_BOOK:
        suffixes = {path.suffix.lower() for path in files}
        if suffixes == {".pdf"}:
            # Native EPUB preferred; PDF-only book dumps go to Review until convert ships.
            identity.review_reason = identity.review_reason or REVIEW_CONVERT
            identity.confidence = "low"
        if identity.confidence != "high" or not (identity.isbn and identity.author and identity.title):
            if not identity.review_reason:
                identity.review_reason = REVIEW_LOW if identity.title else REVIEW_UNKNOWN
                identity.confidence = "low"

    if identity.kind in (KIND_COMIC, KIND_MAGAZINE):
        if not (identity.series_name and identity.series_index):
            identity.review_reason = identity.review_reason or REVIEW_UNKNOWN
            identity.confidence = "low"
        suffixes = {path.suffix.lower() for path in files}
        if identity.kind == KIND_COMIC and suffixes & {".cbr", ".pdf"} and ".cbz" not in suffixes:
            identity.review_reason = identity.review_reason or REVIEW_CONVERT
            identity.confidence = "low"

    if identity.kind == KIND_AUDIOBOOK and not identity.author:
        identity.review_reason = identity.review_reason or REVIEW_UNKNOWN
        identity.confidence = "low"

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
    names = ", ".join(path.name for path in files)
    return (
        f"folder: {folder.name}\n"
        f"files: {names}\n"
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


def dest_layout(identity: Dict[str, Any], settings: Any, *, filename: str) -> Path:
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
        album = safe_path_part(str(identity.get("series_name") or title))
        return Path(settings.incoming_music_root) / author / album / Path(filename).name
    raise ValueError(f"unsupported kind {kind}")


def expected_payload_ok(kind: str, files: Sequence[Path]) -> Optional[str]:
    if not files:
        return REVIEW_NO_PAYLOAD
    suffixes = {path.suffix.lower() for path in files}
    if kind == KIND_COMIC and suffixes & {".cbr", ".pdf"} and ".cbz" not in suffixes:
        return REVIEW_CONVERT
    if kind == KIND_BOOK and suffixes == {".pdf"}:
        return REVIEW_CONVERT
    return None
