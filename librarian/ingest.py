"""Owner/op ingest: add a /data path or watch a drop folder.

Scan walks library roots and does not move files. Ingest relocates when
identify is confident, otherwise Review. Fail closed.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from librarian.config import MEDIA_ROOT_FIELDS, Settings
from librarian.db import Database
from librarian.file_identity import (
    count_media_files,
    payload_media_files,
    volume_content_fingerprint,
)
from librarian.identify import (
    CONTAINER_DATA_PREFIX,
    HOST_DATA_PREFIX,
    JUNK_NAMES,
    MEDIA_EXTENSIONS,
    UNPACK_STUCK,
    inspect_complete_folder,
    list_payload_files,
)

logger = logging.getLogger(__name__)

INGEST_SOURCES = frozenset({"ingest", "watch"})
AUDIO_EXTENSIONS = {".m4b", ".mp3", ".flac", ".m4a", ".ogg", ".opus"}
SKIP_NAMES = {name.lower() for name in JUNK_NAMES}

LIBRARY_ROOT_REFUSAL = "That's already a library root — Scan the shelves instead."
LIBRARY_SHELF_REFUSAL = "That path is already on a library shelf. Scan the shelves instead."
COMPLETE_ROOT_REFUSAL = (
    "That's the downloader complete folder. Point at a finished dump inside it, not the folder itself."
)
INGEST_NO_PAYLOAD_ERROR = "Nothing to identify in here — empty or only junk files."
INGEST_UNPACK_STUCK_ERROR = "Unpack did not finish; archives are still in this folder."
INGEST_MISSING_FOLDER_ERROR = "That path is gone — it moved or was removed."


class PathDenied(ValueError):
    """Path is outside the /data sandbox or otherwise unusable."""


def data_fs_root() -> Path:
    """Container `/data`, or DATA_DIR in tests when `/data` is absent."""
    override = (os.environ.get("LIBRARIAN_FS_ROOT") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    container = Path("/data")
    if container.is_dir():
        return container.resolve()
    data_dir = (os.environ.get("DATA_DIR") or "").strip()
    if data_dir:
        return Path(data_dir).expanduser().resolve()
    return Path(".").resolve()


def _rewrite_host_data(path: Path, root: Path) -> Path:
    text = str(path)
    if text.startswith(HOST_DATA_PREFIX) and str(root) in {CONTAINER_DATA_PREFIX.rstrip("/"), "/data"}:
        return Path(CONTAINER_DATA_PREFIX + text[len(HOST_DATA_PREFIX) :])
    return path


def confined_path(raw: str, *, must_exist: bool = True) -> Path:
    """Resolve a household path under `/data` (or DATA_DIR in tests). Fail closed."""
    text = str(raw or "").strip()
    if not text or text in {".", ".."}:
        raise PathDenied("Path is required")
    parts = Path(text).parts
    if ".." in parts:
        raise PathDenied("Path is outside /data")
    root = data_fs_root()
    candidate = Path(text)
    candidate = _rewrite_host_data(candidate, root)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
    except OSError as error:
        raise PathDenied("Path is outside /data") from error
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise PathDenied("Path is outside /data") from error
    if resolved != root and root not in resolved.parents:
        raise PathDenied("Path is outside /data")
    if must_exist and not resolved.exists():
        raise PathDenied("Path not found")
    return resolved


def skipped_name(name: str) -> bool:
    text = str(name or "")
    if not text or text.startswith(".") or text.startswith("._"):
        return True
    return text.lower() in SKIP_NAMES


def _norm_key(path: Path) -> str:
    try:
        return str(path.resolve())
    except OSError:
        return str(path).rstrip("/")


def media_root_paths(settings: Settings) -> List[Path]:
    roots: List[Path] = []
    for field in MEDIA_ROOT_FIELDS:
        raw = str(getattr(settings, field) or "").strip()
        if raw:
            roots.append(Path(raw))
    complete = str(settings.complete_root or "").strip()
    if complete:
        roots.append(Path(complete))
    return roots


def _overlaps(left: Path, right: Path) -> bool:
    try:
        a = left.resolve() if left.exists() else left
        b = right.resolve() if right.exists() else right
    except OSError:
        a, b = left, right
    try:
        a.relative_to(b)
        return True
    except ValueError:
        pass
    try:
        b.relative_to(a)
        return True
    except ValueError:
        return False


# Smart Map inbox / library — never a Librarian watch folder (Automat media contract).
SMART_MAP_WATCH_FORBIDDEN = (
    Path("/data/media/YouTubeDownload"),
    Path("/data/media/YouTubeLibrary"),
)


def watch_root_forbidden(watch: Path, settings: Settings) -> bool:
    """True when a watch path would re-ingest a library or SAB complete folder."""
    for root in media_root_paths(settings):
        if _overlaps(watch, root):
            return True
    for extra in SMART_MAP_WATCH_FORBIDDEN:
        if _overlaps(watch, extra):
            return True
    return False


def validate_watch_root(raw: str, settings: Settings) -> Optional[str]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        path = confined_path(text, must_exist=False)
    except PathDenied as error:
        return str(error)
    if watch_root_forbidden(path, settings):
        return "Watch folder cannot be a library root, SAB complete folder, or Smart Map inbox"
    return None


def expand_album_context(path: Path) -> Path:
    """A single audio file uses sibling tracks in the same folder (identify folder logic)."""
    if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
        return path
    parent = path.parent
    try:
        siblings = [
            child
            for child in parent.iterdir()
            if child.is_file()
            and not skipped_name(child.name)
            and child.suffix.lower() in MEDIA_EXTENSIONS
        ]
    except OSError:
        return path
    if len(siblings) > 1:
        return parent
    return path


def list_dir(raw: str = "") -> Dict[str, Any]:
    root = data_fs_root()
    path = confined_path(raw, must_exist=True) if str(raw or "").strip() else root
    if not path.is_dir():
        raise PathDenied("Not a folder")
    entries: List[Dict[str, Any]] = []
    try:
        children = sorted(path.iterdir(), key=lambda child: (not child.is_dir(), child.name.lower()))
    except OSError as error:
        raise PathDenied("Cannot read folder") from error
    for child in children:
        if skipped_name(child.name):
            continue
        try:
            confined_path(str(child), must_exist=False)
        except PathDenied:
            continue
        kind = "dir" if child.is_dir() else "file"
        if child.is_symlink():
            try:
                confined_path(str(child.resolve()), must_exist=False)
            except (PathDenied, OSError):
                continue
        entries.append({"name": child.name, "path": str(child), "kind": kind})
    parent: Optional[str] = None
    if path != root:
        parent = str(path.parent)
    return {"root": str(root), "path": str(path), "parent": parent, "entries": entries}


def _title_for_path(path: Path) -> str:
    name = path.name
    if path.is_file():
        name = path.stem
    return name or "Untitled"


def _job_source(job: Dict[str, Any]) -> str:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    return str(payload.get("source") or "")


def enqueue_ingest(
    db: Database,
    settings: Settings,
    *,
    path: Path,
    requested_by: str,
    source: str = "ingest",
    process: bool = True,
) -> Dict[str, Any]:
    if source not in INGEST_SOURCES:
        raise ValueError("Unknown ingest source")
    target = expand_album_context(path)
    stored = _norm_key(target)
    existing = db.get_job_by_storage_path(stored)
    if existing is not None:
        return existing
    refusal = protected_path_refusal(target, settings)
    if refusal:
        raise PathDenied(refusal)
    job = db.create_job(
        {
            "status": "identifying",
            "title": _title_for_path(target),
            "requested_by": requested_by,
            "storage_path": stored,
            "nzo_name": stored,
            "payload": {"source": source, "path": stored},
        }
    )
    if process:
        return progress_ingest_job(db, settings, job["id"])
    return job


def list_ingest_targets(path: Path) -> List[Path]:
    """Expand a dump-parent folder into children; leave single volumes alone.

    A directory whose children are sibling dumps (subfolders and/or release
    files) becomes one target per child — same idea as the watch folder.
    Calibre-style trees (Author → Title (id) → epub) expand recursively so
    an author folder is never ingested as one multi-book work.
    A directory that *is* the volume (top-level media only: book, album,
    loose comic pages) stays a single target.
    """
    return list(iter_ingest_targets(path))


def iter_ingest_targets(path: Path):
    """Yield ingest targets depth-first (same rules as ``list_ingest_targets``)."""
    from librarian.identify import ingest_targets_for_mixed_payload, is_mixed_comic_ebook_payload

    if not path.is_dir():
        yield path
        return
    try:
        children = sorted(path.iterdir(), key=lambda child: child.name.lower())
    except OSError:
        yield path
        return
    dirs: List[Path] = []
    media_files: List[Path] = []
    for child in children:
        if skipped_name(child.name):
            continue
        if child.is_dir():
            dirs.append(child)
        elif child.is_file() and child.suffix.lower() in MEDIA_EXTENSIONS:
            media_files.append(child)
    if dirs and media_files:
        for child in dirs:
            yield from iter_ingest_targets(child)
        # Mixed comic+ebook at the dump root: never one blended volume.
        if is_mixed_comic_ebook_payload(media_files):
            yield from ingest_targets_for_mixed_payload(media_files)
        else:
            yield from media_files
        return
    if len(dirs) >= 2:
        for child in dirs:
            yield from iter_ingest_targets(child)
        return
    if len(dirs) == 1 and not media_files:
        yield from iter_ingest_targets(dirs[0])
        return
    # Leaf volume with both comic archives and ebook encodings → separate works.
    if media_files and is_mixed_comic_ebook_payload(media_files):
        yield from ingest_targets_for_mixed_payload(media_files)
        return
    # Flat multi-title dumps (NYT bestsellers Fiction, etc.): one target per stem.
    if len(media_files) > 1:
        from librarian.identify import (
            ingest_targets_for_multi_title_payload,
            unexpected_extra_files,
        )

        if unexpected_extra_files(media_files):
            yield from ingest_targets_for_multi_title_payload(media_files)
            return
    yield path


def inventory_ingest_paths(
    roots: List[Path],
    *,
    progress: Any = None,
) -> Dict[str, Any]:
    """Recursive pre-scan: expand targets, count media, mark batch duplicates.

    Returns ``targets``, ``files_found``, ``volumes_found``, and
    ``duplicate_indexes`` (set of target indexes that are byte-identical to an
    earlier volume in this batch).
    """
    targets: List[Path] = []
    files_found = 0
    fingerprint_first: Dict[str, int] = {}
    duplicate_indexes: set[int] = set()

    if progress is not None:
        progress.tick(
            phase="scanning",
            done=0,
            total=0,
            volumes_found=0,
            files_found=0,
            current_path=_norm_key(roots[0]) if roots else "",
            current_title="Scanning folders…",
            log="Scanning folders for volumes…",
        )

    for root in roots:
        for target in iter_ingest_targets(root):
            targets.append(target)
            media = payload_media_files(target)
            files_found += len(media)
            index = len(targets) - 1
            title = _title_for_path(target)
            current_path = _norm_key(target)
            fp = volume_content_fingerprint(target)
            if fp:
                prior = fingerprint_first.get(fp)
                if prior is None:
                    fingerprint_first[fp] = index
                else:
                    duplicate_indexes.add(index)
            if progress is not None and (index == 0 or (index + 1) % 5 == 0 or fp and index in duplicate_indexes):
                progress.tick(
                    phase="scanning",
                    done=0,
                    total=0,
                    volumes_found=len(targets),
                    files_found=files_found,
                    duplicates=len(duplicate_indexes),
                    current_path=current_path,
                    current_title=title,
                    log=(
                        f"Found {len(targets)} volume{'s' if len(targets) != 1 else ''}"
                        f" · {files_found} media file{'s' if files_found != 1 else ''}"
                        + (f" · {len(duplicate_indexes)} duplicate" if duplicate_indexes else "")
                    ),
                )

    volumes_found = len(targets)
    if progress is not None:
        dup_note = (
            f" · {len(duplicate_indexes)} anticipated duplicate{'s' if len(duplicate_indexes) != 1 else ''}"
            if duplicate_indexes
            else ""
        )
        progress.tick(
            phase="scanning",
            done=0,
            total=volumes_found,
            volumes_found=volumes_found,
            files_found=files_found,
            duplicates=len(duplicate_indexes),
            current_path="",
            current_title="",
            log=(
                f"Found {volumes_found} volume{'s' if volumes_found != 1 else ''}"
                f" · {files_found} media file{'s' if files_found != 1 else ''}{dup_note}."
            ),
        )
    return {
        "targets": targets,
        "volumes_found": volumes_found,
        "files_found": files_found,
        "duplicate_indexes": duplicate_indexes,
    }


def run_ingest_paths(
    db: Database,
    settings: Settings,
    *,
    paths: List[Path],
    requested_by: str,
    source: str = "ingest",
    progress: Any = None,
    expand: bool = True,
) -> Dict[str, Any]:
    """Identify/organize each path, ticking ``progress`` when provided.

    When ``expand`` is true (default), recursively inventories targets first so
    ``total`` matches the real volume count before organizing begins.
    """
    if progress is not None:
        progress.start(total=0, phase="scanning")

    duplicate_indexes: set[int] = set()
    files_found = 0
    volumes_found = 0
    if expand:
        inventory = inventory_ingest_paths(list(paths), progress=progress)
        targets = list(inventory["targets"])
        duplicate_indexes = set(inventory["duplicate_indexes"])
        files_found = int(inventory["files_found"])
        volumes_found = int(inventory["volumes_found"])
    else:
        targets = list(paths)
        files_found = count_media_files(targets)
        volumes_found = len(targets)

    total = len(targets)
    if progress is not None:
        progress.tick(
            phase="organizing" if total else "scanning",
            done=0,
            total=total,
            volumes_found=volumes_found or total,
            files_found=files_found,
            duplicates=len(duplicate_indexes),
            log=(
                f"Shelving {total} volume{'s' if total != 1 else ''}…"
                if total
                else "Nothing to shelve."
            ),
        )

    shelved = 0
    review = 0
    skipped = 0
    duplicates = 0
    errors = 0
    jobs: List[Dict[str, Any]] = []
    seen = 0

    for index, target in enumerate(targets):
        title = _title_for_path(target)
        current_path = _norm_key(target)
        if progress is not None:
            progress.tick(
                phase="identifying",
                current_path=current_path,
                current_title=title,
                done=index,
                total=total,
                volumes_found=volumes_found or total,
                files_found=files_found,
                shelved=shelved,
                review=review,
                skipped=skipped,
                duplicates=duplicates,
                errors=errors,
            )
        try:
            if index in duplicate_indexes:
                duplicates += 1
                seen += 1
                if progress is not None:
                    progress.tick(
                        phase="organizing",
                        done=index + 1,
                        skipped=skipped,
                        duplicates=duplicates,
                        shelved=shelved,
                        review=review,
                        errors=errors,
                        seen=seen,
                        log=f"Ignored duplicate — {title}",
                    )
                continue
            if target.is_dir() and watch_entry_skippable(target):
                skipped += 1
                seen += 1
                if progress is not None:
                    progress.tick(
                        phase="identifying",
                        done=index + 1,
                        skipped=skipped,
                        duplicates=duplicates,
                        shelved=shelved,
                        review=review,
                        errors=errors,
                        seen=seen,
                        log=f"Skipped — {title}",
                    )
                continue
            stored = _norm_key(expand_album_context(target))
            existing = db.get_job_by_storage_path(stored)
            if existing is not None and existing.get("status") not in {"identifying", "queued"}:
                if str(existing.get("status") or "") == "skipped":
                    duplicates += 1
                    note = f"Ignored duplicate — {title}"
                else:
                    skipped += 1
                    note = f"Already handled — {title}"
                seen += 1
                if progress is not None:
                    progress.tick(
                        phase="identifying",
                        done=index + 1,
                        skipped=skipped,
                        duplicates=duplicates,
                        shelved=shelved,
                        review=review,
                        errors=errors,
                        seen=seen,
                        log=note,
                    )
                continue
            if progress is not None:
                progress.tick(
                    phase="organizing",
                    current_path=current_path,
                    current_title=title,
                    done=index,
                    total=total,
                )
            job = enqueue_ingest(
                db,
                settings,
                path=target,
                requested_by=requested_by,
                source=source,
                process=True,
            )
            jobs.append(job)
            status = str(job.get("status") or "")
            work = db.get_work(str(job.get("work_id") or "")) if job.get("work_id") else None
            quiet = bool(work and str(work.get("review_reason") or "") == "quiet_hours")
            seen += 1
            if status == "organized":
                shelved += 1
                note = f"Shelved — {job.get('title') or title}"
            elif status == "skipped":
                duplicates += 1
                note = f"Ignored duplicate — {job.get('title') or title}"
            elif status == "review":
                review += 1
                note = (
                    f"Parked for quiet hours — {job.get('title') or title}"
                    if quiet
                    else f"Needs you — {job.get('title') or title}"
                )
            elif status == "failed":
                errors += 1
                note = str(job.get("error") or f"Failed — {title}")
            else:
                note = f"On the way — {job.get('title') or title}"
            if progress is not None:
                progress.tick(
                    phase="organizing",
                    current_path=current_path,
                    current_title=str(job.get("title") or title),
                    done=index + 1,
                    total=total,
                    shelved=shelved,
                    review=review,
                    skipped=skipped,
                    duplicates=duplicates,
                    errors=errors,
                    seen=seen,
                    log=note,
                )
        except PathDenied as error:
            errors += 1
            seen += 1
            if progress is not None:
                progress.tick(
                    done=index + 1,
                    errors=errors,
                    shelved=shelved,
                    review=review,
                    skipped=skipped,
                    duplicates=duplicates,
                    seen=seen,
                    log=str(error),
                )
        except Exception as error:  # noqa: BLE001 — surface per-item and keep going
            logger.exception("Ingest failed for %s", target)
            errors += 1
            seen += 1
            if progress is not None:
                progress.tick(
                    done=index + 1,
                    errors=errors,
                    shelved=shelved,
                    review=review,
                    skipped=skipped,
                    duplicates=duplicates,
                    seen=seen,
                    log=f"Failed — {title}: {error}",
                )

    summary = {
        "done": total,
        "seen": seen if seen else total,
        "total": total,
        "shelved": shelved,
        "review": review,
        "skipped": skipped,
        "duplicates": duplicates,
        "errors": errors,
        "jobs": len(jobs),
        "volumes_found": volumes_found or total,
        "files_found": files_found,
    }
    if progress is not None:
        progress.complete(summary)
    return summary


def _resolve_maybe(path: Path) -> Path:
    try:
        return path.resolve() if path.exists() else path
    except OSError:
        return path


def protected_path_refusal(path: Path, settings: Settings) -> Optional[str]:
    """Household English when ingest would hit a Settings root or SAB complete folder."""
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    for field in MEDIA_ROOT_FIELDS:
        raw = str(getattr(settings, field) or "").strip()
        if not raw:
            continue
        root = _resolve_maybe(Path(raw))
        if resolved == root:
            return LIBRARY_ROOT_REFUSAL
        try:
            resolved.relative_to(root)
            return LIBRARY_SHELF_REFUSAL
        except ValueError:
            continue
    complete = str(settings.complete_root or "").strip()
    if complete:
        root = _resolve_maybe(Path(complete))
        if resolved == root:
            return COMPLETE_ROOT_REFUSAL
        try:
            resolved.relative_to(root)
        except ValueError:
            pass
        else:
            # Finished dumps under complete are allowed; only the root itself is refused.
            pass
    return None


def progress_ingest_job(db: Database, settings: Settings, job_id: str) -> Dict[str, Any]:
    job = db.get_job(job_id)
    if job is None:
        raise ValueError("Job not found")
    if _job_source(job) not in INGEST_SOURCES:
        return job
    if job.get("status") not in {"identifying", "queued"}:
        return job
    raw = str(job.get("storage_path") or (job.get("payload") or {}).get("path") or "")
    folder = Path(raw)
    if not folder.exists():
        updated = db.update_job(job_id, status="failed", error=f"{INGEST_MISSING_FOLDER_ERROR} ({folder})")
        return updated or job
    # Archives-only dumps: organize runs par2+unar and parks Review when stuck.
    # Only a truly missing path is a hard fail (handled above when folder.exists is false).
    try:
        from librarian.organize import organize_identified
        organized = organize_identified(db, settings, folder=folder, move_source=True)
    except OSError as error:
        # Permission / IO errors must leave Review — never stay identifying or the
        # poller retries forever and storms the logs (and locks SQLite).
        reason = f"Could not shelve — {error}"
        logger.exception("Ingest organize failed for %s", folder)
        updated = db.update_job(
            job_id,
            status="review",
            error=reason,
            title=str(job.get("title") or _title_for_path(folder)),
        )
        return updated or job
    identity = organized.get("identity") or {}
    work = organized["work"]
    if organized.get("skipped_duplicate"):
        final = "skipped"
    elif organized["organized"] or organized.get("expanded"):
        final = "organized"
    else:
        final = "review"
    updated = db.update_job(
        job_id,
        status=final,
        work_id=work["id"] if work else None,
        title=str(identity.get("title") or job.get("title") or _title_for_path(folder)),
        kind=str(identity.get("kind") or job.get("kind") or "") or None,
        error=None,
    )
    return updated or job


def watch_entry_skippable(path: Path) -> bool:
    if skipped_name(path.name):
        return True
    if path.is_dir():
        try:
            next(path.iterdir())
        except StopIteration:
            return True
        except OSError:
            return True
    inspection = inspect_complete_folder(path)
    problem = inspection.get("problem")
    if problem == UNPACK_STUCK:
        return True
    if problem and not inspection.get("payload") and not list_payload_files(path):
        return True
    return False


def poll_watch_folder(db: Database, settings: Settings) -> int:
    if not getattr(settings, "watch_enabled", False):
        return 0
    raw = str(settings.watch_root or "").strip()
    if not raw:
        return 0
    try:
        root = confined_path(raw, must_exist=True)
    except PathDenied:
        logger.info("Watch folder skipped: path is not readable under /data")
        return 0
    if not root.is_dir():
        return 0
    if watch_root_forbidden(root, settings):
        logger.warning("Watch folder ignored: overlaps a library root")
        return 0
    created = 0
    try:
        children = sorted(root.iterdir(), key=lambda child: child.name.lower())
    except OSError as error:
        logger.info("Watch folder listing failed: %s", error)
        return 0
    for child in children:
        if watch_entry_skippable(child):
            continue
        try:
            target = confined_path(str(child), must_exist=True)
        except PathDenied:
            continue
        stored = _norm_key(expand_album_context(target))
        if db.get_job_by_storage_path(stored) is not None:
            continue
        enqueue_ingest(
            db,
            settings,
            path=target,
            requested_by="watch",
            source="watch",
            process=True,
        )
        created += 1
    return created
