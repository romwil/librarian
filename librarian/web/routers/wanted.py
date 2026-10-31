"""Wanted desk API. Readers may list. Owner and op may add, dismiss, or search.

A newly added or reopened row is searched once right after the response, then
waits for the hourly pass. Search files an Asked slip, and so does an add that
carries the clicked posting's guid. Nothing here calls SABnzbd. Confirm, on the
queue, is what talks to SABnzbd.
"""

from __future__ import annotations

import logging
import time

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from librarian.auth import require_role
from librarian.config import (
    AUTO_AUDIOBOOK_WANTS_ALL,
    AUTO_AUDIOBOOK_WANTS_OFF,
    Settings,
    auto_audiobook_wants_enabled,
    merge_secret_fields,
    save_settings,
)
from librarian.owned import ShelfIndex, annotate_wanted_row
from librarian.wanted import (
    SOURCE_SWEEP,
    SWEEP_RESTORE_SECONDS,
    AlreadyShelved,
    WantedError,
    add_wanted,
    dismiss_sweep_wanted,
    dismiss_wanted,
    page_wanted,
    public_wanted,
    restore_sweep_wanted,
    restore_wanted,
)
from librarian.wanted_search import (
    ask_wanted_hit,
    beyond_wanted,
    search_queued_wanted,
    search_wanted_selection,
)
from librarian.wanted_sweep import OPEN_SWEEP_CAP
from librarian.web.deps import WebDeps
from librarian.web.schemas import (
    WantedAddPayload,
    WantedAskPayload,
    WantedSearchPayload,
    WantedSweepTogglePayload,
)

logger = logging.getLogger(__name__)


def register_wanted_routes(app: FastAPI, deps: WebDeps) -> None:
    db = deps.db

    def _search_new_row(wanted_id: str) -> None:
        try:
            search_queued_wanted(db, deps.settings(), [wanted_id])
        except Exception:
            logger.exception("Wanted search for a new row failed")

    def _public(row: dict, index: ShelfIndex | None = None) -> dict:
        shelves = index or ShelfIndex(db)
        work = None
        work_id = str(row.get("work_id") or "").strip()
        if work_id:
            work = db.get_work(work_id)
        return annotate_wanted_row(public_wanted(row), shelves, work=work)

    def _sweep_meta(now: float | None = None) -> dict:
        moment = time.time() if now is None else float(now)
        since = moment - SWEEP_RESTORE_SECONDS
        return {
            "enabled": auto_audiobook_wants_enabled(deps.settings()),
            "open": db.count_wanted(source=SOURCE_SWEEP),
            "cap": OPEN_SWEEP_CAP,
            "restorable": db.count_restorable_sweep_wanted(since=since),
        }

    @app.get("/api/wanted")
    def wanted_list(
        request: Request,
        status: str = "",
        kind: str = "",
        source: str = "",
        page: int = 1,
        page_size: int = 50,
    ):
        require_role(request.state.user, "owner", "op", "reader")
        try:
            window = page_wanted(
                db,
                status=status,
                kind=kind,
                source=source,
                page=page,
                page_size=page_size,
            )
        except WantedError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        # Shelf matching loads every shelved work. The list stays a cheap read
        # so the desk renders while purge/dedupe is fingerprinting. Add still matches.
        return {
            "items": [public_wanted(row) for row in window["items"]],
            "total": window["total"],
            "page": window["page"],
            "page_size": window["page_size"],
            "kinds": window["kinds"],
            "sweep": _sweep_meta(),
        }

    @app.post("/api/wanted/search")
    def wanted_search(payload: WantedSearchPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            results = search_wanted_selection(
                db,
                deps.settings(),
                ids=payload.ids,
                all_rows=payload.all,
                kind=payload.kind,
            )
        except WantedError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"results": results}

    @app.post("/api/wanted/dismiss-sweep")
    def wanted_dismiss_sweep(request: Request):
        require_role(request.state.user, "owner", "op")
        dismissed = dismiss_sweep_wanted(db)
        return {"dismissed": dismissed, "sweep": _sweep_meta()}

    @app.post("/api/wanted/restore-sweep")
    def wanted_restore_sweep(request: Request):
        require_role(request.state.user, "owner", "op")
        restored = restore_sweep_wanted(db)
        return {"restored": restored, "sweep": _sweep_meta()}

    @app.post("/api/wanted/sweep")
    def wanted_sweep_toggle(payload: WantedSweepTogglePayload, request: Request):
        require_role(request.state.user, "owner")
        incoming = {
            "auto_audiobook_wants": AUTO_AUDIOBOOK_WANTS_ALL if payload.enabled else AUTO_AUDIOBOOK_WANTS_OFF
        }
        merged = merge_secret_fields(incoming, deps.settings())
        saved = Settings.from_mapping(merged)
        save_settings(deps.root, saved)
        return {"sweep": _sweep_meta()}

    @app.post("/api/wanted")
    def wanted_add(payload: WantedAddPayload, request: Request, background: BackgroundTasks):
        require_role(request.state.user, "owner", "op")
        fields = payload.model_dump(exclude={"hit"})
        hit = payload.hit.model_dump() if payload.hit is not None else {}
        try:
            row = add_wanted(db, fields)
            if hit.get("guid", "").strip() and row.get("status") == "wanted":
                asked = ask_wanted_hit(db, str(row["id"]), hit)
                row = db.get_wanted(str(row["id"])) or row
                return {
                    "item": _public(row),
                    "outcome": asked.get("outcome"),
                    "job_id": asked.get("job_id"),
                }
        except AlreadyShelved as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "detail": "Already on the shelf",
                    "work_id": error.work_id,
                    "kind": error.kind,
                },
            ) from error
        except WantedError as error:
            status_code = 404 if str(error) == "Work not found" else 400
            raise HTTPException(status_code=status_code, detail=str(error)) from error
        if row.get("status") == "wanted":
            background.add_task(_search_new_row, str(row["id"]))
        return {"item": _public(row)}

    @app.post("/api/wanted/{wanted_id}/beyond")
    def wanted_beyond(wanted_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            return beyond_wanted(db, deps.settings(), wanted_id, data_dir=deps.root)
        except WantedError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/wanted/{wanted_id}/ask")
    def wanted_ask(wanted_id: str, payload: WantedAskPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            return ask_wanted_hit(db, wanted_id, payload.model_dump())
        except WantedError as error:
            status_code = 404 if str(error) == "Wanted row not found" else 400
            raise HTTPException(status_code=status_code, detail=str(error)) from error

    @app.post("/api/wanted/{wanted_id}/dismiss")
    def wanted_dismiss(wanted_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            row = dismiss_wanted(db, wanted_id)
        except WantedError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"item": _public(row)}

    @app.post("/api/wanted/{wanted_id}/restore")
    def wanted_restore(wanted_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            row = restore_wanted(db, wanted_id)
        except WantedError as error:
            status = 404 if str(error) == "Wanted row not found" else 400
            raise HTTPException(status_code=status, detail=str(error)) from error
        return {"item": _public(row)}
