"""Hall shelves, named shelves, prefs, and gap desks."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request

from librarian.asks import public_asks
from librarian.auth import require_role
from librarian.delight import (
    normalize_ambient,
    normalize_ui_font_step,
    normalize_ui_theme,
    pick_fast_gap,
    series_catch_up,
)
from librarian.gaps import (
    cached_local_gaps,
    catalog_gaps,
    gap_cards,
)
from librarian.gaps_gifts import gift_cards, gift_presence
from librarian.listen import split_continue_rails
from librarian.named_shelves import (
    public_shelf,
    shelf_presence,
)
from librarian.web.deps import WebDeps
from librarian.web.schemas import (
    CelebrationSeenPayload,
    NamedShelfPayload,
    NamedShelfSharePayload,
    PrefsPayload,
)
from librarian.web.serializers import public_works


def register_hall_routes(app: FastAPI, deps: WebDeps) -> None:
    """Register Hall, shelf, preference, and gap routes on the composition-root app."""
    root = deps.root
    db = deps.db
    settings = deps.settings

    @app.get("/api/hall")
    def hall(request: Request):
        user = request.state.user
        recent = db.list_works(limit=18, require_files=True)
        favorites = db.favorite_works(user["id"], limit=18)
        continue_rows = db.continue_works(user["id"], limit=18)
        continue_split = split_continue_rails(continue_rows)
        counts = db.kind_counts()
        named_shelves = []
        for row in db.list_named_shelves_with_counts(user["id"], include_shared=True):
            meta = public_shelf(row, work_count=int(row.get("work_count") or 0))
            if meta:
                named_shelves.append(meta)
        return {
            "whats_new": public_works(recent),
            "favorites": public_works(favorites),
            "named_shelves": named_shelves,
            "named_shelves_presence": shelf_presence(named_shelves),
            "continue": continue_split["reading"],
            "continue_listening": continue_split["listening"],
            "kind_counts": counts,
            "owner_ready": True,
            "empty": not recent,
        }

    @app.get("/api/library-card")
    def library_card(request: Request):
        user = request.state.user
        continue_rows = db.continue_works(user["id"], limit=18)
        continue_split = split_continue_rails(continue_rows)
        finished = db.finished_works(user["id"], limit=18)
        favorites = db.favorite_works(user["id"], limit=18)
        return {
            "continue": continue_split["reading"],
            "continue_listening": continue_split["listening"],
            "finished": public_works(finished),
            "favorites": public_works(favorites),
            "wanted_count": db.count_wanted(),
            "asks": public_asks(db.list_jobs_for_user(user["id"], limit=20)),
        }

    @app.get("/api/shelves")
    def list_shelves(request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        user = request.state.user
        rows = db.list_named_shelves(user["id"], include_shared=True)
        shelves = []
        for row in rows:
            meta = public_shelf(row, work_count=db.shelf_work_count(row["id"]))
            if meta:
                shelves.append(meta)
        return {"shelves": shelves, "presence": shelf_presence(shelves)}

    @app.post("/api/shelves")
    def create_shelf(payload: NamedShelfPayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        try:
            shelf = db.create_named_shelf(
                request.state.user["id"],
                payload.name,
                shared=bool(payload.shared),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        meta = public_shelf(shelf, work_count=0)
        return {"shelf": meta, "presence": shelf_presence(db.list_named_shelves(request.state.user["id"]))}

    @app.post("/api/shelves/{shelf_id}/share")
    def share_shelf(shelf_id: str, payload: NamedShelfSharePayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        try:
            shelf = db.set_shelf_shared(shelf_id, request.state.user["id"], shared=bool(payload.shared))
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"shelf": public_shelf(shelf, work_count=db.shelf_work_count(shelf_id))}

    @app.delete("/api/shelves/{shelf_id}")
    def delete_shelf(shelf_id: str, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        try:
            removed = db.delete_named_shelf(shelf_id, request.state.user["id"])
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if not removed:
            raise HTTPException(status_code=404, detail="Shelf not found")
        return {"ok": True}

    @app.post("/api/shelves/{shelf_id}/works/{work_id}")
    def add_shelf_work(shelf_id: str, work_id: str, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        if db.get_work(work_id) is None:
            raise HTTPException(status_code=404, detail="Work not found")
        try:
            added = db.add_to_named_shelf(shelf_id, request.state.user["id"], work_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"on_shelf": True, "added": added}

    @app.delete("/api/shelves/{shelf_id}/works/{work_id}")
    def remove_shelf_work(shelf_id: str, work_id: str, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        try:
            removed = db.remove_from_named_shelf(shelf_id, request.state.user["id"], work_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"on_shelf": False, "removed": removed}

    def _public_prefs(row: Dict[str, Any]) -> Dict[str, Any]:
        nested = dict(row.get("prefs") or {})
        return {
            **row,
            "ui_theme": normalize_ui_theme(nested.get("ui_theme")),
            "ui_font_step": normalize_ui_font_step(nested.get("ui_font_step")),
        }

    @app.get("/api/prefs")
    def get_prefs(request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        return _public_prefs(db.get_user_prefs(request.state.user["id"]))

    @app.put("/api/prefs")
    def put_prefs(payload: PrefsPayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        ambient = normalize_ambient(payload.ambient) if payload.ambient is not None else None
        nested: Dict[str, Any] = {}
        if payload.ui_theme is not None:
            nested["ui_theme"] = normalize_ui_theme(payload.ui_theme)
        if payload.ui_font_step is not None:
            nested["ui_font_step"] = normalize_ui_font_step(payload.ui_font_step)
        return _public_prefs(
            db.set_user_prefs(
                request.state.user["id"],
                ambient=ambient,
                prefs=nested or None,
            )
        )

    @app.post("/api/celebrations/seen")
    def celebration_seen(payload: CelebrationSeenPayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        key = str(payload.key or "").strip()
        if not key:
            raise HTTPException(status_code=400, detail="Missing celebration key")
        db.mark_celebration_seen(request.state.user["id"], key)
        return {"ok": True}

    @app.get("/api/gaps")
    def gaps(request: Request):
        require_role(request.state.user, "owner", "op")
        rows = catalog_gaps(db, settings())
        return {"series": rows, "cards": gap_cards(rows)}

    @app.get("/api/gaps/local")
    def gaps_local(request: Request):
        """Local holes only (no catalog HTTP). Short TTL under DATA_DIR."""
        require_role(request.state.user, "owner", "op", "reader")
        rows = cached_local_gaps(db, root)
        cards = gap_cards(rows)
        gifts = gift_cards(cards)
        catch_up = series_catch_up(cards)
        return {
            "series": rows,
            "cards": cards,
            "gaps": gifts,
            "gaps_presence": gift_presence(gifts),
            "series_catch_up": catch_up,
            "tonight_gap": pick_fast_gap(gifts),
            "gaps_pending": False,
        }
