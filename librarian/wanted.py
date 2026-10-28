"""Wanted rows: a title the house does not have yet.

Status is ``wanted`` (still looking), ``asked`` (one slip is in the queue),
or ``dismissed`` (never searched). The backoff clock lives on ``next_search_at``.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, Mapping, Optional

from librarian.db import Database
from librarian.identify import isbn_match_keys
from librarian.indexers.rank import heuristic_score
from librarian.kinds import ALL_KINDS
from librarian.owned import ShelfIndex

STATUS_WANTED = "wanted"
STATUS_ASKED = "asked"
STATUS_DISMISSED = "dismissed"

# First miss waits 2× base, second 4× base. Three misses lock the slow cadence.
BASE_BACKOFF_SECONDS = 6 * 60 * 60
SLOW_CADENCE_SECONDS = 7 * 24 * 60 * 60
SLOW_AFTER_MISSES = 3
# Title overlap is worth 3 and author overlap 2. 4.5 needs both, not a title-only glance.
CONFIDENT_SCORE = 4.5
# A posting name this long that matches exactly is the release itself, not a glance.
RELEASE_NAME_MIN_CHARS = 16

_JUNK_MULTIDISC = re.compile(
    r"(?ix)"
    r"(?:\b(?:cd|disc|disk)[\s._-]*0*\d+\b)"
    r"|(?:\bmulti[\s-]?disc\b)"
    r"|(?:\b\d+\s*cds?\b)"
    r"|(?:\.part\d+\.rar\b)"
    r"|(?:\brars?\s*set\b)"
)


class WantedError(ValueError):
    """Caller-facing Wanted validation error. Never includes tokens."""


class AlreadyShelved(WantedError):
    """That title and kind already have a file on the shelves."""

    def __init__(self, work_id: str, kind: str) -> None:
        super().__init__("Already on the shelf")
        self.work_id = str(work_id or "")
        self.kind = str(kind or "")


def backoff_seconds(streak: int) -> float:
    """How long to wait after this miss streak. Three or more stays on the slow clock."""
    count = max(0, int(streak))
    if count >= SLOW_AFTER_MISSES:
        return float(SLOW_CADENCE_SECONDS)
    return float(BASE_BACKOFF_SECONDS) * (2 ** count)


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _isbn_identity(isbn: str) -> str:
    keys = isbn_match_keys(isbn)
    for key in keys:
        if len(key) == 13:
            return key
    return keys[0] if keys else ""


def dedupe_key(
    *,
    kind: str,
    work_id: str = "",
    title: str = "",
    author: str = "",
    isbn: str = "",
) -> str:
    """One Wanted row per shelved work, else per ISBN, else per title+author."""
    shelf_kind = str(kind or "").strip().lower()
    wid = str(work_id or "").strip()
    if wid:
        return f"work:{wid}:{shelf_kind}"
    identity = _isbn_identity(isbn)
    if identity:
        return f"isbn:{identity}:{shelf_kind}"
    return f"name:{_norm(title)}:{_norm(author)}:{shelf_kind}"


def is_junk_multidisc(hit: Mapping[str, Any]) -> bool:
    """A split disc or leftover archive is not a complete audiobook."""
    blob = " ".join(
        str(hit.get(key) or "")
        for key in ("title", "book_title", "category_name")
    )
    return _JUNK_MULTIDISC.search(blob) is not None


def is_release_name_match(sought: Mapping[str, Any], hit: Mapping[str, Any]) -> bool:
    """The Wanted title is this posting's own name (a pick saved from Discover or RSS)."""
    want = _norm(sought.get("title"))
    if len(want) < RELEASE_NAME_MIN_CHARS:
        return False
    return want == _norm(hit.get("title"))


def is_confident_hit(sought: Mapping[str, Any], hit: Mapping[str, Any]) -> bool:
    """ISBN agreement, the exact posting name, or a strong title and author overlap. Fail closed."""
    if not str(hit.get("guid") or hit.get("indexer_guid") or "").strip():
        return False
    if is_junk_multidisc(hit):
        return False
    want = set(isbn_match_keys(str(sought.get("isbn") or "")))
    got = set(isbn_match_keys(str(hit.get("isbn") or "")))
    if want and got and want.intersection(got):
        return True
    if is_release_name_match(sought, hit):
        return True
    return heuristic_score(sought, hit) >= CONFIDENT_SCORE


def public_wanted(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "id": row.get("id"),
        "work_id": row.get("work_id") or None,
        "title": row.get("title") or "",
        "author": row.get("author") or "",
        "isbn": row.get("isbn") or "",
        "kind": row.get("kind") or "",
        "status": row.get("status") or "",
        "miss_streak": int(row.get("miss_streak") or 0),
        "next_search_at": row.get("next_search_at"),
        "job_id": row.get("job_id") or None,
    }


def _clean(value: Any) -> str:
    return str(value or "").strip()


def add_wanted(db: Database, payload: Mapping[str, Any], *, now: Optional[float] = None) -> Dict[str, Any]:
    """Insert or reopen a Wanted row. Does not search and does not call SABnzbd."""
    moment = time.time() if now is None else float(now)
    kind = _clean(payload.get("kind")).lower() or "audiobook"
    if kind not in ALL_KINDS:
        raise WantedError("Wanted kind must be book, magazine, comic, audiobook, or music")
    work_id = _clean(payload.get("work_id"))
    title = _clean(payload.get("title"))
    author = _clean(payload.get("author"))
    isbn = _clean(payload.get("isbn"))
    series_name = ""
    series_index = ""
    work: Optional[Dict[str, Any]] = None
    if work_id:
        work = db.get_work(work_id)
        if work is None:
            raise WantedError("Work not found")
        title = title or _clean(work.get("title"))
        author = author or _clean(work.get("author"))
        isbn = isbn or _clean(work.get("isbn"))
        series_name = _clean(work.get("series_name"))
        series_index = _clean(work.get("series_index"))
    if not title and not isbn:
        raise WantedError("Title or ISBN is required")
    shelves = ShelfIndex(db)
    owned = shelves.by_id(kind, work_id) or shelves.of_kind(
        {
            "title": title,
            "author": author,
            "isbn": isbn,
            "series_name": series_name,
            "series_index": series_index,
        },
        kind,
    )
    if owned and owned.get("id"):
        raise AlreadyShelved(str(owned["id"]), kind)
    key = dedupe_key(kind=kind, work_id=work_id, title=title, author=author, isbn=isbn)
    existing = db.get_wanted_by_dedupe(key)
    fields = {"title": title, "author": author, "isbn": isbn}
    if existing and existing.get("status") == STATUS_DISMISSED:
        reopened = db.reopen_wanted(str(existing["id"]), now=moment, fields=fields)
        assert reopened is not None
        return reopened
    if existing:
        return existing
    return db.insert_wanted(
        {
            "dedupe_key": key,
            "work_id": work_id or None,
            "title": title,
            "author": author,
            "isbn": isbn,
            "kind": kind,
            "status": STATUS_WANTED,
            "miss_streak": 0,
            "next_search_at": moment,
            "created_at": moment,
            "updated_at": moment,
            "source": "manual",
        }
    )


def dismiss_wanted(db: Database, wanted_id: str, *, now: Optional[float] = None) -> Dict[str, Any]:
    moment = time.time() if now is None else float(now)
    row = db.dismiss_wanted(wanted_id, now=moment)
    if row is None:
        raise WantedError("Wanted row not found")
    return row


DEFAULT_WANTED_PAGE_SIZE = 50
MAX_WANTED_PAGE_SIZE = 200

_KNOWN_STATUSES = {STATUS_WANTED, STATUS_ASKED, STATUS_DISMISSED}


def list_wanted(db: Database, *, status: str = "") -> list[Dict[str, Any]]:
    key = _clean(status).lower()
    if key == "all":
        return db.list_wanted(include_dismissed=True)
    if key:
        if key not in _KNOWN_STATUSES:
            raise WantedError("Unknown Wanted status")
        return db.list_wanted(status=key)
    return db.list_wanted()


def page_wanted(
    db: Database,
    *,
    status: str = "",
    kind: str = "",
    page: int = 1,
    page_size: int = DEFAULT_WANTED_PAGE_SIZE,
) -> Dict[str, Any]:
    """One page of Wanted rows. Kind narrows the set before the page window."""
    key = _clean(status).lower()
    kind_key = _clean(kind).lower()
    if kind_key and kind_key not in ALL_KINDS:
        raise WantedError("Unknown Wanted kind")
    include_dismissed = key == "all"
    status_arg: Optional[str] = None
    if key and not include_dismissed:
        if key not in _KNOWN_STATUSES:
            raise WantedError("Unknown Wanted status")
        status_arg = key
    try:
        page_no = int(page)
    except (TypeError, ValueError):
        page_no = 1
    page_no = max(1, page_no)
    try:
        size = int(page_size)
    except (TypeError, ValueError):
        size = DEFAULT_WANTED_PAGE_SIZE
    if size < 1:
        size = DEFAULT_WANTED_PAGE_SIZE
    size = min(size, MAX_WANTED_PAGE_SIZE)
    total = db.count_wanted(
        kind=kind_key or None, status=status_arg, include_dismissed=include_dismissed
    )
    rows = db.list_wanted(
        kind=kind_key or None,
        limit=size,
        offset=(page_no - 1) * size,
        status=status_arg,
        include_dismissed=include_dismissed,
    )
    kinds = db.distinct_wanted_kinds(status=status_arg, include_dismissed=include_dismissed)
    return {
        "items": rows,
        "total": total,
        "page": page_no,
        "page_size": size,
        "kinds": kinds,
    }
