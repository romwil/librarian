"""Book → audiobook companion matching on the local shelves.

ISBN first when both sides have one. Then the same author with an equal title,
or one title that is the other plus a subtitle. Then series name + index when
both have a series. Fail closed — a shared word, or a title with no author, is
not a match.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional

from librarian.identify import isbn_match_keys

# Colon, em dash, en dash, or a spaced hyphen. Parenthetical tail counts too.
_SUBTITLE = re.compile(r"\s*(?::|\u2014|\u2013)\s*|\s+-\s+|\s+\((?=[^)]+\))")


def _norm_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _author_key(value: Any) -> str:
    """Order-independent author key. ``Clear, James`` matches ``James Clear``."""
    tokens = re.findall(r"[a-z0-9]+", str(value or "").lower())
    return " ".join(sorted(tokens))


def _title_parts(value: Any) -> tuple[str, str]:
    text = str(value or "").strip()
    match = _SUBTITLE.search(text)
    if match is None:
        return text, ""
    main = text[: match.start()].strip()
    rest = text[match.end() :].strip().strip("()").strip()
    if not main or not rest:
        return text, ""
    return main, rest


def titles_are_same_work(left: Any, right: Any) -> bool:
    """Equal titles, or one title is the other plus a subtitle. Not a shared word."""
    a = str(left or "").strip()
    b = str(right or "").strip()
    if not a or not b:
        return False
    if _norm_name(a) == _norm_name(b):
        return True
    a_main, a_sub = _title_parts(a)
    b_main, b_sub = _title_parts(b)
    if a_sub and not b_sub and _norm_name(a_main) == _norm_name(b):
        return True
    if b_sub and not a_sub and _norm_name(b_main) == _norm_name(a):
        return True
    return False


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


def _isbn_keys(row: Mapping[str, Any]) -> set[str]:
    return set(isbn_match_keys(str(row.get("isbn") or "")))


def _isbn_conflict(sought_keys: set[str], row: Mapping[str, Any]) -> bool:
    """Both sides have an ISBN and they name different books."""
    if not sought_keys:
        return False
    got = _isbn_keys(row)
    return bool(got) and not sought_keys.intersection(got)


def match_catalog_work(
    sought: Mapping[str, Any],
    candidates: List[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """ISBN when both sides have one, then title+author (subtitle allowed), then series.

    A title with no author is not a match. A longer title that merely shares a
    word is not a subtitle.
    """
    want_isbn = _isbn_keys(sought)
    if want_isbn:
        for row in candidates:
            if want_isbn.intersection(_isbn_keys(row)):
                return dict(row)
    author_key = _author_key(sought.get("author"))
    if author_key and str(sought.get("title") or "").strip():
        for row in candidates:
            if _isbn_conflict(want_isbn, row):
                continue
            if _author_key(row.get("author")) != author_key:
                continue
            if titles_are_same_work(sought.get("title"), row.get("title")):
                return dict(row)
    series = _norm_name(sought.get("series_name") or sought.get("series"))
    index = _index_key(sought.get("series_index"))
    if series and index:
        for row in candidates:
            if _isbn_conflict(want_isbn, row):
                continue
            if _norm_name(row.get("series_name")) != series:
                continue
            if _index_key(row.get("series_index")) == index:
                return dict(row)
    return None


def match_companion_audiobook(
    book: Mapping[str, Any],
    audiobooks: List[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Pick the best local audiobook for a book work. None when unsure."""
    if str(book.get("kind") or "") != "book":
        return None
    pool = [row for row in audiobooks if str(row.get("kind") or "") in ("", "audiobook")]
    return match_catalog_work(book, pool)


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
