"""Newznab category id → Librarian kind (display / Find / Request).

Movies (2000), TV (5000), and XXX (6000) map to extra kinds for Beyond/Discover.
Hall identify/organize still refuses those families via ``kind_from_newznab``
(``extra=False``) and ``REFUSED_FAMILIES`` — extras never become Hall works.
"""

from __future__ import annotations

# Families that must never file onto Hall shelves (RSS / identify refuse).
REFUSED_FAMILIES = (2000, 5000, 6000)

KIND_BOOK = "book"
KIND_MAGAZINE = "magazine"
KIND_COMIC = "comic"
KIND_AUDIOBOOK = "audiobook"
KIND_MUSIC = "music"
KIND_MOVIE = "movie"
KIND_TV = "tv"
KIND_XXX = "xxx"

EXTRA_KINDS = (KIND_MOVIE, KIND_TV, KIND_XXX)


def newznab_cat_to_kind(cat: int) -> str | None:
    """Map a Newznab category id to a display kind, or None if unknown.

    Includes movie/tv/xxx for Find/Discover/Request. Callers that file onto
    Hall shelves must use ``kind_from_newznab(..., extra=False)`` instead.
    """
    family = (cat // 1000) * 1000
    if family == 2000:
        return KIND_MOVIE
    if family == 5000:
        return KIND_TV
    if family == 6000:
        return KIND_XXX
    if cat == 7030:
        return KIND_COMIC
    if cat == 7010:
        return KIND_MAGAZINE
    if 7000 <= cat <= 7099:
        return KIND_BOOK
    if cat == 3030:
        return KIND_AUDIOBOOK
    if cat in (3000, 3010, 3040, 3999):
        return KIND_MUSIC
    return None
