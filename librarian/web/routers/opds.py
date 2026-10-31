"""OPDS 1.2 catalog. Navigation uses a catalog token, never the session cookie."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from librarian.auth import require_role
from librarian.opds_feed import (
    ACQUISITION_TYPE,
    KIND_TITLES,
    NAVIGATION_TYPE,
    OPDS_KINDS,
    PAGE_SIZE,
    SEARCH_TYPE,
    acquisition_feed,
    atom_entry,
    atom_link,
    atom_time,
    feed_document,
    reading_authors,
    search_description,
    shelved_author_page,
    shelved_page,
    with_query,
)
from librarian.opds_tokens import OPDS_TTL_DAYS, create_catalog_token, parse_catalog_token
from librarian.web.deps import WebDeps


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _catalog_token(request: Request, data_dir, db=None) -> str:
    raw = str(request.query_params.get("token") or "").strip()
    if not raw:
        header = str(request.headers.get("authorization") or "").strip()
        if header.lower().startswith("bearer "):
            raw = header[7:].strip()
    payload = parse_catalog_token(raw, data_dir=data_dir)
    if payload is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    uid = str(payload.get("uid") or "").strip()
    if uid and db is not None:
        user = db.get_user(uid)
        if user is None or int(user.get("disabled") or 0):
            raise HTTPException(status_code=401, detail="Authentication required")
    return raw


def _xml(body: str, media_type: str) -> Response:
    return Response(content=body, media_type=media_type)


def register_opds_routes(app: FastAPI, deps: WebDeps) -> None:
    """Register the OPDS catalog and the cookie-authenticated link the household copies."""
    root = deps.root
    db = deps.db

    @app.get("/api/opds")
    def opds_catalog_link(request: Request):
        """SPA session may mint a catalog URL. Reader apps then use the token, not the cookie."""
        require_role(request.state.user, "owner", "op", "reader")
        user = request.state.user or {}
        token = create_catalog_token(user_id=str(user.get("id") or ""), data_dir=root)
        return {
            "catalog_url": f"{_base(request)}/opds?token={quote(token, safe='')}",
            "ttl_days": OPDS_TTL_DAYS,
        }

    @app.get("/opds")
    def opds_root(request: Request):
        token = _catalog_token(request, root, db)
        base = _base(request)
        start = with_query(f"{base}/opds", token=token)
        updated = atom_time(None)
        entries = []
        for kind in OPDS_KINDS:
            href = with_query(f"{base}/opds/kind/{kind}", token=token)
            entries.append(
                atom_entry(
                    KIND_TITLES[kind],
                    f"urn:librarian:opds:kind:{kind}",
                    updated,
                    atom_link("subsection", href, ACQUISITION_TYPE),
                )
            )
        authors = with_query(f"{base}/opds/authors", token=token)
        entries.append(
            atom_entry(
                "Authors",
                "urn:librarian:opds:authors",
                updated,
                atom_link("subsection", authors, NAVIGATION_TYPE),
            )
        )
        search_href = f"{base}/opds/search.xml?token={quote(token, safe='')}"
        links = [
            atom_link("self", start, NAVIGATION_TYPE),
            atom_link("start", start, NAVIGATION_TYPE),
            atom_link("search", search_href, SEARCH_TYPE),
        ]
        body = feed_document(
            title="Librarian",
            feed_id="urn:librarian:opds:root",
            updated=updated,
            links=links,
            entries=entries,
        )
        return _xml(body, NAVIGATION_TYPE)

    @app.get("/opds/search.xml")
    def opds_search_description(request: Request):
        token = _catalog_token(request, root, db)
        base = _base(request)
        template = f"{base}/opds/search?q={{searchTerms}}&token={quote(token, safe='')}"
        return _xml(search_description(short_name="Librarian", template=template), SEARCH_TYPE)

    @app.get("/opds/kind/{kind}")
    def opds_kind(kind: str, request: Request, offset: int = 0):
        token = _catalog_token(request, root, db)
        if kind not in OPDS_KINDS:
            raise HTTPException(status_code=404, detail="Kind not found")
        return _acquisition_response(
            request,
            token,
            title=KIND_TITLES[kind],
            feed_id=f"urn:librarian:opds:kind:{kind}",
            path=f"/opds/kind/{kind}",
            page=shelved_page(db, kind=kind, offset=offset),
            extra={},
        )

    @app.get("/opds/authors")
    def opds_authors(request: Request, offset: int = 0):
        token = _catalog_token(request, root, db)
        base = _base(request)
        start = with_query(f"{base}/opds", token=token)
        names = reading_authors(db)
        skip = max(0, int(offset))
        window = names[skip : skip + PAGE_SIZE]
        updated = atom_time(None)
        entries = []
        for name in window:
            href = with_query(f"{base}/opds/author", token=token, author=name)
            entries.append(
                atom_entry(
                    name,
                    f"urn:librarian:opds:author:{name.casefold()}",
                    updated,
                    atom_link("subsection", href, ACQUISITION_TYPE),
                )
            )
        self_href = with_query(f"{base}/opds/authors", token=token, offset=skip or None)
        links = [
            atom_link("self", self_href, NAVIGATION_TYPE),
            atom_link("start", start, NAVIGATION_TYPE),
        ]
        if skip + PAGE_SIZE < len(names):
            links.append(
                atom_link(
                    "next",
                    with_query(f"{base}/opds/authors", token=token, offset=skip + PAGE_SIZE),
                    NAVIGATION_TYPE,
                )
            )
        body = feed_document(
            title="Authors",
            feed_id="urn:librarian:opds:authors",
            updated=updated,
            links=links,
            entries=entries,
        )
        return _xml(body, NAVIGATION_TYPE)

    @app.get("/opds/author")
    def opds_author(request: Request, author: str = "", offset: int = 0):
        token = _catalog_token(request, root, db)
        name = str(author or "").strip()
        if not name:
            raise HTTPException(status_code=404, detail="Author not found")
        return _acquisition_response(
            request,
            token,
            title=name,
            feed_id=f"urn:librarian:opds:author:{name.casefold()}",
            path="/opds/author",
            page=shelved_author_page(db, name, offset=offset),
            extra={"author": name},
        )

    @app.get("/opds/search")
    def opds_search(request: Request, q: str = ""):
        token = _catalog_token(request, root, db)
        base = _base(request)
        start = with_query(f"{base}/opds", token=token)
        query = str(q or "").strip()
        works = []
        if query:
            seen: set[str] = set()
            for kind in OPDS_KINDS:
                for work in db.search_works(query, limit=PAGE_SIZE, kind=kind):
                    work_id = str(work.get("id") or "")
                    if work_id and work_id not in seen:
                        seen.add(work_id)
                        works.append(work)
        self_href = with_query(f"{base}/opds/search", token=token, q=query)
        body = acquisition_feed(
            db,
            works,
            title=query or "Search",
            feed_id="urn:librarian:opds:search",
            self_href=self_href,
            start_href=start,
            data_dir=root,
            download_base=base,
        )
        return _xml(body, ACQUISITION_TYPE)

    def _acquisition_response(request, token, *, title, feed_id, path, page, extra):
        base = _base(request)
        start = with_query(f"{base}/opds", token=token)
        skip = int(page["offset"])
        self_href = with_query(f"{base}{path}", token=token, offset=skip or None, **extra)
        next_href = ""
        if skip + int(page["limit"]) < int(page["total"]):
            next_href = with_query(
                f"{base}{path}",
                token=token,
                offset=skip + int(page["limit"]),
                **extra,
            )
        body = acquisition_feed(
            db,
            page["items"],
            title=title,
            feed_id=feed_id,
            self_href=self_href,
            start_href=start,
            data_dir=root,
            download_base=base,
            next_href=next_href,
        )
        return _xml(body, ACQUISITION_TYPE)
