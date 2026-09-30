"""Work detail, shelveside actions, progress, and catalog edits."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Request

from librarian.audiobook_match import companion_audiobook_payload
from librarian.auth import require_role
from librarian.convert import ALLOWED_EBOOK_FORMATS, which_ebook_convert
from librarian.delight import (
    WHISPER_LIST_LIMIT,
    finished_notice_copy,
    plexamp_handoff,
    progress_already_finished,
    sanitize_whisper,
    series_ribbon,
)
from librarian.enrich import (
    apply_audnexus_match,
    apply_comicvine_match,
    apply_openlibrary_match,
    clear_enrichment,
    enrich_work,
    list_match_candidates,
    update_work_metadata,
)
from librarian.gaps import (
    gaps_for_series,
)
from librarian.kinds import ALL_KINDS
from librarian.komga import komga_payload
from librarian.listen import listen_payload
from librarian.notifications import fan_out_notifications
from librarian.organize import promote_music
from librarian.parts import build_part_set
from librarian.serve import (
    annotate_work_files,
    can_read_work,
    existing_file_paths,
)
from librarian.web.deps import WebDeps
from librarian.web.schemas import (
    ApplyMatchPayload,
    ProgressPayload,
    WhisperPayload,
    WorkMetadataPayload,
)
from librarian.web.serializers import public_work, public_work_admin, public_works

logger = logging.getLogger("librarian.web")


def register_works_routes(app: FastAPI, deps: WebDeps) -> None:
    """Register work detail, progress, and catalog-edit routes on the composition-root app."""
    root = deps.root
    db = deps.db
    settings = deps.settings

    @app.get("/api/works/{work_id}")
    def work_detail(work_id: str, request: Request):
        work = public_work(db.get_work(work_id))
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        files = db.files_for_work(work_id)
        on_disk = existing_file_paths(files)
        part_set = build_part_set(work, files)
        if part_set:
            work["part_set"] = part_set
        related = []
        if work.get("author"):
            related = [
                row
                for row in public_works(db.search_works(str(work["author"]), limit=8))
                if row and row.get("id") != work_id
            ]
        progress = db.get_progress(request.state.user["id"], work_id)
        ribbon = []
        series_name = str(work.get("series_name") or "").strip()
        kind = str(work.get("kind") or "")
        if kind == "audiobook" and str(work.get("abs_item_id") or "").strip():
            try:
                from librarian.audiobookshelf import pull_abs_listen_progress

                pulled = pull_abs_listen_progress(
                    db,
                    settings(),
                    user_id=str(request.state.user["id"]),
                    work=work,
                    files=files,
                )
                if pulled:
                    progress = pulled
            except Exception:  # noqa: BLE001 — fail-soft ABS federation
                pass
        if series_name and kind in ALL_KINDS:
            card = gaps_for_series(db, kind=kind, series_name=series_name)
            owned = card.get("owned_indexes") or [
                str(row.get("series_index") or "")
                for row in db.works_for_series(kind=kind, series_name=series_name)
            ]
            missing = card.get("missing") or card.get("series_missing") or []
            ribbon = series_ribbon(
                owned_indexes=owned,
                missing_indexes=missing,
                current=work.get("series_index"),
            )
        whispers = db.list_whispers(work_id, limit=WHISPER_LIST_LIMIT)
        can_download = bool(on_disk)
        companion_candidates: List[Dict[str, Any]] = []
        if kind == "book":
            # Narrow search beats scanning hundreds of audiobooks on every book open.
            probe = " ".join(
                part
                for part in (str(work.get("author") or "").strip(), str(work.get("title") or "").strip())
                if part
            ).strip() or str(work.get("series_name") or "").strip()
            if probe:
                companion_candidates = db.search_works(probe, limit=40, kind="audiobook")
        audiobook = companion_audiobook_payload(work, audiobooks=companion_candidates)
        return {
            "work": work,
            "files": annotate_work_files(files, on_disk),
            "file_count": len(on_disk),
            "can_open": bool(on_disk),
            "can_download": can_download,
            "can_read": can_read_work(str(work.get("kind") or ""), on_disk),
            "listen": listen_payload(
                work,
                can_download=can_download,
                settings=settings(),
                progress=progress,
            ),
            "komga": komga_payload(work, settings()),
            "audiobook": audiobook,
            "favorite": db.is_favorite(request.state.user["id"], work_id),
            "related": related,
            "progress": progress,
            "ebook_convert": bool(which_ebook_convert()),
            "formats": list(ALLOWED_EBOOK_FORMATS),
            "series_ribbon": ribbon,
            "whispers": whispers,
        }

    @app.post("/api/works/{work_id}/favorite")
    def favorite(work_id: str, request: Request):
        if db.get_work(work_id) is None:
            raise HTTPException(status_code=404, detail="Work not found")
        on = db.toggle_favorite(request.state.user["id"], work_id)
        return {"favorite": on}

    @app.get("/api/works/{work_id}/whispers")
    def work_whispers(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        if db.get_work(work_id) is None:
            raise HTTPException(status_code=404, detail="Work not found")
        return {"whispers": db.list_whispers(work_id, limit=WHISPER_LIST_LIMIT)}

    @app.post("/api/works/{work_id}/whispers")
    def add_work_whisper(work_id: str, payload: WhisperPayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        if db.get_work(work_id) is None:
            raise HTTPException(status_code=404, detail="Work not found")
        body = sanitize_whisper(payload.body)
        if not body:
            raise HTTPException(status_code=400, detail="Whisper is empty")
        whisper = db.add_whisper(work_id=work_id, user_id=request.state.user["id"], body=body)
        return {"whisper": whisper, "whispers": db.list_whispers(work_id, limit=WHISPER_LIST_LIMIT)}

    @app.post("/api/works/{work_id}/progress")
    def touch_progress(work_id: str, payload: ProgressPayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        existing = db.get_progress(request.state.user["id"], work_id)
        already_finished = progress_already_finished(existing)
        if payload.finished:
            fraction = 1.0
        elif payload.fraction is not None:
            fraction = float(payload.fraction)
        elif existing:
            fraction = float(existing.get("fraction") or 0)
        else:
            fraction = 0.05
        position = payload.position or (existing or {}).get("position") or ""
        row = db.upsert_progress(
            user_id=request.state.user["id"],
            work_id=work_id,
            position=str(position),
            fraction=fraction,
        )
        whisper_row = None
        whisper_text = ""
        if payload.finished and payload.whisper is not None:
            whisper_text = sanitize_whisper(payload.whisper)
            if whisper_text:
                whisper_row = db.add_whisper(
                    work_id=work_id,
                    user_id=request.state.user["id"],
                    body=whisper_text,
                )
        # Beautiful Finished: first transition to Finished whispers the household
        # (optional note rides along). Re-finish does not re-notify.
        if payload.finished and not already_finished:
            notice = finished_notice_copy(
                finisher_name=request.state.user.get("display_name") or "",
                work_title=work.get("title") or "",
                whisper_body=whisper_text,
            )
            others = [
                str(u["id"])
                for u in db.list_users()
                if str(u.get("id") or "") and str(u["id"]) != str(request.state.user["id"])
            ]
            if others:
                try:
                    fan_out_notifications(
                        db,
                        settings(),
                        user_ids=others,
                        kind="someone_finished",
                        title=notice["title"],
                        body=notice["body"] or None,
                        payload={"work_id": work_id, "path": f"/works/{work_id}"},
                        from_user_id=str(request.state.user["id"]),
                        related_id=work_id,
                    )
                except Exception:  # noqa: BLE001 — fail-soft household whisper
                    logger.exception("someone_finished fan-out failed for %s", work_id)
        if (
            work
            and str(work.get("kind") or "") == "audiobook"
            and str(work.get("abs_item_id") or "").strip()
        ):
            try:
                from librarian.audiobookshelf import push_abs_listen_progress

                push_abs_listen_progress(
                    settings(),
                    work,
                    fraction=fraction,
                    position=str(position),
                    finished=bool(payload.finished),
                    force=bool(payload.finished),
                )
            except Exception:  # noqa: BLE001 — fail-soft ABS federation
                pass
        out: Dict[str, Any] = {"progress": row}
        if whisper_row is not None:
            out["whisper"] = whisper_row
            out["whispers"] = db.list_whispers(work_id, limit=WHISPER_LIST_LIMIT)
        return out

    @app.post("/api/music/{work_id}/promote")
    def music_promote(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            work = promote_music(db, settings(), work_id)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        # plexamp_handoff still needs the raw row; response work is allowlisted.
        return {"work": public_work_admin(work), "plexamp": plexamp_handoff(work)}

    @app.post("/api/works/{work_id}/enrich")
    def work_enrich(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            result = enrich_work(db, settings(), work_id, data_dir=root)
        except ValueError as error:
            detail = str(error)
            status = 404 if detail == "Work not found" else 400
            raise HTTPException(status_code=status, detail=detail) from error
        result["work"] = public_work(result.get("work"))
        return result

    @app.patch("/api/works/{work_id}/metadata")
    def work_metadata(work_id: str, payload: WorkMetadataPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        fields = payload.model_dump(exclude_unset=True)
        if not fields:
            raise HTTPException(status_code=400, detail="No metadata fields to update")
        try:
            work = update_work_metadata(db, work_id, fields, data_dir=root)
        except ValueError as error:
            detail = str(error)
            status = 404 if detail == "Work not found" else 400
            raise HTTPException(status_code=status, detail=detail) from error
        return {"work": public_work(work)}

    @app.get("/api/works/{work_id}/match-candidates")
    def work_match_candidates(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        if str(work.get("kind") or "") not in ("book", "audiobook", "comic"):
            raise HTTPException(
                status_code=400, detail="Only books, audiobooks, and comics can be matched"
            )
        candidates = list_match_candidates(work, settings=settings())
        return {"candidates": candidates, "title": work.get("title"), "author": work.get("author")}

    @app.post("/api/works/{work_id}/apply-match")
    def work_apply_match(work_id: str, payload: ApplyMatchPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        try:
            kind = str(work.get("kind") or "")
            if kind == "comic":
                result = apply_comicvine_match(
                    db,
                    settings(),
                    work_id,
                    payload.match_key,
                )
            elif kind == "audiobook":
                result = apply_audnexus_match(
                    db,
                    settings(),
                    work_id,
                    payload.match_key,
                    data_dir=root,
                )
            else:
                result = apply_openlibrary_match(
                    db,
                    settings(),
                    work_id,
                    payload.match_key,
                    data_dir=root,
                )
        except ValueError as error:
            detail = str(error)
            status = (
                404
                if detail
                in (
                    "Work not found",
                    "Open Library match not found",
                    "Comic Vine match not found",
                    "Audnexus match not found",
                )
                else 400
            )
            raise HTTPException(status_code=status, detail=detail) from error
        result["work"] = public_work(result.get("work"))
        return result

    @app.post("/api/works/{work_id}/clear-enrich")
    def work_clear_enrich(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            work = clear_enrichment(db, work_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"work": public_work(work)}
