"""Scan Settings library roots into works + files. Never moves files."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from librarian.config import Settings
from librarian.db import Database
from librarian.identify import (
    REVIEW_COLLISION,
    REVIEW_UNKNOWN,
    extract_isbn,
    list_payload_files,
    parse_usenet_name,
    tidy_title,
)
from librarian.kinds import KIND_AUDIOBOOK, KIND_BOOK, KIND_COMIC, KIND_MAGAZINE, KIND_MUSIC
from librarian.metadata import (
    read_cbz_comicinfo,
    read_epub_opf,
    read_folder_metadata,
    sidecar_named,
)

SCAN_ROOTS: Tuple[Tuple[str, str, Optional[str]], ...] = (
    ("books_root", KIND_BOOK, None),
    ("magazines_root", KIND_MAGAZINE, None),
    ("comics_root", KIND_COMIC, None),
    ("audiobooks_root", KIND_AUDIOBOOK, None),
    ("incoming_music_root", KIND_MUSIC, "incoming"),
    ("music_root", KIND_MUSIC, "promoted"),
)

COVER_NAMES = ("cover.jpg", "cover.jpeg", "cover.png")


def scan_library(db: Database, settings: Settings) -> Dict[str, int]:
    """Walk configured roots and upsert catalog rows. Idempotent; collisions → Review."""
    counts = {"scanned": 0, "created": 0, "updated": 0, "review": 0}
    claimed = _existing_roots(settings)
    seen_files: set[str] = set()
    for field, kind, music_state in SCAN_ROOTS:
        root = Path(str(getattr(settings, field) or "").strip())
        if not root.is_dir():
            continue
        skip_under = [
            other
            for other in claimed
            if other != root.resolve() and _is_under(other, root.resolve())
        ]
        for folder, files in _group_work_folders(root, skip_under, seen_files):
            counts["scanned"] += 1
            outcome = _ingest_folder(
                db,
                kind=kind,
                music_state=music_state,
                folder=folder,
                files=files,
                root=root,
            )
            counts[outcome["action"]] += 1
            if outcome["review"]:
                counts["review"] += 1
    return counts


def _existing_roots(settings: Settings) -> List[Path]:
    roots: List[Path] = []
    for field, _kind, _state in SCAN_ROOTS:
        path = Path(str(getattr(settings, field) or "").strip())
        if path.is_dir():
            roots.append(path.resolve())
    return roots


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent)
        return child.resolve() != parent
    except ValueError:
        return False


def _group_work_folders(
    root: Path,
    skip_under: Sequence[Path],
    seen_files: set[str],
) -> List[Tuple[Path, List[Path]]]:
    groups: Dict[Path, List[Path]] = {}
    for path in list_payload_files(root):
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        key = str(resolved)
        if key in seen_files:
            continue
        if any(_is_under(resolved, other) or resolved == other for other in skip_under):
            continue
        seen_files.add(key)
        groups.setdefault(path.parent, []).append(path)
    return sorted(groups.items(), key=lambda item: str(item[0]))


def _ingest_folder(
    db: Database,
    *,
    kind: str,
    music_state: Optional[str],
    folder: Path,
    files: Sequence[Path],
    root: Path,
) -> Dict[str, Any]:
    identity = identity_from_library_folder(kind, folder, files, root=root)
    if music_state:
        identity["music_state"] = music_state
    folder_path = str(folder)
    existing, collision = _match_existing(db, identity, folder_path=folder_path, files=files)
    review_reason = identity.get("review_reason")
    if collision:
        review_reason = REVIEW_COLLISION
    if not str(identity.get("title") or "").strip():
        review_reason = review_reason or REVIEW_UNKNOWN
        identity["title"] = tidy_title(folder.name) or "Untitled"
    identity["review_reason"] = review_reason
    identity["review_state"] = "needs_review" if review_reason else "none"
    identity["folder_path"] = folder_path
    identity["kind"] = kind
    cover = _existing_cover(folder)
    if cover:
        identity["cover_path"] = cover
    elif existing and existing.get("cover_path"):
        identity["cover_path"] = existing.get("cover_path")

    payload = _merge_work(existing, identity)
    work = db.upsert_work(payload)
    created = existing is None
    for path in files:
        claimed = db.get_file_by_path(str(path))
        if claimed and claimed.get("work_id") not in (None, work["id"]):
            continue
        db.upsert_file(
            {
                "work_id": work["id"],
                "path": str(path),
                "filename": path.name,
                "kind": kind,
                "size": path.stat().st_size if path.is_file() else 0,
            }
        )
    return {
        "action": "created" if created else "updated",
        "review": work.get("review_state") == "needs_review",
        "work": work,
    }


def _merge_work(existing: Optional[Dict[str, Any]], identity: Dict[str, Any]) -> Dict[str, Any]:
    if existing is None:
        return identity
    merged = dict(existing)
    for key, value in identity.items():
        if value in (None, ""):
            continue
        merged[key] = value
    merged["id"] = existing["id"]
    merged["review_state"] = identity.get("review_state") or "none"
    merged["review_reason"] = identity.get("review_reason")
    if identity.get("music_state"):
        merged["music_state"] = identity["music_state"]
    return merged


def _match_existing(
    db: Database,
    identity: Dict[str, Any],
    *,
    folder_path: str,
    files: Sequence[Path],
) -> Tuple[Optional[Dict[str, Any]], bool]:
    by_folder = db.get_work_by_folder_path(folder_path)
    by_file = None
    for path in files:
        row = db.get_file_by_path(str(path))
        if row and row.get("work_id"):
            by_file = db.get_work(str(row["work_id"]))
            if by_file:
                break

    existing: Optional[Dict[str, Any]] = by_folder
    collision = False
    folder_key = folder_path.rstrip("/")
    if existing is None and by_file:
        other = str(by_file.get("folder_path") or "").rstrip("/")
        if other and other != folder_key:
            collision = True
        else:
            existing = by_file
    if existing is None:
        hit = _identity_match(db, identity)
        if hit:
            other = str(hit.get("folder_path") or "").rstrip("/")
            if other and other != folder_key:
                collision = True
            else:
                existing = hit

    conflict = db.find_work_conflict(
        kind=str(identity.get("kind") or ""),
        folder_path=folder_path,
        isbn=str(identity.get("isbn") or ""),
        series_name=str(identity.get("series_name") or ""),
        series_index=str(identity.get("series_index") or ""),
        title=str(identity.get("title") or ""),
        author=str(identity.get("author") or ""),
        music_state=identity.get("music_state"),
        exclude_id=None if existing is None else str(existing["id"]),
    )
    if existing is None:
        collision = collision or bool(conflict)
    elif conflict and str(existing.get("review_reason") or "") == REVIEW_COLLISION:
        collision = True
    return existing, collision


def _identity_match(db: Database, identity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    kind = str(identity.get("kind") or "")
    isbn = extract_isbn(str(identity.get("isbn") or ""))
    if kind == KIND_BOOK and isbn:
        hit = db.get_work_by_isbn(isbn)
        if hit:
            return hit
    if kind in (KIND_COMIC, KIND_MAGAZINE):
        hit = db.get_work_by_series_issue(
            kind=kind,
            series_name=str(identity.get("series_name") or ""),
            series_index=str(identity.get("series_index") or ""),
        )
        if hit:
            return hit
    title = str(identity.get("title") or "").strip()
    if not title:
        return None
    return db.get_work_by_kind_title(
        kind=kind,
        title=title,
        author=str(identity.get("author") or ""),
        music_state=identity.get("music_state"),
    )


def identity_from_library_folder(
    kind: str,
    folder: Path,
    files: Sequence[Path],
    *,
    root: Path,
) -> Dict[str, Any]:
    """Identity from layout + OPF/ComicInfo/tags. Does not treat the folder as a SAB dump."""
    layout = _layout_identity(kind, folder, root)
    sidecar = read_folder_metadata(folder)
    embedded = _embedded_identity(kind, files)
    tags = _tag_identity(kind, files)
    parsed = _filename_identity(kind, folder, files)
    identity: Dict[str, Any] = {"kind": kind, "title": "", "author": "", "source": "scan"}
    for layer in (parsed, layout, tags, embedded, sidecar):
        for key, value in layer.items():
            if value in (None, ""):
                continue
            identity[key] = value
    if kind in (KIND_COMIC, KIND_MAGAZINE) and identity.get("series_name") and not identity.get("title"):
        index = identity.get("series_index") or ""
        identity["title"] = f"{identity['series_name']} #{index}".strip(" #")
    if kind == KIND_MUSIC and identity.get("series_name") and not identity.get("title"):
        identity["title"] = str(identity["series_name"])
    identity["isbn"] = extract_isbn(str(identity.get("isbn") or ""))
    identity["confidence"] = "high" if identity.get("title") else "low"
    identity["rationale"] = "library scan"
    return identity


def _layout_identity(kind: str, folder: Path, root: Path) -> Dict[str, Any]:
    try:
        relative = folder.resolve().relative_to(root.resolve())
    except ValueError:
        relative = Path(folder.name)
    parts = [tidy_title(part) for part in relative.parts if part not in (".", "")]
    if not parts:
        return {}
    if kind in (KIND_BOOK, KIND_AUDIOBOOK):
        if len(parts) >= 2:
            return {"author": parts[-2], "title": parts[-1]}
        return {"title": parts[-1]}
    if kind in (KIND_COMIC, KIND_MAGAZINE):
        if len(parts) >= 2:
            series, index = parts[-2], parts[-1]
            title = f"{series} #{index}" if kind == KIND_COMIC else f"{series} {index}"
            return {"series_name": series, "series_index": index, "title": title, "author": series}
        return {"title": parts[-1], "series_name": parts[-1]}
    if kind == KIND_MUSIC:
        if len(parts) >= 2:
            return {
                "author": parts[-2],
                "title": parts[-1],
                "series_name": parts[-1],
            }
        return {"title": parts[-1], "series_name": parts[-1]}
    return {"title": parts[-1]}


def _embedded_identity(kind: str, files: Sequence[Path]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for path in files:
        suffix = path.suffix.lower()
        if kind in (KIND_BOOK, KIND_MAGAZINE) and suffix == ".epub":
            merged.update(read_epub_opf(path))
        if kind in (KIND_BOOK, KIND_MAGAZINE) and suffix == ".pdf":
            from librarian.metadata import read_pdf_info

            merged.update(read_pdf_info(path))
        if kind in (KIND_COMIC, KIND_MAGAZINE) and suffix == ".cbz":
            merged.update(read_cbz_comicinfo(path))
    return merged


def _tag_identity(kind: str, files: Sequence[Path]) -> Dict[str, Any]:
    if kind not in (KIND_MUSIC, KIND_AUDIOBOOK):
        return {}
    from librarian.metadata import read_audio_tags

    merged: Dict[str, Any] = {}
    for path in files:
        if path.suffix.lower() not in {".flac", ".mp3", ".m4a", ".m4b", ".ogg", ".opus", ".mp4"}:
            continue
        tags = read_audio_tags(path)
        for key, value in tags.items():
            if value in (None, "") or merged.get(key) not in (None, ""):
                continue
            merged[key] = value
        if merged.get("title") or merged.get("album"):
            break
    if kind == KIND_MUSIC and merged.get("album") and not merged.get("title"):
        merged["title"] = merged["album"]
    return merged


def _filename_identity(kind: str, folder: Path, files: Sequence[Path]) -> Dict[str, Any]:
    name = files[0].stem if files else folder.name
    parsed = parse_usenet_name(name)
    out: Dict[str, Any] = {}
    if parsed.title:
        out["title"] = parsed.title
    if parsed.author:
        out["author"] = parsed.author
    if parsed.series_name:
        out["series_name"] = parsed.series_name
    if parsed.series_index:
        out["series_index"] = parsed.series_index
    if parsed.year:
        out["year"] = parsed.year
    if parsed.isbn:
        out["isbn"] = parsed.isbn
    if kind in (KIND_COMIC, KIND_MAGAZINE) and not out.get("series_name"):
        out["series_name"] = tidy_title(folder.parent.name if folder.parent != folder else folder.name)
    return out


def _existing_cover(folder: Path) -> Optional[str]:
    found = sidecar_named(folder, *COVER_NAMES)
    if found is not None and found.is_file():
        return str(found)
    return None
