"""Newznab category → Librarian kind.

TV/movies/XXX stay off the shelves. Discover/Find may map them to extra kinds
when the owner opts into Show categories — they never become Hall works.
"""

from __future__ import annotations

from typing import Optional

from librarian.indexers.kind_map import (
    EXTRA_KINDS,
    KIND_AUDIOBOOK,
    KIND_BOOK,
    KIND_COMIC,
    KIND_MAGAZINE,
    KIND_MOVIE,
    KIND_MUSIC,
    KIND_TV,
    KIND_XXX,
    REFUSED_FAMILIES,
    newznab_cat_to_kind,
)

READING_KINDS = (KIND_BOOK, KIND_MAGAZINE, KIND_COMIC)
LISTENING_KINDS = (KIND_AUDIOBOOK, KIND_MUSIC)
ALL_KINDS = READING_KINDS + LISTENING_KINDS
REQUEST_KINDS = ALL_KINDS + EXTRA_KINDS

REFUSED_PREFIXES = REFUSED_FAMILIES

NEWZNAB_COMIC = 7030
NEWZNAB_MAGAZINE = 7010
NEWZNAB_AUDIOBOOK = 3030
NEWZNAB_MUSIC = (3010, 3040, 3999)
NEWZNAB_MOVIE = 2000
NEWZNAB_TV = 5000
NEWZNAB_XXX = 6000


def _as_int(value: object) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def kind_from_newznab(category: object, *, extra: bool = False) -> Optional[str]:
    """Map a Newznab category id to a kind, or None if refused/unknown.

    Display/Find/Request use the full map (including movie/TV/XXX). Hall
    identify/organize pass ``extra=False`` so extras stay off the shelves.
    """
    cat = _as_int(category)
    if cat is None:
        return None
    mapped = newznab_cat_to_kind(cat)
    if mapped in EXTRA_KINDS and not extra:
        return None
    return mapped



def kind_from_caps_cat(cat: object, *, parent: object = None, extra: bool = False) -> Optional[str]:
    """Kind for a capabilities-tree category. Parent 7000 'Other' is still a book."""
    mapped = kind_from_newznab(cat, extra=extra)
    if mapped:
        return mapped
    cat_int = _as_int(cat)
    parent_int = _as_int(parent)
    if cat_int is None:
        return None
    family = (cat_int // 1000) * 1000
    parent_family = ((parent_int or family) // 1000) * 1000
    if family in REFUSED_FAMILIES or parent_family in REFUSED_FAMILIES:
        if extra:
            return kind_from_newznab(cat_int, extra=True) or kind_from_newznab(parent_family, extra=True)
        return None
    if parent_family == 7000 or family == 7000:
        if cat_int == NEWZNAB_COMIC:
            return KIND_COMIC
        if cat_int == NEWZNAB_MAGAZINE:
            return KIND_MAGAZINE
        return KIND_BOOK
    return None


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
    if kind == KIND_MOVIE:
        return str(NEWZNAB_MOVIE)
    if kind == KIND_TV:
        return str(NEWZNAB_TV)
    if kind == KIND_XXX:
        return str(NEWZNAB_XXX)
    return None


def canonical_extension(kind: str) -> str:
    if kind == KIND_BOOK:
        return ".epub"
    if kind == KIND_COMIC:
        return ".cbz"
    if kind == KIND_AUDIOBOOK:
        return ".m4b"
    return ""
