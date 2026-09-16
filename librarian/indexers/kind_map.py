"""Newznab category id → Librarian kind.

TV (5000), movies (2000), and XXX (6000) families are refused.
"""

from __future__ import annotations

REFUSED_FAMILIES = (2000, 5000, 6000)

KIND_BOOK = "book"
KIND_MAGAZINE = "magazine"
KIND_COMIC = "comic"
KIND_AUDIOBOOK = "audiobook"
KIND_MUSIC = "music"


def newznab_cat_to_kind(cat: int) -> str | None:
    """Map a Newznab category id to a Librarian kind, or None if refused/unknown."""
    family = (cat // 1000) * 1000
    if family in REFUSED_FAMILIES:
        return None
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
