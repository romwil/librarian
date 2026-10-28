"""Organize identified payloads into per-kind library layouts.

The organize flow lives here; its parts are split out:

- ``librarian.organize.move``: copy/move onto the shelf, source cleanup, music promote.
- ``librarian.organize.unpack``: par2 + unar before identify, and Review Repair.
- ``librarian.organize.review``: Review Apply error copy, slip actions, soft repairs.
- ``librarian.organize.notify``: Komga / Audiobookshelf rescans.

Every name importable from the old single-module ``librarian.organize`` is
still importable from here, and ``maybe_*`` / ``identify_completed`` stay
patchable on this package.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from librarian.config import Settings
from librarian.convert import (
    maybe_convert_payload as maybe_convert_payload,
)
from librarian.convert import (
    maybe_par2_repair as maybe_par2_repair,
)
from librarian.convert import (
    maybe_unpack_archives as maybe_unpack_archives,
)
from librarian.convert import (
    release_folder as release_folder,
)
from librarian.covers import ensure_music_cover as ensure_music_cover
from librarian.covers import fetch_cover
from librarian.db import Database
from librarian.delight import in_quiet_hours
from librarian.file_identity import files_byte_identical, volume_content_fingerprint
from librarian.identify import (
    REVIEW_AUDNEXUS_AMBIGUOUS as REVIEW_AUDNEXUS_AMBIGUOUS,
)
from librarian.identify import (
    REVIEW_AUDNEXUS_UNMATCHED as REVIEW_AUDNEXUS_UNMATCHED,
)
from librarian.identify import (
    REVIEW_COLLISION,
    REVIEW_EXTRA,
    REVIEW_NO_PAYLOAD,
    REVIEW_UNKNOWN,
    REVIEW_UNPACK_STUCK,
    Identity,
    dest_layout,
    identify_completed,
    identify_evidence,
    inspect_complete_folder,
    list_payload_files,
    looks_like_dump_title,
    music_state_for_folder,
    resolve_storage_path,
    usable_folder,
)
from librarian.identify import (
    REVIEW_COMICVINE_AMBIGUOUS as REVIEW_COMICVINE_AMBIGUOUS,
)
from librarian.identify import (
    REVIEW_COMICVINE_UNMATCHED as REVIEW_COMICVINE_UNMATCHED,
)
from librarian.identify import (
    REVIEW_CONVERT as REVIEW_CONVERT,
)
from librarian.identify import (
    REVIEW_LOW as REVIEW_LOW,
)
from librarian.identify import (
    REVIEW_MISSING_FOLDER as REVIEW_MISSING_FOLDER,
)
from librarian.identify import (
    REVIEW_UNEXPECTED as REVIEW_UNEXPECTED,
)
from librarian.identify import (
    diagnose_review_folder as diagnose_review_folder,
)
from librarian.ingest import enqueue_ingest, list_ingest_targets
from librarian.kinds import KIND_AUDIOBOOK, KIND_BOOK, KIND_COMIC, KIND_MAGAZINE, KIND_MUSIC
from librarian.llm import (
    LLM_FAIL_COPY,
    LLM_UNSET_COPY,
    LLMError,
    client_from_settings,
    merge_llm_identity,
    suggestion_fields,
)
from librarian.metadata import apply_audio_tags_in_folder, write_comicinfo, write_opf
from librarian.metadata import comicinfo_xml as comicinfo_xml
from librarian.organize.move import (
    _cleanup_moved_source as _cleanup_moved_source,
)
from librarian.organize.move import (
    _copy_into as _copy_into,
)
from librarian.organize.move import (
    _inject_comicinfo as _inject_comicinfo,
)
from librarian.organize.move import (
    _same_path as _same_path,
)
from librarian.organize.move import (
    _source_folder_value as _source_folder_value,
)
from librarian.organize.move import (
    promote_music as promote_music,
)
from librarian.organize.notify import notify_shelf_scanners as notify_shelf_scanners
from librarian.organize.review import (
    _RETRYABLE_REVIEW_REASONS as _RETRYABLE_REVIEW_REASONS,
)
from librarian.organize.review import (
    COLLISION_APPLY_ERROR as COLLISION_APPLY_ERROR,
)
from librarian.organize.review import (
    EXTRA_FILES_NO_MATCH_APPLY_ERROR as EXTRA_FILES_NO_MATCH_APPLY_ERROR,
)
from librarian.organize.review import (
    MISSING_FOLDER_APPLY_ERROR as MISSING_FOLDER_APPLY_ERROR,
)
from librarian.organize.review import (
    NO_PAYLOAD_APPLY_ERROR as NO_PAYLOAD_APPLY_ERROR,
)
from librarian.organize.review import (
    PERMISSION_APPLY_ERROR as PERMISSION_APPLY_ERROR,
)
from librarian.organize.review import (
    UNPACK_STUCK_APPLY_ERROR as UNPACK_STUCK_APPLY_ERROR,
)
from librarian.organize.review import (
    _permission_apply_error as _permission_apply_error,
)
from librarian.organize.review import (
    review_find_query as review_find_query,
)
from librarian.organize.review import (
    review_recommended_motion as review_recommended_motion,
)
from librarian.organize.review import (
    review_slip_actions as review_slip_actions,
)
from librarian.organize.review import (
    shelf_work_for_collision as shelf_work_for_collision,
)
from librarian.organize.review import (
    soft_repair_review_reasons as soft_repair_review_reasons,
)
from librarian.organize.unpack import (
    repair_review as repair_review,
)
from librarian.organize.unpack import (
    unpack_release as unpack_release,
)
from librarian.parts import infer_part_fields, merge_part_fields_for_work, part_for_filename
from librarian.review_reasons import REVIEW_QUIET_HOURS


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


def _owned_shelf_release(db: Database, work: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Drop a new slip when this title is already a shelved file. None to keep it."""
    from librarian.owned_slip import release_slip_already_on_shelf

    return release_slip_already_on_shelf(db, work)


def _merge_identity(identity: Dict[str, Any], overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(identity)
    for key, value in (overrides or {}).items():
        if value is not None:
            merged[key] = value
    return merged


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
        record_review_suggestion(db, work, outcome=SUGGEST_FAILED, explanation=LLM_UNSET_COPY)
        return {
            "configured": False,
            "suggestion": None,
            "note": LLM_UNSET_COPY,
            "work_id": work_id,
            "outcome": SUGGEST_FAILED,
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
    evidence = identify_evidence(evidence_folder, payload, files, identity)
    try:
        parsed = llm.identify(evidence)
    except LLMError as error:
        from librarian.llm import friendly_llm_error

        record_review_suggestion(
            db, work, outcome=SUGGEST_FAILED, explanation=friendly_llm_error(error) or LLM_FAIL_COPY
        )
        return {
            "configured": True,
            "suggestion": None,
            "note": LLM_FAIL_COPY,
            "work_id": work_id,
            "outcome": SUGGEST_FAILED,
        }
    if not parsed:
        record_review_suggestion(db, work, outcome=SUGGEST_FAILED, explanation=LLM_FAIL_COPY)
        return {
            "configured": True,
            "suggestion": None,
            "note": LLM_FAIL_COPY,
            "work_id": work_id,
            "outcome": SUGGEST_FAILED,
        }
    merged = merge_llm_identity(identity, parsed, evidence)
    suggestion = suggestion_fields(merged)
    if not suggestion.get("title") or looks_like_dump_title(str(suggestion.get("title") or "")):
        explanation = "The model returned no clean title — the name still reads like a release dump."
        record_review_suggestion(
            db,
            work,
            outcome=SUGGEST_AMBIGUOUS,
            suggestion=suggestion if suggestion.get("title") else None,
            explanation=explanation,
        )
        return {
            "configured": True,
            "suggestion": suggestion if suggestion.get("title") else None,
            "note": LLM_FAIL_COPY,
            "work_id": work_id,
            "outcome": SUGGEST_AMBIGUOUS,
            "explanation": explanation,
        }
    trusted = merged.confidence == "high"
    explanation = "" if trusted else suggestion_gaps(work, merged)
    outcome = SUGGEST_TRUSTED if trusted else SUGGEST_AMBIGUOUS
    record_review_suggestion(
        db, work, outcome=outcome, suggestion=suggestion, explanation=explanation
    )
    return {
        "configured": True,
        "suggestion": suggestion,
        "note": explanation,
        "work_id": work_id,
        "auto_apply": False,
        "outcome": outcome,
        "explanation": explanation,
    }


SUGGEST_TRUSTED = "trusted"
SUGGEST_AMBIGUOUS = "ambiguous"
SUGGEST_FAILED = "failed"


def suggestion_gaps(work: Dict[str, Any], merged: Identity) -> str:
    """Why a model suggestion is not trusted: the missing or conflicting fields."""
    from librarian.duplicate_gate import normalize_author, normalize_title

    kind = str(merged.kind or work.get("kind") or "")
    missing: List[str] = []
    if not merged.title:
        missing.append("title")
    if kind in (KIND_COMIC, KIND_MAGAZINE):
        if not merged.series_name:
            missing.append("series")
        if not merged.series_index:
            missing.append("issue number")
    elif not merged.author:
        missing.append("author")
    if kind == KIND_BOOK and not merged.isbn:
        missing.append("ISBN in the evidence")
    conflicts: List[str] = []
    stored_author = str(work.get("author") or "").strip()
    if (
        stored_author
        and merged.author
        and not looks_like_dump_title(stored_author)
        and normalize_author(stored_author) != normalize_author(merged.author)
    ):
        conflicts.append(f"author (folder says {stored_author}, model says {merged.author})")
    stored_series = str(work.get("series_name") or "").strip()
    if (
        stored_series
        and merged.series_name
        and normalize_title(stored_series) != normalize_title(merged.series_name)
    ):
        conflicts.append(f"series (folder says {stored_series}, model says {merged.series_name})")
    parts: List[str] = []
    if missing:
        parts.append("Missing " + ", ".join(missing))
    if conflicts:
        parts.append("Conflicting " + "; ".join(conflicts))
    if not parts:
        parts.append("The model was not confident enough to file this on its own")
    return ". ".join(parts) + "."


def record_review_suggestion(
    db: Database,
    work: Dict[str, Any],
    *,
    outcome: str,
    suggestion: Optional[Dict[str, Any]] = None,
    explanation: str = "",
) -> None:
    """Persist the model's answer on the slip right away (before the next slip is sent).

    A trusted answer clears the low-confidence reason; ambiguous answers keep it.
    """
    work_id = str(work.get("id") or "")
    if not work_id:
        return
    db.set_review_suggestion(
        work_id, outcome=outcome, suggestion=suggestion, explanation=explanation
    )
    if outcome == SUGGEST_TRUSTED and str(work.get("review_reason") or "") in (
        REVIEW_LOW,
        REVIEW_UNKNOWN,
    ):
        db.set_review_reason(work_id, None)


_GATED_IDENTITY_REASONS = frozenset({"", REVIEW_LOW, REVIEW_UNKNOWN, REVIEW_COLLISION})


def _pre_slip_gate(
    db: Database,
    *,
    identity: Dict[str, Any],
    folder: Path,
    files: List[Path],
    indexer_item: Optional[Dict[str, Any]],
    convert_failed_twice: bool,
) -> Dict[str, Any]:
    """Checks before a new slip: purge cooldown, bad release, duplicate evidence.

    Returns ``{"result": <organize result>}`` to stop here, else flags for the slip.
    """
    from librarian.duplicate_gate import duplicate_gate, slip_cooldown_active
    from librarian.review_reasons import REVIEW_POSSIBLE_DUPLICATE

    names = [str(path) for path in files]
    if slip_cooldown_active(db, _source_folder_value(folder) or folder):
        return {
            "result": {
                "organized": False,
                "work": None,
                "identity": identity,
                "files": names,
                "skipped_cooldown": True,
                "reason": "cooldown",
            }
        }
    item = indexer_item or {}
    if convert_failed_twice and identity.get("review_reason") == REVIEW_CONVERT:
        from librarian.bad_releases import release_bad_wanted

        selected = item.get("selected") if isinstance(item.get("selected"), dict) else {}
        released = release_bad_wanted(
            db,
            reason=REVIEW_CONVERT,
            job_id=str(item.get("job_id") or "") or None,
            guid=str(item.get("guid") or "") or None,
            host_id=str(selected.get("host_id") or item.get("host_id") or "") or None,
            record_missing=False,
        )
        if released["released"]:
            return {
                "result": {
                    "organized": False,
                    "work": None,
                    "identity": identity,
                    "files": names,
                    "released_bad": True,
                    "reason": "bad_release",
                    "wanted_id": released.get("wanted_id"),
                }
            }
        return {"needs_owner": True}
    reason = str(identity.get("review_reason") or "")
    if reason not in _GATED_IDENTITY_REASONS:
        return {}
    gate = duplicate_gate(db, identity, folder)
    if gate["action"] == "resolve" and gate.get("work"):
        return {
            "result": {
                "work": gate["work"],
                "identity": identity,
                "organized": False,
                "already_on_shelf": True,
                "skipped_duplicate": True,
                "reason": gate["evidence"],
                "files": names,
            }
        }
    if gate["action"] == "hold":
        identity["review_reason"] = REVIEW_POSSIBLE_DUPLICATE
        identity["confidence"] = "low"
    return {}


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
    folder = release_folder(Path(folder))
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
        released = _owned_shelf_release(db, work)
        if released:
            return {
                "organized": False,
                "work": released["work"],
                "identity": parked,
                "files": [],
                "auto_organize": False,
                "already_on_shelf": True,
                "reason": released["reason"],
                "quiet_hours": True,
                "unpacked": {"unpacked": False},
                "converted": {"converted": False},
            }
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
    unpacked = unpack_release(folder, **convert_kwargs)
    preview = identify_completed(folder, **identify_kwargs)
    kind = str((identity_overrides or {}).get("kind") or preview["identity"].get("kind") or "")
    converted = maybe_convert_payload(folder, kind, **convert_kwargs)
    # A convert that fails once is tried again. A second failure is a bad release.
    convert_failed_twice = False
    if not converted.get("converted") and kind == KIND_COMIC:
        again = maybe_convert_payload(folder, kind, **convert_kwargs)
        if again.get("converted"):
            converted = again
        else:
            convert_failed_twice = True
    result = (
        identify_completed(folder, **identify_kwargs)
        if converted["converted"] or unpacked["unpacked"]
        else preview
    )
    identity = _merge_identity(dict(result["identity"]), identity_overrides)
    files = [Path(path) for path in result["files"]]
    from librarian.slip_gate import sign_path_clear_dict

    sign_path_clear_dict(identity, folder, files)
    if identity.get("confidence") == "high" and not identity.get("review_reason"):
        result["auto_organize"] = True
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
    # Never shelve comic archives + ebook encodings as one work (even on force Apply).
    from librarian.identify import is_mixed_comic_ebook_payload, unexpected_extra_files

    if files and is_mixed_comic_ebook_payload(files):
        identity["review_reason"] = REVIEW_EXTRA
        identity["confidence"] = "low"
        result["auto_organize"] = False
    # Never force-shelve a multi-title dump under one identity (NYT Fiction, etc.).
    elif (
        files
        and unexpected_extra_files(files)
        and str(identity.get("kind") or "") not in (KIND_MUSIC, KIND_AUDIOBOOK, KIND_MAGAZINE)
    ):
        identity["review_reason"] = REVIEW_EXTRA
        identity["confidence"] = "low"
        result["auto_organize"] = False
    result["identity"] = identity
    if not force and not files:
        problem = inspect_complete_folder(folder).get("problem")
        if problem in {REVIEW_NO_PAYLOAD, REVIEW_UNPACK_STUCK}:
            return {
                "organized": False,
                "skipped_unreadable": True,
                "work": None,
                "identity": identity,
                "files": [],
                "reason": "unreadable",
                "problem": problem,
                "unpacked": unpacked,
                "converted": converted,
            }
    if not force:
        from librarian.slip_gate import shelf_match_for_organize

        shelf_match = shelf_match_for_organize(db, identity)
        if shelf_match["ambiguous"]:
            result["auto_organize"] = False
            identity["_keep_slip"] = True
        elif shelf_match["drop"] and shelf_match.get("work"):
            subtitle = str(identity.get("subtitle") or identity.get("comic_subtitle") or "").strip()
            if subtitle:
                db.set_work_subtitle(str(shelf_match["work"]["id"]), subtitle)
            from librarian.owned_slip import ALREADY_ON_SHELF

            return {
                "work": shelf_match["work"],
                "identity": identity,
                "organized": False,
                "already_on_shelf": True,
                "skipped_duplicate": True,
                "reason": ALREADY_ON_SHELF,
                "files": [str(path) for path in files],
            }
    source_folder = _source_folder_value(folder)
    payload_names = [path.name for path in files]
    part_fields = _part_fields_for_organize(
        identity=identity,
        indexer_item=indexer_item,
        filenames=payload_names,
    )
    if not result["auto_organize"] or not apply:
        needs_owner = False
        if apply and not force:
            gated = _pre_slip_gate(
                db,
                identity=identity,
                folder=folder,
                files=files,
                indexer_item=indexer_item,
                convert_failed_twice=convert_failed_twice,
            )
            if gated.get("result") is not None:
                return gated["result"]
            needs_owner = bool(gated.get("needs_owner"))
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
        released = None if identity.get("_keep_slip") else _owned_shelf_release(db, work)
        if released:
            return {
                "work": released["work"],
                "identity": identity,
                "organized": False,
                "already_on_shelf": True,
                "reason": released["reason"],
                "files": [str(p) for p in files],
            }
        if needs_owner:
            from librarian.bad_releases import NEEDS_OWNER_ACTION

            db.record_review_audit(
                NEEDS_OWNER_ACTION,
                work_id=str(work.get("id") or ""),
                guid=str((indexer_item or {}).get("guid") or "") or None,
                reason=str(identity.get("review_reason") or ""),
                detail={"missing": "wanted_or_guid"},
            )
        # Flat multi-title / Calibre dumps: expand into per-title ingest instead of one
        # confusing extra_files Review slip. Skip when force Apply (peel path) or mixed kinds.
        if (
            apply
            and not force
            and identity.get("review_reason") == REVIEW_EXTRA
            and files
            and not is_mixed_comic_ebook_payload(files)
            and unexpected_extra_files(files)
            and usable_folder(folder)
            and folder.is_dir()
        ):
            expanded = expand_extra_files_folder(
                db,
                settings,
                folder=folder,
                work=work,
                requested_by=str((indexer_item or {}).get("requested_by") or "owner"),
            )
            if expanded is not None:
                refreshed = db.get_work(work["id"]) or work
                return {
                    "work": refreshed,
                    "identity": identity,
                    "organized": False,
                    "expanded": True,
                    "files": [str(p) for p in files],
                    **expanded,
                }
        return {"work": work, "identity": identity, "organized": False, "files": [str(p) for p in files]}

    # Preflight every dest before moving any file — a mid-loop collision with
    # move_source=True would otherwise orphan already-relocated siblings.
    # Byte-identical payloads already on the shelf are ignored duplicates, not Review.
    planned: List[tuple[Path, Path]] = []
    collisions: List[tuple[Path, Path]] = []
    for src in files:
        dest = dest_layout(identity, settings, filename=src.name, source=src)
        if dest.exists() and dest.resolve() != src.resolve():
            collisions.append((src, dest))
        planned.append((src, dest))
    if collisions:
        dest_folder = collisions[0][1].parent
        identical = all(files_byte_identical(src, dest) for src, dest in collisions)
        all_present = len(collisions) == len(planned)
        # Path-aligned identical copies, OR the dest folder already holds the same
        # media payload under different names (Calibre "Title - Author.epub" vs
        # dest_layout's "Title.epub").
        source_fp = volume_content_fingerprint(folder)
        dest_fp = volume_content_fingerprint(dest_folder)
        payload_duplicate = bool(source_fp and dest_fp and source_fp == dest_fp)
        if (identical and all_present) or payload_duplicate:
            shelf = db.get_work_by_folder_path(str(dest_folder))
            work = shelf or db.upsert_work(
                {
                    **identity,
                    **part_fields,
                    "folder_path": str(dest_folder),
                    "review_state": "none",
                    "review_reason": None,
                    "indexer_guid": (indexer_item or {}).get("guid"),
                }
            )
            return {
                "work": work,
                "identity": identity,
                "organized": False,
                "skipped_duplicate": True,
                "files": [str(p) for p in files],
            }
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
        released = _owned_shelf_release(db, work)
        if released:
            return {
                "work": released["work"],
                "identity": identity,
                "organized": False,
                "already_on_shelf": True,
                "reason": released["reason"],
                "files": [str(p) for p in files],
            }
        return {"work": work, "identity": identity, "organized": False, "files": [str(p) for p in files]}

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
        released = _owned_shelf_release(db, work)
        if released:
            return {
                "work": released["work"],
                "identity": identity,
                "organized": False,
                "already_on_shelf": True,
                "reason": released["reason"],
                "files": [str(p) for p in files],
            }
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
        hardcover_token=str(getattr(settings, "hardcover_api_token", "") or ""),
        transport=cover_transport,
        require_safe_url=True,
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
    scans = notify_shelf_scanners(settings, str(identity.get("kind") or ""))
    return {
        "work": work,
        "identity": identity,
        "organized": True,
        "files": placed,
        "cover": str(cover) if cover else None,
        "komga_scan": scans["komga_scan"],
        "abs_scan": scans["abs_scan"],
        "m4b": remux_note,
    }


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
    try:
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
    except PermissionError as error:
        raise ValueError(_permission_apply_error(error)) from error
    if result.get("skipped_duplicate"):
        # Shelf already holds the same bytes (possibly under Calibre filenames).
        # Remove this Review slip; keep the shelved catalog row.
        slip_id = str(work.get("id") or "")
        if slip_id and slip_id != str((result.get("work") or {}).get("id") or ""):
            db.delete_work(slip_id)
        return {
            **result,
            "work": result.get("work"),
            "shelf_work": result.get("work"),
            "organized": False,
            "skipped_duplicate": True,
            "slip_deleted": True,
        }
    if not result["organized"]:
        reason = result.get("identity", {}).get("review_reason") or result["work"].get("review_reason")
        if reason == REVIEW_EXTRA:
            from librarian.identify import (
                expand_organize_payload,
                is_mixed_comic_ebook_payload,
                unexpected_extra_files,
            )
            from librarian.split_mixed_kinds import split_mixed_payload_folder

            payload = expand_organize_payload(resolved)
            if is_mixed_comic_ebook_payload(payload):
                return split_mixed_payload_folder(
                    db,
                    settings,
                    work_id=work_id,
                    folder=resolved,
                    requested_by=str(work.get("requested_by") or "owner"),
                )
            if unexpected_extra_files(payload):
                return _peel_matched_extra_files(
                    db,
                    settings,
                    work=work,
                    folder=resolved,
                    identity=merged,
                    indexer_item=fake_item,
                    payload=payload,
                )
        if reason == REVIEW_UNPACK_STUCK:
            raise ValueError(UNPACK_STUCK_APPLY_ERROR)
        if reason == REVIEW_NO_PAYLOAD:
            raise ValueError(NO_PAYLOAD_APPLY_ERROR)
        if reason == REVIEW_COLLISION:
            raise ValueError(COLLISION_APPLY_ERROR)
    return result


def _peel_matched_extra_files(
    db: Database,
    settings: Settings,
    *,
    work: Dict[str, Any],
    folder: Path,
    identity: Dict[str, Any],
    indexer_item: Dict[str, Any],
    payload: List[Path],
) -> Dict[str, Any]:
    """Shelve files matching the confirmed identity; leave other titles in the dump."""
    from librarian.identify import (
        match_payload_files_to_identity,
        safe_path_part,
    )

    matched = match_payload_files_to_identity(payload, identity)
    if not matched:
        raise ValueError(EXTRA_FILES_NO_MATCH_APPLY_ERROR)

    peel_label = safe_path_part(str(identity.get("title") or "Peeled"), fallback="Peeled")
    stage = folder / f".librarian-peel-{peel_label}"
    if stage.exists():
        stage = folder / f".librarian-peel-{str(work.get('id') or 'x')[:8]}"
    stage.mkdir(parents=True, exist_ok=True)
    moved: List[Path] = []
    try:
        for src in matched:
            dest = stage / src.name
            if src.resolve() != dest.resolve():
                shutil.move(str(src), str(dest))
            moved.append(dest)
        try:
            result = organize_identified(
                db,
                settings,
                folder=stage,
                indexer_item=indexer_item,
                apply=True,
                identity_overrides=identity,
                force=True,
                move_source=True,
            )
        except PermissionError as error:
            raise ValueError(_permission_apply_error(error)) from error
    except Exception:
        # Best-effort restore so the dump stays intact for a retry.
        for path in moved:
            restore = folder / path.name
            if path.exists() and not restore.exists():
                try:
                    shutil.move(str(path), str(restore))
                except OSError:
                    pass
        if stage.exists() and stage.is_dir() and not any(stage.iterdir()):
            shutil.rmtree(stage, ignore_errors=True)
        raise

    remaining = list_payload_files(folder)
    expanded_remaining = None
    if remaining:
        # Do not park another confusing extra_files slip — expand the rest like Clear.
        expanded_remaining = expand_extra_files_folder(
            db,
            settings,
            folder=folder,
            work=None,
            requested_by=str(work.get("requested_by") or "owner"),
        )
    elif stage.exists() and stage.is_dir() and not any(stage.iterdir()):
        shutil.rmtree(stage, ignore_errors=True)

    return {
        **result,
        "peeled": True,
        "peeled_files": [str(path) for path in matched],
        "remaining": len(remaining),
        "leftover_work": None,
        "expanded_remaining": expanded_remaining,
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


# Small Calibre splits can sync-organize immediately. Author dumps (dozens/hundreds
# of title folders) must enqueue only — sync process=True hung Clear on Jenika Snow
# (~168 titles) and starved Review Apply of the SQLite writer.
EXTRA_FILES_SYNC_CHILD_LIMIT = 4


EXTRA_FILES_ITEM_TIMEOUT_S = 120.0


def expand_extra_files_folder(
    db: Database,
    settings: Settings,
    *,
    folder: Path,
    work: Optional[Dict[str, Any]] = None,
    requested_by: str = "owner",
    on_progress: Any = None,
) -> Optional[Dict[str, Any]]:
    """Expand a multi-title dump into per-title ingest jobs.

    Used by Clear extra-files, auto-organize of collection folders, and Apply peel
    leftovers. Returns None when the folder is a single volume (caller may Apply).
    """
    targets = list_ingest_targets(folder)
    split_targets = [path for path in targets if not _same_path(path, folder)]
    if not (len(targets) > 1 or split_targets):
        return None
    children = split_targets or targets
    work_id = str((work or {}).get("id") or "") or None
    if work is not None and work_id:
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
    from librarian.identify import expand_organize_payload, is_mixed_comic_ebook_payload
    from librarian.split_mixed_kinds import split_mixed_payload_folder

    work = db.get_work(work_id)
    if work is None:
        raise ValueError("Work not found")
    reason = str(work.get("review_reason") or "")
    if reason != REVIEW_EXTRA:
        raise ValueError("Not an extra_files slip")
    folder = Path(str(work.get("folder_path") or ""))
    if not usable_folder(folder):
        raise ValueError(MISSING_FOLDER_APPLY_ERROR)

    # Flat folder with cbz + epub/azw3: never force-Apply as one comic.
    payload = expand_organize_payload(folder)
    if is_mixed_comic_ebook_payload(payload):
        return split_mixed_payload_folder(
            db,
            settings,
            work_id=work_id,
            folder=folder,
            requested_by=requested_by,
            on_progress=on_progress,
        )

    expanded = expand_extra_files_folder(
        db,
        settings,
        folder=folder,
        work=work,
        requested_by=requested_by,
        on_progress=on_progress,
    )
    if expanded is not None:
        return expanded

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

    fetch_limit = 5000
    if limit and limit > 0:
        fetch_limit = max(1, int(limit))
    extras = db.list_works(
        review_state="needs_review",
        review_reason=REVIEW_EXTRA,
        limit=fetch_limit,
    )
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

