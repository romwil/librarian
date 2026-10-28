"""Title identity and browse-sort normalization."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

_SUBTITLE = re.compile(r"\s*(?::|\s+-\s+)\s*")
_ARTICLE = re.compile(r"^(?:the|an|a)\s+", re.IGNORECASE)
_TOKENS = re.compile(r"\d+|[a-z]+")


def base_title(value: Any) -> str:
    """Return the title before a conventional subtitle separator."""
    text = str(value or "").strip()
    if not text:
        return ""
    match = _SUBTITLE.search(text)
    if match is None:
        return text
    base = text[: match.start()].strip()
    return base or text


def _fold(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()


def title_sort(value: Any) -> str:
    """Article-free, accent-folded sort key with numeric runs zero padded."""
    text = _ARTICLE.sub("", base_title(value)).strip()
    return " ".join(
        token.zfill(10) if token.isdigit() else token
        for token in _TOKENS.findall(_fold(text))
    )


def title_match_key(value: Any) -> str:
    """Accent-folded base-title key used for equality, not display sorting."""
    return "".join(_TOKENS.findall(_fold(base_title(value))))


__all__ = ["base_title", "title_match_key", "title_sort"]
