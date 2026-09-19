"""Book → audiobook companion matching on the local shelves.

ISBN first, then exact title+author, then same series name + index when both
have a series. Fail closed — never invents a match from title alone.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional

from librarian.identify import isbn_match_keys


def _norm_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _index_key(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text.lower()


def audiobook_find_fields(work: Mapping[str, Any]) -> Dict[str, str]:
    """Prefill Find for an audiobook request of this book."""
    title = str(work.get("title") or "").strip()
    author = str(work.get("author") or "").strip()
    isbn = str(work.get("isbn") or "").strip()
    series = str(work.get("series_name") or "").strip()
    composed = title or series
    return {
        "q": " ".join(part for part in (author, composed) if part).strip() or composed,
        "kind": "audiobook",
        "title": title or series,
        "author": author,
        "isbn": isbn,
        "series": series,
    }


def match_companion_audiobook(
    book: Mapping[str, Any],
    audiobooks: List[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Pick the best local audiobook for a book work. None when unsure."""
    if str(book.get("kind") or "") != "book":
        return None
    want_isbn = set(isbn_match_keys(str(book.get("isbn") or "")))
    if want_isbn:
        for row in audiobooks:
            if str(row.get("kind") or "") not in ("", "audiobook"):
                continue
            if want_isbn.intersection(isbn_match_keys(str(row.get("isbn") or ""))):
                return dict(row)
    title_key = _norm_name(book.get("title"))
    author_key = _norm_name(book.get("author"))
    if title_key and author_key:
        for row in audiobooks:
            if _norm_name(row.get("title")) != title_key:
                continue
            if _norm_name(row.get("author")) == author_key:
                return dict(row)
    series = _norm_name(book.get("series_name"))
    index = _index_key(book.get("series_index"))
    if series and index:
        for row in audiobooks:
            if _norm_name(row.get("series_name")) != series:
                continue
            if _index_key(row.get("series_index")) == index:
                return dict(row)
    return None


def companion_audiobook_payload(
    book: Mapping[str, Any],
    *,
    audiobooks: List[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Work-page payload: shelved companion and Find prefill for misses."""
    if str(book.get("kind") or "") != "book":
        return {"applicable": False, "shelved": None, "find": {}}
    hit = match_companion_audiobook(book, audiobooks)
    find = audiobook_find_fields(book)
    if hit is None:
        return {"applicable": True, "shelved": None, "find": find}
    return {
        "applicable": True,
        "shelved": {
            "id": hit.get("id"),
            "title": hit.get("title"),
            "author": hit.get("author"),
            "isbn": hit.get("isbn"),
            "kind": "audiobook",
            "has_cover": bool(hit.get("cover_path") or hit.get("has_cover")),
        },
        "find": find,
    }
