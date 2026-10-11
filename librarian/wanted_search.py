"""Recurring Wanted search. Files one Asked slip. Never calls SABnzbd.

Only ``wanted`` rows whose ``next_search_at`` has passed are searched. A confident
hit compare-and-sets the row to ``asked`` and inserts one queue job. Overlapping
polls lose that update and do not enqueue again. Dismissed rows are never read
here. A miss or a multi-disc junk archive pushes the backoff clock.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Mapping, Optional

from librarian.config import Settings
from librarian.db import Database
from librarian.indexers.query import build_job_payload
from librarian.indexers.rank import heuristic_rank
from librarian.kinds import search_category_for_kind
from librarian.nzbfinder import NZBFinderClient, NZBFinderError
from librarian.wanted import (
    BASE_BACKOFF_SECONDS,
    SLOW_AFTER_MISSES,
    STATUS_ASKED,
    is_confident_hit,
    is_junk_multidisc,
)

logger = logging.getLogger(__name__)

MAX_SEARCHES_PER_TICK = 5

SearchFn = Callable[[Mapping[str, Any]], List[Dict[str, Any]]]


def _text(value: Any) -> str:
    return str(value or "").strip()


def sought_for_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    kind = _text(row.get("kind")) or "audiobook"
    title = _text(row.get("title"))
    author = _text(row.get("author"))
    isbn = _text(row.get("isbn"))
    query = isbn or " ".join(part for part in (author, title) if part).strip()
    return {
        "kind": kind,
        "title": title,
        "author": author,
        "isbn": isbn,
        "q": query,
        "cat": search_category_for_kind(kind) or "",
    }


def nzbfinder_search(client: NZBFinderClient, sought: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """NZBFinder category for this row. Audiobooks use 3030."""
    query = _text(sought.get("q"))
    cat = _text(sought.get("cat"))
    kind = _text(sought.get("kind"))
    if not query or not cat:
        return []
    return client.search(query, cat=cat, kind=kind or None, limit=25)


def choose_hit(
    sought: Mapping[str, Any],
    hits: List[Mapping[str, Any]],
) -> tuple[str, Optional[Dict[str, Any]]]:
    """Return ``hit``, ``junk``, or ``miss`` plus the chosen release."""
    usable: List[Dict[str, Any]] = []
    saw_junk = False
    for hit in hits or []:
        if not isinstance(hit, Mapping):
            continue
        if is_junk_multidisc(hit):
            saw_junk = True
            continue
        if is_confident_hit(sought, hit):
            usable.append(dict(hit))
    if usable:
        ranked = heuristic_rank(usable, sought)
        if ranked:
            return "hit", ranked[0]
    if saw_junk:
        return "junk", None
    return "miss", None


def _log_slow(row: Mapping[str, Any]) -> None:
    if int(row.get("miss_streak") or 0) != SLOW_AFTER_MISSES:
        return
    logger.info(
        "Wanted %s dropped to slow search after %s misses",
        row.get("id"),
        row.get("miss_streak"),
    )


def _note_miss(db: Database, wanted_id: str, *, now: float, from_status: str) -> None:
    updated = db.backoff_wanted(wanted_id, now=now, from_status=from_status)
    if updated is not None:
        _log_slow(updated)


def release_failed_wanted(db: Database, job_id: str, *, now: Optional[float] = None) -> None:
    """A failed or cleared slip returns its Wanted row to the backoff clock."""
    row = db.get_wanted_by_job(job_id)
    if row is None or row.get("status") != STATUS_ASKED:
        return
    moment = time.time() if now is None else float(now)
    _note_miss(db, str(row["id"]), now=moment, from_status=STATUS_ASKED)


def reconcile_asked(db: Database, *, now: float) -> int:
    """Failed or missing jobs unlock ``asked`` rows. Live slips stay locked."""
    released = 0
    for row in db.list_wanted(status=STATUS_ASKED):
        job_id = _text(row.get("job_id"))
        if not job_id:
            continue
        job = db.get_job(job_id)
        if job is not None and job.get("status") != "failed":
            continue
        _note_miss(db, str(row["id"]), now=now, from_status=STATUS_ASKED)
        released += 1
    return released


def _file_asked(
    db: Database,
    row: Mapping[str, Any],
    hit: Mapping[str, Any],
    sought: Mapping[str, Any],
    *,
    now: float,
) -> Optional[Dict[str, Any]]:
    payload = build_job_payload(
        sought=dict(sought),
        selected=dict(hit),
        rank_method="heuristic",
        rank_reason="wanted confident hit",
    )
    payload["source"] = "wanted"
    payload["wanted_id"] = row.get("id")
    job = {
        "status": "asked",
        "indexer_guid": payload.get("guid") or hit.get("guid"),
        "title": payload.get("title") or row.get("title") or hit.get("title"),
        "kind": sought.get("kind") or row.get("kind"),
        "requested_by": "wanted",
        "payload": payload,
    }
    return db.claim_and_create_wanted_job(str(row["id"]), job, now=now)


def poll_wanted(
    db: Database,
    settings: Settings,
    *,
    now: Optional[float] = None,
    client: Optional[NZBFinderClient] = None,
    search: Optional[SearchFn] = None,
) -> int:
    """Search due Wanted rows. Returns how many indexer calls this tick made.

    Does not confirm slips and does not call SABnzbd.
    """
    moment = time.time() if now is None else float(now)
    reconcile_asked(db, now=moment)
    due = db.list_due_wanted(now=moment, limit=MAX_SEARCHES_PER_TICK)
    if not due:
        return 0

    own_client = False
    finder = client
    if search is None and finder is None:
        token = _text(getattr(settings, "nzbfinder_api_token", ""))
        muted = bool(getattr(settings, "nzbfinder_muted", False))
        if not token or muted:
            return 0
        finder = NZBFinderClient(
            str(getattr(settings, "nzbfinder_url", "") or ""),
            token,
        )
        own_client = True

    def _default_search(sought: Mapping[str, Any]) -> List[Dict[str, Any]]:
        assert finder is not None
        return nzbfinder_search(finder, sought)

    run_search = search or _default_search
    calls = 0
    try:
        for row in due:
            fresh = db.get_wanted(str(row["id"]))
            if fresh is None or fresh.get("status") != "wanted":
                continue
            if float(fresh.get("next_search_at") or 0) > moment:
                continue
            sought = sought_for_row(fresh)
            if not sought["q"] or not sought["cat"]:
                db.postpone_wanted(str(fresh["id"]), now=moment, delay=BASE_BACKOFF_SECONDS)
                continue
            calls += 1
            try:
                hits = run_search(sought)
            except NZBFinderError as error:
                logger.info("Wanted search skipped for %s: %s", fresh.get("id"), error)
                db.postpone_wanted(str(fresh["id"]), now=moment, delay=BASE_BACKOFF_SECONDS)
                continue
            outcome, hit = choose_hit(sought, list(hits or []))
            if outcome == "hit" and hit is not None:
                _file_asked(db, fresh, hit, sought, now=moment)
                continue
            _note_miss(db, str(fresh["id"]), now=moment, from_status="wanted")
    finally:
        if own_client and finder is not None:
            finder.close()
    return calls
