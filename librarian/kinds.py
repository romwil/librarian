"""Newznab category → Librarian kind. TV/movies/XXX are refused."""

from __future__ import annotations

from typing import Optional

from librarian.indexers.kind_map import (
    KIND_AUDIOBOOK,
    KIND_BOOK,
    KIND_COMIC,
    KIND_MAGAZINE,
    KIND_MUSIC,
    REFUSED_FAMILIES,
    newznab_cat_to_kind,
)

READING_KINDS = (KIND_BOOK, KIND_MAGAZINE, KIND_COMIC)
LISTENING_KINDS = (KIND_AUDIOBOOK, KIND_MUSIC)
ALL_KINDS = READING_KINDS + LISTENING_KINDS

REFUSED_PREFIXES = REFUSED_FAMILIES

NEWZNAB_COMIC = 7030
NEWZNAB_MAGAZINE = 7010
NEWZNAB_AUDIOBOOK = 3030
NEWZNAB_MUSIC = (3010, 3040, 3999)


def _as_int(value: object) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def kind_from_newznab(category: object) -> Optional[str]:
    """Map a Newznab category id to a Librarian kind, or None if refused/unknown."""
    cat = _as_int(category)
    if cat is None:
        return None
    return newznab_cat_to_kind(cat)


def search_category_for_kind(kind: str) -> Optional[str]:
    if kind == KIND_COMIC:
        return str(NEWZNAB_COMIC)
    if kind == KIND_MAGAZINE:
        return str(NEWZNAB_MAGAZINE)
    if kind == KIND_BOOK:
        return "7000"
    if kind == KIND_AUDIOBOOK:
        return str(NEWZNAB_AUDIOBOOK)
    if kind == KIND_MUSIC:
        return "3000"
    return None


def canonical_extension(kind: str) -> str:
    if kind == KIND_BOOK:
        return ".epub"
    if kind == KIND_COMIC:
        return ".cbz"
    if kind == KIND_AUDIOBOOK:
        return ".m4b"
    return ""
