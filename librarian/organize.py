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
from librarian.identify import REVIEW_COLLISION, dest_layout, identify_completed
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
) -> Dict[str, Any]:
    llm = llm_client if llm_client is not None else client_from_settings(settings)
    preview = identify_completed(folder, indexer_item=indexer_item, category=category, llm_client=llm)
    kind = str(preview["identity"].get("kind") or "")
    convert_kwargs = {"runner": convert_runner} if convert_runner is not None else {}
    converted = maybe_convert_payload(folder, kind, **convert_kwargs)
    result = (
        identify_completed(folder, indexer_item=indexer_item, category=category, llm_client=llm)
        if converted["converted"]
        else preview
    )
    identity = dict(result["identity"])
    files = [Path(path) for path in result["files"]]
    if not result["auto_organize"] or not apply:
        work = db.upsert_work(
            {
                **identity,
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
    merged = {
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
        "title": merged["title"],
        "author": merged.get("author"),
        "isbn": merged.get("isbn"),
        "category": None,
        "guid": work.get("indexer_guid"),
        "name": folder.name,
    }
    result = identify_completed(folder, indexer_item=fake_item)
    result["identity"].update(merged)
    result["auto_organize"] = True
    return organize_identified(
        db,
        settings,
        folder=folder,
        indexer_item=fake_item,
        apply=True,
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
