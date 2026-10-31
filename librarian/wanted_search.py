"""Recurring Wanted search. Files one Asked slip. Never calls SABnzbd.

Only ``wanted`` rows whose ``next_search_at`` has passed are searched. A newly
queued row is searched right away; after that the hourly pass walks every due
row. Each row walks the search ladder (ISBN, then title, then title and author)
and stops on a confident hit. A hit compare-and-sets the row to ``asked`` and
inserts one queue job. Overlapping searches lose that update and do not enqueue
again. Dismissed rows are never read here. A miss or a multi-disc junk archive
pushes the backoff clock. A 429 stops the pass and is not a miss.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Mapping, Optional

from librarian.config import Settings
from librarian.db import Database
from librarian.indexers.query import build_job_payload, search_ladder
from librarian.indexers.rank import heuristic_rank
from librarian.kinds import ALL_KINDS, search_category_for_kind
from librarian.nzbfinder import NZBFinderClient, NZBFinderError, is_rate_limited
from librarian.wanted import (
    BASE_BACKOFF_SECONDS,
    STATUS_ASKED,
    WantedError,
    is_confident_hit,
    is_junk_multidisc,
)

logger = logging.getLogger(__name__)

SearchFn = Callable[[Mapping[str, Any]], List[Dict[str, Any]]]

RATE_LIMITED_NOTE = "The indexer asked us to wait. The next hourly pass tries again."

# One hourly pass at a time, and one search per row at a time across the pass,
# a just-queued row, and Search selected.
_PASS_LOCK = threading.Lock()
_IN_FLIGHT: set[str] = set()
_IN_FLIGHT_LOCK = threading.Lock()


def _text(value: Any) -> str:
    return str(value or "").strip()


def sought_for_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    """What the row seeks. ``q`` is the first ladder rung, not every field at once."""
    kind = _text(row.get("kind")) or "audiobook"
    title = _text(row.get("title"))
    author = _text(row.get("author"))
    isbn = _text(row.get("isbn"))
    ladder = ladder_for_row(row)
    return {
        "kind": kind,
        "title": title,
        "author": author,
        "isbn": isbn,
        "q": ladder[0]["q"] if ladder else "",
        "cat": search_category_for_kind(kind) or "",
    }


def ladder_for_row(row: Mapping[str, Any]) -> List[Dict[str, str]]:
    """The row's search ladder as ``{rung, q}`` pairs, most exact first."""
    kind = _text(row.get("kind")) or "audiobook"
    plans = search_ladder(
        kind=kind,
        title=_text(row.get("title")),
        author=_text(row.get("author")),
        isbn=_text(row.get("isbn")),
    )
    return [
        {"rung": str(plan.get("rung") or ""), "q": str(plan.get("query") or "")}
        for plan in plans
        if str(plan.get("query") or "").strip()
    ]


def nzbfinder_search(client: NZBFinderClient, sought: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """NZBFinder category for this row. Audiobooks use 3030."""
    query = _text(sought.get("q"))
    cat = _text(sought.get("cat"))
    kind = _text(sought.get("kind"))
    if not query or not cat:
        return []
    return client.search(query, cat=cat, kind=kind or None, limit=25)


def search_wanted_hosts(
    settings: Settings,
    sought: Mapping[str, Any],
    *,
    transport: Any = None,
) -> List[Dict[str, Any]]:
    """One ladder rung against every enabled indexer. A 429 is raised; other host errors skip."""
    from librarian.indexers.hosts import enabled_hosts

    query = _text(sought.get("q"))
    cat = _text(sought.get("cat"))
    if not query or not cat:
        return []
    hits: List[Dict[str, Any]] = []
    seen: set[str] = set()
    last_error: Optional[NZBFinderError] = None
    for host in enabled_hosts(settings):
        client = NZBFinderClient(
            host["url"],
            host["api_token"],
            transport=transport,
            label=host["name"],
            dialect=host.get("dialect") or "",
        )
        try:
            batch = nzbfinder_search(client, sought)
        except NZBFinderError as error:
            if is_rate_limited(error):
                raise
            last_error = error
            continue
        finally:
            client.close()
        for hit in batch or []:
            if not isinstance(hit, Mapping):
                continue
            tagged = dict(hit)
            tagged["host_id"] = host["id"]
            tagged["host_name"] = host["name"]
            key = _text(tagged.get("guid") or tagged.get("indexer_guid")) or (
                f"{tagged.get('title')}:{tagged.get('size')}"
            )
            if not key or key in seen:
                continue
            seen.add(key)
            hits.append(tagged)
    if last_error is not None and not hits:
        raise last_error
    return hits


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


def _note_miss(db: Database, wanted_id: str, *, now: float, from_status: str) -> None:
    db.backoff_wanted(wanted_id, now=now, from_status=from_status)


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
    """One Wanted row, same rules as the poller. Does not call SABnzbd.

    A row another search is already walking is left alone.
    """
    wanted_id = str(row.get("id") or "")
    with _IN_FLIGHT_LOCK:
        if wanted_id in _IN_FLIGHT:
            return {"id": wanted_id, "outcome": "in_flight", "searched": False, "calls": 0}
        _IN_FLIGHT.add(wanted_id)
    try:
        result = _walk_row(db, row, now=now, run_search=run_search)
    finally:
        with _IN_FLIGHT_LOCK:
            _IN_FLIGHT.discard(wanted_id)
    result.setdefault("calls", 0)
    return result


def _walk_row(
    db: Database,
    row: Mapping[str, Any],
    *,
    now: float,
    run_search: SearchFn,
) -> Dict[str, Any]:
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
    ladder = ladder_for_row(fresh)
    if not ladder or not sought["cat"]:
        db.postpone_wanted(str(fresh["id"]), now=now, delay=BASE_BACKOFF_SECONDS)
        return {"id": wanted_id, "outcome": "skipped", "searched": False}
    calls = 0
    for rung in ladder:
        asked = {**sought, "q": rung["q"], "rung": rung["rung"]}
        calls += 1
        try:
            hits = run_search(asked)
        except NZBFinderError as error:
            note = str(error)
            if is_rate_limited(error):
                logger.info("Wanted search paused at %s: %s", fresh.get("id"), error)
                return {
                    "id": wanted_id,
                    "outcome": "rate_limited",
                    "note": RATE_LIMITED_NOTE,
                    "searched": True,
                    "calls": calls,
                }
            logger.info("Wanted search skipped for %s: %s", fresh.get("id"), error)
            db.postpone_wanted(str(fresh["id"]), now=now, delay=BASE_BACKOFF_SECONDS)
            outcome = "downloader" if "sabnzbd" in note.lower() else "indexer_error"
            return {
                "id": wanted_id,
                "outcome": outcome,
                "note": note,
                "searched": True,
                "calls": calls,
            }
        outcome, hit = choose_hit(sought, drop_bad_releases(db, list(hits or [])))
        if outcome != "hit" or hit is None:
            continue
        job = _file_asked(db, fresh, hit, sought, now=now)
        if job is None:
            current = db.get_wanted(wanted_id) or fresh
            return {
                "id": wanted_id,
                "outcome": "already_asked",
                "job_id": current.get("job_id"),
                "note": "Already on a slip",
                "searched": True,
                "calls": calls,
            }
        return {
            "id": wanted_id,
            "outcome": "hit",
            "job_id": job.get("id"),
            "note": "A hit is on a slip",
            "searched": True,
            "calls": calls,
        }
    _note_miss(db, str(fresh["id"]), now=now, from_status="wanted")
    return {
        "id": wanted_id,
        "outcome": "miss",
        "note": "Nothing found",
        "searched": True,
        "calls": calls,
    }


def _open_search(
    settings: Settings,
    search: Optional[SearchFn],
) -> tuple[SearchFn, Optional[NZBFinderClient], bool]:
    if search is not None:
        return search, None, False
    from librarian.indexers.hosts import enabled_hosts

    if not enabled_hosts(settings):
        raise WantedError("Beyond the shelves needs an NZBFinder token in Settings.")

    def _default_search(sought: Mapping[str, Any]) -> List[Dict[str, Any]]:
        return search_wanted_hosts(settings, sought)

    return _default_search, None, False


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
    paused = False
    try:
        for row in rows:
            if paused:
                results.append(
                    {"id": row.get("id"), "outcome": "rate_limited", "note": RATE_LIMITED_NOTE}
                )
                continue
            result = _consider_row(db, row, now=moment, run_search=run_search)
            result.pop("searched", None)
            result.pop("calls", None)
            results.append(result)
            paused = result.get("outcome") == "rate_limited"
    finally:
        if own_client and finder is not None:
            finder.close()
    return results


def search_queued_wanted(
    db: Database,
    settings: Settings,
    ids: List[str],
    *,
    now: Optional[float] = None,
    search: Optional[SearchFn] = None,
) -> List[Dict[str, Any]]:
    """Search rows that were just queued (add, reopen, audiobook sweep) right away.

    Rows not yet due are left alone. A miss starts the 6-hour walkoff, so the
    hourly pass does not search them again. Without an indexer token this is quiet.
    """
    chosen = [_text(item) for item in ids or [] if _text(item)]
    if not chosen:
        return []
    try:
        results = search_wanted_selection(db, settings, ids=chosen, now=now, search=search)
    except WantedError:
        return []
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
    should_stop: Optional[Callable[[], bool]] = None,
) -> int:
    """The hourly pass: walk every due Wanted row. Returns indexer calls made.

    A pass already walking means this call does nothing. A 429 ends the pass and
    leaves the rest for the next hour. Does not confirm slips or call SABnzbd.
    """
    if not _PASS_LOCK.acquire(blocking=False):
        return 0
    try:
        return _walk_due(
            db, settings, now=now, client=client, search=search, should_stop=should_stop
        )
    finally:
        _PASS_LOCK.release()


def _walk_due(
    db: Database,
    settings: Settings,
    *,
    now: Optional[float],
    client: Optional[NZBFinderClient],
    search: Optional[SearchFn],
    should_stop: Optional[Callable[[], bool]],
) -> int:
    moment = time.time() if now is None else float(now)
    reconcile_asked(db, now=moment)
    due = db.list_due_wanted(now=moment)
    if not due:
        return 0

    own_client = False
    finder = client
    if search is None and finder is None:
        from librarian.indexers.hosts import enabled_hosts

        if not enabled_hosts(settings):
            return 0

        def _hosts_search(sought: Mapping[str, Any]) -> List[Dict[str, Any]]:
            return search_wanted_hosts(settings, sought)

        run_search = _hosts_search
    elif search is None:
        assert finder is not None

        def _client_search(sought: Mapping[str, Any]) -> List[Dict[str, Any]]:
            return nzbfinder_search(finder, sought)

        run_search = _client_search
    else:
        run_search = search
    calls = 0
    try:
        for row in due:
            if should_stop is not None and should_stop():
                break
            result = _consider_row(db, row, now=moment, run_search=run_search)
            calls += int(result.get("calls") or 0)
            if result.get("outcome") == "rate_limited":
                logger.info("Wanted pass stopped on a 429; the rest wait for the next hour")
                break
    finally:
        if own_client and finder is not None:
            finder.close()
    return calls
