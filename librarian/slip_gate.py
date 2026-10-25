"""Shelve a clear book before a slip exists.

Match order for an already-shelved work: ISBN, then title plus author, then
subtitle, then series plus index. Title alone never matches. A folder with
nothing readable is a skip, not a slip. Shelved files are never deleted.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from librarian.db import Database
from librarian.kinds import KIND_BOOK
from librarian.review_reasons import (
    REVIEW_COLLISION,
    REVIEW_CONVERT,
    REVIEW_EXTRA,
    REVIEW_LOW,
    REVIEW_UNKNOWN,
)

_BOOK_EXTENSIONS = {".epub", ".pdf", ".mobi", ".azw", ".azw3", ".azw4", ".kfx"}
_STAGING_ROOTS = frozenset(
    {
        "inbox",
        "complete",
        "downloads",
        "download",
        "usenet",
        "newlib",
        "books",
        "comics",
        "magazines",
        "audiobooks",
        "music",
        "incoming",
        "incoming-music",
        "media",
        "data",
        "tmp",
        "temp",
        "drop",
        "watch",
        "mnt",
        "user",
        "appdata",
        "private",
        "var",
        "folders",
    }
)


def _same(left: object, right: object) -> bool:
    a = str(left or "").strip().casefold()
    b = str(right or "").strip().casefold()
    return bool(a) and a == b


def _staging_author(name: str) -> bool:
    raw = str(name or "").strip()
    if not raw or raw in {".", ".."}:
        return True
    key = raw.casefold()
    compact = re.sub(r"[\s_\-]+", "", key)
    if key in _STAGING_ROOTS or compact in _STAGING_ROOTS:
        return True
    if "migrated" in key:
        return True
    if key.startswith(("test_", "pytest", "tmp", "private")):
        return True
    # Calibre-style folders sometimes keep a single trailing underscore after
    # an author name (for example ``Box, C.J_``). It is cosmetic, unlike
    # embedded underscore release names such as ``Some_Author_Collection``.
    if "_" in raw.rstrip("_"):
        return True
    if len(raw) > 80:
        return True
    return False


_CALIBRE_ID = re.compile(r"\s*\(\d+\)\s*$")
_SERIES_PAREN = re.compile(r"^(?P<title>.+?)\s*\((?P<series>[^)]+)\)$")


def restore_path_punctuation(name: str) -> str:
    """Turn a single folder underscore back into the punctuation it replaced.

    A trailing underscore after initials is a period (``G.G_`` → ``G.G.``).
    One underscore before the rest of a title is a colon (``Resist_ Tales``).
    Names with several underscores stay untouched so dumps are still rejected.
    """
    text = re.sub(r"\s+", " ", str(name or "").strip())
    if text.count("_") != 1:
        return text
    if text.endswith("_"):
        return text[:-1] + "."
    if re.search(r"_\s+\S", text):
        return re.sub(r"_\s+", ": ", text, count=1)
    return text


def _title_and_series(name: str) -> Tuple[str, str]:
    text = _CALIBRE_ID.sub("", restore_path_punctuation(name)).strip()
    match = _SERIES_PAREN.match(text)
    if match and not match.group("series").strip().isdigit():
        return match.group("title").strip(), match.group("series").strip()
    return text, ""


def parse_library_volume(folder: Path) -> Optional[Dict[str, str]]:
    """Author, title, and series from ``Author/Title (id)`` or a Calibre volume.

    Periods in initials stay periods. A clean parse is confident enough to file;
    a dump name or a staging directory is not a parse.
    """
    path = Path(folder)
    volume = path if path.is_dir() else path.parent
    author = restore_path_punctuation(volume.parent.name)
    title, series = _title_and_series(volume.name)
    if not author or not title:
        return None
    if _staging_author(author) or _staging_author(title):
        return None
    if "_" in author or "_" in title:
        return None
    if author.casefold() == title.casefold():
        return None
    return {"author": author, "title": title, "series_name": series}


def path_author_title(folder: Path) -> Optional[Tuple[str, str]]:
    """Author/Title from a volume folder. Staging roots and dump names do not count."""
    parsed = parse_library_volume(folder)
    if not parsed:
        return None
    return parsed["author"], parsed["title"]


def _book_files(files: Sequence[Path]) -> List[Path]:
    return [Path(path) for path in files if Path(path).suffix.lower() in _BOOK_EXTENSIONS]


def folder_is_path_clear(folder: Path) -> bool:
    """True when Author/Title holds an epub or pdf (or another book encoding)."""
    from librarian.identify import list_payload_files

    parsed = path_author_title(folder)
    if not parsed:
        return False
    root = Path(folder)
    volume = root if root.is_dir() else root.parent
    if not volume.exists():
        return False
    return bool(_book_files(list_payload_files(volume)))


def sign_path_clear_dict(identity: Dict[str, Any], folder: Path, files: Sequence[Path]) -> None:
    """Same path-clear sign as ``sign_path_clear_book``, for an organize identity dict."""

    class _Box:
        kind = ""
        title = ""
        author = ""
        review_reason = None
        confidence = "low"
        rationale = ""

    box = _Box()
    box.kind = str(identity.get("kind") or "")
    box.title = str(identity.get("title") or "")
    box.author = str(identity.get("author") or "")
    box.review_reason = identity.get("review_reason")
    box.confidence = str(identity.get("confidence") or "low")
    box.rationale = str(identity.get("rationale") or "")
    sign_path_clear_book(box, folder, files)
    identity["kind"] = box.kind
    identity["title"] = box.title
    identity["author"] = box.author
    identity["review_reason"] = box.review_reason
    identity["confidence"] = box.confidence
    identity["rationale"] = box.rationale


def sign_path_clear_book(identity: Any, folder: Path, files: Sequence[Path]) -> None:
    """Sign a book from an Author/Title path. Title alone stays unsigned.

    When the author field is the title, the folder is parsed first. A clear
    path with a readable book file is high confidence even without an ISBN.
    """
    from librarian.identify import looks_like_dump_title

    if str(getattr(identity, "kind", "") or "") != KIND_BOOK:
        return
    if identity.review_reason == REVIEW_EXTRA:
        return
    volume = Path(folder)
    if not volume.is_dir():
        volume = volume.parent
    parsed = path_author_title(volume)
    if _same(identity.author, identity.title):
        if parsed:
            identity.author, identity.title = parsed
        else:
            identity.review_reason = REVIEW_UNKNOWN
            identity.confidence = "low"
            return
    if not parsed:
        return
    author, title = parsed
    if not str(identity.author or "").strip():
        identity.author = author
    if not str(identity.title or "").strip() or looks_like_dump_title(str(identity.title or "")):
        identity.title = title
    if not _same(identity.author, author):
        return
    if _same(identity.author, identity.title):
        identity.review_reason = REVIEW_UNKNOWN
        identity.confidence = "low"
        return
    if not _book_files(files):
        return
    if identity.review_reason in (None, "", REVIEW_LOW, REVIEW_UNKNOWN, REVIEW_CONVERT):
        identity.review_reason = None
        identity.confidence = "high"
        identity.rationale = "author/title path"


def _classify(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    unique: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        work_id = str(row.get("id") or "")
        if not work_id or work_id in seen:
            continue
        seen.add(work_id)
        unique.append(row)
    if len(unique) == 1:
        return {"status": "unique", "work": unique[0], "works": unique}
    if len(unique) > 1:
        return {"status": "ambiguous", "work": None, "works": unique}
    return {"status": "none", "work": None, "works": []}


def match_shelved(db: Database, identity: Dict[str, Any]) -> Dict[str, Any]:
    """Find a shelved work. Title alone returns none."""
    from librarian.identify import extract_isbn

    kind = str(identity.get("kind") or "")
    isbn = extract_isbn(str(identity.get("isbn") or ""))
    if isbn:
        hit = _classify(db.list_shelved_by_isbn(isbn))
        if hit["status"] != "none":
            return hit
    title = str(identity.get("title") or "").strip()
    author = str(identity.get("author") or "").strip()
    if title and author and not _same(title, author):
        hit = _classify(db.list_shelved_by_title_author(kind=kind, title=title, author=author))
        if hit["status"] != "none":
            return hit
    subtitle = str(identity.get("subtitle") or identity.get("comic_subtitle") or "").strip()
    if subtitle:
        hit = _classify(db.list_shelved_by_subtitle(subtitle))
        if hit["status"] != "none":
            return hit
    series = str(identity.get("series_name") or "").strip()
    index = str(identity.get("series_index") or "").strip()
    if series and index:
        hit = _classify(
            db.list_shelved_by_series(kind=kind, series_name=series, series_index=index)
        )
        if hit["status"] != "none":
            return hit
    return {"status": "none", "work": None, "works": []}


def shelf_match_for_organize(db: Database, identity: Dict[str, Any]) -> Dict[str, Any]:
    """Drop a unique shelf match. Two close matches stay a slip. Never deletes files.

    Music tracks join an existing album under the same artist and title, so a
    title-plus-author hit is not a duplicate book.
    """
    if str(identity.get("kind") or "") == "music":
        return {"drop": False, "work": None, "ambiguous": False}
    matched = match_shelved(db, identity)
    if matched["status"] == "unique":
        return {
            "drop": True,
            "work": matched["work"],
            "ambiguous": False,
        }
    if matched["status"] == "ambiguous":
        identity["review_reason"] = REVIEW_COLLISION
        identity["confidence"] = "low"
        return {"drop": False, "work": None, "ambiguous": True}
    return {"drop": False, "work": None, "ambiguous": False}


def accept_path_clear_slips(db: Database, *, reason: str) -> Dict[str, Any]:
    """Shelve path-clear slips in one reason group. Leave every file on disk."""
    from librarian.identify import list_payload_files

    wanted = str(reason or "").strip()
    accepted = 0
    kept = 0
    works = db.list_works(review_state="needs_review", review_reason=wanted or None, limit=20000)
    if not wanted:
        works = db.list_works(review_state="needs_review", limit=20000)
    for work in works:
        if wanted and str(work.get("review_reason") or "") != wanted:
            continue
        folder_raw = str(work.get("folder_path") or "")
        folder = Path(folder_raw) if folder_raw else Path()
        if not folder_is_path_clear(folder):
            kept += 1
            continue
        parsed = path_author_title(folder if folder.is_dir() else folder.parent)
        identity = {
            "kind": work.get("kind") or KIND_BOOK,
            "title": (parsed[1] if parsed else work.get("title")) or "",
            "author": (parsed[0] if parsed else work.get("author")) or "",
            "isbn": work.get("isbn") or "",
            "subtitle": work.get("subtitle") or "",
            "series_name": work.get("series_name") or "",
            "series_index": work.get("series_index") or "",
        }
        if _same(identity["author"], identity["title"]):
            kept += 1
            continue
        matched = match_shelved(db, identity)
        if matched["status"] == "ambiguous":
            kept += 1
            continue
        if matched["status"] == "unique":
            db.upsert_work({**work, "review_state": "resolved", "review_reason": None})
            accepted += 1
            continue
        volume = folder if folder.is_dir() else folder.parent
        payload = _book_files(list_payload_files(volume))
        shelved = db.upsert_work(
            {
                **work,
                "kind": KIND_BOOK,
                "title": identity["title"] or work.get("title") or volume.name,
                "author": identity["author"] or work.get("author"),
                "folder_path": str(volume),
                "review_state": "none",
                "review_reason": None,
                "confidence": "high",
            }
        )
        for path in payload:
            db.upsert_file(
                {
                    "work_id": shelved["id"],
                    "path": str(path),
                    "filename": path.name,
                    "kind": KIND_BOOK,
                    "size": path.stat().st_size if path.is_file() else 0,
                }
            )
        accepted += 1
    return {"accepted": accepted, "kept": kept, "reason": wanted}
