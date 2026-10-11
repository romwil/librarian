"""New & noted desk. Readers may list. Owner and op may add to Wanted elsewhere.

This route does not search the indexer for a grab and does not call SABnzbd.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request

from librarian.auth import require_role
from librarian.noted import NotedError, noted_desk
from librarian.web.deps import WebDeps


def register_noted_routes(app: FastAPI, deps: WebDeps) -> None:
    db = deps.db
    settings = deps.settings
    root = deps.root

    @app.get("/api/noted")
    def noted_list(
        request: Request,
        period: str = "daily",
        preset: str = "hardcover-fiction",
        date: str = "current",
    ):
        require_role(request.state.user, "owner", "op", "reader")
        user = request.state.user
        try:
            payload = noted_desk(
                settings(),
                db,
                period=period,
                preset=preset,
                date=date,
                data_dir=root,
            )
        except NotedError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        payload["can_add"] = user["role"] in ("owner", "op")
        return payload
