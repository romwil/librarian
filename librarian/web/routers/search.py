"""Find: search, browse, suggest, discover, and curated lists."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from librarian.auth import require_role
from librarian.lists import chase_missing_items, file_missing_as_wanted
from librarian.nyt_books import normalize_list_date
from librarian.rate_limit import enforce_rate_limit
from librarian.services import search as search_service
from librarian.services.search import CONFIRM_ROLES, REQUEST_ROLES
from librarian.suggest import SUGGEST_FIELDS, suggest_items
from librarian.web.availability import annotate_browse_availability
from librarian.web.deps import WebDeps
from librarian.web.schemas import (
    AddMissingPayload,
    FinishSetEtaPayload,
    LlmListChasePayload,
    LlmListPayload,
    PublicDomainShelvePayload,
    SearchAskPayload,
)
from librarian.web.service_errors import http_errors


def register_search_routes(app: FastAPI, deps: WebDeps) -> None:
    """Register search, browse, discover, and curated-list routes on the composition-root app."""
    root = deps.root
    db = deps.db
    settings = deps.settings

    @app.get("/api/search")
    def search(
        request: Request,
        q: str = "",
        beyond: int = 0,
        kind: str = "",
        title: str = "",
        author: str = "",
        isbn: str = "",
        series: str = "",
        issue: str = "",
        artist: str = "",
        album: str = "",
        year: str = "",
        mode: str = "",
    ):
        return search_service.run_search(
            db,
            settings,
            root=root,
            user=request.state.user,
            q=q,
            beyond=beyond,
            kind=kind,
            title=title,
            author=author,
            isbn=isbn,
            series=series,
            issue=issue,
            artist=artist,
            album=album,
            year=year,
            mode=mode,
        )

    @app.get("/api/search/beyond")
    def search_beyond(
        request: Request,
        q: str = "",
        kind: str = "",
        title: str = "",
        author: str = "",
        isbn: str = "",
        series: str = "",
        issue: str = "",
        artist: str = "",
        album: str = "",
        year: str = "",
        mode: str = "",
    ):
        with http_errors():
            return search_service.run_search_beyond(
                db,
                settings,
                root=root,
                user=request.state.user,
                q=q,
                kind=kind,
                title=title,
                author=author,
                isbn=isbn,
                series=series,
                issue=issue,
                artist=artist,
                album=album,
                year=year,
                mode=mode,
            )

    @app.post("/api/search/ask")
    def search_ask(payload: SearchAskPayload, request: Request):
        """File a Wanted row from Search. Does not search indexers or call SABnzbd."""
        require_role(request.state.user, "owner", "op", "reader")
        with http_errors():
            return search_service.ask_from_search(
                db,
                request.state.user,
                q=payload.q,
                kind=payload.kind,
                title=payload.title,
                author=payload.author,
                isbn=payload.isbn,
                settings=settings(),
            )

    @app.get("/api/browse")
    def browse(
        request: Request,
        kind: str = "",
        author: str = "",
        letter: str = "",
        series: str = "",
        genre: str = "",
        shelf: str = "",
        sort: str = "",
        sort_dir: str = "",
        offset: int = 0,
        limit: int = 48,
    ):
        with http_errors():
            return search_service.browse_page(
                db,
                request.state.user,
                annotate=annotate_browse_availability,
                kind=kind,
                author=author,
                letter=letter,
                series=series,
                genre=genre,
                shelf=shelf,
                sort=sort,
                sort_dir=sort_dir,
                offset=offset,
                limit=limit,
            )

    @app.get("/api/browse/export.csv")
    def browse_export_csv(
        request: Request,
        kind: str = "",
        author: str = "",
        letter: str = "",
        series: str = "",
        genre: str = "",
        shelf: str = "",
        sort: str = "",
        sort_dir: str = "",
        columns: str = "",
    ):
        """CSV for the current stacks filters, capped at ``BROWSE_EXPORT_ROW_CAP`` rows.

        Offset and limit are page controls on ``GET /api/browse`` only. This route
        always starts at the first match. ``columns`` selects a visible subset;
        omit it, or pass ``all``, for title, author, year, kind, series, genre.
        """
        with http_errors():
            export = search_service.export_browse_csv(
                db,
                request.state.user,
                columns=columns,
                kind=kind,
                author=author,
                letter=letter,
                series=series,
                genre=genre,
                shelf=shelf,
                sort=sort,
                sort_dir=sort_dir,
            )
        return Response(
            content=export.body,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="librarian-stacks.csv"',
                "Cache-Control": "private, no-store",
                "X-Librarian-Export-Cap": str(export.cap),
                "X-Librarian-Export-Total": str(export.total),
                "X-Librarian-Export-Returned": str(export.returned),
            },
        )

    @app.get("/api/browse/facets")
    def browse_facets_endpoint(
        request: Request,
        kind: str = "",
        shelf: str = "",
    ):
        with http_errors():
            return search_service.browse_facets(db, request.state.user, kind=kind, shelf=shelf)

    @app.get("/api/suggest")
    def suggest(
        request: Request,
        field: str = "",
        kind: str = "",
        q: str = "",
        limit: int = 12,
    ):
        enforce_rate_limit(request, bucket="suggest", limit=120, window_seconds=60)
        key = str(field or "").strip().lower()
        if key not in SUGGEST_FIELDS:
            raise HTTPException(status_code=400, detail="Unknown suggest field")
        items = suggest_items(db, root, field=key, kind=kind, q=q, limit=limit)
        return {"field": key, "kind": kind, "q": q, "items": items}

    @app.get("/api/discover")
    def discover(
        request: Request,
        kind: str = "",
        cat: str = "",
        limit: int = 0,
        offset: int = 0,
        page: int = 0,
    ):
        require_role(request.state.user, "owner", "op")
        with http_errors():
            return search_service.discover_page(
            settings(),
            root=root,
            user=request.state.user,
            kind=kind,
            cat=cat,
            limit=limit,
            offset=offset,
            page=page,
        )

    @app.get("/api/lists/presets")
    def curated_list_presets(request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        return search_service.curated_list_presets(settings())

    @app.post("/api/lists/llm")
    def curated_llm_list(payload: LlmListPayload, request: Request):
        """BYO LLM curated list → match local shelves. Fail closed without LLM."""
        require_role(request.state.user, "owner", "op", "reader")
        when = normalize_list_date(payload.date)
        if not when:
            raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD or current")
        return search_service.curated_llm_list(
            db,
            settings(),
            root=root,
            user=request.state.user,
            preset=payload.preset,
            date=when,
            query=payload.query,
        )

    @app.post("/api/lists/llm/chase")
    def curated_llm_chase(payload: LlmListChasePayload, request: Request):
        """Find beyond for missing list titles (book + audiobook). Never auto-queues."""
        require_role(request.state.user, "owner", "op", "reader")
        items = [row.model_dump() for row in (payload.items or [])]
        results = chase_missing_items(settings(), items)
        return {
            "results": results,
            "can_request": request.state.user["role"] in REQUEST_ROLES,
            "can_confirm": request.state.user["role"] in CONFIRM_ROLES,
        }

    @app.post("/api/lists/add-missing")
    def curated_add_missing(payload: AddMissingPayload, request: Request):
        """One confirm files Wanted rows for list items not on the shelf.

        Does not search, does not open a slip per title, and does not call SABnzbd.
        """
        require_role(request.state.user, "owner", "op")
        items = [row.model_dump() for row in (payload.items or [])]
        result = file_missing_as_wanted(db, items)
        result["can_confirm"] = True
        return result

    @app.post("/api/public-domain/shelve")
    def public_domain_shelve(payload: PublicDomainShelvePayload, request: Request):
        """Shelve one Gutenberg or Standard Ebooks epub. No SABnzbd."""
        require_role(request.state.user, "owner", "op")
        with http_errors():
            return search_service.shelve_public_domain(db, settings(), payload.model_dump())

    @app.post("/api/find/finish-eta")
    def finish_eta(payload: FinishSetEtaPayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        return search_service.finish_set_eta(
            db,
            settings(),
            missing_count=payload.missing_count,
            kind=payload.kind,
            multipart=bool(payload.multipart),
            total_bytes=payload.total_bytes,
        )
