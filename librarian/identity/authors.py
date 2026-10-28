"""Author display, sort, and matching normalization."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, List, Optional

_MULTIPLE_AUTHORS = re.compile(r"\s*(?:;|&|\band\b)\s*", re.IGNORECASE)
_INITIAL = re.compile(r"^[A-Za-z]$")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def split_authors(value: Any) -> List[str]:
    """Split the common multi-author separators, preserving name order."""
    return [part.strip() for part in _MULTIPLE_AUTHORS.split(str(value or "")) if part.strip()]


def _standardize_initials(value: str) -> str:
    words = value.split()
    normalized = [
        f"{word}." if _INITIAL.fullmatch(word) else word
        for word in words
    ]
    # J.R.R. is already its conventional form; do not turn it into J. R. R.
    return " ".join(normalized)


def display_name(value: Any) -> str:
    """Turn ``Last, First`` into display order and normalize lone initials."""
    text = str(value or "").strip()
    if not text:
        return ""
    if "," in text:
        last, first = (part.strip() for part in text.split(",", 1))
        if last and first:
            text = f"{first} {last}"
    return _standardize_initials(text)


def sort_name(value: Any) -> str:
    """Return the stable ``Last, First`` form for one author."""
    text = str(value or "").strip()
    if not text:
        return ""
    if "," in text:
        last, first = (part.strip() for part in text.split(",", 1))
        if last and first:
            return f"{last}, {_standardize_initials(first)}"
    shown = display_name(text)
    words = shown.split()
    if len(words) < 2:
        return shown
    return f"{words[-1]}, {' '.join(words[:-1])}"


def canonical_author(value: Any, db: Optional[Any] = None) -> str:
    """Resolve a display name through canonical author aliases when available."""
    shown = display_name(value)
    if not shown or db is None:
        return shown
    # Try both forms so aliases recorded before normalization still resolve.
    for name in (str(value or "").strip(), shown):
        author = db.get_author_by_name(name)
        if author:
            return str(author.get("display_name") or shown)
    return shown


def author_match_key(value: Any, db: Optional[Any] = None) -> str:
    """Accent- and punctuation-insensitive key with surname order normalized."""
    names = [canonical_author(part, db) for part in split_authors(value)]
    folded = []
    for name in names:
        ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
        key = _NON_ALNUM.sub("", ascii_name.casefold())
        if key:
            folded.append(key)
    return "&".join(sorted(folded))


__all__ = [
    "author_match_key",
    "canonical_author",
    "display_name",
    "sort_name",
    "split_authors",
]
