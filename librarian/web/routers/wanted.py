"""Wanted desk API. Readers may list. Owner and op may add, dismiss, or search.

A newly added or reopened row is searched once right after the response, then
waits for the hourly pass. Search files an Asked slip, and so does an add that
carries the clicked posting's guid. Nothing here calls SABnzbd. Confirm, on the
queue, is what talks to SABnzbd.
"""

from __future__ import annotations

import logging

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from librarian.auth import require_role
from librarian.owned import ShelfIndex, annotate_wanted_row
from librarian.wanted import (
    AlreadyShelved,
    WantedError,
    add_wanted,
    dismiss_wanted,
    page_wanted,
    public_wanted,
)
from librarian.wanted_search import (
    ask_wanted_hit,
    beyond_wanted,
    search_queued_wanted,
    search_wanted_selection,
)
from librarian.web.deps import WebDeps
from librarian.web.schemas import WantedAddPayload, WantedAskPayload, WantedSearchPayload

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

    @app.get("/api/wanted")
    def wanted_list(
        request: Request,
        status: str = "",
        kind: str = "",
        page: int = 1,
        page_size: int = 50,
    ):
        require_role(request.state.user, "owner", "op", "reader")
        try:
            window = page_wanted(
                db,
                status=status,
                kind=kind,
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
        require_role(request.state.user, "owner", "op", "reader")
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
