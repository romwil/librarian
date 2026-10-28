"""Compatibility shim — comic token rules live in ``librarian.naming.comic``."""

from __future__ import annotations

from librarian.naming.comic import (
    ComicTokens,
    comic_identity_fields,
    normalize_comic_name,
    scrub_comic_stem,
)

__all__ = ["ComicTokens", "comic_identity_fields", "normalize_comic_name", "scrub_comic_stem"]
