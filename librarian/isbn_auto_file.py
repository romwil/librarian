"""BD-3 option 4 · Hybrid ISBN-strong auto-file experiment (opt-in, default OFF).

Books with a check-digit-valid ISBN plus author + title may leave Sorting when the
owner toggle is on. Audio, comics, music, and magazines stay Sorting-first.
Hard gates (extra files, collision, convert, unpack) never auto-file.
Never talks to SABnzbd. Undo is the Sorting 24h window; undoing counts as a
mis-shelve signal on House pulse.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from librarian.config import Settings
from librarian.db import Database
from librarian.kinds import KIND_BOOK
from librarian.naming.isbn import validated_isbn
from librarian.review_reasons import (
    REVIEW_COLLISION,
    REVIEW_CONVERT,
    REVIEW_EXTRA,
    REVIEW_LOW,
    REVIEW_MISSING_FOLDER,
    REVIEW_NO_PAYLOAD,
    REVIEW_POSSIBLE_DUPLICATE,
    REVIEW_QUIET_HOURS,
    REVIEW_UNEXPECTED,
    REVIEW_UNKNOWN,
    REVIEW_UNPACK_STUCK,
)

logger = logging.getLogger("librarian.isbn_auto_file")

TICK_LIMIT = 25
ACTION_ID = "isbn_auto_file"
METRIC_FILED = "isbn_auto_file"
METRIC_UNDO = "isbn_auto_file_undo"

SOFT_REASONS = frozenset({REVIEW_LOW, REVIEW_UNKNOWN, REVIEW_QUIET_HOURS, ""})
HARD_REASONS = frozenset(
    {
        REVIEW_EXTRA,
        REVIEW_COLLISION,
        REVIEW_CONVERT,
        REVIEW_NO_PAYLOAD,
        REVIEW_UNPACK_STUCK,
        REVIEW_MISSING_FOLDER,
        REVIEW_UNEXPECTED,
        REVIEW_POSSIBLE_DUPLICATE,
        "comicvine_ambiguous",
        "comicvine_unmatched",
        "audnexus_ambiguous",
        "audnexus_unmatched",
    }
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def isbn_auto_file_enabled(settings: Any) -> bool:
    """Kill switch — default OFF."""
    return bool(getattr(settings, "isbn_auto_file_enabled", False))


def work_isbn(work: Mapping[str, Any]) -> str:
    return validated_isbn(_text(work.get("isbn")))


def is_isbn_strong(work: Mapping[str, Any]) -> bool:
    """Book + valid ISBN + author + title. Never invents an ISBN."""
    if _text(work.get("kind")).lower() != KIND_BOOK:
        return False
    if not work_isbn(work):
        return False
    if not _text(work.get("author")):
        return False
    if not _text(work.get("title")):
        return False
    return True


def soft_reason_ok(reason: Any) -> bool:
    key = _text(reason)
    if key in HARD_REASONS:
        return False
    return key in SOFT_REASONS


def is_eligible_slip(work: Mapping[str, Any]) -> bool:
    """Sorting slip that the experiment may file. Audio/comics never."""
    if _text(work.get("review_state")) != "needs_review":
        return False
    if not is_isbn_strong(work):
        return False
    if not soft_reason_ok(work.get("review_reason")):
        return False
    if not _text(work.get("folder_path")):
        return False
    return True


def eligible_slips(db: Database, *, limit: int = TICK_LIMIT) -> List[Dict[str, Any]]:
    """Needs-review books that pass ISBN-strong + soft-reason gates."""
    capped = max(1, min(int(limit or TICK_LIMIT), 200))
    out: List[Dict[str, Any]] = []
    for work in db.list_works(review_state="needs_review", kind=KIND_BOOK, limit=2000):
        if is_eligible_slip(work):
            out.append(work)
        if len(out) >= capped:
            break
    return out


def _file_one(db: Database, work: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Shelve in place — leave files on disk. Never SAB."""
    work_id = _text(work.get("id"))
    if not work_id:
        return None
    folder_raw = _text(work.get("folder_path"))
    folder = Path(folder_raw) if folder_raw else Path()
    volume = folder if folder.is_dir() else folder.parent
    isbn = work_isbn(work)
    shelved = db.upsert_work(
        {
            **dict(work),
            "id": work_id,
            "kind": KIND_BOOK,
            "title": _text(work.get("title")) or volume.name,
            "author": _text(work.get("author")),
            "isbn": isbn,
            "folder_path": str(volume) if volume else folder_raw,
            "review_state": "none",
            "review_reason": None,
            "confidence": "high",
        }
    )
    return shelved


def run_isbn_auto_file(
    db: Database,
    settings: Settings,
    *,
    limit: int = TICK_LIMIT,
    force: bool = False,
) -> Dict[str, Any]:
    """File eligible ISBN-strong book slips when the owner toggle is on.

    ``force=True`` runs a one-shot regardless of the toggle (tests / explicit
    Maintain kick). Production poller always passes the default (respect toggle).
    """
    if not force and not isbn_auto_file_enabled(settings):
        return {
            "enabled": False,
            "examined": 0,
            "filed": 0,
            "failed": 0,
            "undo_recorded": False,
        }

    candidates = eligible_slips(db, limit=limit)
    filed_rows: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    for work in candidates:
        work_id = _text(work.get("id"))
        try:
            shelved = _file_one(db, work)
            if shelved is None:
                failures.append({"id": work_id, "error": "missing id"})
                continue
            fresh = db.get_work(work_id)
            if fresh is None or _text(fresh.get("review_state")) == "needs_review":
                failures.append({"id": work_id, "error": "still needs_review"})
                continue
            filed_rows.append(work)
        except Exception as error:  # noqa: BLE001 — one bad slip must not stop the tick
            logger.exception("ISBN auto-file failed for %s", work_id)
            failures.append({"id": work_id, "error": str(error)[:200]})

    undo = False
    if filed_rows:
        from librarian.sorting_undo import record_sorting_undo

        undo = bool(
            record_sorting_undo(
                db,
                action=ACTION_ID,
                works=filed_rows,
                reason="isbn_strong",
            )
        )
        try:
            from librarian.pulse import increment

            increment(db, METRIC_FILED, count=len(filed_rows))
        except Exception:  # noqa: BLE001 — metrics must not undo a successful file
            logger.exception("isbn_auto_file pulse increment failed")

    logger.info(
        "ISBN auto-file examined %s, filed %s, failed %s (undo=%s, enabled=%s)",
        len(candidates),
        len(filed_rows),
        len(failures),
        undo,
        isbn_auto_file_enabled(settings) or force,
    )
    return {
        "enabled": True,
        "examined": len(candidates),
        "filed": len(filed_rows),
        "failed": len(failures),
        "failures": failures[:20],
        "undo_recorded": undo,
    }


def record_mis_shelve_undo(db: Database, *, count: int = 1) -> None:
    """Owner undid an ISBN auto-file batch — count as mis-shelve signal."""
    n = max(0, int(count or 0))
    if n <= 0:
        return
    try:
        from librarian.pulse import increment

        increment(db, METRIC_UNDO, count=n)
    except Exception:  # noqa: BLE001
        logger.exception("isbn_auto_file_undo pulse increment failed")


__all__ = [
    "ACTION_ID",
    "HARD_REASONS",
    "METRIC_FILED",
    "METRIC_UNDO",
    "SOFT_REASONS",
    "TICK_LIMIT",
    "eligible_slips",
    "is_eligible_slip",
    "is_isbn_strong",
    "isbn_auto_file_enabled",
    "record_mis_shelve_undo",
    "run_isbn_auto_file",
    "soft_reason_ok",
    "work_isbn",
]
