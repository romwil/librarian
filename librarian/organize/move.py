"""Placing files on the shelf: copy/move into the layout, ComicInfo injection, source cleanup."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from librarian.config import Settings
from librarian.covers import ensure_music_cover
from librarian.db import Database
from librarian.identify import list_payload_files, usable_folder
from librarian.kinds import KIND_MUSIC
from librarian.metadata import apply_audio_tags_in_folder, comicinfo_xml


def _copy_into(src: Path, dest: Path, *, move: bool = False) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.resolve() != src.resolve():
        raise FileExistsError(str(dest))
    if dest.resolve() != src.resolve():
        if move:
            shutil.move(str(src), str(dest))
        else:
            shutil.copy2(src, dest)
    return dest


def _inject_comicinfo(cbz: Path, identity: Dict[str, Any], guid: str) -> None:
    if cbz.suffix.lower() != ".cbz" or not cbz.is_file():
        return
    from librarian.convert import clean_cbz

    # Prefer a full clean remux (junk strip + embedded ComicInfo). Fall back to append.
    cleaned = clean_cbz(cbz, identity=identity, guid=guid)
    if cleaned is not None:
        return
    xml = comicinfo_xml(identity, guid=guid)
    try:
        with zipfile.ZipFile(cbz, "a") as archive:
            names = {name.lower() for name in archive.namelist()}
            if "comicinfo.xml" in names:
                return
            archive.writestr("ComicInfo.xml", xml)
    except zipfile.BadZipFile:
        return


def _source_folder_value(folder: Path) -> Optional[str]:
    return str(folder) if usable_folder(folder) else None


def _cleanup_moved_source(source: Path, placed: List[str]) -> None:
    """Remove an ingest/watch/SAB source after a confident move. Leave it on Review/collision."""
    if not source.exists():
        return
    try:
        source_key = str(source.resolve())
    except OSError:
        source_key = str(source)
    placed_keys = set()
    for path in placed:
        try:
            placed_keys.add(str(Path(path).resolve()))
        except OSError:
            placed_keys.add(str(path))
    prefix = source_key.rstrip("/") + "/"
    # If the library dest is still under the source tree, leave staging alone.
    if any(key == source_key or key.startswith(prefix) for key in placed_keys):
        return
    if source.is_file():
        if source_key not in placed_keys:
            source.unlink(missing_ok=True)
        return
    if not source.is_dir():
        return
    # Payload still here means identify did not absorb everything — keep the dump.
    if list_payload_files(source):
        return
    shutil.rmtree(source, ignore_errors=True)


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return str(left) == str(right)


def promote_music(db: Database, settings: Settings, work_id: str) -> Dict[str, Any]:
    work = db.get_work(work_id)
    if work is None:
        raise ValueError("Work not found")
    if work.get("kind") != KIND_MUSIC:
        raise ValueError("Only incoming music can be promoted")
    folder = Path(work.get("folder_path") or "")
    if not folder.is_dir():
        raise ValueError("Work has no incoming folder")
    incoming = Path(settings.incoming_music_root)
    dest_root = Path(settings.music_root)
    try:
        relative = folder.relative_to(incoming)
    except ValueError as error:
        raise ValueError("Work is not under incoming_music_root") from error
    dest = dest_root / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise ValueError("Promote collision")
    shutil.move(str(folder), str(dest))
    db.relocate_work_files(work_id, str(folder), str(dest))
    music_cover = ensure_music_cover(
        dest,
        mbid=str(work.get("mbid") or ""),
    )
    cover = dest / "cover.jpg"
    old_cover = str(work.get("cover_path") or "")
    if old_cover.startswith(str(folder)):
        old_cover = str(dest / Path(old_cover).relative_to(folder))
    if getattr(settings, "music_write_tags", False):
        apply_audio_tags_in_folder(dest, work)
    updated = db.upsert_work(
        {
            **work,
            "folder_path": str(dest),
            "cover_path": str(music_cover)
            if music_cover is not None
            else (str(cover) if cover.is_file() else old_cover or work.get("cover_path")),
            "music_state": "promoted",
            "review_state": "none",
        }
    )
    return updated

