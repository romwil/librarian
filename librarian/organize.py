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
from librarian.delight import REVIEW_QUIET_HOURS, in_quiet_hours
from librarian.identify import (
    REVIEW_COLLISION,
    REVIEW_CONVERT,
    REVIEW_EXTRA,
    REVIEW_LOW,
    REVIEW_MISSING_FOLDER,
    REVIEW_NO_PAYLOAD,
    REVIEW_UNKNOWN,
    REVIEW_UNPACK_STUCK,
    Identity,
    dest_layout,
    diagnose_review_folder,
    identify_completed,
    inspect_complete_folder,
    list_payload_files,
    looks_like_dump_title,
    music_state_for_folder,
    resolve_storage_path,
    usable_folder,
)
from librarian.kinds import KIND_AUDIOBOOK, KIND_BOOK, KIND_COMIC, KIND_MAGAZINE, KIND_MUSIC
from librarian.llm import (
    LLM_FAIL_COPY,
    LLM_UNSET_COPY,
    LLMError,
    client_from_settings,
    merge_llm_identity,
    suggestion_fields,
)
from librarian.metadata import apply_audio_tags_in_folder, comicinfo_xml, write_comicinfo, write_opf
from librarian.parts import infer_part_fields, merge_part_fields_for_work, part_for_filename


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


def _part_fields_for_organize(
    *,
    identity: Dict[str, Any],
    indexer_item: Optional[Dict[str, Any]],
    filenames: List[str],
    existing: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist multipart total/style/base from NZB title and/or payload filenames."""
    base_work = {**(existing or {}), **identity}
    return merge_part_fields_for_work(
        work=base_work,
        indexer_item=indexer_item,
        filenames=filenames,
    )


def _file_part_index(
    *,
    filename: str,
    indexer_item: Optional[Dict[str, Any]],
    filenames: List[str],
) -> Optional[int]:
    titles = []
    if indexer_item:
        titles.extend([indexer_item.get("title"), indexer_item.get("name")])
    inferred = infer_part_fields(titles=titles, filenames=filenames)
    parts = inferred.get("file_parts") or {}
    found = part_for_filename(filename, parts)
    if found is not None:
        return found
    # dest_layout renames .m4b → {Title}.m4b, which drops "Part N" from the name.
    for title in titles:
        key = str(title or "")
        if key and key in parts:
            return parts[key]
    values = [int(v) for v in parts.values() if v is not None]
    if len(set(values)) == 1:
        return values[0]
    return None


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


# Retry / Repair only help when unpack, quiet-hours, or convert can progress.
_RETRYABLE_REVIEW_REASONS = frozenset(
    {
        REVIEW_UNPACK_STUCK,
        REVIEW_QUIET_HOURS,
        REVIEW_CONVERT,
        REVIEW_NO_PAYLOAD,
    }
)


def review_slip_actions(
    work: Dict[str, Any],
    diagnosis: Dict[str, Any],
    *,
    llm_configured: bool = False,
) -> Dict[str, Any]:
    """Flags for Review CTAs: Repair / Retry / Request new version / re-grab / LLM suggest."""
    problem = str(diagnosis.get("problem") or work.get("review_reason") or "")
    par2_count = int(diagnosis.get("par2_count") or 0)
    folder_hint = str(
        diagnosis.get("resolved_path") or diagnosis.get("path") or work.get("folder_path") or ""
    )
    reason = str(work.get("review_reason") or problem or "")
    retry_reason = problem if problem in _RETRYABLE_REVIEW_REASONS else reason
    can_retry = retry_reason in _RETRYABLE_REVIEW_REASONS and usable_folder(folder_hint)
    fails = int(work.get("repair_fail_count") or 0)
    title = str(work.get("title") or "")
    author = str(work.get("author") or "").strip()
    dumpish = looks_like_dump_title(title) or (not author and reason in {REVIEW_UNKNOWN, REVIEW_LOW, ""})
    identity_weak = reason in {REVIEW_UNKNOWN, REVIEW_LOW, "unexpected_kind"} or dumpish
    return {
        "can_repair": problem == REVIEW_UNPACK_STUCK and par2_count > 0,
        "can_retry": can_retry,
        "find_query": review_find_query(work),
        "quiet_hours": problem == REVIEW_QUIET_HOURS,
        "can_regrab": fails >= 2 and problem == REVIEW_UNPACK_STUCK,
        "repair_fail_count": fails,
        "llm_configured": bool(llm_configured),
        "can_suggest_llm": bool(llm_configured) and identity_weak and problem not in {
            REVIEW_MISSING_FOLDER,
            REVIEW_NO_PAYLOAD,
            REVIEW_UNPACK_STUCK,
        },
        "needs_llm_suggest": bool(llm_configured) and dumpish and problem not in {
            REVIEW_MISSING_FOLDER,
            REVIEW_NO_PAYLOAD,
            REVIEW_UNPACK_STUCK,
        },
    }


def suggest_review_identity(
    db: Database,
    settings: Settings,
    *,
    work_id: str,
    llm_client: Any = None,
    job: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """BYO LLM identity suggest for a Review slip. Pre-fill only — never Apply.

    Fail closed when LLM is unset. Never invents an ISBN.
    """
    work = db.get_work(work_id)
    if work is None:
        raise ValueError("Work not found")
    llm = llm_client if llm_client is not None else client_from_settings(settings)
    if llm is None:
        return {
            "configured": False,
            "suggestion": None,
            "note": LLM_UNSET_COPY,
            "work_id": work_id,
        }

    folder_raw = str(work.get("folder_path") or "")
    folder = Path(folder_raw) if folder_raw else Path()
    resolved = resolve_storage_path(folder, settings.complete_root) if usable_folder(folder) else folder
    files = list_payload_files(resolved) if usable_folder(resolved) and resolved.exists() else []

    payload = dict(job or {})
    if not payload.get("title"):
        payload["title"] = work.get("title") or ""
    if not payload.get("author"):
        payload["author"] = work.get("author") or ""
    if not payload.get("kind"):
        payload["kind"] = work.get("kind") or ""
    sought = {
        "kind": work.get("kind") or payload.get("kind") or "",
        "title": work.get("title") or payload.get("title") or "",
        "author": work.get("author") or payload.get("author") or "",
        "isbn": work.get("isbn") or "",
    }
    payload["sought"] = sought

    identity = Identity(
        kind=str(work.get("kind") or ""),
        title=str(work.get("title") or ""),
        author=str(work.get("author") or ""),
        series_name=str(work.get("series_name") or ""),
        series_index=str(work.get("series_index") or ""),
        year=work.get("year") if isinstance(work.get("year"), int) else None,
        isbn=str(work.get("isbn") or ""),
        confidence="low",
        review_reason=str(work.get("review_reason") or REVIEW_UNKNOWN),
        source="review",
    )
    evidence_folder = resolved if usable_folder(resolved) else Path(str(work.get("title") or "unknown"))
    from librarian.identify import _identify_evidence

    evidence = _identify_evidence(evidence_folder, payload, files, identity)
    try:
        parsed = llm.identify(evidence)
    except LLMError:
        return {
            "configured": True,
            "suggestion": None,
            "note": LLM_FAIL_COPY,
            "work_id": work_id,
        }
    if not parsed:
        return {
            "configured": True,
            "suggestion": None,
            "note": LLM_FAIL_COPY,
            "work_id": work_id,
        }
    merged = merge_llm_identity(identity, parsed, evidence)
    suggestion = suggestion_fields(merged)
    if not suggestion.get("title") or looks_like_dump_title(str(suggestion.get("title") or "")):
        return {
            "configured": True,
            "suggestion": suggestion if suggestion.get("title") else None,
            "note": LLM_FAIL_COPY,
            "work_id": work_id,
        }
    return {
        "configured": True,
        "suggestion": suggestion,
        "note": "",
        "work_id": work_id,
        "auto_apply": False,
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
    quiet = (not force) and in_quiet_hours(settings)
    # SAB often leaves damaged rar/7z; when stuck, par2 then unar before identify.
    # Quiet hours defer heavy unpack/convert — park for tonight.
    if quiet:
        parked = {
            "kind": str((identity_overrides or {}).get("kind") or (indexer_item or {}).get("kind") or "book"),
            "title": str(
                (identity_overrides or {}).get("title")
                or (indexer_item or {}).get("title")
                or folder.name
            ),
            "author": (identity_overrides or {}).get("author") or (indexer_item or {}).get("author"),
            "folder_path": str(folder),
            "indexer_guid": (indexer_item or {}).get("guid") or (indexer_item or {}).get("indexer_guid"),
            "review_state": "needs_review",
            "review_reason": REVIEW_QUIET_HOURS,
            "confidence": "low",
        }
        if identity_overrides:
            parked.update({k: v for k, v in identity_overrides.items() if v is not None})
        work = db.upsert_work(parked)
        return {
            "organized": False,
            "work": work,
            "identity": parked,
            "files": [],
            "auto_organize": False,
            "quiet_hours": True,
            "unpacked": {"unpacked": False},
            "converted": {"converted": False},
        }
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
    remux_note: Dict[str, Any] = {"remuxed": False}
    if (
        identity.get("kind") == KIND_AUDIOBOOK
        and str(identity.get("asin") or "").strip()
        and (result.get("auto_organize") or force)
    ):
        from librarian.m4b import chapters_from_audnexus, maybe_remux_audiobook_folder

        chapter_rows = None
        try:
            from librarian.audnexus import client_from_settings as audnexus_client_from_settings

            client = audnexus_client_from_settings(
                settings, transport=catalog_transport or cover_transport
            )
            try:
                chapter_rows = chapters_from_audnexus(
                    client.chapters(str(identity.get("asin") or ""))
                ) or None
            finally:
                client.close()
        except Exception:
            chapter_rows = None
        remux_note = maybe_remux_audiobook_folder(
            folder,
            identity,
            runner=convert_runner,
            chapters=chapter_rows,
            force=True,
        )
        if remux_note.get("remuxed") and remux_note.get("path"):
            files = [Path(str(remux_note["path"]))]
            result["files"] = [str(path) for path in files]
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
    payload_names = [path.name for path in files]
    part_fields = _part_fields_for_organize(
        identity=identity,
        indexer_item=indexer_item,
        filenames=payload_names,
    )
    if not result["auto_organize"] or not apply:
        work = db.upsert_work(
            {
                **identity,
                **part_fields,
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

    # Preflight every dest before moving any file — a mid-loop collision with
    # move_source=True would otherwise orphan already-relocated siblings.
    planned: List[tuple[Path, Path]] = []
    for src in files:
        dest = dest_layout(identity, settings, filename=src.name, source=src)
        if dest.exists() and dest.resolve() != src.resolve():
            identity["review_reason"] = REVIEW_COLLISION
            identity["confidence"] = "low"
            work = db.upsert_work(
                {
                    **identity,
                    **part_fields,
                    "folder_path": source_folder,
                    "review_state": "needs_review",
                    "review_reason": REVIEW_COLLISION,
                    "indexer_guid": (indexer_item or {}).get("guid"),
                }
            )
            return {"work": work, "identity": identity, "organized": False, "files": [str(p) for p in files]}
        planned.append((src, dest))

    placed: List[str] = []
    folder_path = None
    try:
        for src, dest in planned:
            written = _copy_into(src, dest, move=move_source)
            placed.append(str(written))
            folder_path = written.parent
    except FileExistsError:
        identity["review_reason"] = REVIEW_COLLISION
        work = db.upsert_work(
            {
                **identity,
                **part_fields,
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
        part_fields = _part_fields_for_organize(
            identity=identity,
            indexer_item=indexer_item,
            filenames=payload_names + [Path(path).name for path in placed],
            existing=existing,
        )
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
            **part_fields,
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
    placed_names = [Path(path).name for path in placed]
    for path in placed:
        name = Path(path).name
        db.upsert_file(
            {
                "work_id": work["id"],
                "path": path,
                "filename": name,
                "kind": identity["kind"],
                "size": Path(path).stat().st_size if Path(path).exists() else 0,
                "part": _file_part_index(
                    filename=name,
                    indexer_item=indexer_item,
                    filenames=payload_names + placed_names,
                ),
            }
        )
    if move_source:
        _cleanup_moved_source(folder, placed)
    komga_scan = None
    if identity.get("kind") == KIND_COMIC:
        try:
            from librarian.komga import notify_komga_scan

            komga_scan = notify_komga_scan(settings)
        except Exception:
            komga_scan = {"ok": False, "skipped": False, "error": "unexpected"}
    abs_scan = None
    if identity.get("kind") == KIND_AUDIOBOOK:
        try:
            from librarian.audiobookshelf import notify_abs_scan

            abs_scan = notify_abs_scan(settings)
        except Exception:
            abs_scan = {"ok": False, "skipped": False, "error": "unexpected"}
    return {
        "work": work,
        "identity": identity,
        "organized": True,
        "files": placed,
        "cover": str(cover) if cover else None,
        "komga_scan": komga_scan,
        "abs_scan": abs_scan,
        "m4b": remux_note,
    }


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
        move_source=True,
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
    fails = int(work.get("repair_fail_count") or 0)
    if problem == REVIEW_UNPACK_STUCK:
        fails += 1
        updated = db.upsert_work(
            {
                **work,
                "review_reason": REVIEW_UNPACK_STUCK,
                "folder_path": str(resolved),
                "repair_fail_count": fails,
            }
        )
    elif problem:
        if str(work.get("review_reason") or "") != problem:
            updated = db.upsert_work({**work, "review_reason": problem, "folder_path": str(resolved)})
    elif str(work.get("review_reason") or "") == REVIEW_UNPACK_STUCK:
        updated = db.upsert_work(
            {
                **work,
                "review_reason": "unknown_identity",
                "folder_path": str(resolved),
                "repair_fail_count": 0,
            }
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


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return str(left) == str(right)


# Small Calibre splits can sync-organize immediately. Author dumps (dozens/hundreds
# of title folders) must enqueue only — sync process=True hung Clear on Jenika Snow
# (~168 titles) and starved Review Apply of the SQLite writer.
EXTRA_FILES_SYNC_CHILD_LIMIT = 4
EXTRA_FILES_ITEM_TIMEOUT_S = 120.0


def reprocess_extra_files_work(
    db: Database,
    settings: Settings,
    *,
    work_id: str,
    requested_by: str = "owner",
    on_progress: Any = None,
) -> Dict[str, Any]:
    """Clear one ``extra_files`` slip: split Calibre author trees, or Apply multi-format volumes.

    Multi-title author folders must not force-Apply under one identity — expand to title
    children, resolve the parent slip, and ingest each child. Single-volume multi-format
    (epub+mobi) uses the same path as Apply.

    Large splits enqueue without ``process=True`` so the job poller shelves them and the
    Clear thread keeps heartbeating / releasing the write queue for interactive Review.
    """
    from librarian.ingest import enqueue_ingest, list_ingest_targets

    work = db.get_work(work_id)
    if work is None:
        raise ValueError("Work not found")
    reason = str(work.get("review_reason") or "")
    if reason != REVIEW_EXTRA:
        raise ValueError("Not an extra_files slip")
    folder = Path(str(work.get("folder_path") or ""))
    if not usable_folder(folder):
        raise ValueError(MISSING_FOLDER_APPLY_ERROR)

    targets = list_ingest_targets(folder)
    split_targets = [path for path in targets if not _same_path(path, folder)]
    if len(targets) > 1 or split_targets:
        children = split_targets or targets
        db.upsert_work({**work, "review_state": "resolved", "review_reason": None})
        process_sync = len(children) <= EXTRA_FILES_SYNC_CHILD_LIMIT
        jobs: List[Dict[str, Any]] = []
        for index, target in enumerate(children, start=1):
            if on_progress is not None:
                on_progress(
                    child_index=index,
                    child_total=len(children),
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
            "action": "split",
            "work_id": work_id,
            "targets": len(children),
            "shelved": shelved,
            "review": review,
            "queued": 0 if process_sync else len(children),
            "process_sync": process_sync,
            "jobs": [{"id": job.get("id"), "status": job.get("status"), "title": job.get("title")} for job in jobs],
        }

    if on_progress is not None:
        on_progress(child_index=1, child_total=1, child_title=folder.name, process_sync=True)
    result = apply_review(
        db,
        settings,
        work_id=work_id,
        folder=folder,
        identity_overrides={},
    )
    return {
        "action": "apply",
        "work_id": work_id,
        "organized": bool(result.get("organized")),
        "work": result.get("work"),
    }


def reprocess_extra_files_reviews(
    db: Database,
    settings: Settings,
    *,
    requested_by: str = "owner",
    limit: int = 0,
    progress: Any = None,
    item_timeout_s: float = EXTRA_FILES_ITEM_TIMEOUT_S,
) -> Dict[str, Any]:
    """Owner bulk clear for ``extra_files`` needs_review slips (newlib / multi-format backlog)."""
    import threading

    works = db.list_works(review_state="needs_review", limit=max(int(limit) or 5000, 1))
    extras = [row for row in works if str(row.get("review_reason") or "") == REVIEW_EXTRA]
    if limit and limit > 0:
        extras = extras[: int(limit)]
    total = len(extras)
    if progress is not None:
        progress.start(total=total, phase="reprocessing")
    split = 0
    applied = 0
    failed = 0
    shelved = 0
    still_review = 0
    errors: List[str] = []
    timeout_s = float(item_timeout_s) if item_timeout_s and item_timeout_s > 0 else EXTRA_FILES_ITEM_TIMEOUT_S
    timeout_s = max(0.05, timeout_s)

    def _child_progress(title: str, **fields: Any) -> None:
        if progress is None:
            return
        child_index = int(fields.get("child_index") or 0)
        child_total = int(fields.get("child_total") or 0)
        child_title = str(fields.get("child_title") or "").strip()
        note = title
        if child_total > 1 and child_title:
            note = f"{title} · {child_index}/{child_total} · {child_title}"
        elif child_title:
            note = child_title
        progress.tick(
            phase="reprocessing",
            current_title=note,
            shelved=shelved,
            split=split,
            applied=applied,
            failed=failed,
            still_review=still_review,
        )

    def _run_one(work_id: str, title: str) -> Dict[str, Any]:
        box: Dict[str, Any] = {}
        done = threading.Event()

        def _target() -> None:
            try:
                box["value"] = reprocess_extra_files_work(
                    db,
                    settings,
                    work_id=work_id,
                    requested_by=requested_by,
                    on_progress=lambda **kw: _child_progress(title, **kw),
                )
            except BaseException as exc:  # noqa: BLE001 — surface to waiter
                box["error"] = exc
            finally:
                done.set()

        worker = threading.Thread(
            target=_target,
            name="librarian-extra-files-item",
            daemon=True,
        )
        worker.start()
        if not done.wait(timeout=timeout_s):
            raise TimeoutError(
                f"Timed out after {int(timeout_s)}s — skipped so Clear can continue"
            )
        if "error" in box:
            raise box["error"]
        return box["value"]

    for index, row in enumerate(extras, start=1):
        title = str(row.get("title") or row.get("id") or "").strip()
        if progress is not None:
            progress.tick(
                phase="reprocessing",
                current_title=title,
                done=index - 1,
                total=total,
                shelved=shelved,
                split=split,
                applied=applied,
                failed=failed,
                still_review=still_review,
            )
        try:
            outcome = _run_one(str(row["id"]), title)
        except Exception as error:  # noqa: BLE001 — keep going through the backlog
            failed += 1
            if len(errors) < 12:
                errors.append(f"{title or row.get('id')}: {error}")
            if progress is not None:
                progress.tick(
                    phase="reprocessing",
                    current_title=title,
                    done=index,
                    total=total,
                    shelved=shelved,
                    split=split,
                    applied=applied,
                    failed=failed,
                    still_review=still_review,
                    log=f"Failed — {title or row.get('id')}: {error}",
                )
            continue
        if outcome.get("action") == "split":
            split += 1
            shelved += int(outcome.get("shelved") or 0)
            still_review += int(outcome.get("review") or 0)
            if int(outcome.get("queued") or 0) and progress is not None:
                progress.log(
                    f"Queued {outcome.get('queued')} titles from {title or row.get('id')} for the ingest poller."
                )
        else:
            applied += 1
            if outcome.get("organized"):
                shelved += 1
            else:
                still_review += 1
        if progress is not None:
            progress.tick(
                phase="reprocessing",
                current_title=title,
                done=index,
                total=total,
                shelved=shelved,
                split=split,
                applied=applied,
                failed=failed,
                still_review=still_review,
            )
    result = {
        "considered": total,
        "done": total,
        "total": total,
        "split": split,
        "applied": applied,
        "failed": failed,
        "shelved": shelved,
        "still_review": still_review,
        "errors": errors,
    }
    if progress is not None:
        progress.complete(result)
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
