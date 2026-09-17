"""Organize identified payloads into per-kind library layouts."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from librarian.config import Settings
from librarian.convert import maybe_convert_payload, maybe_par2_repair, maybe_unpack_archives
from librarian.covers import ensure_music_cover, fetch_cover
from librarian.db import Database
from librarian.identify import (
    REVIEW_COLLISION,
    REVIEW_MISSING_FOLDER,
    REVIEW_NO_PAYLOAD,
    REVIEW_UNPACK_STUCK,
    dest_layout,
    diagnose_review_folder,
    identify_completed,
    inspect_complete_folder,
    list_payload_files,
    music_state_for_folder,
    resolve_storage_path,
    usable_folder,
)
from librarian.kinds import KIND_BOOK, KIND_COMIC, KIND_MAGAZINE, KIND_MUSIC
from librarian.llm import client_from_settings
from librarian.metadata import apply_audio_tags_in_folder, comicinfo_xml, write_comicinfo, write_opf


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
    xml = comicinfo_xml(identity, guid=guid)
    try:
        with zipfile.ZipFile(cbz, "a") as archive:
            names = {name.lower() for name in archive.namelist()}
            if "comicinfo.xml" in names:
                return
            archive.writestr("ComicInfo.xml", xml)
    except zipfile.BadZipFile:
        return


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
    "Apply will not overwrite. Change title, author, series, or folder so the "
    "destination path is free, or Skip to keep what is on the shelf."
)


def shelf_work_for_collision(db: Database, work: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Catalog row already on the shelf for the same identity (different folder)."""
    if str(work.get("review_reason") or "") != REVIEW_COLLISION:
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


def _source_folder_value(folder: Path) -> Optional[str]:
    return str(folder) if usable_folder(folder) else None


def _merge_identity(identity: Dict[str, Any], overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(identity)
    for key, value in (overrides or {}).items():
        if value is not None:
            merged[key] = value
    return merged


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


def review_slip_actions(work: Dict[str, Any], diagnosis: Dict[str, Any]) -> Dict[str, Any]:
    """Flags for Review CTAs: Repair / Retry / Request new version."""
    problem = str(diagnosis.get("problem") or work.get("review_reason") or "")
    par2_count = int(diagnosis.get("par2_count") or 0)
    folder_hint = str(
        diagnosis.get("resolved_path") or diagnosis.get("path") or work.get("folder_path") or ""
    )
    can_retry = problem != REVIEW_MISSING_FOLDER and usable_folder(folder_hint)
    return {
        "can_repair": problem == REVIEW_UNPACK_STUCK and par2_count > 0,
        "can_retry": can_retry,
        "find_query": review_find_query(work),
    }


def organize_identified(
    db: Database,
    settings: Settings,
    *,
    folder: Path,
    indexer_item: Optional[Dict[str, Any]] = None,
    category: object = None,
    apply: bool = True,
    llm_client: Any = None,
    cover_transport=None,
    convert_runner=None,
    identity_overrides: Optional[Dict[str, Any]] = None,
    force: bool = False,
    move_source: bool = False,
    catalog_lookup: Any = None,
    catalog_transport: Any = None,
) -> Dict[str, Any]:
    llm = llm_client if llm_client is not None else client_from_settings(settings)
    identify_kwargs = {
        "indexer_item": indexer_item,
        "category": category,
        "llm_client": llm,
        "settings": settings,
        "catalog_lookup": catalog_lookup,
        "catalog_transport": catalog_transport,
    }
    convert_kwargs = {"runner": convert_runner} if convert_runner is not None else {}
    # SAB often leaves damaged rar/7z; when stuck, par2 then unar before identify.
    if inspect_complete_folder(folder).get("problem") == REVIEW_UNPACK_STUCK:
        maybe_par2_repair(folder, **convert_kwargs)
    unpacked = maybe_unpack_archives(folder, **convert_kwargs)
    preview = identify_completed(folder, **identify_kwargs)
    kind = str((identity_overrides or {}).get("kind") or preview["identity"].get("kind") or "")
    converted = maybe_convert_payload(folder, kind, **convert_kwargs)
    result = (
        identify_completed(folder, **identify_kwargs)
        if converted["converted"] or unpacked["unpacked"]
        else preview
    )
    identity = _merge_identity(dict(result["identity"]), identity_overrides)
    files = [Path(path) for path in result["files"]]
    if force:
        if files:
            identity["confidence"] = "high"
            identity["review_reason"] = None
            result["auto_organize"] = True
        else:
            stuck = inspect_complete_folder(folder).get("problem")
            identity["review_reason"] = (
                REVIEW_UNPACK_STUCK if stuck == REVIEW_UNPACK_STUCK else REVIEW_NO_PAYLOAD
            )
            identity["confidence"] = "low"
            result["auto_organize"] = False
    result["identity"] = identity
    source_folder = _source_folder_value(folder)
    if not result["auto_organize"] or not apply:
        work = db.upsert_work(
            {
                **identity,
                "folder_path": source_folder,
                "review_state": "needs_review" if identity.get("review_reason") or not result["auto_organize"] else "none",
                "review_reason": identity.get("review_reason"),
                "music_state": (
                    music_state_for_folder(settings, Path(source_folder))
                    if identity.get("kind") == KIND_MUSIC and source_folder
                    else ("incoming" if identity.get("kind") == KIND_MUSIC else None)
                ),
                "indexer_guid": (indexer_item or {}).get("guid"),
            }
        )
        return {"work": work, "identity": identity, "organized": False, "files": [str(p) for p in files]}

    placed: List[str] = []
    folder_path = None
    try:
        for src in files:
            dest = dest_layout(identity, settings, filename=src.name, source=src)
            if dest.exists() and dest.resolve() != src.resolve():
                identity["review_reason"] = REVIEW_COLLISION
                identity["confidence"] = "low"
                work = db.upsert_work(
                    {
                        **identity,
                        "folder_path": source_folder,
                        "review_state": "needs_review",
                        "review_reason": REVIEW_COLLISION,
                        "indexer_guid": (indexer_item or {}).get("guid"),
                    }
                )
                return {"work": work, "identity": identity, "organized": False, "files": [str(p) for p in files]}
            written = _copy_into(src, dest, move=move_source)
            placed.append(str(written))
            folder_path = written.parent
    except FileExistsError:
        identity["review_reason"] = REVIEW_COLLISION
        work = db.upsert_work(
            {
                **identity,
                "folder_path": source_folder,
                "review_state": "needs_review",
                "review_reason": REVIEW_COLLISION,
                "indexer_guid": (indexer_item or {}).get("guid"),
            }
        )
        return {"work": work, "identity": identity, "organized": False, "files": [str(p) for p in files]}

    assert folder_path is not None
    guid = str((indexer_item or {}).get("guid") or "")
    existing = db.get_work_by_folder_path(str(folder_path))
    if existing:
        identity["id"] = existing["id"]
    if identity["kind"] in (KIND_BOOK, KIND_MAGAZINE):
        write_opf(folder_path, identity, guid=guid)
    if identity["kind"] == KIND_COMIC:
        write_comicinfo(folder_path, identity, guid=guid)
        write_opf(folder_path, identity, guid=guid)
        for path in placed:
            _inject_comicinfo(Path(path), identity, guid)

    cover_url = str((indexer_item or {}).get("cover") or "")
    cover = fetch_cover(
        Path(folder_path),
        identity,
        indexer_cover_url=cover_url,
        transport=cover_transport,
    )
    if identity["kind"] == KIND_MUSIC:
        music_cover = ensure_music_cover(
            Path(folder_path),
            mbid=str(identity.get("mbid") or ""),
            transport=cover_transport,
        )
        if music_cover is not None:
            cover = music_cover
        if getattr(settings, "music_write_tags", False):
            apply_audio_tags_in_folder(
                Path(folder_path),
                identity,
                paths=[Path(path) for path in placed],
            )

    work = db.upsert_work(
        {
            **identity,
            "folder_path": str(folder_path),
            "cover_path": str(cover) if cover else None,
            "review_state": "none",
            "review_reason": None,
            "music_state": (
                existing.get("music_state")
                if existing and existing.get("music_state")
                else music_state_for_folder(settings, Path(folder_path))
            )
            if identity["kind"] == KIND_MUSIC
            else None,
            "indexer_guid": guid or None,
        }
    )
    for path in placed:
        db.upsert_file(
            {
                "work_id": work["id"],
                "path": path,
                "filename": Path(path).name,
                "kind": identity["kind"],
                "size": Path(path).stat().st_size if Path(path).exists() else 0,
            }
        )
    if move_source:
        _cleanup_moved_source(folder, placed)
    return {"work": work, "identity": identity, "organized": True, "files": placed, "cover": str(cover) if cover else None}


def _cleanup_moved_source(source: Path, placed: List[str]) -> None:
    """Remove an ingest/watch source after a confident move. Leave it on collision."""
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
    if any(key == source_key or key.startswith(prefix) for key in placed_keys):
        return
    if source.is_file():
        if source_key not in placed_keys:
            source.unlink(missing_ok=True)
        return
    if source.is_dir() and not list_payload_files(source):
        shutil.rmtree(source, ignore_errors=True)


def apply_review(
    db: Database,
    settings: Settings,
    *,
    work_id: str,
    folder: Path,
    identity_overrides: Dict[str, Any],
) -> Dict[str, Any]:
    work = db.get_work(work_id)
    if work is None:
        raise ValueError("Work not found")
    source = folder if usable_folder(folder) else Path(str(work.get("folder_path") or ""))
    if not usable_folder(source):
        raise ValueError(MISSING_FOLDER_APPLY_ERROR)
    resolved = resolve_storage_path(source, settings.complete_root)
    merged = {
        "id": work["id"],
        "title": work.get("title"),
        "author": work.get("author"),
        "kind": work.get("kind"),
        "series_name": work.get("series_name"),
        "series_index": work.get("series_index"),
        "year": work.get("year"),
        "isbn": work.get("isbn"),
        **identity_overrides,
        "confidence": "high",
        "review_reason": None,
    }
    fake_item = {
        "title": merged.get("title"),
        "author": merged.get("author"),
        "isbn": merged.get("isbn"),
        "category": None,
        "guid": work.get("indexer_guid"),
        "name": resolved.name,
    }
    result = organize_identified(
        db,
        settings,
        folder=resolved,
        indexer_item=fake_item,
        apply=True,
        identity_overrides=merged,
        force=True,
    )
    if not result["organized"]:
        reason = result.get("identity", {}).get("review_reason") or result["work"].get("review_reason")
        if reason == REVIEW_UNPACK_STUCK:
            raise ValueError(UNPACK_STUCK_APPLY_ERROR)
        if reason == REVIEW_NO_PAYLOAD:
            raise ValueError(NO_PAYLOAD_APPLY_ERROR)
        if reason == REVIEW_COLLISION:
            raise ValueError(COLLISION_APPLY_ERROR)
    return result


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
    convert_kwargs = {"runner": convert_runner} if convert_runner is not None else {}
    repaired = maybe_par2_repair(resolved, **convert_kwargs)
    unpacked = maybe_unpack_archives(resolved, **convert_kwargs)
    diagnosis = diagnose_review_folder(resolved, settings.complete_root)
    problem = diagnosis.get("problem")
    updated = work
    if problem:
        if str(work.get("review_reason") or "") != problem:
            updated = db.upsert_work({**work, "review_reason": problem, "folder_path": str(resolved)})
    elif str(work.get("review_reason") or "") == REVIEW_UNPACK_STUCK:
        updated = db.upsert_work(
            {**work, "review_reason": "unknown_identity", "folder_path": str(resolved)}
        )
    actions = review_slip_actions(updated, diagnosis)
    return {
        "work": updated,
        "repaired": repaired,
        "unpacked": unpacked,
        "folder_diagnosis": diagnosis,
        "actions": actions,
    }


def retry_review(
    db: Database,
    settings: Settings,
    *,
    work_id: str,
    identity_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Force re-organize / apply using the parked work identity."""
    work = db.get_work(work_id)
    if work is None:
        raise ValueError("Work not found")
    folder = Path(str(work.get("folder_path") or ""))
    return apply_review(
        db,
        settings,
        work_id=work_id,
        folder=folder,
        identity_overrides=dict(identity_overrides or {}),
    )


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
