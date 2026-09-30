"""Find: search, browse, suggest, discover, and curated lists."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Request

from librarian.auth import require_role
from librarian.delight import (
    estimate_finish_eta_minutes,
    finish_set_label,
    in_quiet_hours,
)
from librarian.indexers.discover import discover_beyond, resolve_feed_limit
from librarian.indexers.rank import search_and_rank
from librarian.indexers.scrub import (
    public_indexer_hit,
    public_indexer_hits,
)
from librarian.kinds import ALL_KINDS, EXTRA_KINDS
from librarian.lists import chase_missing_items, curated_list_payload, list_presets
from librarian.nyt_books import (
    NytBooksClient,
    NytBooksError,
    default_list_names,
    match_local_work,
    normalize_list_date,
    normalize_list_name,
)
from librarian.rate_limit import enforce_rate_limit
from librarian.search_forgive import search_with_forgiveness
from librarian.suggest import SUGGEST_FIELDS, suggest_items
from librarian.web.deps import WebDeps
from librarian.web.schemas import (
    FinishSetEtaPayload,
    LlmListChasePayload,
    LlmListPayload,
)
from librarian.web.serializers import public_work, public_works


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
    ):
        user = request.state.user
        local_kind = kind if kind in ALL_KINDS else None
        local_q = q.strip()
        forgiven = {"local": [], "did_you_mean": [], "forgave": False}
        if local_q:
            forgiven = search_with_forgiveness(db, local_q, limit=24, kind=local_kind)
        local = public_works(forgiven.get("local") or [])
        indexer = []
        beyond_error = None
        sought = {
            "kind": kind,
            "q": q,
            "title": title,
            "author": author,
            "isbn": isbn,
            "series": series,
            "issue": issue,
            "artist": artist,
            "album": album,
            "year": year,
        }
        has_beyond_query = bool(beyond) and any(
            str(sought[key] or "").strip() for key in sought if key != "kind"
        )
        extra_on = bool(settings().show_extra_categories)
        search_trace = None
        pick = None
        candidates: List[Dict[str, Any]] = []
        rank_method = ""
        rank_reason = ""
        if kind in EXTRA_KINDS and not extra_on:
            indexer, beyond_error = [], None
        elif has_beyond_query:
            ranked = search_and_rank(settings(), data_dir=root, **sought)
            indexer = list(ranked.get("hits") or [])
            beyond_error = ranked.get("error")
            if beyond_error:
                from librarian.llm import friendly_llm_error

                beyond_error = friendly_llm_error(RuntimeError(str(beyond_error)))
            pick = ranked.get("pick")
            candidates = list(ranked.get("candidates") or [])
            rank_method = str(ranked.get("rank_method") or "")
            rank_reason = str(ranked.get("rank_reason") or "")
            search_trace = {
                "conversation": list(ranked.get("conversation") or []),
                "steps": list(ranked.get("steps") or []),
                "results": list(ranked.get("results") or []),
                "plan": ranked.get("plan"),
                "raw_count": ranked.get("raw_count"),
                "rejected_count": ranked.get("rejected_count"),
                "rank_method": rank_method,
                "rank_reason": rank_reason,
            }
        owner_trace = user["role"] in ("owner", "op")
        return {
            "q": q,
            "local": local,
            "did_you_mean": list(forgiven.get("did_you_mean") or []),
            "forgave": bool(forgiven.get("forgave")),
            "beyond": public_indexer_hits(indexer),
            "beyond_error": beyond_error,
            "pick": public_indexer_hit(pick) if isinstance(pick, dict) else pick,
            "candidates": public_indexer_hits(candidates),
            "rank_method": rank_method,
            "rank_reason": rank_reason,
            "search_trace": search_trace if owner_trace else None,
            "can_request": user["role"] in ("owner", "op", "reader"),
        }

    @app.get("/api/browse")
    def browse(
        request: Request,
        kind: str = "",
        author: str = "",
        letter: str = "",
        series: str = "",
        genre: str = "",
        shelf: str = "",
        sort: str = "author",
        offset: int = 0,
        limit: int = 48,
    ):
        user = request.state.user
        kind_key = kind if kind in ALL_KINDS else None
        raw_shelf = str(shelf or "").strip()
        shelf_key = None
        if raw_shelf.lower() == "favorites":
            shelf_key = "favorites"
        elif raw_shelf:
            shelf_row = db.get_shelf(raw_shelf)
            if not shelf_row or not db.user_can_view_shelf(shelf_row, user["id"]):
                raise HTTPException(status_code=404, detail="Shelf not found")
            shelf_key = shelf_row["id"]
        try:
            page = db.browse_works(
                kind=kind_key,
                author=author.strip() or None,
                letter=letter.strip() or None,
                series=series.strip() or None,
                genre=genre.strip() or None,
                shelf=shelf_key,
                user_id=user["id"] if shelf_key else None,
                sort=sort,
                offset=offset,
                limit=limit,
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {
            "items": public_works(page["items"]),
            "total": page["total"],
            "offset": page["offset"],
            "limit": page["limit"],
            "sort": page["sort"],
            "filters": {
                "kind": kind_key or "",
                "author": author.strip(),
                "letter": letter.strip().upper(),
                "series": series.strip(),
                "genre": genre.strip(),
                "shelf": shelf_key or "",
            },
        }

    @app.get("/api/browse/facets")
    def browse_facets_endpoint(
        request: Request,
        kind: str = "",
        shelf: str = "",
    ):
        user = request.state.user
        kind_key = kind if kind in ALL_KINDS else None
        shelf_key = "favorites" if str(shelf or "").strip().lower() == "favorites" else None
        facets = db.browse_facets(
            kind=kind_key,
            shelf=shelf_key,
            user_id=user["id"] if shelf_key else None,
        )
        return facets

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
    def discover(request: Request, kind: str = "", cat: str = "", limit: int = 0):
        cfg = settings()
        feed_limit = resolve_feed_limit(cat=cat, limit=limit if limit else None)
        items, categories, beyond_error = discover_beyond(cfg, kind=kind, cat=cat, limit=feed_limit)
        return {
            "kind": kind,
            "cat": cat,
            "limit": feed_limit,
            "items": public_indexer_hits(items),
            "categories": categories,
            "beyond_error": beyond_error,
            "show_extra_categories": bool(cfg.show_extra_categories),
            "can_request": request.state.user["role"] in ("owner", "op", "reader"),
        }

    @app.get("/api/lists/presets")
    def curated_list_presets(request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        cfg = settings()
        from librarian.llm_providers import resolve_llm_connection

        llm_ok = bool(resolve_llm_connection(cfg).get("api_key"))
        return {
            "presets": list_presets(),
            "configured": llm_ok,
            "source": "llm",
            "empty_copy": (
                "" if llm_ok else "Add a BYO LLM in Settings to load curated bestseller lists."
            ),
        }

    @app.post("/api/lists/llm")
    def curated_llm_list(payload: LlmListPayload, request: Request):
        """BYO LLM curated list → match local shelves. Fail closed without LLM."""
        require_role(request.state.user, "owner", "op", "reader")
        when = normalize_list_date(payload.date)
        if not when:
            raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD or current")
        result = curated_list_payload(
            settings(),
            db,
            preset=payload.preset,
            date=when,
            query=payload.query,
            data_dir=root,
        )
        # Enrich shelved stubs with public_work cover flags.
        for entry in result.get("books") or []:
            for key in ("shelved", "shelved_audiobook"):
                stub = entry.get(key)
                if not stub or not stub.get("id"):
                    continue
                work = public_work(db.get_work(str(stub["id"])))
                if work:
                    entry[key] = {
                        "id": work.get("id"),
                        "title": work.get("title"),
                        "author": work.get("author"),
                        "kind": stub.get("kind") or work.get("kind"),
                        "has_cover": bool(work.get("has_cover") or work.get("cover_path")),
                    }
        result["can_request"] = request.state.user["role"] in ("owner", "op", "reader")
        result["can_confirm"] = request.state.user["role"] in ("owner", "op")
        return result

    @app.post("/api/lists/llm/chase")
    def curated_llm_chase(payload: LlmListChasePayload, request: Request):
        """Find beyond for missing list titles (book + audiobook). Never auto-queues."""
        require_role(request.state.user, "owner", "op", "reader")
        items = [row.model_dump() for row in (payload.items or [])]
        results = chase_missing_items(settings(), items)
        return {
            "results": results,
            "can_request": request.state.user["role"] in ("owner", "op", "reader"),
            "can_confirm": request.state.user["role"] in ("owner", "op"),
        }

    @app.get("/api/lists/nyt/names")
    def nyt_list_names(request: Request):
        """Legacy NYT Books API names — prefer POST /api/lists/llm."""
        require_role(request.state.user, "owner", "op", "reader")
        cfg = settings()
        key = str(cfg.nyt_books_api_key or "").strip()
        if not key:
            return {
                "configured": False,
                "names": default_list_names(),
                "empty_reason": "missing_key",
                "empty_copy": "Add a BYO LLM in Settings for curated bestseller lists.",
                "deprecated": True,
            }
        client = NytBooksClient(key, data_dir=root)
        try:
            names = client.list_names()
        except NytBooksError as error:
            return {
                "configured": True,
                "names": default_list_names(),
                "empty_reason": "error",
                "empty_copy": str(error),
                "deprecated": True,
            }
        finally:
            client.close()
        return {
            "configured": True,
            "names": names or default_list_names(),
            "empty_reason": "",
            "empty_copy": "",
            "deprecated": True,
        }

    @app.get("/api/lists/nyt")
    def nyt_bestseller_list(
        request: Request,
        list: str = "hardcover-fiction",  # noqa: A002 — query param name matches NYT docs
        date: str = "current",
    ):
        require_role(request.state.user, "owner", "op", "reader")
        slug = normalize_list_name(list) or "hardcover-fiction"
        when = normalize_list_date(date)
        if not when:
            raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD or current")
        cfg = settings()
        key = str(cfg.nyt_books_api_key or "").strip()
        client = NytBooksClient(key, data_dir=root)
        try:
            payload = client.bestseller_list(slug, date=when)
        except NytBooksError as error:
            client.close()
            return {
                "configured": bool(key),
                "list_name": slug,
                "date": when,
                "published_date": "",
                "display_name": slug,
                "books": [],
                "empty_reason": "error",
                "empty_copy": str(error),
            }
        client.close()
        books = []
        for book in payload.get("books") or []:
            query = " ".join(
                part
                for part in (
                    str(book.get("author") or "").strip(),
                    str(book.get("title") or "").strip(),
                )
                if part
            )
            candidates: List[Dict[str, Any]] = []
            isbn = str(book.get("isbn") or "").strip()
            if isbn:
                candidates.extend(db.search_works(isbn, limit=8, kind="book"))
            if query:
                candidates.extend(db.search_works(query, limit=12, kind="book"))
            # Deduplicate by id while preserving order.
            seen: set[str] = set()
            uniq: List[Dict[str, Any]] = []
            for row in candidates:
                wid = str(row.get("id") or "")
                if not wid or wid in seen:
                    continue
                seen.add(wid)
                uniq.append(row)
            local = match_local_work(book, uniq)
            entry = dict(book)
            if local:
                pub = public_work(local)
                entry["shelved"] = {
                    "id": pub.get("id") if pub else local.get("id"),
                    "title": (pub or local).get("title"),
                    "author": (pub or local).get("author"),
                    "has_cover": bool(
                        (pub or local).get("has_cover") or (pub or local).get("cover_path")
                    ),
                }
            else:
                entry["shelved"] = None
            books.append(entry)
        empty_reason = str(payload.get("empty_reason") or "")
        empty_copy = ""
        if empty_reason == "missing_key":
            empty_copy = "Add a BYO LLM in Settings for curated bestseller lists."
        elif empty_reason == "empty_list":
            empty_copy = "That list came back empty for this date."
        elif not books and not empty_reason:
            empty_copy = "No titles on this list yet."
        return {
            **payload,
            "books": books,
            "empty_copy": empty_copy,
            "deprecated": True,
        }

    @app.post("/api/find/finish-eta")
    def finish_eta(payload: FinishSetEtaPayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        miss = int(payload.missing_count or 0)
        kind = str(payload.kind or "").strip()
        multipart = bool(payload.multipart)
        kind_samples = (
            db.recent_job_durations(kind=kind, multipart=True if multipart else None)
            if kind
            else []
        )
        pool_approximate = False
        if len(kind_samples) >= 2:
            samples = kind_samples
        else:
            global_samples = db.recent_job_durations(multipart=True if multipart else None)
            if len(global_samples) >= 2:
                samples = global_samples
                pool_approximate = bool(kind)
            elif kind_samples:
                samples = kind_samples
                pool_approximate = True
            else:
                samples = global_samples
                pool_approximate = True
        eta = estimate_finish_eta_minutes(
            missing_count=miss,
            recent_seconds=samples,
            total_bytes=payload.total_bytes,
        )
        minutes = eta.get("eta_minutes")
        approximate = bool(eta.get("approximate")) or (bool(minutes) and pool_approximate)
        return {
            "eta_minutes": minutes,
            "approximate": approximate if minutes else False,
            "label": finish_set_label(
                missing_count=miss,
                eta_minutes=minutes,
                approximate=approximate if minutes else False,
            ),
            "quiet_hours": in_quiet_hours(settings()),
        }
