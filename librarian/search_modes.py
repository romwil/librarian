"""One search field, one mode: title, author, ISBN, series, or narrator."""

from __future__ import annotations

from typing import Any, Dict, Mapping

SEARCH_MODES = ("title", "author", "isbn", "series", "narrator")

# Modes that name one edition. Author, series, and narrator are shelves, not an edition.
EDITION_MODES = ("title", "isbn")


def normalize_search_mode(value: Any) -> str:
    key = str(value or "").strip().lower()
    return key if key in SEARCH_MODES else ""


def apply_search_mode(sought: Mapping[str, Any], mode: str, query: str) -> Dict[str, str]:
    """Copy sought and fill the mode's field from the single query when it is empty."""
    out = {str(key): str(value or "") for key, value in dict(sought).items()}
    key = normalize_search_mode(mode)
    text = str(query or "").strip()
    if not key or not text:
        return out
    if key == "narrator":
        out["q"] = text
        return out
    field = {"title": "title", "author": "author", "isbn": "isbn", "series": "series"}[key]
    if not str(out.get(field) or "").strip():
        out[field] = text
    if not str(out.get("q") or "").strip():
        out["q"] = text
    return out
