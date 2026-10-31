"""Ebook scene-release names → author + title. Calibre ``(id)`` suffixes dropped."""

from __future__ import annotations

import re
from typing import Optional, Tuple

from librarian.naming.tokens import YEAR, tidy_title

_CALIBRE_ID = re.compile(r"\s*\(\d+\)\s*$")
_SCENE_GROUP = re.compile(r"-([A-Za-z0-9]{2,16})$")
_SCENE_EBOOK_TAIL = re.compile(
    r"(?i)(?:[\.\-_ ]+)(?:epub|mobi|azw3?|pdf|ebook|retail|proper|repack|hybrid|"
    r"kindle|digital|web-?rip|bitbook)(?:[\.\-_ ].*)?$"
)
_BY_SPLIT = re.compile(r"\s+by\s+", re.IGNORECASE)


def strip_calibre_suffix(name: str) -> str:
    """Drop a trailing Calibre ``(11630)`` so the title can match the shelf."""
    return _CALIBRE_ID.sub("", str(name or "")).strip()


def _looks_like_scene(raw: str) -> bool:
    """True for dotted Usenet dumps, not Calibre ``Title - Author.epub`` or ``hobbit-rip``."""
    if _BY_SPLIT.search(raw):
        return True
    dots = raw.count(".")
    has_year = bool(YEAR.search(raw))
    has_ebook = bool(_SCENE_EBOOK_TAIL.search(raw))
    has_group = bool(_SCENE_GROUP.search(raw))
    if has_year and (dots >= 2 or has_ebook or has_group):
        return True
    if dots >= 3 and has_ebook:
        return True
    return False


def parse_book_scene(name: str) -> Optional[Tuple[str, str]]:
    """Author and title from a dotted/hyphen ebook dump, or None when unclear.

    Handles ``Author.Name-Title.Words.2024.EPUB-GROUP`` and ``Title by Author``.
    A name that is only tokens (no human words) is not a parse.
    """
    raw = strip_calibre_suffix(str(name or "").strip())
    if not raw or not _looks_like_scene(raw):
        return None
    stem = _SCENE_GROUP.sub("", raw)
    stem = _SCENE_EBOOK_TAIL.sub("", stem)
    stem = YEAR.sub(" ", stem)
    stem = re.sub(r"[\.\-_]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" -")
    if not stem:
        return None
    author = ""
    title = ""
    if " - " in raw:
        left, right = raw.split(" - ", 1)
        author = tidy_title(_SCENE_EBOOK_TAIL.sub("", _SCENE_GROUP.sub("", left)))
        title = tidy_title(_SCENE_EBOOK_TAIL.sub("", YEAR.sub(" ", _SCENE_GROUP.sub("", right))))
        title = strip_calibre_suffix(title)
    elif "-" in raw and re.search(r"[A-Za-z]\-[A-Za-z]", raw):
        left, right = re.split(r"(?<=[A-Za-z0-9])-(?=[A-Za-z])", raw, maxsplit=1)
        author = tidy_title(_SCENE_GROUP.sub("", left))
        title = tidy_title(_SCENE_EBOOK_TAIL.sub("", YEAR.sub(" ", _SCENE_GROUP.sub("", right))))
        title = strip_calibre_suffix(title)
    elif _BY_SPLIT.search(stem):
        head, tail = _BY_SPLIT.split(stem, maxsplit=1)
        title, author = tidy_title(head), tidy_title(tail)
    if not author or not title:
        return None
    if author.casefold() == title.casefold():
        return None
    if len(author) < 2 or len(title) < 2:
        return None
    if author.casefold() in {"unknown", "unknown author", "va", "various"}:
        return None
    return author, title


__all__ = ["parse_book_scene", "strip_calibre_suffix"]
