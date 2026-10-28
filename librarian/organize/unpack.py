"""Unpack and par2: repair damaged SAB archives before identify, and the Review Repair action."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from librarian.config import Settings
from librarian.convert import release_folder
from librarian.db import Database
from librarian.identify import (
    REVIEW_UNPACK_STUCK,
    diagnose_review_folder,
    inspect_complete_folder,
    resolve_storage_path,
    usable_folder,
)
from librarian.organize.review import MISSING_FOLDER_APPLY_ERROR, review_slip_actions


def _converters() -> Any:
    # Resolved on the package so ``librarian.organize.maybe_*`` stays the one patch point.
    import librarian.organize as organize

    return organize


def unpack_release(folder: Path, **convert_kwargs: Any) -> Dict[str, Any]:
    """SAB often leaves damaged rar/7z: par2 when stuck, then unar. Returns the unpack note."""
    convert = _converters()
    if inspect_complete_folder(folder).get("problem") == REVIEW_UNPACK_STUCK:
        convert.maybe_par2_repair(folder, **convert_kwargs)
    return convert.maybe_unpack_archives(folder, **convert_kwargs)


def repair_review(
    db: Database,
    settings: Settings,
    *,
    work_id: str,
    convert_runner=None,
) -> Dict[str, Any]:
    """Run par2 then unar on a Review slip folder; does not shelve."""
    work = db.get_work(work_id)
    if work is None:
        raise ValueError("Work not found")
    source = Path(str(work.get("folder_path") or ""))
    if not usable_folder(source):
        raise ValueError(MISSING_FOLDER_APPLY_ERROR)
    resolved = resolve_storage_path(source, settings.complete_root)
    if not usable_folder(resolved) or not resolved.exists():
        raise ValueError(MISSING_FOLDER_APPLY_ERROR)
    resolved = release_folder(resolved)
    convert_kwargs = {"runner": convert_runner} if convert_runner is not None else {}
    convert = _converters()
    repaired = convert.maybe_par2_repair(resolved, **convert_kwargs)
    unpacked = convert.maybe_unpack_archives(resolved, **convert_kwargs)
    diagnosis = diagnose_review_folder(resolved, settings.complete_root)
    problem = diagnosis.get("problem")
    updated = work
    fails = int(work.get("repair_fail_count") or 0)
    if problem == REVIEW_UNPACK_STUCK:
        fails += 1
        updated = db.upsert_work(
            {
                **work,
                "review_reason": REVIEW_UNPACK_STUCK,
                "folder_path": str(resolved),
                "repair_fail_count": fails,
            }
        )
    elif problem:
        if str(work.get("review_reason") or "") != problem:
            updated = db.upsert_work({**work, "review_reason": problem, "folder_path": str(resolved)})
    elif str(work.get("review_reason") or "") == REVIEW_UNPACK_STUCK:
        updated = db.upsert_work(
            {
                **work,
                "review_reason": "unknown_identity",
                "folder_path": str(resolved),
                "repair_fail_count": 0,
            }
        )
    actions = review_slip_actions(updated, diagnosis)
    return {
        "work": updated,
        "repaired": repaired,
        "unpacked": unpacked,
        "folder_diagnosis": diagnosis,
        "actions": actions,
    }

