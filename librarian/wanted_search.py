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
from librarian.kinds import ALL_KINDS, search_category_for_kind
from librarian.nzbfinder import NZBFinderClient, NZBFinderError
from librarian.wanted import (
    BASE_BACKOFF_SECONDS,
    SLOW_AFTER_MISSES,
    STATUS_ASKED,
    WantedError,
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


def drop_bad_releases(db: Database, hits: List[Any]) -> List[Any]:
    """Never pick a release that already came back empty or would not convert."""
    from librarian.db import safe_release_guid

    bad = db.bad_indexer_guids()
    if not bad:
        return list(hits or [])
    kept = []
    for hit in hits or []:
        if isinstance(hit, Mapping):
            guid = safe_release_guid(hit.get("guid") or hit.get("indexer_guid"))
            if guid and guid in bad:
                continue
        kept.append(hit)
    return kept


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


def _consider_row(
    db: Database,
    row: Mapping[str, Any],
    *,
    now: float,
    run_search: SearchFn,
) -> Dict[str, Any]:
    """One Wanted row, same rules as the poller. Does not call SABnzbd."""
    fresh = db.get_wanted(str(row.get("id") or ""))
    wanted_id = str((fresh or row).get("id") or "")
    if fresh is None or fresh.get("status") == "dismissed":
        return {"id": wanted_id, "outcome": "missing", "searched": False}
    if fresh.get("status") == STATUS_ASKED:
        return {
            "id": wanted_id,
            "outcome": "already_asked",
            "job_id": fresh.get("job_id"),
            "note": "Already on a slip",
            "searched": False,
        }
    if fresh.get("status") != "wanted":
        return {"id": wanted_id, "outcome": "skipped", "searched": False}
    if float(fresh.get("next_search_at") or 0) > now:
        return {
            "id": wanted_id,
            "outcome": "not_due",
            "next_search_at": fresh.get("next_search_at"),
            "searched": False,
        }
    sought = sought_for_row(fresh)
    if not sought["q"] or not sought["cat"]:
        db.postpone_wanted(str(fresh["id"]), now=now, delay=BASE_BACKOFF_SECONDS)
        return {"id": wanted_id, "outcome": "skipped", "searched": False}
    try:
        hits = run_search(sought)
    except NZBFinderError as error:
        logger.info("Wanted search skipped for %s: %s", fresh.get("id"), error)
        db.postpone_wanted(str(fresh["id"]), now=now, delay=BASE_BACKOFF_SECONDS)
        note = str(error)
        outcome = "downloader" if "sabnzbd" in note.lower() else "indexer_error"
        return {
            "id": wanted_id,
            "outcome": outcome,
            "note": note,
            "searched": True,
        }
    outcome, hit = choose_hit(sought, drop_bad_releases(db, list(hits or [])))
    if outcome == "hit" and hit is not None:
        job = _file_asked(db, fresh, hit, sought, now=now)
        if job is None:
            current = db.get_wanted(wanted_id) or fresh
            return {
                "id": wanted_id,
                "outcome": "already_asked",
                "job_id": current.get("job_id"),
                "note": "Already on a slip",
                "searched": True,
            }
        return {
            "id": wanted_id,
            "outcome": "hit",
            "job_id": job.get("id"),
            "note": "A hit is on a slip",
            "searched": True,
        }
    _note_miss(db, str(fresh["id"]), now=now, from_status="wanted")
    return {
        "id": wanted_id,
        "outcome": "miss",
        "note": "Nothing found",
        "searched": True,
    }


def _open_search(
    settings: Settings,
    search: Optional[SearchFn],
) -> tuple[SearchFn, Optional[NZBFinderClient], bool]:
    if search is not None:
        return search, None, False
    token = _text(getattr(settings, "nzbfinder_api_token", ""))
    muted = bool(getattr(settings, "nzbfinder_muted", False))
    if not token or muted:
        raise WantedError("Beyond the shelves needs an NZBFinder token in Settings.")
    finder = NZBFinderClient(
        str(getattr(settings, "nzbfinder_url", "") or ""),
        token,
    )

    def _default_search(sought: Mapping[str, Any]) -> List[Dict[str, Any]]:
        return nzbfinder_search(finder, sought)

    return _default_search, finder, True


def search_wanted_selection(
    db: Database,
    settings: Settings,
    *,
    ids: Optional[List[str]] = None,
    all_rows: bool = False,
    kind: str = "",
    now: Optional[float] = None,
    search: Optional[SearchFn] = None,
) -> List[Dict[str, Any]]:
    """Search the chosen rows, or every open row of one kind. Same work as the poller."""
    moment = time.time() if now is None else float(now)
    chosen = [str(item or "").strip() for item in (ids or []) if str(item or "").strip()]
    if chosen:
        rows = []
        for wanted_id in chosen:
            row = db.get_wanted(wanted_id)
            rows.append(row or {"id": wanted_id, "status": "dismissed"})
    elif all_rows:
        kind_key = _text(kind).lower()
        if kind_key and kind_key not in ALL_KINDS:
            raise WantedError("Unknown Wanted kind")
        rows = db.list_wanted(kind=kind_key or None)
    else:
        raise WantedError("Choose rows or search all")
    if not rows:
        return []
    run_search, finder, own_client = _open_search(settings, search)
    results: List[Dict[str, Any]] = []
    try:
        for row in rows:
            result = _consider_row(db, row, now=moment, run_search=run_search)
            result.pop("searched", None)
            results.append(result)
    finally:
        if own_client and finder is not None:
            finder.close()
    return results


def beyond_wanted(
    db: Database,
    settings: Settings,
    wanted_id: str,
    *,
    data_dir: Any = None,
) -> Dict[str, Any]:
    """Indexer search for one Wanted row. Shows hits. Does not file a slip."""
    from librarian.indexers.rank import search_and_rank
    from librarian.indexers.scrub import public_indexer_hit, public_indexer_hits
    from librarian.llm import friendly_llm_error

    row = db.get_wanted(str(wanted_id or "").strip())
    if row is None or row.get("status") == "dismissed":
        raise WantedError("Wanted row not found")
    sought = sought_for_row(row)
    ranked = search_and_rank(
        settings,
        data_dir=data_dir,
        kind=sought["kind"],
        q=sought["q"],
        title=sought["title"],
        author=sought["author"],
        isbn=sought["isbn"],
    )
    beyond_error = ranked.get("error")
    if beyond_error:
        beyond_error = friendly_llm_error(RuntimeError(str(beyond_error)))
    pick = ranked.get("pick")
    if isinstance(pick, dict) and not drop_bad_releases(db, [pick]):
        pick = None
    return {
        "id": row.get("id"),
        "hits": public_indexer_hits(drop_bad_releases(db, list(ranked.get("hits") or []))),
        "candidates": public_indexer_hits(
            drop_bad_releases(db, list(ranked.get("candidates") or []))
        ),
        "pick": public_indexer_hit(pick) if isinstance(pick, dict) else None,
        "beyond_error": beyond_error,
        "rank_method": str(ranked.get("rank_method") or ""),
        "rank_reason": str(ranked.get("rank_reason") or ""),
    }


def ask_wanted_hit(
    db: Database,
    wanted_id: str,
    hit: Mapping[str, Any],
    *,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """File one Asked slip for a hit the house picked. A second call does not enqueue."""
    from librarian.wanted import public_wanted

    moment = time.time() if now is None else float(now)
    row = db.get_wanted(str(wanted_id or "").strip())
    if row is None or row.get("status") == "dismissed":
        raise WantedError("Wanted row not found")
    if row.get("status") == STATUS_ASKED:
        return {
            "outcome": "already_asked",
            "note": "Already on a slip",
            "job_id": row.get("job_id"),
            "item": public_wanted(row),
        }
    if row.get("status") != "wanted":
        raise WantedError("Wanted row not found")
    if not _text(hit.get("guid") or hit.get("indexer_guid")):
        raise WantedError("This release is missing its id")
    sought = sought_for_row(row)
    job = _file_asked(db, row, hit, sought, now=moment)
    fresh = db.get_wanted(str(row["id"])) or row
    if job is None:
        return {
            "outcome": "already_asked",
            "note": "Already on a slip",
            "job_id": fresh.get("job_id"),
            "item": public_wanted(fresh),
        }
    return {
        "outcome": "hit",
        "note": "A hit is on a slip",
        "job_id": job.get("id"),
        "item": public_wanted(fresh),
    }


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
            result = _consider_row(db, row, now=moment, run_search=run_search)
            if result.get("searched"):
                calls += 1
    finally:
        if own_client and finder is not None:
            finder.close()
    return calls
