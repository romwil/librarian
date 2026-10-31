"""Wanted rows: a title the house does not have yet.

Status is ``wanted`` (still looking), ``asked`` (one slip is in the queue),
``arrived`` (filed on the shelf), or ``dismissed`` (never searched).
The backoff clock lives on ``next_search_at``. ``asked`` locks further searches.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, Mapping, Optional

from librarian.db import Database
from librarian.identify import isbn_match_keys
from librarian.indexers.match import (  # noqa: F401 — Wanted callers import these here
    CONFIDENT_SCORE,
    RELEASE_NAME_MIN_CHARS,
    is_junk_multidisc,
    is_release_name_match,
)
from librarian.indexers.match import is_confident_match as is_confident_hit  # noqa: F401
from librarian.kinds import ALL_KINDS
from librarian.owned import ShelfIndex

STATUS_WANTED = "wanted"
STATUS_ASKED = "asked"
STATUS_ARRIVED = "arrived"
STATUS_DISMISSED = "dismissed"

SOURCE_SWEEP = "sweep"
SOURCE_MANUAL = "manual"
SWEEP_RESTORE_SECONDS = 30 * 24 * 60 * 60

# First miss waits 6 hours, the second 12. Every later miss stays at 12.
BASE_BACKOFF_SECONDS = 6 * 60 * 60
MAX_BACKOFF_SECONDS = 12 * 60 * 60


class WantedError(ValueError):
    """Caller-facing Wanted validation error. Never includes tokens."""


class AlreadyShelved(WantedError):
    """That title and kind already have a file on the shelves."""

    def __init__(self, work_id: str, kind: str) -> None:
        super().__init__("Already on the shelf")
        self.work_id = str(work_id or "")
        self.kind = str(kind or "")


def backoff_seconds(streak: int) -> float:
    """How long to wait after this miss streak: 6 hours, then 12, then 12 again."""
    count = max(1, int(streak))
    return float(min(BASE_BACKOFF_SECONDS * (2 ** (count - 1)), MAX_BACKOFF_SECONDS))


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


def wanted_source(row: Mapping[str, Any]) -> str:
    """Sweep vs owner-asked. Unsourced legacy rows were sweep-seeded."""
    source = str(row.get("source") or "").strip().lower()
    if source == SOURCE_MANUAL:
        return SOURCE_MANUAL
    return SOURCE_SWEEP


def is_restorable_sweep(row: Mapping[str, Any], *, now: Optional[float] = None) -> bool:
    if str(row.get("status") or "") != STATUS_DISMISSED:
        return False
    if wanted_source(row) != SOURCE_SWEEP:
        return False
    moment = time.time() if now is None else float(now)
    dismissed_at = float(row.get("updated_at") or 0)
    return dismissed_at > 0 and (moment - dismissed_at) <= SWEEP_RESTORE_SECONDS


def public_wanted(row: Mapping[str, Any], *, now: Optional[float] = None) -> Dict[str, Any]:
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
        "source": wanted_source(row),
        "restorable": is_restorable_sweep(row, now=now),
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
            "source": SOURCE_MANUAL,
        }
    )


def dismiss_wanted(db: Database, wanted_id: str, *, now: Optional[float] = None) -> Dict[str, Any]:
    moment = time.time() if now is None else float(now)
    row = db.dismiss_wanted(wanted_id, now=moment)
    if row is None:
        raise WantedError("Wanted row not found")
    return row


def dismiss_sweep_wanted(db: Database, *, now: Optional[float] = None) -> int:
    """Bulk-dismiss open sweep rows. Owner-added wants and asked slips stay."""
    moment = time.time() if now is None else float(now)
    return int(db.dismiss_open_sweep_wanted(now=moment) or 0)


def restore_wanted(db: Database, wanted_id: str, *, now: Optional[float] = None) -> Dict[str, Any]:
    moment = time.time() if now is None else float(now)
    row = db.get_wanted(wanted_id)
    if row is None:
        raise WantedError("Wanted row not found")
    if str(row.get("status") or "") != STATUS_DISMISSED:
        return row
    if not is_restorable_sweep(row, now=moment):
        raise WantedError("That sweep want can no longer be restored")
    reopened = db.reopen_wanted(
        wanted_id,
        now=moment,
        fields={
            "title": row.get("title") or "",
            "author": row.get("author") or "",
            "isbn": row.get("isbn") or "",
        },
    )
    if reopened is None:
        raise WantedError("Wanted row not found")
    return reopened


def restore_sweep_wanted(db: Database, *, now: Optional[float] = None) -> int:
    moment = time.time() if now is None else float(now)
    since = moment - SWEEP_RESTORE_SECONDS
    return int(db.restore_recent_sweep_wanted(now=moment, since=since) or 0)


DEFAULT_WANTED_PAGE_SIZE = 50
MAX_WANTED_PAGE_SIZE = 200

_KNOWN_STATUSES = {STATUS_WANTED, STATUS_ASKED, STATUS_ARRIVED, STATUS_DISMISSED}


def mark_wanted_arrived(db: Database, job: Mapping[str, Any], *, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """The volume is on the shelf — stop locking searches as Asked."""
    moment = time.time() if now is None else float(now)
    job_id = str(job.get("id") or "").strip()
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    wanted_id = str(payload.get("wanted_id") or "").strip()
    row = db.get_wanted_by_job(job_id) if job_id else None
    if row is None and wanted_id:
        row = db.get_wanted(wanted_id)
    if row is None:
        return None
    work_id = str(job.get("work_id") or row.get("work_id") or "").strip() or None
    return db.mark_wanted_arrived(str(row["id"]), now=moment, work_id=work_id)


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
    source: str = "",
    page: int = 1,
    page_size: int = DEFAULT_WANTED_PAGE_SIZE,
) -> Dict[str, Any]:
    """One page of Wanted rows. Kind narrows the set before the page window."""
    key = _clean(status).lower()
    kind_key = _clean(kind).lower()
    source_key = _clean(source).lower()
    if kind_key and kind_key not in ALL_KINDS:
        raise WantedError("Unknown Wanted kind")
    if source_key and source_key not in {SOURCE_SWEEP, SOURCE_MANUAL}:
        raise WantedError("Unknown Wanted source")
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
        kind=kind_key or None,
        status=status_arg,
        source=source_key or None,
        include_dismissed=include_dismissed,
    )
    rows = db.list_wanted(
        kind=kind_key or None,
        source=source_key or None,
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
