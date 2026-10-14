"""Wanted desk API. Readers may list. Owner and op may add or dismiss.

Adding a row does not search and does not call SABnzbd.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request

from librarian.auth import require_role
from librarian.owned import ShelfIndex, annotate_wanted_row
from librarian.wanted import (
    AlreadyShelved,
    WantedError,
    add_wanted,
    dismiss_wanted,
    list_wanted,
    public_wanted,
)
from librarian.web.deps import WebDeps
from librarian.web.schemas import WantedAddPayload


def register_wanted_routes(app: FastAPI, deps: WebDeps) -> None:
    db = deps.db

    def _public(row: dict, index: ShelfIndex | None = None) -> dict:
        shelves = index or ShelfIndex(db)
        work = None
        work_id = str(row.get("work_id") or "").strip()
        if work_id:
            work = db.get_work(work_id)
        return annotate_wanted_row(public_wanted(row), shelves, work=work)

    @app.get("/api/wanted")
    def wanted_list(request: Request, status: str = ""):
        require_role(request.state.user, "owner", "op", "reader")
        try:
            rows = list_wanted(db, status=status)
        except WantedError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        shelves = ShelfIndex(db)
        return {"items": [_public(row, shelves) for row in rows]}

    @app.post("/api/wanted")
    def wanted_add(payload: WantedAddPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            row = add_wanted(db, payload.model_dump())
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
        return {"item": _public(row)}

    @app.post("/api/wanted/{wanted_id}/dismiss")
    def wanted_dismiss(wanted_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            row = dismiss_wanted(db, wanted_id)
        except WantedError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"item": _public(row)}
