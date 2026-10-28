"""New & noted desk. Readers may list. Owner and op may add to Wanted elsewhere.

This route does not search the indexer for a grab and does not call SABnzbd.
"""

from __future__ import annotations

from fastapi import Body, FastAPI, HTTPException, Request

from librarian.auth import require_role
from librarian.noted import (
    NotedError,
    add_missing_noted_history,
    cached_noted_desk,
    noted_desk,
    noted_history,
    run_noted_refresh,
)
from librarian.web.deps import WebDeps


def register_noted_routes(app: FastAPI, deps: WebDeps) -> None:
    db = deps.db
    settings = deps.settings
    root = deps.root

    @app.get("/api/noted")
    def noted_list(
        request: Request,
        period: str = "",
        preset: str = "hardcover-fiction",
        date: str = "current",
    ):
        require_role(request.state.user, "owner", "op", "reader")
        user = request.state.user
        try:
            # Compatibility for existing deep links. The new SPA deliberately
            # sends no selection parameters and receives every cached list.
            payload = (
                noted_desk(settings(), db, period=period or "daily", preset=preset, date=date, data_dir=root)
                if "period" in request.query_params or "preset" in request.query_params or "date" in request.query_params
                else cached_noted_desk(db, settings(), data_dir=root)
            )
        except NotedError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        payload["can_add"] = user["role"] in ("owner", "op")
        return payload

    @app.post("/api/maintain/noted/refresh")
    def refresh_noted(request: Request):
        require_role(request.state.user, "owner")
        try:
            counts = run_noted_refresh(db, settings(), data_dir=root)
        except Exception as error:  # noqa: BLE001
            raise HTTPException(status_code=502, detail="New & noted refresh failed") from error
        return {"status": "completed", "counts": counts, "phase": "New & noted refreshed"}

    @app.get("/api/noted/history")
    def noted_history_list(
        request: Request,
        list_name: str,
        start: str,
        end: str,
    ):
        require_role(request.state.user, "owner")
        try:
            return noted_history(db, settings(), list_name=list_name, start=start, end=end, data_dir=root)
        except (NotedError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/noted/history/add-missing")
    def noted_history_add_missing(request: Request, body: dict = Body(...)):
        require_role(request.state.user, "owner")
        items = body.get("items") if isinstance(body, dict) else None
        if not isinstance(items, list):
            raise HTTPException(status_code=400, detail="Items must be a list")
        return {"added": add_missing_noted_history(db, items)}
