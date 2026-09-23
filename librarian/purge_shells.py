"""Conservative purge of catalog shells with no media on disk.

Removes works that:

1. Are not open Review slips (``needs_review`` stays in the bag).
2. Have zero rows in ``files``.
3. Have no readable payload files under ``folder_path`` (missing folder,
   empty dump, or empty string).

Keeps:

- Works with registered file rows (real shelf volumes).
- Works whose folder still holds payload media (re-scan can claim them).
- Goodreads-style wishlist stubs: ``review_state=none``, ISBN set, no folder.

Does not delete media on disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping

from librarian.config import Settings
from librarian.db import Database
from librarian.identify import list_payload_files, resolve_storage_path, usable_folder

PURGE_SHELL_LIMIT_DEFAULT = 8000


def _folder_has_payload(work: Mapping[str, Any], settings: Settings) -> bool:
    raw = str(work.get("folder_path") or "").strip()
    if not usable_folder(raw):
        return False
    resolved = resolve_storage_path(Path(raw), settings.complete_root)
    if not usable_folder(resolved) or not resolved.exists():
        return False
    try:
        return bool(list_payload_files(resolved))
    except OSError:
        return False


def is_wishlist_stub(work: Mapping[str, Any]) -> bool:
    """Thin Find/Goodreads stub — keep until a volume is shelved."""
    if str(work.get("review_state") or "") != "none":
        return False
    if not str(work.get("isbn") or "").strip():
        return False
    if str(work.get("folder_path") or "").strip():
        return False
    return True


def classify_shell_purge(
    db: Database,
    settings: Settings,
    *,
    limit: int = PURGE_SHELL_LIMIT_DEFAULT,
) -> Dict[str, str]:
    """Return ``{work_id: reason}`` for safe shell deletes."""
    to_purge: Dict[str, str] = {}
    for work in db.list_shell_works(limit=max(1, int(limit) or PURGE_SHELL_LIMIT_DEFAULT)):
        work_id = str(work.get("id") or "")
        if not work_id:
            continue
        if is_wishlist_stub(work):
            continue
        if _folder_has_payload(work, settings):
            continue
        # Re-check file rows so a concurrent organize cannot race us.
        if db.files_for_work(work_id):
            continue
        to_purge[work_id] = "no_media"
    return to_purge


def purge_shell_works(
    db: Database,
    settings: Settings,
    *,
    limit: int = PURGE_SHELL_LIMIT_DEFAULT,
    progress: Any = None,
) -> Dict[str, Any]:
    """Owner bulk: delete catalog shells with no on-disk media."""
    candidates = db.list_shell_works(limit=max(1, int(limit) or PURGE_SHELL_LIMIT_DEFAULT))
    total = len(candidates)
    if progress is not None:
        progress.start(total=total, phase="classifying")
        progress.log(f"Checking {total} catalog rows without registered files…")

    to_purge = classify_shell_purge(db, settings, limit=limit)
    purged = 0
    kept = 0
    failed = 0
    errors: List[str] = []

    if progress is not None:
        progress.tick(phase="purging", done=0, total=total, purged=0, kept=0, failed=0)

    for index, work in enumerate(candidates, start=1):
        work_id = str(work.get("id") or "")
        title = str(work.get("title") or work_id)
        reason = to_purge.get(work_id)
        if progress is not None:
            progress.tick(
                phase="purging",
                current_title=title,
                done=index - 1,
                total=total,
                purged=purged,
                kept=kept,
                failed=failed,
            )
        if not reason:
            kept += 1
            if progress is not None:
                progress.tick(
                    phase="purging",
                    current_title=title,
                    done=index,
                    total=total,
                    purged=purged,
                    kept=kept,
                    failed=failed,
                )
            continue
        try:
            fresh = db.get_work(work_id)
            if fresh is None:
                kept += 1
                continue
            if str(fresh.get("review_state") or "") == "needs_review":
                kept += 1
                continue
            if db.files_for_work(work_id) or _folder_has_payload(fresh, settings):
                kept += 1
                continue
            if is_wishlist_stub(fresh):
                kept += 1
                continue
            if not db.delete_work(work_id):
                kept += 1
                continue
            purged += 1
        except Exception as error:  # noqa: BLE001 — keep going through the backlog
            failed += 1
            if len(errors) < 12:
                errors.append(f"{title or work_id}: {error}")
            if progress is not None:
                progress.tick(
                    phase="purging",
                    current_title=title,
                    done=index,
                    total=total,
                    purged=purged,
                    kept=kept,
                    failed=failed,
                    log=f"Failed — {title or work_id}: {error}",
                )
            continue
        if progress is not None:
            progress.tick(
                phase="purging",
                current_title=title,
                done=index,
                total=total,
                purged=purged,
                kept=kept,
                failed=failed,
            )

    result = {
        "considered": total,
        "done": total,
        "total": total,
        "purged": purged,
        "kept": kept,
        "failed": failed,
        "errors": errors,
    }
    if progress is not None:
        progress.complete(result)
    return result
