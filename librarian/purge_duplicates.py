"""Conservative purge of redundant Review slips.

Only dismisses slips that are safely redundant:

1. **Shelf twin** — the slip's media fingerprint matches content already on the
   shelf (identity conflict folder or ``dest_layout`` destination folder).
2. **Slip twin** — two or more Review slips share the same fingerprint; keep
   the oldest, dismiss the rest.

Ambiguous Identify slips without a shelved (or sibling-slip) twin are kept.
Does not delete media on disk — same as Skip / ignored-duplicate Apply.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from librarian.config import Settings
from librarian.db import Database
from librarian.file_identity import volume_content_fingerprint
from librarian.identify import dest_layout, list_payload_files, resolve_storage_path, usable_folder

PURGE_SLIP_LIMIT_DEFAULT = 8000


def _created_sort_key(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dismiss_slip(db: Database, work: Mapping[str, Any]) -> Dict[str, Any]:
    return db.upsert_work(
        {
            **dict(work),
            "review_state": "resolved",
            "review_reason": None,
        }
    )


def _slip_folder(work: Mapping[str, Any], settings: Settings) -> Optional[Path]:
    raw = str(work.get("folder_path") or "").strip()
    if not usable_folder(raw):
        return None
    resolved = resolve_storage_path(Path(raw), settings.complete_root)
    if not usable_folder(resolved) or not resolved.exists():
        return None
    return resolved


def _predicted_dest_folder(work: Mapping[str, Any], settings: Settings, source: Path) -> Optional[Path]:
    files = list_payload_files(source)
    if not files:
        return None
    try:
        dest = dest_layout(
            {
                "kind": work.get("kind"),
                "title": work.get("title"),
                "author": work.get("author"),
                "series_name": work.get("series_name"),
                "series_index": work.get("series_index"),
                "year": work.get("year"),
                "isbn": work.get("isbn"),
                "publisher": work.get("publisher"),
                "volume_year": work.get("volume_year"),
                "comic_format": work.get("comic_format"),
                "comic_subtitle": work.get("comic_subtitle"),
                "asin": work.get("asin"),
                "album": work.get("album"),
                "mbid": work.get("mbid"),
            },
            settings,
            filename=files[0].name,
            source=files[0],
        )
    except (ValueError, TypeError, OSError):
        return None
    return dest.parent


def _shelved_identity_twin(db: Database, work: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Another catalog row with the same identity that is not a Review slip."""
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
    if str(conflict.get("review_state") or "") == "needs_review":
        return None
    twin_folder = str(conflict.get("folder_path") or "").strip()
    if not twin_folder:
        return None
    return conflict


def _folder_fingerprint(
    path: Optional[Path],
    cache: Dict[str, Optional[str]],
) -> Optional[str]:
    if path is None:
        return None
    key = str(path.resolve()) if path.exists() else str(path)
    if key not in cache:
        try:
            cache[key] = volume_content_fingerprint(path) if path.exists() else None
        except OSError:
            cache[key] = None
    return cache[key]


def classify_purge_candidates(
    db: Database,
    settings: Settings,
    slips: List[Dict[str, Any]],
    *,
    progress: Any = None,
) -> Tuple[Dict[str, str], Dict[str, Optional[str]]]:
    """Return ``{work_id: reason}`` for safe purges and slip fingerprints.

    Reasons: ``shelf_duplicate`` | ``slip_duplicate``.
    """
    fp_cache: Dict[str, Optional[str]] = {}
    slip_fps: Dict[str, Optional[str]] = {}
    total = len(slips)

    for index, slip in enumerate(slips, start=1):
        work_id = str(slip.get("id") or "")
        title = str(slip.get("title") or work_id).strip()
        if progress is not None and (index == 1 or index % 10 == 0 or index == total):
            progress.tick(
                phase="fingerprinting",
                current_title=title,
                done=index - 1,
                total=total,
            )
        folder = _slip_folder(slip, settings)
        slip_fps[work_id] = _folder_fingerprint(folder, fp_cache)

    to_purge: Dict[str, str] = {}

    # 1) Shelf twins — fingerprint matches shelved identity or dest_layout folder.
    for index, slip in enumerate(slips, start=1):
        work_id = str(slip.get("id") or "")
        fp = slip_fps.get(work_id)
        if not fp:
            continue
        title = str(slip.get("title") or work_id).strip()
        if progress is not None and (index == 1 or index % 10 == 0 or index == total):
            progress.tick(
                phase="matching",
                current_title=title,
                done=index - 1,
                total=total,
            )
        folder = _slip_folder(slip, settings)
        twin = _shelved_identity_twin(db, slip)
        if twin is not None:
            twin_path = Path(str(twin.get("folder_path") or ""))
            twin_fp = _folder_fingerprint(twin_path if twin_path.exists() else None, fp_cache)
            if twin_fp and twin_fp == fp:
                to_purge[work_id] = "shelf_duplicate"
                continue
        if folder is not None:
            dest_folder = _predicted_dest_folder(slip, settings, folder)
            if dest_folder is not None and dest_folder.exists():
                try:
                    same_path = dest_folder.resolve() == folder.resolve()
                except OSError:
                    same_path = False
                if not same_path:
                    dest_fp = _folder_fingerprint(dest_folder, fp_cache)
                    if dest_fp and dest_fp == fp:
                        to_purge[work_id] = "shelf_duplicate"

    # 2) Exact duplicate slips of each other — keep the oldest, purge the rest.
    #    Skip slips already marked as shelf duplicates (they all go).
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for slip in slips:
        work_id = str(slip.get("id") or "")
        if work_id in to_purge:
            continue
        fp = slip_fps.get(work_id)
        if not fp:
            continue
        groups[fp].append(slip)

    for members in groups.values():
        if len(members) < 2:
            continue
        ordered = sorted(
            members,
            key=lambda row: (
                _created_sort_key(row.get("created_at")),
                str(row.get("updated_at") or ""),
                str(row.get("id") or ""),
            ),
        )
        for other in ordered[1:]:
            oid = str(other.get("id") or "")
            if oid and oid not in to_purge:
                to_purge[oid] = "slip_duplicate"

    return to_purge, slip_fps


def purge_duplicate_reviews(
    db: Database,
    settings: Settings,
    *,
    limit: int = 0,
    progress: Any = None,
) -> Dict[str, Any]:
    """Owner bulk: dismiss safely redundant Review slips (background-friendly)."""
    fetch_limit = max(int(limit) or PURGE_SLIP_LIMIT_DEFAULT, 1)
    slips = db.list_works(review_state="needs_review", limit=fetch_limit)
    if limit and limit > 0:
        slips = slips[: int(limit)]
    total = len(slips)
    if progress is not None:
        progress.start(total=total, phase="fingerprinting")

    to_purge, _slip_fps = classify_purge_candidates(db, settings, slips, progress=progress)

    purged = 0
    shelf_twins = 0
    slip_twins = 0
    kept = 0
    failed = 0
    errors: List[str] = []

    for index, slip in enumerate(slips, start=1):
        work_id = str(slip.get("id") or "")
        title = str(slip.get("title") or work_id).strip()
        reason = to_purge.get(work_id)
        if progress is not None:
            progress.tick(
                phase="purging",
                current_title=title,
                done=index - 1,
                total=total,
                purged=purged,
                shelf_twins=shelf_twins,
                slip_twins=slip_twins,
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
                    shelf_twins=shelf_twins,
                    slip_twins=slip_twins,
                    kept=kept,
                    failed=failed,
                )
            continue
        try:
            fresh = db.get_work(work_id) or slip
            if str(fresh.get("review_state") or "") != "needs_review":
                kept += 1
                continue
            _dismiss_slip(db, fresh)
            purged += 1
            if reason == "shelf_duplicate":
                shelf_twins += 1
            else:
                slip_twins += 1
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
                    shelf_twins=shelf_twins,
                    slip_twins=slip_twins,
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
                shelf_twins=shelf_twins,
                slip_twins=slip_twins,
                kept=kept,
                failed=failed,
            )

    result = {
        "considered": total,
        "done": total,
        "total": total,
        "purged": purged,
        "shelf_twins": shelf_twins,
        "slip_twins": slip_twins,
        "kept": kept,
        "failed": failed,
        "errors": errors,
    }
    if progress is not None:
        progress.complete(result)
    return result
