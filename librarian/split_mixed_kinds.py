"""Split works that blended comic archives with ebook encodings.

Mass-import / Clear-extra fallout shelved ``.cbz`` next to ``.epub``/``.azw3``
under one comic identity. Forward ingest splits those payloads; this module
repairs already-catalogued blends without deleting media.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from librarian.config import Settings
from librarian.db import Database
from librarian.identify import (
    EBOOK_FORMAT_EXTENSIONS,
    dest_layout,
    expand_organize_payload,
    identify_completed,
    ingest_targets_for_mixed_payload,
    is_mixed_comic_ebook_payload,
    partition_comic_ebook_files,
    tidy_title,
)
from librarian.kinds import KIND_BOOK, KIND_COMIC

logger = logging.getLogger(__name__)

SPLIT_MIXED_LIMIT_DEFAULT = 8000


def _suffix(path: Path | str) -> str:
    return Path(path).suffix.lower()


def _paths_from_work_files(rows: Sequence[Mapping[str, Any]]) -> List[Path]:
    out: List[Path] = []
    for row in rows:
        raw = str(row.get("path") or "").strip()
        if raw:
            out.append(Path(raw))
    return out


def file_rows_are_mixed_comic_ebook(rows: Sequence[Mapping[str, Any]]) -> bool:
    """True when registered file rows include both comic archives and ebooks."""
    return is_mixed_comic_ebook_payload(_paths_from_work_files(rows))


def classify_mixed_kind_works(
    db: Database,
    *,
    limit: int = SPLIT_MIXED_LIMIT_DEFAULT,
) -> List[Dict[str, Any]]:
    """Return works whose file rows mix comic archives with ebook encodings."""
    hits: List[Dict[str, Any]] = []
    capped = max(1, min(int(limit) or SPLIT_MIXED_LIMIT_DEFAULT, 20000))
    for work in db.list_works(limit=capped):
        work_id = str(work.get("id") or "")
        if not work_id:
            continue
        rows = db.files_for_work(work_id)
        if not file_rows_are_mixed_comic_ebook(rows):
            continue
        hits.append(
            {
                "id": work_id,
                "title": work.get("title"),
                "kind": work.get("kind"),
                "folder_path": work.get("folder_path"),
                "files": len(rows),
            }
        )
    return hits


def count_mixed_kind_works(db: Database, *, limit: int = SPLIT_MIXED_LIMIT_DEFAULT) -> int:
    return len(classify_mixed_kind_works(db, limit=limit))


def _identity_for_files(
    files: Sequence[Path],
    *,
    kind: str,
    settings: Settings,
) -> Dict[str, Any]:
    if not files:
        return {"kind": kind, "title": "Untitled", "confidence": "low"}
    anchor = files[0]
    result = identify_completed(anchor if anchor.is_file() else anchor, settings=settings)
    identity = dict(result.get("identity") or {})
    identity["kind"] = kind
    if not str(identity.get("title") or "").strip():
        identity["title"] = tidy_title(anchor.stem) or "Untitled"
    return identity


def _place_file(src: Path, dest: Path, *, move: bool) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        try:
            if dest.resolve() == src.resolve():
                return dest
        except OSError:
            pass
        raise FileExistsError(str(dest))
    if move:
        shutil.move(str(src), str(dest))
    else:
        shutil.copy2(str(src), str(dest))
    return dest


def split_mixed_kind_work(
    db: Database,
    settings: Settings,
    *,
    work_id: str,
    move_files: bool = True,
) -> Dict[str, Any]:
    """Split one blended work into comic + book catalog rows. Never deletes media."""
    work = db.get_work(work_id)
    if work is None:
        raise ValueError("Work not found")
    rows = db.files_for_work(work_id)
    if not file_rows_are_mixed_comic_ebook(rows):
        raise ValueError("Work is not a comic+ebook blend")

    paths = _paths_from_work_files(rows)
    parts = partition_comic_ebook_files(paths)
    comic_paths = [path for path in (parts.get("comic") or []) if path.exists()]
    book_paths = [path for path in (parts.get("book") or []) if path.exists()]
    if not comic_paths or not book_paths:
        raise ValueError("Work is not a comic+ebook blend")

    row_by_path = {str(Path(str(row.get("path") or ""))): row for row in rows}

    comic_identity = _identity_for_files(comic_paths, kind=KIND_COMIC, settings=settings)
    book_identity = _identity_for_files(book_paths, kind=KIND_BOOK, settings=settings)

    # 1) Peel ebooks onto a new book work under books_root.
    placed_books: List[Path] = []
    book_folder: Optional[Path] = None
    for src in book_paths:
        dest = dest_layout(book_identity, settings, filename=src.name, source=src)
        written = _place_file(src, dest, move=move_files)
        placed_books.append(written)
        book_folder = written.parent
        old = row_by_path.get(str(src))
        if old:
            db.delete_file(str(old["id"]))

    assert book_folder is not None
    book_work = db.upsert_work(
        {
            **book_identity,
            "folder_path": str(book_folder),
            "review_state": "none",
            "review_reason": None,
        }
    )
    for written in placed_books:
        db.upsert_file(
            {
                "work_id": book_work["id"],
                "path": str(written),
                "filename": written.name,
                "kind": KIND_BOOK,
                "size": written.stat().st_size if written.exists() else 0,
            }
        )

    # 2) Keep comic archives on the original work (correct kind).
    comic_folder = comic_paths[0].parent
    for src in comic_paths:
        old = row_by_path.get(str(src))
        if old:
            db.upsert_file(
                {
                    "work_id": work_id,
                    "path": str(src),
                    "filename": src.name,
                    "kind": KIND_COMIC,
                    "size": src.stat().st_size if src.exists() else old.get("size"),
                }
            )
        comic_folder = src.parent

    comic_work = db.upsert_work(
        {
            **work,
            **comic_identity,
            "id": work_id,
            "kind": KIND_COMIC,
            "folder_path": str(comic_folder),
            "review_state": "none",
            "review_reason": None,
        }
    )

    # 3) Drop any leftover ebook/pdf rows still linked to the comic work.
    for row in list(db.files_for_work(work_id)):
        suffix = _suffix(str(row.get("path") or row.get("filename") or ""))
        if suffix in EBOOK_FORMAT_EXTENSIONS or suffix == ".pdf":
            # PDF went with books in the partition; comics keep only archives.
            path = Path(str(row.get("path") or ""))
            if suffix == ".pdf" and path.exists() and path in comic_paths:
                continue
            if suffix in EBOOK_FORMAT_EXTENSIONS or (
                suffix == ".pdf" and path not in comic_paths
            ):
                db.delete_file(str(row["id"]))

    return {
        "work_id": work_id,
        "comic_work_id": comic_work["id"],
        "book_work_id": book_work["id"],
        "comic_files": len(comic_paths),
        "book_files": len(placed_books),
        "comic_folder": str(comic_folder),
        "book_folder": str(book_folder),
    }


def split_mixed_kind_works(
    db: Database,
    settings: Settings,
    *,
    limit: int = 0,
    progress: Any = None,
    move_files: bool = True,
) -> Dict[str, Any]:
    """Owner bulk: split every comic+ebook blend found in the catalog."""
    candidates = classify_mixed_kind_works(
        db, limit=max(int(limit) or SPLIT_MIXED_LIMIT_DEFAULT, 1)
    )
    if limit and limit > 0:
        candidates = candidates[: int(limit)]
    total = len(candidates)
    if progress is not None:
        progress.start(total=total, phase="splitting")
    split = 0
    failed = 0
    errors: List[str] = []
    created_books: List[str] = []
    for index, row in enumerate(candidates, start=1):
        title = str(row.get("title") or row.get("id") or "").strip()
        if progress is not None:
            progress.tick(
                phase="splitting",
                current_title=title,
                done=index - 1,
                total=total,
                split=split,
                failed=failed,
            )
        try:
            result = split_mixed_kind_work(
                db,
                settings,
                work_id=str(row["id"]),
                move_files=move_files,
            )
            split += 1
            created_books.append(str(result.get("book_work_id") or ""))
            if progress is not None:
                progress.log(f"Split {title} → book {result.get('book_work_id')}")
        except Exception as error:  # noqa: BLE001 — keep bulk going
            failed += 1
            msg = f"{title}: {error}"
            errors.append(msg)
            logger.exception("Split mixed kinds failed for %s", row.get("id"))
            if progress is not None:
                progress.log(f"Failed {msg}")
        if progress is not None:
            progress.tick(
                phase="splitting",
                current_title=title,
                done=index,
                total=total,
                split=split,
                failed=failed,
            )
    summary = {
        "considered": total,
        "split": split,
        "failed": failed,
        "done": total,
        "total": total,
        "book_work_ids": [wid for wid in created_books if wid],
        "errors": errors[:20],
    }
    if progress is not None:
        progress.finish(result=summary)
    return summary


def split_mixed_payload_folder(
    db: Database,
    settings: Settings,
    *,
    work_id: str,
    folder: Path,
    requested_by: str = "owner",
    on_progress: Any = None,
) -> Dict[str, Any]:
    """Clear an ``extra_files`` slip whose folder mixes comics and ebooks via ingest."""
    from librarian.ingest import enqueue_ingest

    work = db.get_work(work_id)
    if work is None:
        raise ValueError("Work not found")
    files = expand_organize_payload(folder)
    if not is_mixed_comic_ebook_payload(files):
        raise ValueError("Folder is not a comic+ebook mix")
    targets = ingest_targets_for_mixed_payload(files)
    db.upsert_work({**work, "review_state": "resolved", "review_reason": None})
    process_sync = len(targets) <= 4
    jobs: List[Dict[str, Any]] = []
    for index, target in enumerate(targets, start=1):
        if on_progress is not None:
            on_progress(
                child_index=index,
                child_total=len(targets),
                child_title=target.name,
                process_sync=process_sync,
            )
        jobs.append(
            enqueue_ingest(
                db,
                settings,
                path=target,
                requested_by=requested_by,
                source="ingest",
                process=process_sync,
            )
        )
    shelved = sum(1 for job in jobs if str(job.get("status") or "") == "organized")
    review = sum(1 for job in jobs if str(job.get("status") or "") == "review")
    return {
        "action": "split_mixed_kinds",
        "work_id": work_id,
        "targets": len(targets),
        "shelved": shelved,
        "review": review,
        "queued": 0 if process_sync else len(targets),
        "process_sync": process_sync,
        "jobs": [{"id": job.get("id"), "status": job.get("status"), "title": job.get("title")} for job in jobs],
    }
