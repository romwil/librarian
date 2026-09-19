"""Rank indexer hits: BYO LLM best-match when configured, else heuristic.

Used by Find beyond, Bestsellers chase, Review re-grab, and job candidate memory.
Never invents guids — pick must already exist in the candidate list.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from librarian.identify import tidy_title
from librarian.llm import LLMClient, LLMError, client_from_settings


def friendly_reason(error: BaseException) -> str:
    text = str(error or "").strip()
    if getattr(error, "rate_limited", False) or re.search(r"\b429\b|rate.?limit", text, re.I):
        return "rate-limited — using heuristic"
    return text or "LLM error"

logger = logging.getLogger(__name__)

MAX_CANDIDATES_REMEMBERED = 25
MAX_LLM_CANDIDATES = 20

RANK_PROMPT = """You pick the best Usenet/indexer release for a household library request.
Return ONLY JSON: {"guid":"<exact guid from the list or empty>","reason":"short why","ranked":["guid1","guid2"]}
Rules:
- Choose only a guid that appears in the candidate list. Never invent a guid.
- Prefer the correct title and author/artist over a wrong popular title.
- Prefer complete ebook/audiobook releases matching the requested kind.
- ranked is optional: best-first guids from the list (subset ok).
- If nothing matches, return {"guid":"","reason":"no match","ranked":[]}.
"""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _tokens(value: str) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9]+", " ", tidy_title(value).lower())
    return {tok for tok in cleaned.split() if len(tok) > 1}


def _hit_guid(hit: Mapping[str, Any]) -> str:
    return _text(hit.get("guid") or hit.get("indexer_guid"))


def compact_candidate(hit: Mapping[str, Any], *, rank: int = 0, note: str = "") -> Dict[str, Any]:
    """Safe subset stored on jobs / chase traces for dud-primary fallback."""
    out = {
        "guid": _hit_guid(hit),
        "title": _text(hit.get("title") or hit.get("book_title")),
        "book_title": _text(hit.get("book_title")),
        "author": _text(hit.get("author") or hit.get("artist")),
        "kind": _text(hit.get("kind")),
        "size": hit.get("size"),
        "category": hit.get("category"),
        "category_name": _text(hit.get("category_name")),
        "host_id": _text(hit.get("host_id")),
        "host_name": _text(hit.get("host_name") or hit.get("host") or hit.get("indexer")),
        "download_url": _text(hit.get("download_url")),
        "cover": _text(hit.get("cover")),
        "isbn": _text(hit.get("isbn")),
        "poster": _text(hit.get("poster")),
        "rank": int(rank) if rank else None,
        "note": _text(note),
    }
    return {key: value for key, value in out.items() if value not in (None, "", [])}


def remember_candidates(
    hits: Sequence[Mapping[str, Any]],
    *,
    limit: int = MAX_CANDIDATES_REMEMBERED,
    notes: Optional[Mapping[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Deduped compact list for job payload / disclosure (guid required)."""
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    note_map = dict(notes or {})
    for index, hit in enumerate(hits or []):
        if not isinstance(hit, Mapping):
            continue
        guid = _hit_guid(hit)
        if not guid or guid in seen:
            continue
        seen.add(guid)
        out.append(compact_candidate(hit, rank=index + 1, note=note_map.get(guid, "")))
        if len(out) >= max(0, int(limit)):
            break
    return out


def heuristic_score(sought: Mapping[str, Any], hit: Mapping[str, Any]) -> float:
    """Title/author token overlap — graceful degrade when LLM is off or fails."""
    want_title = _text(
        sought.get("title") or sought.get("album") or sought.get("series") or sought.get("q")
    )
    want_author = _text(sought.get("author") or sought.get("artist"))
    hit_title = _text(hit.get("book_title") or hit.get("title"))
    hit_author = _text(hit.get("author") or hit.get("artist"))
    score = 0.0
    want_t = _tokens(want_title)
    hit_t = _tokens(hit_title)
    if want_t and hit_t:
        score += 3.0 * (len(want_t & hit_t) / float(len(want_t | hit_t)))
    want_a = _tokens(want_author)
    hit_a = _tokens(hit_author)
    if want_a and hit_a:
        score += 2.0 * (len(want_a & hit_a) / float(len(want_a | hit_a)))
    want_isbn = _text(sought.get("isbn"))
    hit_isbn = _text(hit.get("isbn"))
    if want_isbn and hit_isbn and want_isbn == hit_isbn:
        score += 2.5
    if _hit_guid(hit):
        score += 0.05
    return score


def heuristic_rank(
    hits: Sequence[Mapping[str, Any]],
    sought: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    scored: List[tuple[float, Dict[str, Any]]] = []
    for hit in hits or []:
        if not isinstance(hit, Mapping):
            continue
        if not _hit_guid(hit):
            continue
        row = dict(hit)
        score = heuristic_score(sought, row)
        row["_rank_score"] = round(score, 4)
        scored.append((score, row))
    scored.sort(key=lambda pair: (-pair[0], str(pair[1].get("title") or "")))
    out: List[Dict[str, Any]] = []
    for _score, row in scored:
        row.pop("_rank_score", None)
        out.append(row)
    return out


def _llm_rank(
    llm: LLMClient,
    *,
    sought: Mapping[str, Any],
    hits: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Ask the model to pick/order guids. Fail closed to empty pick on errors."""
    compact = []
    for index, hit in enumerate(hits[:MAX_LLM_CANDIDATES]):
        compact.append(
            {
                "i": index,
                "guid": _hit_guid(hit),
                "title": _text(hit.get("title") or hit.get("book_title")),
                "author": _text(hit.get("author") or hit.get("artist")),
                "kind": _text(hit.get("kind")),
                "size": hit.get("size"),
                "host": _text(hit.get("host_name") or hit.get("host")),
            }
        )
    known = {row["guid"] for row in compact if row["guid"]}
    user = (
        "Sought:\n"
        + json_dumps_sought(sought)
        + "\n\nCandidates:\n"
        + _json_dumps(compact)
    )
    try:
        payload = llm.chat_json(system=RANK_PROMPT, user=user, temperature=0.1)
    except LLMError as error:
        return {
            "guid": "",
            "reason": friendly_reason(error),
            "ranked": [],
            "error": str(error),
            "rate_limited": bool(getattr(error, "rate_limited", False)),
        }
    if not isinstance(payload, dict):
        return {"guid": "", "reason": "LLM returned non-object", "ranked": []}
    guid = _text(payload.get("guid"))
    if guid and guid not in known:
        guid = ""
    ranked_raw = payload.get("ranked") if isinstance(payload.get("ranked"), list) else []
    ranked = [_text(item) for item in ranked_raw if _text(item) in known]
    return {
        "guid": guid,
        "reason": _text(payload.get("reason")),
        "ranked": ranked,
        "error": "",
    }


def json_dumps_sought(sought: Mapping[str, Any]) -> str:
    keys = ("kind", "title", "author", "isbn", "q", "series", "issue", "artist", "album", "year")
    slim = {key: _text(sought.get(key)) for key in keys if _text(sought.get(key))}
    return _json_dumps(slim)


def _json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def rank_beyond_hits(
    hits: Sequence[Mapping[str, Any]],
    sought: Optional[Mapping[str, Any]] = None,
    *,
    llm: Optional[LLMClient] = None,
    settings: Any = None,
    transport: Any = None,
) -> Dict[str, Any]:
    """Pick best hit + remember ordered candidates. LLM when configured, else heuristic.

    Returns:
      pick, candidates, method (llm|heuristic|empty), conversation, reason, error
    """
    sought_map: Dict[str, Any] = dict(sought or {})
    guid_hits = [dict(hit) for hit in hits or [] if isinstance(hit, Mapping) and _hit_guid(hit)]
    conversation: List[Dict[str, str]] = [
        {
            "role": "user",
            "content": f"Rank {len(guid_hits)} indexer hits for {json_dumps_sought(sought_map)}",
        }
    ]
    if not guid_hits:
        conversation.append({"role": "assistant", "content": "No requestable hits (missing guid)."})
        return {
            "pick": None,
            "candidates": [],
            "method": "empty",
            "conversation": conversation,
            "reason": "no guid hits",
            "error": "",
            "hits": [],
        }

    own_client = False
    client = llm
    if client is None and settings is not None:
        client = client_from_settings(settings, transport=transport)
        own_client = client is not None

    method = "heuristic"
    reason = ""
    error = ""
    ordered = heuristic_rank(guid_hits, sought_map)
    pick: Optional[Dict[str, Any]] = ordered[0] if ordered else None
    notes: Dict[str, str] = {}

    try:
        if client is not None and client.configured() and ordered:
            conversation.append(
                {
                    "role": "system",
                    "content": "BYO LLM ranking over full result titles/metadata.",
                }
            )
            llm_result = _llm_rank(client, sought=sought_map, hits=ordered)
            error = _text(llm_result.get("error"))
            reason = _text(llm_result.get("reason"))
            ranked_guids = list(llm_result.get("ranked") or [])
            pick_guid = _text(llm_result.get("guid"))
            by_guid = {_hit_guid(hit): hit for hit in ordered}
            rate_limited = bool(llm_result.get("rate_limited"))
            if ranked_guids:
                remapped = [by_guid[guid] for guid in ranked_guids if guid in by_guid]
                leftover = [hit for hit in ordered if _hit_guid(hit) not in set(ranked_guids)]
                ordered = remapped + leftover
            if pick_guid and pick_guid in by_guid:
                pick = by_guid[pick_guid]
                ordered = [pick] + [hit for hit in ordered if _hit_guid(hit) != pick_guid]
                method = "llm"
                notes[pick_guid] = reason or "LLM best match"
                conversation.append(
                    {
                        "role": "assistant",
                        "content": f"LLM pick guid={pick_guid}" + (f" — {reason}" if reason else ""),
                    }
                )
            elif rate_limited or error:
                conversation.append(
                    {
                        "role": "assistant",
                        "content": f"LLM unavailable ({reason or error}); using heuristic first hit.",
                    }
                )
                method = "heuristic"
                reason = reason or f"LLM failed: {error}"
                if rate_limited:
                    error = error or "rate-limited"
            else:
                conversation.append(
                    {
                        "role": "assistant",
                        "content": "LLM returned no usable guid; using heuristic first hit.",
                    }
                )
                method = "heuristic"
                reason = reason or "LLM no match; heuristic"
        else:
            conversation.append(
                {
                    "role": "assistant",
                    "content": "No BYO LLM — heuristic title/author ranking.",
                }
            )
            if pick:
                reason = "heuristic best token overlap"
                notes[_hit_guid(pick)] = reason
    finally:
        if own_client and client is not None:
            client.close()

    if pick and method == "heuristic" and not notes.get(_hit_guid(pick)):
        notes[_hit_guid(pick)] = reason or "heuristic"

    candidates = remember_candidates(ordered, notes=notes)
    conversation.append(
        {
            "role": "assistant",
            "content": (
                f"method={method} pick={_hit_guid(pick) if pick else 'none'} "
                f"candidates={len(candidates)}"
            ),
        }
    )
    return {
        "pick": pick,
        "candidates": candidates,
        "method": method,
        "conversation": conversation,
        "reason": reason,
        "error": error,
        "hits": ordered,
    }


def search_and_rank(
    settings: Any,
    *,
    transport: Any = None,
    llm: Optional[LLMClient] = None,
    **fields: Any,
) -> Dict[str, Any]:
    """Indexer search + rank. Attaches pick/candidates/conversation onto the traced search."""
    from librarian.indexers.hosts import search_beyond_traced
    from librarian.indexers.query import clean_sought

    traced = search_beyond_traced(settings, transport=transport, **fields)
    sought = clean_sought(fields)
    ranked = rank_beyond_hits(
        traced.get("hits") or [],
        sought,
        llm=llm,
        settings=settings if llm is None else None,
        transport=transport,
    )
    hits = list(ranked.get("hits") or traced.get("hits") or [])
    steps = list(traced.get("steps") or [])
    steps.append(
        {
            "step": "rank",
            "detail": f"method={ranked.get('method')} pick={_hit_guid(ranked.get('pick') or {}) or 'none'}",
        }
    )
    conversation = list(ranked.get("conversation") or [])
    results = list(traced.get("results") or [])
    if not results and hits:
        pick_guid = _hit_guid(ranked.get("pick") or {})
        for index, hit in enumerate(hits):
            guid = _hit_guid(hit)
            decision = "pick" if guid and guid == pick_guid else "alternate"
            results.append(
                {
                    "decision": decision,
                    "reason": str(ranked.get("reason") or ranked.get("method") or ""),
                    "title": _text(hit.get("title") or hit.get("book_title")),
                    "guid": guid,
                    "kind": _text(hit.get("kind")),
                    "host_name": _text(hit.get("host_name") or hit.get("host")),
                    "rank": index + 1,
                }
            )
    return {
        **traced,
        "hits": hits,
        "pick": ranked.get("pick"),
        "candidates": ranked.get("candidates") or [],
        "rank_method": ranked.get("method"),
        "rank_reason": ranked.get("reason") or "",
        "conversation": conversation,
        "steps": steps,
        "results": results,
        "sought": sought,
        "error": ranked.get("error") or traced.get("error"),
    }
