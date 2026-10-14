"""In-situ Review slip search and retrieve.

Smart re-grab replays the remembered title, author, and rank and queues a better
release on the slip. Request new version searches for a different release
(English retail EPUB when the accepted hit is the wrong language) and queues that.
Neither action sends the household to Find.

Owner and op grabs go straight to SABnzbd. Readers file an Asked slip. A slip
that already has an active job is not sent again. If the downloader is
unreachable, the search does not run.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional

from librarian.config import Settings
from librarian.db import Database
from librarian.delight import rank_regrab_candidates
from librarian.indexers.hosts import enabled_hosts
from librarian.indexers.rank import remember_candidates, search_and_rank
from librarian.indexers.scrub import public_indexer_hit, public_indexer_hits, public_job
from librarian.jobs import ACTIVE_STATUSES, enqueue_indexer_item
from librarian.kinds import search_category_for_kind
from librarian.nzbfinder import NZBFinderError
from librarian.sabnzbd import SABClient, SABError

INTENT_REGRAB = "regrab"
INTENT_NEW_VERSION = "new_version"
_INTENTS = {INTENT_REGRAB, INTENT_NEW_VERSION}

_NON_ENGLISH = re.compile(
    r"(?ix)\b("
    r"german|deutsch|deutsche|french|francais|français|spanish|espanol|español|"
    r"italian|italiano|dutch|nederlands|portuguese|português|russian|polish|"
    r"swedish|norwegian|danish|finnish|chinese|japanese|korean"
    r")\b"
)
_ENGLISH = re.compile(r"(?i)\b(?:english|eng)\b")
_RETAIL = re.compile(r"(?i)\bretail\b")
_EPUB = re.compile(r"(?i)\bepub\b")


class SlipDownError(Exception):
    """Downloader is unreachable. The indexer was not queried."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _text(value: Any) -> str:
    return str(value or "").strip()


def release_blob(hit: Mapping[str, Any]) -> str:
    return " ".join(
        _text(hit.get(key))
        for key in ("title", "book_title", "category_name", "author")
        if _text(hit.get(key))
    )


def looks_non_english(text: str) -> bool:
    return bool(_NON_ENGLISH.search(text or ""))


def english_retail_score(hit: Mapping[str, Any], *, want_epub: bool) -> int:
    """Higher when the release looks like an English retail EPUB."""
    blob = release_blob(hit)
    score = 0
    if _ENGLISH.search(blob):
        score += 4
    if want_epub and _EPUB.search(blob):
        score += 3
    if want_epub and _RETAIL.search(blob):
        score += 2
    if looks_non_english(blob):
        score -= 8
    return score


def _sab_message(error: BaseException) -> str:
    text = _text(error) or "did not answer"
    if "sabnzbd" not in text.lower():
        return f"SABnzbd did not answer: {text}"
    return text


def _query(work: Mapping[str, Any]) -> str:
    return " ".join(
        part
        for part in (_text(work.get("title")), _text(work.get("author")))
        if part
    )


def _accepted_blob(db: Database, work: Mapping[str, Any]) -> str:
    parts = [_text(work.get("title")), _text(work.get("author"))]
    guid = _text(work.get("indexer_guid"))
    if guid:
        prior = db.get_job_by_indexer_guid(guid)
        if prior:
            raw_payload = prior.get("payload")
            payload = raw_payload if isinstance(raw_payload, dict) else {}
            raw_selected = payload.get("selected")
            selected = raw_selected if isinstance(raw_selected, dict) else {}
            parts.append(_text(selected.get("title")))
            parts.append(_text(prior.get("title")))
            parts.append(_text(prior.get("nzo_name")))
    return " ".join(part for part in parts if part)


def _failed_context(db: Database, work: Mapping[str, Any]) -> tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
    failed_guid = _text(work.get("indexer_guid"))
    failed: Dict[str, Any] = {
        "guid": failed_guid,
        "title": _text(work.get("title")),
        "host": "",
        "size": None,
    }
    remembered: List[Dict[str, Any]] = []
    if failed_guid:
        prior = db.get_job_by_indexer_guid(failed_guid)
        if prior:
            raw_payload = prior.get("payload")
            payload = raw_payload if isinstance(raw_payload, dict) else {}
            raw_selected = payload.get("selected")
            selected = raw_selected if isinstance(raw_selected, dict) else {}
            if selected.get("title"):
                failed["title"] = _text(selected.get("title"))
            if selected.get("size") is not None:
                failed["size"] = selected.get("size")
            elif prior.get("bytes") is not None:
                failed["size"] = prior.get("bytes")
            failed["host"] = _text(
                selected.get("host_name") or selected.get("host") or selected.get("indexer")
            )
            if isinstance(payload.get("candidates"), list):
                remembered = remember_candidates(payload["candidates"])
    return failed_guid, failed, remembered


def active_job_for_slip(db: Database, work_id: str) -> Optional[Dict[str, Any]]:
    wid = _text(work_id)
    if not wid:
        return None
    for job in db.list_jobs(statuses=ACTIVE_STATUSES, limit=80):
        if _text(job.get("work_id")) == wid:
            return job
    return None


def _friendly_beyond(error: Any) -> Optional[str]:
    if not error:
        return None
    from librarian.llm import friendly_llm_error

    return friendly_llm_error(RuntimeError(str(error)))


def _search(
    settings: Settings,
    *,
    transport: Any,
    data_dir: Any,
    work: Mapping[str, Any],
    q: str,
) -> Dict[str, Any]:
    return search_and_rank(
        settings,
        transport=transport,
        data_dir=data_dir,
        q=q,
        kind=_text(work.get("kind")),
        title=_text(work.get("title")),
        author=_text(work.get("author")),
        isbn=_text(work.get("isbn")),
    )


def _merge_hits(primary: List[Dict[str, Any]], extra: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = {_text(row.get("guid")) for row in primary}
    out = list(primary)
    for row in extra:
        guid = _text(row.get("guid"))
        if not guid or guid in seen:
            continue
        out.append(dict(row))
        seen.add(guid)
    return out


def _english_followup(
    settings: Settings,
    *,
    transport: Any,
    work: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    """One extra indexer query for an English retail file when the first page is the wrong language."""
    hosts = enabled_hosts(settings)
    if not hosts:
        return []
    kind = _text(work.get("kind"))
    want_epub = kind in {"book", "magazine"}
    tail = "english epub" if want_epub else "english"
    query = " ".join(part for part in (_text(work.get("title")), _text(work.get("author")), tail) if part)
    cat = search_category_for_kind(kind)
    from librarian.indexers import hosts as hostmod

    found: List[Dict[str, Any]] = []
    for host in hosts:
        client = hostmod.NZBFinderClient(
            host["url"],
            host["api_token"],
            transport=transport,
            label=host["name"],
        )
        try:
            rows = client.search(query, cat=cat, kind=kind or None, limit=25)
        except NZBFinderError:
            rows = []
        finally:
            client.close()
        for row in rows:
            if isinstance(row, dict):
                tagged = dict(row)
                tagged.setdefault("host_id", host["id"])
                tagged.setdefault("host_name", host["name"])
                found.append(tagged)
    return found


def _order_new_version(
    hits: List[Dict[str, Any]],
    *,
    failed_guid: str,
    exclude: set[str],
    accepted_blob: str,
    want_epub: bool,
) -> List[Dict[str, Any]]:
    wrong = looks_non_english(accepted_blob)
    ranked: List[tuple[tuple[int, int], Dict[str, Any]]] = []
    seen = set()
    for raw in hits:
        guid = _text(raw.get("guid"))
        if not guid or guid == failed_guid or guid in exclude or guid in seen:
            continue
        seen.add(guid)
        item = dict(raw)
        lang = english_retail_score(item, want_epub=want_epub)
        # Wrong-language accepts: language first. Otherwise keep indexer order, still prefer English EPUB.
        key = (lang, 0) if wrong else (0, lang)
        item["diff"] = release_blob(item) or item.get("title") or "Release"
        ranked.append((key, item))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return [item for _key, item in ranked]


def gather_releases(
    db: Database,
    settings: Settings,
    work: Mapping[str, Any],
    *,
    intent: str,
    transport: Any = None,
    data_dir: Any = None,
) -> Dict[str, Any]:
    """Search for slip releases. Does not call SABnzbd."""
    failed_guid, failed_ctx, remembered = _failed_context(db, work)
    exclude = set(db.tried_indexer_guids_for_work(work))
    q = _query(work)
    beyond_error = None
    rank_method = ""
    rank_reason = ""
    search_trace = None
    ranked_memory: List[Dict[str, Any]] = []
    hits: List[Dict[str, Any]] = []

    if intent == INTENT_REGRAB and remembered:
        hits = [row for row in remembered if _text(row.get("guid")) not in exclude]

    if intent == INTENT_NEW_VERSION or len(hits) < 3:
        ranked = _search(settings, transport=transport, data_dir=data_dir, work=work, q=q)
        beyond_error = _friendly_beyond(ranked.get("error"))
        rank_method = _text(ranked.get("rank_method"))
        rank_reason = _text(ranked.get("rank_reason"))
        ranked_memory = list(ranked.get("candidates") or [])
        search_trace = {
            "conversation": list(ranked.get("conversation") or []),
            "steps": list(ranked.get("steps") or []),
            "results": list(ranked.get("results") or []),
            "rank_method": rank_method,
            "rank_reason": rank_reason,
        }
        seen = {_text(row.get("guid")) for row in hits}
        for row in list(ranked.get("hits") or []):
            guid = _text(row.get("guid"))
            if not guid or guid in seen or guid in exclude:
                continue
            hits.append(dict(row))
            seen.add(guid)

    accepted = _accepted_blob(db, work)
    want_epub = _text(work.get("kind")) in {"book", "magazine"}
    if intent == INTENT_NEW_VERSION:
        ordered = _order_new_version(
            hits,
            failed_guid=failed_guid,
            exclude=exclude,
            accepted_blob=accepted,
            want_epub=want_epub,
        )
        needs_english = looks_non_english(accepted) and not any(
            english_retail_score(row, want_epub=want_epub) > 0 for row in ordered
        )
        if needs_english:
            extra = _english_followup(settings, transport=transport, work=work)
            hits = _merge_hits(hits, extra)
            ordered = _order_new_version(
                hits,
                failed_guid=failed_guid,
                exclude=exclude,
                accepted_blob=accepted,
                want_epub=want_epub,
            )
        candidates = ordered[:8]
    else:
        candidates = rank_regrab_candidates(
            hits,
            failed_guid=failed_guid,
            failed=failed_ctx,
            exclude_guids=list(exclude),
            limit=3,
        )

    memory = ranked_memory or remember_candidates(hits)
    return {
        "candidates": candidates,
        "remembered_candidates": memory,
        "beyond_error": beyond_error,
        "rank_method": rank_method,
        "rank_reason": rank_reason,
        "search_trace": search_trace,
        "repair_fail_count": int(work.get("repair_fail_count") or 0),
    }


def _label(hit: Mapping[str, Any]) -> str:
    title = _text(hit.get("title") or hit.get("book_title")) or "release"
    return title


def _queue_hit(
    db: Database,
    settings: Settings,
    work: Mapping[str, Any],
    hit: Mapping[str, Any],
    bag: Mapping[str, Any],
    *,
    role: str,
    requested_by: str,
    sab: Optional[SABClient],
) -> Dict[str, Any]:
    selected = dict(hit)
    kind = _text(work.get("kind") or selected.get("kind"))
    title = _text(work.get("title") or selected.get("book_title") or selected.get("title"))
    author = _text(work.get("author") or selected.get("author"))
    item = {
        "title": title,
        "author": author,
        "kind": kind,
        "isbn": _text(work.get("isbn") or selected.get("isbn")),
        "guid": _text(selected.get("guid")),
        "download_url": _text(selected.get("download_url")),
        "category": selected.get("category"),
        "size": selected.get("size"),
        "host_id": _text(selected.get("host_id")),
        "host_name": _text(selected.get("host_name")),
        "selected": selected,
        "sought": {
            "kind": kind,
            "title": title,
            "author": author,
            "isbn": _text(work.get("isbn")),
            "q": _query(work),
        },
        "candidates": list(bag.get("remembered_candidates") or bag.get("candidates") or []),
        "rank_method": _text(bag.get("rank_method")),
        "rank_reason": _text(bag.get("rank_reason")),
    }
    job = enqueue_indexer_item(
        db,
        settings,
        item=item,
        requested_by=requested_by,
        role=role,
        sab=sab,
    )
    linked = db.update_job(str(job["id"]), work_id=_text(work.get("id")))
    return linked or job


def _empty_note(intent: str) -> str:
    if intent == INTENT_REGRAB:
        return "No better release in the remembered search."
    return "No other release turned up for this slip."


def _queued_note(job: Mapping[str, Any], hit: Mapping[str, Any]) -> str:
    title = _label(hit)
    if _text(job.get("status")) == "asked":
        return f"Asked for {title}. Confirm it on the queue."
    return f"Queued {title}."


def retrieve_slip_release(
    db: Database,
    settings: Settings,
    *,
    work_id: str,
    intent: str,
    role: str,
    requested_by: str,
    transport: Any = None,
    data_dir: Any = None,
    sab: Optional[SABClient] = None,
) -> Dict[str, Any]:
    """Search on the slip and queue the chosen release. Raises SlipDownError before search."""
    key = _text(intent)
    if key not in _INTENTS:
        raise ValueError("Unknown slip retrieve")
    work = db.get_work(work_id)
    if work is None:
        raise ValueError("Work not found")

    active = active_job_for_slip(db, work_id)
    if active is not None:
        return {
            "intent": key,
            "searched": False,
            "ready": False,
            "queued": False,
            "already_active": True,
            "candidates": [],
            "chosen": None,
            "job": public_job(active),
            "sab_error": None,
            "beyond_error": None,
            "note": "A download for this slip is already active.",
            "search_trace": None,
            "rank_method": "",
            "rank_reason": "",
            "remembered_candidates": [],
        }

    own_sab = False
    client = sab
    if role != "reader":
        if client is None:
            client = SABClient(settings.sabnzbd_url, settings.sabnzbd_api_key)
            own_sab = True
        try:
            client.queue()
        except SABError as error:
            if own_sab:
                client.close()
            raise SlipDownError(_sab_message(error)) from error

    try:
        bag = gather_releases(
            db,
            settings,
            work,
            intent=key,
            transport=transport,
            data_dir=data_dir,
        )
        candidates = list(bag.get("candidates") or [])
        chosen = candidates[0] if candidates else None
        sab_error = None
        job = None
        queued = False
        if chosen is None:
            note = bag.get("beyond_error") or _empty_note(key)
        else:
            try:
                job = _queue_hit(
                    db,
                    settings,
                    work,
                    chosen,
                    bag,
                    role=role,
                    requested_by=requested_by,
                    sab=client,
                )
                queued = True
                note = _queued_note(job, chosen)
            except (SABError, NZBFinderError) as error:
                sab_error = _sab_message(error)
                note = sab_error
    finally:
        if own_sab and client is not None:
            client.close()

    return {
        "intent": key,
        "searched": True,
        "ready": True,
        "queued": queued,
        "already_active": False,
        "candidates": public_indexer_hits(candidates),
        "chosen": public_indexer_hit(chosen) if isinstance(chosen, dict) else None,
        "job": public_job(job),
        "sab_error": sab_error,
        "beyond_error": bag.get("beyond_error"),
        "note": note,
        "search_trace": bag.get("search_trace"),
        "rank_method": bag.get("rank_method") or "",
        "rank_reason": bag.get("rank_reason") or "",
        "remembered_candidates": public_indexer_hits(bag.get("remembered_candidates") or []),
        "repair_fail_count": bag.get("repair_fail_count") or 0,
    }
