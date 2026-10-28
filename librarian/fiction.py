"""Classify catalog genre text as fiction, nonfiction, or unknown.

``works.genre`` is Open Library and Hardcover subjects joined by ``join_subjects``.
Nonfiction markers win when a string contains both. ``science`` is nonfiction
except inside ``science fiction``. Empty or ambiguous text is unknown.
"""

from __future__ import annotations

import re
from typing import Literal

GenreClass = Literal["fiction", "nonfiction", "unknown"]

_NONFICTION = (
    "nonfiction",
    "non fiction",
    "biography",
    "history",
    "self help",
    "cooking",
    "reference",
    "business",
    "religion",
    "true crime",
)

_FICTION = (
    "literary fiction",
    "science fiction",
    "juvenile fiction",
    "short stories",
    "fiction",
    "novel",
    "fantasy",
    "mystery",
    "thriller",
    "romance",
    "horror",
)

_SCIENCE_FICTION = re.compile(r"(?<![a-z0-9])science fiction(?![a-z0-9])")


def _normalize(genre: str | None) -> str:
    text = str(genre or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def _is_nonfiction(text: str) -> bool:
    if any(_contains(text, phrase) for phrase in _NONFICTION):
        return True
    without_science_fiction = _SCIENCE_FICTION.sub(" ", text)
    return _contains(without_science_fiction, "science")


def classify_genre(genre: str | None) -> GenreClass:
    """Return fiction, nonfiction, or unknown. Nonfiction markers win."""
    text = _normalize(genre)
    if not text:
        return "unknown"
    if _is_nonfiction(text):
        return "nonfiction"
    if any(_contains(text, phrase) for phrase in _FICTION):
        return "fiction"
    return "unknown"
