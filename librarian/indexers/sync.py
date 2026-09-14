"""Settings-backed NZBFinder row in the indexers table + opt-in caps ping."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from librarian.config import Settings
from librarian.db import Database
from librarian.nzbfinder import NZBFinderClient, NZBFinderError

NZBFINDER_ID = "nzbfinder"


def summarize_capabilities(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"ok": False, "error": "unexpected caps payload"}
    server = payload.get("server") or {}
    searching = payload.get("searching") or {}
    categories = payload.get("categories") or []
    books = searching.get("books") or {}
    search = searching.get("search") or {}
    return {
        "ok": True,
        "server": server.get("title") or "NZBFinder",
        "url": server.get("url") or "",
        "books": str(books.get("available") or "").lower() == "yes",
        "search": str(search.get("available") or "").lower() == "yes",
        "category_count": len(categories) if isinstance(categories, list) else 0,
    }


def sync_nzbfinder(
    db: Database,
    settings: Settings,
    *,
    last_caps_ok: Optional[int] = None,
    last_caps_at: Optional[float] = None,
) -> Dict[str, Any]:
    row = db.get_indexer(NZBFINDER_ID) or {}
    payload: Dict[str, Any] = {
        "id": NZBFINDER_ID,
        "name": "NZBFinder",
        "kind": "nzbfinder",
        "base_url": settings.nzbfinder_url,
        "token_set": bool(str(settings.nzbfinder_api_token or "").strip()),
        "last_caps_ok": row.get("last_caps_ok") if last_caps_ok is None else last_caps_ok,
        "last_caps_at": row.get("last_caps_at") if last_caps_at is None else last_caps_at,
    }
    return db.upsert_indexer(payload)


def ping_nzbfinder(
    db: Database,
    settings: Settings,
    *,
    client: Optional[NZBFinderClient] = None,
) -> Dict[str, Any]:
    if not str(settings.nzbfinder_api_token or "").strip():
        return {"ok": False, "error": "NZBFinder api_token is not configured"}
    nzb = client or NZBFinderClient(settings.nzbfinder_url, settings.nzbfinder_api_token)
    try:
        summary = summarize_capabilities(nzb.capabilities())
    except NZBFinderError as error:
        sync_nzbfinder(db, settings, last_caps_ok=0, last_caps_at=time.time())
        return {"ok": False, "error": str(error)}
    sync_nzbfinder(
        db,
        settings,
        last_caps_ok=1 if summary.get("ok") else 0,
        last_caps_at=time.time(),
    )
    return summary
