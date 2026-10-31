"""Review slip reasons in organize: Apply error copy, CTA flags, and the one recommended motion."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from librarian.config import Settings
from librarian.db import Database
from librarian.identify import (
    REVIEW_AUDNEXUS_AMBIGUOUS,
    REVIEW_AUDNEXUS_UNMATCHED,
    REVIEW_COLLISION,
    REVIEW_COMICVINE_AMBIGUOUS,
    REVIEW_COMICVINE_UNMATCHED,
    REVIEW_CONVERT,
    REVIEW_EXTRA,
    REVIEW_LOW,
    REVIEW_MISSING_FOLDER,
    REVIEW_NO_PAYLOAD,
    REVIEW_UNEXPECTED,
    REVIEW_UNKNOWN,
    REVIEW_UNPACK_STUCK,
    diagnose_review_folder,
    looks_like_dump_title,
    usable_folder,
)
from librarian.kinds import KIND_BOOK
from librarian.review_reasons import REVIEW_POSSIBLE_DUPLICATE, REVIEW_QUIET_HOURS

NO_PAYLOAD_APPLY_ERROR = (
    "No book, comic, or audio file at this path. Apply cannot invent a payload — "
    "point the folder at files this Librarian can read, fix SAB unpack, or Skip."
)


UNPACK_STUCK_APPLY_ERROR = (
    "Archives are still here after Librarian tried to repair (par2) and unpack (rar/7z). "
    "Use Repair, fix in SABnzbd, extract manually, then Retry — or Skip."
)


MISSING_FOLDER_APPLY_ERROR = (
    "No complete folder. Enter the SAB storage path this Librarian can read, "
    "set SAB complete root, or Skip."
)


COLLISION_APPLY_ERROR = (
    "A file already exists at the library destination. "
    "Apply will not overwrite — change the title/folder, or Skip to keep the shelf copy."
)


PERMISSION_APPLY_ERROR = (
    "Couldn't write into the library shelf — a folder is locked for the lamp "
    "(PUID ownership under the books root). Fix permissions, then Apply again."
)


EXTRA_FILES_NO_MATCH_APPLY_ERROR = (
    "Could not match a file in this dump to the confirmed title/author/ISBN. "
    "Adjust the fields to match a filename here, or Skip."
)


def _permission_apply_error(error: BaseException) -> str:
    """Surface the locked path when PermissionError carries a filename."""
    path = getattr(error, "filename", None)
    if path:
        return f"{PERMISSION_APPLY_ERROR} Locked path: {path}"
    return PERMISSION_APPLY_ERROR


def shelf_work_for_collision(db: Database, work: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Catalog row already on the shelf for the same identity (different folder)."""
    reason = str(work.get("review_reason") or "")
    if reason == REVIEW_POSSIBLE_DUPLICATE:
        from librarian.duplicate_gate import normalized_shelf_matches

        matches = normalized_shelf_matches(db, work, exclude_id=str(work.get("id") or "") or None)
        if not matches:
            return None
        twin = matches[0]
        return {
            "id": twin["id"],
            "title": twin.get("title"),
            "author": twin.get("author"),
            "folder_path": twin.get("folder_path"),
            "kind": twin.get("kind"),
        }
    if reason != REVIEW_COLLISION:
        return None
    conflict = db.find_work_conflict(
        kind=str(work.get("kind") or ""),
        folder_path=str(work.get("folder_path") or ""),
        isbn=str(work.get("isbn") or ""),
        series_name=str(work.get("series_name") or ""),
        series_index=str(work.get("series_index") or ""),
        title=str(work.get("title") or ""),
        author=str(work.get("author") or ""),
        music_state=work.get("music_state"),
        exclude_id=str(work.get("id") or "") or None,
    )
    if conflict is None:
        return None
    return {
        "id": conflict["id"],
        "title": conflict.get("title"),
        "author": conflict.get("author"),
        "folder_path": conflict.get("folder_path"),
        "kind": conflict.get("kind"),
    }


def review_find_query(work: Dict[str, Any]) -> str:
    """Find deep-link query for Request a new version."""
    title = str(work.get("title") or "").strip()
    author = str(work.get("author") or "").strip()
    parts: List[str] = []
    if title:
        parts.append(title)
    if author and author.lower() not in title.lower():
        parts.append(author)
    return " ".join(parts)


# Retry / Repair only help when unpack, quiet-hours, or convert can progress.
_RETRYABLE_REVIEW_REASONS = frozenset(
    {
        REVIEW_UNPACK_STUCK,
        REVIEW_QUIET_HOURS,
        REVIEW_CONVERT,
        REVIEW_NO_PAYLOAD,
    }
)


def review_recommended_motion(
    *,
    reason: str,
    problem: str,
    can_repair: bool,
    can_retry: bool,
    can_regrab: bool,
    can_suggest_llm: bool,
    needs_llm_suggest: bool,
    diagnosis: Dict[str, Any],
) -> str:
    """One recommended motion per hold slip — sorting returns, not a ticket queue."""
    stored = str(reason or "").strip()
    live = str(problem or "").strip()
    # Parked filing reasons win over live folder overlays (a collision slip whose
    # complete folder is gone is still a collision — Skip, not Request new).
    parked = {
        REVIEW_COLLISION,
        REVIEW_POSSIBLE_DUPLICATE,
        REVIEW_EXTRA,
        REVIEW_UNKNOWN,
        REVIEW_LOW,
        REVIEW_UNEXPECTED,
        REVIEW_CONVERT,
        REVIEW_COMICVINE_AMBIGUOUS,
        REVIEW_COMICVINE_UNMATCHED,
        REVIEW_AUDNEXUS_AMBIGUOUS,
        REVIEW_AUDNEXUS_UNMATCHED,
    }
    if stored in parked:
        effective = stored
    elif live in {
        REVIEW_UNPACK_STUCK,
        REVIEW_MISSING_FOLDER,
        REVIEW_NO_PAYLOAD,
        REVIEW_QUIET_HOURS,
    }:
        effective = live
    else:
        effective = stored or live
    if effective == REVIEW_QUIET_HOURS:
        return "wait"
    if effective == REVIEW_UNPACK_STUCK:
        if can_repair:
            return "repair"
        if can_regrab:
            return "regrab"
        if can_retry:
            return "retry"
        return "apply"
    if effective == REVIEW_EXTRA:
        titles = int(diagnosis.get("distinct_title_count") or 0)
        if diagnosis.get("collection_dump") or titles >= 2:
            return "clear_extra_files"
        return "apply"
    if effective in {REVIEW_COLLISION, REVIEW_POSSIBLE_DUPLICATE}:
        return "skip"
    if effective in {
        REVIEW_COMICVINE_AMBIGUOUS,
        REVIEW_COMICVINE_UNMATCHED,
        REVIEW_AUDNEXUS_AMBIGUOUS,
        REVIEW_AUDNEXUS_UNMATCHED,
    }:
        return "pick_match"
    if needs_llm_suggest or can_suggest_llm:
        return "suggest"
    if effective in {REVIEW_MISSING_FOLDER, REVIEW_NO_PAYLOAD}:
        if diagnosis.get("suggested_folder"):
            return "apply"
        return "request_new"
    if effective == REVIEW_CONVERT:
        return "apply"
    return "apply"


def review_slip_actions(
    work: Dict[str, Any],
    diagnosis: Dict[str, Any],
    *,
    llm_configured: bool = False,
) -> Dict[str, Any]:
    """Flags for Review CTAs: Repair / Retry / Request new version / re-grab / LLM suggest."""
    problem = str(diagnosis.get("problem") or work.get("review_reason") or "")
    par2_count = int(diagnosis.get("par2_count") or 0)
    folder_hint = str(
        diagnosis.get("resolved_path") or diagnosis.get("path") or work.get("folder_path") or ""
    )
    reason = str(work.get("review_reason") or problem or "")
    retry_reason = problem if problem in _RETRYABLE_REVIEW_REASONS else reason
    can_retry = retry_reason in _RETRYABLE_REVIEW_REASONS and usable_folder(folder_hint)
    fails = int(work.get("repair_fail_count") or 0)
    title = str(work.get("title") or "")
    author = str(work.get("author") or "").strip()
    # A readable book already named by a safe Author/Title folder is a
    # trustworthy filing candidate, even if the earlier identify pass parked it
    # as low confidence for lack of an ISBN. Keep genuinely unclear names in
    # the LLM pile; this only recognizes the same conservative path shape used
    # by the pre-slip gate.
    path_identity_clear = False
    if str(work.get("kind") or "") == KIND_BOOK and usable_folder(folder_hint):
        from librarian.slip_gate import folder_is_path_clear, parse_library_volume

        folder = Path(folder_hint)
        # The folder parse is the confidence signal. A stored author that lost
        # its periods (``G G``) does not put a clean Author/Title path back
        # into the model pile.
        path_identity_clear = bool(parse_library_volume(folder) and folder_is_path_clear(folder))
    dumpish = looks_like_dump_title(title) or (not author and reason in {REVIEW_UNKNOWN, REVIEW_LOW, ""})
    if path_identity_clear:
        dumpish = False
    identity_weak = (reason in {REVIEW_UNKNOWN, REVIEW_LOW, REVIEW_UNEXPECTED} or dumpish) and not path_identity_clear
    can_repair = problem == REVIEW_UNPACK_STUCK and par2_count > 0
    can_regrab = fails >= 2 and problem == REVIEW_UNPACK_STUCK
    can_suggest_llm = bool(llm_configured) and identity_weak and problem not in {
        REVIEW_MISSING_FOLDER,
        REVIEW_NO_PAYLOAD,
        REVIEW_UNPACK_STUCK,
    }
    needs_llm_suggest = bool(llm_configured) and dumpish and problem not in {
        REVIEW_MISSING_FOLDER,
        REVIEW_NO_PAYLOAD,
        REVIEW_UNPACK_STUCK,
    }
    return {
        "can_repair": can_repair,
        "can_retry": can_retry,
        "find_query": review_find_query(work),
        "quiet_hours": problem == REVIEW_QUIET_HOURS,
        "can_regrab": can_regrab,
        "repair_fail_count": fails,
        "llm_configured": bool(llm_configured),
        "can_suggest_llm": can_suggest_llm,
        "needs_llm_suggest": needs_llm_suggest,
        "recommended_motion": review_recommended_motion(
            reason=reason,
            problem=problem,
            can_repair=can_repair,
            can_retry=can_retry,
            can_regrab=can_regrab,
            can_suggest_llm=can_suggest_llm,
            needs_llm_suggest=needs_llm_suggest,
            diagnosis=diagnosis if isinstance(diagnosis, dict) else {},
        ),
    }


def soft_repair_review_reasons(
    db: Database,
    settings: Settings,
    *,
    limit: int = 80,
) -> int:
    """Persist folder-diagnosis soft repairs off the GET /api/review path.

    Archives left behind were often parked as ``no_payload``. Promote those slips
    to ``unpack_stuck`` in SQLite so Repair/Retry filters stay honest without
    mutating the catalog on every Review list poll.
    """
    repaired = 0
    works = db.list_works(review_state="needs_review", limit=max(1, int(limit)))
    for work in works:
        stored = str(work.get("review_reason") or "")
        if stored not in {"", REVIEW_NO_PAYLOAD}:
            continue
        folder_raw = str(work.get("folder_path") or "")
        if not folder_raw:
            continue
        diagnosis = diagnose_review_folder(Path(folder_raw), settings.complete_root)
        from librarian.review_diagnosis import diagnosis_from_live

        db.upsert_review_diagnosis(
            str(work.get("id") or ""),
            folder_path=folder_raw,
            diagnosis=diagnosis_from_live(diagnosis),
        )
        if diagnosis.get("problem") != REVIEW_UNPACK_STUCK:
            continue
        db.upsert_work({**work, "review_reason": REVIEW_UNPACK_STUCK})
        repaired += 1
    return repaired

