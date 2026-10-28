"""Shelf layout names: ``Author/Title (id)``, Calibre volumes, and scanned library files.

Calibre swaps path punctuation for underscores. A single trailing underscore
is a period (``G.G_``), a single underscore before the rest of a title is a
colon (``Resist_ Tales``), and a parenthetical that is not a number is the
series. Names with several underscores are release dumps and never parse.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from librarian.kinds import KIND_COMIC, KIND_MAGAZINE
from librarian.naming.release import parse_usenet_name
from librarian.naming.tokens import tidy_title

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

_CALIBRE_ID = re.compile(r"\s*\(\d+\)\s*$")
_SERIES_PAREN = re.compile(r"^(?P<title>.+?)\s*\((?P<series>[^)]+)\)$")


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


def title_and_series(name: str) -> Tuple[str, str]:
    """Title and parenthetical series from a volume folder name, Calibre ``(id)`` dropped."""
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
    title, series = title_and_series(volume.name)
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


def library_file_fields(kind: str, folder: Path, files: Sequence[Path]) -> Dict[str, Any]:
    """Weakest scan layer: the first file stem (or the folder) parsed as a release name."""
    name = files[0].stem if files else folder.name
    parsed = parse_usenet_name(name)
    out: Dict[str, Any] = {}
    if parsed.title:
        out["title"] = parsed.title
    if parsed.author:
        out["author"] = parsed.author
    if parsed.series_name:
        out["series_name"] = parsed.series_name
    if parsed.series_index:
        out["series_index"] = parsed.series_index
    if parsed.year:
        out["year"] = parsed.year
    if parsed.isbn:
        out["isbn"] = parsed.isbn
    if kind in (KIND_COMIC, KIND_MAGAZINE) and not out.get("series_name"):
        out["series_name"] = tidy_title(folder.parent.name if folder.parent != folder else folder.name)
    return out
