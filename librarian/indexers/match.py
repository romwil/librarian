"""Is this returned release the title we asked for? Fail closed.

Shared by Wanted search and the Find search ladder. ``rapidfuzz`` only scores a
returned title against the sought title; query planning stays in ``query.py``.
"""

from __future__ import annotations

import re
from typing import Any, List, Mapping

from rapidfuzz import fuzz

from librarian.identify import isbn_match_keys
from librarian.indexers.rank import heuristic_score

# Title overlap is worth 3 and author overlap 2. 4.5 needs both, not a title-only glance.
CONFIDENT_SCORE = 4.5
# A posting name this long that matches exactly is the release itself, not a glance.
RELEASE_NAME_MIN_CHARS = 16
# A title-only query may accept a release whose cleaned title scores this high
# against the sought title, when the sought author also agrees.
CLEAR_TITLE_RATIO = 90.0
AUTHOR_AGREE_RATIO = 85.0

_JUNK_MULTIDISC = re.compile(
    r"(?ix)"
    r"(?:\b(?:cd|disc|disk)[\s._-]*0*\d+\b)"
    r"|(?:\bmulti[\s-]?disc\b)"
    r"|(?:\b\d+\s*cds?\b)"
    r"|(?:\.part\d+\.rar\b)"
    r"|(?:\brars?\s*set\b)"
)
_YEAR = re.compile(r"^(?:19|20)\d{2}$")
_SCENE_GROUP = re.compile(r"-([A-Za-z0-9]{2,})$")
_RELEASE_NOISE = frozenset(
    {
        "epub", "mobi", "azw", "azw3", "pdf", "ebook", "ebooks", "retail",
        "audiobook", "audiobooks", "mp3", "m4b", "m4a", "flac", "aac",
        "unabridged", "abridged", "cbr", "cbz", "comic", "hybrid", "web",
        "repack", "proper", "english", "eng", "kbps",
    }
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _words(value: Any) -> List[str]:
    out: List[str] = []
    for word in re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split():
        if word.isdigit():
            word = word.lstrip("0") or "0"
        out.append(word)
    return out


def is_junk_multidisc(hit: Mapping[str, Any]) -> bool:
    """A split disc or leftover archive is not a complete audiobook."""
    blob = " ".join(
        str(hit.get(key) or "")
        for key in ("title", "book_title", "category_name")
    )
    return _JUNK_MULTIDISC.search(blob) is not None


def is_release_name_match(sought: Mapping[str, Any], hit: Mapping[str, Any]) -> bool:
    """The sought title is this posting's own name (a pick saved from Discover or RSS)."""
    want = _norm(sought.get("title"))
    if len(want) < RELEASE_NAME_MIN_CHARS:
        return False
    return want == _norm(hit.get("title"))


def _sought_title(sought: Mapping[str, Any]) -> str:
    series = _text(sought.get("series"))
    if series:
        return " ".join(part for part in (series, _text(sought.get("issue"))) if part)
    return _text(sought.get("title") or sought.get("album") or sought.get("q"))


def _sought_author(sought: Mapping[str, Any]) -> str:
    return _text(sought.get("author") or sought.get("artist"))


def _release_title_words(raw: str, author_words: set[str]) -> List[str]:
    text = raw.strip()
    if text and " " not in text:
        group = _SCENE_GROUP.search(text)
        if group and group.group(1) == group.group(1).upper():
            text = text[: group.start()]
    return [
        word
        for word in _words(text)
        if word not in _RELEASE_NOISE and word not in author_words and not _YEAR.match(word)
    ]


def title_similarity(sought: Mapping[str, Any], hit: Mapping[str, Any]) -> float:
    """0..100: the hit's cleaned title against the sought title (author, year, format dropped)."""
    want = " ".join(_words(_sought_title(sought)))
    if not want:
        return 0.0
    author_words = {word for word in _words(_sought_author(sought)) if len(word) > 1}
    candidates = []
    book_title = _text(hit.get("book_title"))
    if book_title:
        candidates.append(" ".join(w for w in _words(book_title) if w not in _RELEASE_NOISE))
    raw = _text(hit.get("title"))
    if raw:
        candidates.append(" ".join(_release_title_words(raw, author_words)))
    return max((fuzz.token_sort_ratio(want, cand) for cand in candidates if cand), default=0.0)


def author_agrees(sought: Mapping[str, Any], hit: Mapping[str, Any]) -> bool:
    """The hit's author field agrees, or the sought surname is in the posting name."""
    want = " ".join(word for word in _words(_sought_author(sought)) if len(word) > 1)
    if not want:
        return False
    got = " ".join(_words(hit.get("author") or hit.get("artist")))
    if got:
        return fuzz.token_set_ratio(want, got) >= AUTHOR_AGREE_RATIO
    surname = want.split()[-1]
    return surname in set(_words(hit.get("title")))


def is_clear_title_match(sought: Mapping[str, Any], hit: Mapping[str, Any]) -> bool:
    """A title-only query found the book: the title is a clear match and the author agrees.

    Needs a sought author. A bare short title with no author is still a glance.
    """
    if not _sought_author(sought):
        return False
    if title_similarity(sought, hit) < CLEAR_TITLE_RATIO:
        return False
    return author_agrees(sought, hit)


def is_confident_match(sought: Mapping[str, Any], hit: Mapping[str, Any]) -> bool:
    """ISBN agreement, the exact posting name, a strong title and author overlap,
    or a clear title match with the author agreeing. Fail closed."""
    if not _text(hit.get("guid") or hit.get("indexer_guid")):
        return False
    if is_junk_multidisc(hit):
        return False
    want = set(isbn_match_keys(_text(sought.get("isbn"))))
    got = set(isbn_match_keys(_text(hit.get("isbn"))))
    if want and got and want.intersection(got):
        return True
    if is_release_name_match(sought, hit):
        return True
    if heuristic_score(sought, hit) >= CONFIDENT_SCORE:
        return True
    return is_clear_title_match(sought, hit)
