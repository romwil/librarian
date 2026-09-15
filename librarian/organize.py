"""Organize identified payloads into per-kind library layouts."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from librarian.config import Settings
from librarian.convert import maybe_convert_payload
from librarian.covers import fetch_cover
from librarian.db import Database
from librarian.identify import (
    REVIEW_COLLISION,
    REVIEW_NO_PAYLOAD,
    dest_layout,
    identify_completed,
    resolve_storage_path,
    usable_folder,
)
from librarian.kinds import KIND_BOOK, KIND_COMIC, KIND_MAGAZINE, KIND_MUSIC
from librarian.llm import client_from_settings
from librarian.metadata import comicinfo_xml, write_comicinfo, write_opf


def _copy_into(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.resolve() != src.resolve():
        raise FileExistsError(str(dest))
    if dest.resolve() != src.resolve():
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
    "No payload files at this path. Librarian cannot invent an EPUB/CBZ. "
    "Point the folder at a complete directory this process can read, "
    "set SAB complete root to map /downloads, or Skip."
)
MISSING_FOLDER_APPLY_ERROR = (
    "No complete folder. Enter the SAB storage path this Librarian can read, "
    "set SAB complete root, or Skip."
)


def _source_folder_value(folder: Path) -> Optional[str]:
    return str(folder) if usable_folder(folder) else None


def _merge_identity(identity: Dict[str, Any], overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(identity)
    for key, value in (overrides or {}).items():
        if value is not None:
            merged[key] = value
    return merged


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
) -> Dict[str, Any]:
    llm = llm_client if llm_client is not None else client_from_settings(settings)
    preview = identify_completed(folder, indexer_item=indexer_item, category=category, llm_client=llm)
    kind = str((identity_overrides or {}).get("kind") or preview["identity"].get("kind") or "")
    convert_kwargs = {"runner": convert_runner} if convert_runner is not None else {}
    converted = maybe_convert_payload(folder, kind, **convert_kwargs)
    result = (
        identify_completed(folder, indexer_item=indexer_item, category=category, llm_client=llm)
        if converted["converted"]
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
            identity["review_reason"] = REVIEW_NO_PAYLOAD
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
                "music_state": "incoming" if identity.get("kind") == KIND_MUSIC else None,
                "indexer_guid": (indexer_item or {}).get("guid"),
            }
        )
        return {"work": work, "identity": identity, "organized": False, "files": [str(p) for p in files]}

    placed: List[str] = []
    folder_path = None
    try:
        for src in files:
            dest = dest_layout(identity, settings, filename=src.name)
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
            written = _copy_into(src, dest)
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

    work = db.upsert_work(
        {
            **identity,
            "folder_path": str(folder_path),
            "cover_path": str(cover) if cover else None,
            "review_state": "none",
            "review_reason": None,
            "music_state": "incoming" if identity["kind"] == KIND_MUSIC else None,
            "indexer_guid": guid or None,
        }
    )
    for path in placed:
        db.add_file(
            {
                "work_id": work["id"],
                "path": path,
                "filename": Path(path).name,
                "kind": identity["kind"],
                "size": Path(path).stat().st_size if Path(path).exists() else 0,
            }
        )
    return {"work": work, "identity": identity, "organized": True, "files": placed, "cover": str(cover) if cover else None}


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
        if reason == REVIEW_NO_PAYLOAD:
            raise ValueError(NO_PAYLOAD_APPLY_ERROR)
        if reason == REVIEW_COLLISION:
            raise ValueError("A file already exists at the library destination.")
    return result


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
    cover = dest / "cover.jpg"
    updated = db.upsert_work(
        {
            **work,
            "folder_path": str(dest),
            "cover_path": str(cover) if cover.is_file() else work.get("cover_path"),
            "music_state": "promoted",
            "review_state": "none",
        }
    )
    return updated
