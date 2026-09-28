"""Public indexer disclosure — never ship api_token/apikey or raw Newznab blobs."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

from librarian.indexers.query import strip_secret_query

_DROP_KEYS = frozenset({"raw", "description"})
_URL_KEYS = ("download_url", "link", "cover", "url")


def public_indexer_hit(hit: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """Safe subset of a Find-beyond / queue hit for authenticated clients."""
    if not isinstance(hit, Mapping):
        return None
    out = {key: value for key, value in hit.items() if key not in _DROP_KEYS}
    for key in _URL_KEYS:
        if key in out:
            out[key] = strip_secret_query(str(out.get(key) or ""))
    return out


def public_indexer_hits(rows: Optional[Iterable[Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        scrubbed = public_indexer_hit(row if isinstance(row, Mapping) else None)
        if scrubbed is not None:
            out.append(scrubbed)
    return out


def public_job_payload(payload: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Scrub nested selected / candidates / URL fields on a persisted job payload."""
    if not isinstance(payload, Mapping):
        return {}
    out = {key: value for key, value in payload.items() if key not in _DROP_KEYS}
    for key in ("selected", "retrieved", "details"):
        nested = out.get(key)
        if isinstance(nested, Mapping):
            scrubbed = public_indexer_hit(nested)
            out[key] = scrubbed if scrubbed is not None else {}
    if isinstance(out.get("candidates"), list):
        out["candidates"] = public_indexer_hits(out["candidates"])
    for key in _URL_KEYS:
        if key in out:
            out[key] = strip_secret_query(str(out.get(key) or ""))
    return out


def public_job(job: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(job, Mapping):
        return None
    out = dict(job)
    payload = out.get("payload")
    if isinstance(payload, Mapping):
        out["payload"] = public_job_payload(payload)
    return out


def public_jobs(rows: Optional[Iterable[Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        scrubbed = public_job(row if isinstance(row, Mapping) else None)
        if scrubbed is not None:
            out.append(scrubbed)
    return out
