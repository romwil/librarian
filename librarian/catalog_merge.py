"""Owner duplicate-merge on the finished canonical model (Phase 4.3).

Merges run only after a named snapshot. Rollback is restore-from-snapshot, not
the 200-row Safe undo. Do not point this at live Automat without that snapshot
and an owner walk of one merged work.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from librarian.backup import BackupError, backup_dir_for, snapshot_named
from librarian.identity.match import (
    calibre_suffixed_titles,
    duplicate_groups,
    sample_groups,
)
from librarian.identity.titles import strip_calibre_suffix, title_sort


class MergeRefused(ValueError):
    """Apply was asked without a snapshot (or the snapshot failed)."""


def preview_duplicate_merge(db: Any) -> Dict[str, Any]:
    """Dry-run: merge groups, possible duplicates, Calibre suffixes still on titles."""
    automatic, possible = duplicate_groups(db)
    calibre = calibre_suffixed_titles(db)
    return {
        "merge_groups": len(automatic),
        "works_to_merge": sum(len(group) - 1 for group in automatic),
        "possible_duplicates": len(possible),
        "calibre_suffixes": len(calibre),
        "sample_groups": sample_groups(automatic),
        "possible_samples": sample_groups(possible),
        "calibre_samples": calibre[:10],
        "requires_snapshot": True,
    }


def _strip_stored_titles(db: Any) -> int:
    changed = 0
    with db._connect() as conn:
        rows = list(conn.execute("SELECT id, title FROM works"))
    updates: List[tuple[str, str, str]] = []
    for row in rows:
        title = str(row["title"] or "")
        stripped = strip_calibre_suffix(title)
        if stripped and stripped != title.strip():
            updates.append((stripped, title_sort(stripped), str(row["id"])))
    if not updates:
        return 0

    def _write() -> None:
        nonlocal changed
        with db._connect() as conn:
            for title, sort_key, work_id in updates:
                conn.execute(
                    "UPDATE works SET title=?, title_sort=?, updated_at=strftime('%s','now') WHERE id=?",
                    (title, sort_key, work_id),
                )
                changed += 1

    db.run_write(_write, label="strip_calibre_titles")
    return changed


def apply_duplicate_merge(
    db: Any,
    *,
    settings: Any,
    data_dir: Any,
    snapshot: bool = True,
) -> Dict[str, Any]:
    """Merge automatic duplicate groups after a named snapshot.

    ``possible`` clusters are not merged and are not pushed onto Sorting — the
    owner names those separately. Reversible via the snapshot file.
    """
    from librarian.cleanup import _merge_group, _quarantine_root

    root = Path(data_dir)
    snapshot_file: Optional[str] = None
    if snapshot:
        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        try:
            path = snapshot_named(db.path, backup_dir_for(root), f"pre-duplicate-merge-{stamp}")
        except BackupError as error:
            raise MergeRefused(f"Duplicate merge needs a snapshot first: {error}") from error
        snapshot_file = path.name

    preview = preview_duplicate_merge(db)
    stripped = _strip_stored_titles(db)
    automatic, _possible = duplicate_groups(db)
    from datetime import date

    quarantine = _quarantine_root(settings, date.today().isoformat())
    totals = {"merged": 0, "moved_files": 0, "quarantined_bytes": 0}
    for group in automatic:
        result = _merge_group(db, group, settings=settings, quarantine=quarantine)
        for key in totals:
            totals[key] += result[key]
    return {
        **preview,
        **totals,
        "calibre_titles_stripped": stripped,
        "snapshot": snapshot_file,
        "quarantine": str(quarantine) if quarantine.exists() else None,
    }
