"""NZBFinder plus extra Newznab hosts. Fail closed per host; merge by guid."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from librarian.config import Settings
from librarian.indexers.query import run_plan_traced
from librarian.indexers.scrub import public_indexer_hit
from librarian.nzbfinder import (
    DIALECT_NEWZNAB,
    DIALECT_V2,
    NZBFinderClient,
    NZBFinderError,
    _hit_summary,
    infer_newznab_dialect,
    is_classic_newznab_host,
    is_rate_limited,
)

NZBFINDER_ID = "nzbfinder"
DRUNKENSLUG_ID = "drunkenslug"
DRUNKENSLUG_NAME = "DrunkenSlug"
DRUNKENSLUG_URL = "https://drunkenslug.com"
DRUNKENSLUG_PRESET = {
    "id": DRUNKENSLUG_ID,
    "name": DRUNKENSLUG_NAME,
    "url": DRUNKENSLUG_URL,
    "dialect": DIALECT_NEWZNAB,
}
MAX_EXTRA_INDEXERS = 12
_DIALECTS = frozenset({DIALECT_V2, DIALECT_NEWZNAB})


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "on"}


def _extra_dialect(item: Mapping[str, Any], url: str) -> str:
    dialect = infer_newznab_dialect(
        url,
        dialect=_text(item.get("dialect")),
        label=_text(item.get("name")),
    )
    return dialect if dialect in _DIALECTS else ""


def normalize_extra_indexers(raw: Any) -> List[Dict[str, Any]]:
    """Keep extra hosts as a list of {id, name, url, api_token, enabled, dialect}."""
    data = raw
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        url = _text(item.get("url") or item.get("base_url")).rstrip("/")
        if not url:
            continue
        name = _text(item.get("name")) or "Indexer"
        indexer_id = _text(item.get("id"))
        if indexer_id == NZBFINDER_ID:
            indexer_id = ""
        if not indexer_id:
            if is_classic_newznab_host(url) and DRUNKENSLUG_ID not in seen:
                indexer_id = DRUNKENSLUG_ID
            else:
                indexer_id = uuid.uuid4().hex
        if indexer_id in seen:
            indexer_id = uuid.uuid4().hex
        seen.add(indexer_id)
        if not name or name == "Indexer":
            if indexer_id == DRUNKENSLUG_ID or is_classic_newznab_host(url):
                name = DRUNKENSLUG_NAME
        out.append(
            {
                "id": indexer_id,
                "name": name[:80],
                "url": url,
                "api_token": _text(item.get("api_token")),
                "enabled": _as_bool(item.get("enabled"), True),
                "dialect": _extra_dialect(item, url),
            }
        )
        if len(out) >= MAX_EXTRA_INDEXERS:
            break
    return out


def merge_extra_indexers(incoming: Any, existing: Any) -> List[Dict[str, Any]]:
    """Blank extra-host tokens keep the stored value (same as other secrets)."""
    current = {row["id"]: row for row in normalize_extra_indexers(existing)}
    merged: List[Dict[str, Any]] = []
    for row in normalize_extra_indexers(incoming):
        previous = current.get(row["id"], {})
        if not row["api_token"]:
            row["api_token"] = _text(previous.get("api_token"))
        merged.append(row)
    return merged


def mask_extra_indexers(raw: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in normalize_extra_indexers(raw):
        token = _text(row.get("api_token"))
        out.append(
            {
                "id": row["id"],
                "name": row["name"],
                "url": row["url"],
                "enabled": bool(row.get("enabled", True)),
                "api_token": "",
                "api_token_set": bool(token),
                "dialect": _text(row.get("dialect")),
            }
        )
    return out


def enabled_hosts(settings: Settings) -> List[Dict[str, str]]:
    """Hosts with a URL and token. NZBFinder stays first when configured and unmuted."""
    hosts: List[Dict[str, str]] = []
    nzb_token = _text(getattr(settings, "nzbfinder_api_token", ""))
    nzb_url = _text(getattr(settings, "nzbfinder_url", ""))
    nzb_muted = bool(getattr(settings, "nzbfinder_muted", False))
    if nzb_token and nzb_url and not nzb_muted:
        hosts.append(
            {
                "id": NZBFINDER_ID,
                "name": "NZBFinder",
                "url": nzb_url,
                "api_token": nzb_token,
                "dialect": DIALECT_V2,
            }
        )
    for row in normalize_extra_indexers(getattr(settings, "extra_indexers", [])):
        if not row.get("enabled"):
            continue
        if not row.get("api_token") or not row.get("url"):
            continue
        hosts.append(
            {
                "id": row["id"],
                "name": row["name"],
                "url": row["url"],
                "api_token": row["api_token"],
                "dialect": _text(row.get("dialect")),
            }
        )
    return hosts


def client_for_host(
    settings: Settings,
    host_id: str = "",
    *,
    transport: Optional[Any] = None,
) -> NZBFinderClient:
    wanted = _text(host_id) or NZBFINDER_ID
    for host in enabled_hosts(settings):
        if host["id"] == wanted:
            return NZBFinderClient(
                host["url"],
                host["api_token"],
                transport=transport,
                label=host["name"],
                dialect=host.get("dialect") or "",
            )
    return NZBFinderClient(
        getattr(settings, "nzbfinder_url", ""),
        getattr(settings, "nzbfinder_api_token", ""),
        transport=transport,
        label="NZBFinder",
        dialect=DIALECT_V2,
    )


def _hit_key(item: Dict[str, Any]) -> str:
    guid = _text(item.get("guid"))
    if guid:
        return f"guid:{guid}"
    title = _text(item.get("title"))
    size = item.get("size")
    return f"title:{title}:size:{size}"


def _record_probe(
    data_dir: Optional[Path],
    *,
    host: Mapping[str, Any],
    ok: bool,
    latency_ms: Optional[float],
    hit_count: int = 0,
    error: str = "",
    rate_limited: bool = False,
    kind: str = "",
) -> None:
    if data_dir is None:
        return
    try:
        from librarian.indexer_scorecard import record_host_probe

        record_host_probe(
            Path(data_dir),
            host_id=str(host.get("id") or ""),
            host_name=str(host.get("name") or ""),
            ok=ok,
            latency_ms=latency_ms,
            hit_count=hit_count,
            error=error,
            rate_limited=rate_limited,
            kind=kind,
        )
    except Exception:  # noqa: BLE001 — scorecard must never break Find
        return


def search_beyond(
    settings: Settings,
    *,
    transport: Optional[Any] = None,
    data_dir: Optional[Path] = None,
    **fields: Any,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Query every enabled host. One 502 must not blank the others."""
    traced = search_beyond_traced(settings, transport=transport, data_dir=data_dir, **fields)
    return traced["hits"], traced.get("error")


def search_beyond_traced(
    settings: Settings,
    *,
    transport: Optional[Any] = None,
    data_dir: Optional[Path] = None,
    **fields: Any,
) -> Dict[str, Any]:
    """Beyond search with a decision trail for Bestsellers chase diagnostics.

    Walks the search ladder one precise query at a time and stops once a rung
    returns a confident hit. A host that errors is not asked again this search.
    """
    from librarian.indexers.match import is_confident_match
    from librarian.indexers.query import search_ladder

    ladder = search_ladder(**fields)
    plan = ladder[0] if ladder else None
    hosts = enabled_hosts(settings)
    steps: List[Dict[str, str]] = []
    if plan is None:
        steps.append({"step": "plan", "detail": "nothing to seek"})
        return {
            "hits": [],
            "error": None,
            "plan": None,
            "steps": steps,
            "results": [],
            "raw_count": 0,
            "rejected_count": 0,
        }
    if not hosts:
        steps.append({"step": "plan", "detail": _plan_detail(plan)})
        steps.append({"step": "hosts", "detail": "NZBFinder api_token is not configured"})
        return {
            "hits": [],
            "error": "NZBFinder api_token is not configured",
            "plan": plan,
            "plans": [plan],
            "steps": steps,
            "results": [],
            "raw_count": 0,
            "rejected_count": 0,
        }

    hits: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    errors: List[str] = []
    seen: set[str] = set()
    raw_count = 0
    rejected_count = 0
    probe_kind = _text(fields.get("kind"))
    sought = plan.get("sought") or {}
    walked: List[Dict[str, Any]] = []
    failed_hosts: set[str] = set()
    for rung in ladder:
        live = [host for host in hosts if host["id"] not in failed_hosts]
        if not live:
            break
        walked.append(rung)
        steps.append({"step": "plan", "detail": _plan_detail(rung)})
        rung_start = len(hits)
        for host in live:
            client = NZBFinderClient(
                host["url"],
                host["api_token"],
                transport=transport,
                label=host["name"],
                dialect=host.get("dialect") or "",
            )
            started = time.perf_counter()
            try:
                traced = run_plan_traced(client, rung)
            except NZBFinderError as error:
                latency_ms = (time.perf_counter() - started) * 1000.0
                err_text = str(error)
                failed_hosts.add(host["id"])
                errors.append(err_text)
                steps.append({"step": "host", "detail": f"{host['name']}: {error}"})
                _record_probe(
                    data_dir,
                    host=host,
                    ok=False,
                    latency_ms=latency_ms,
                    error=err_text,
                    rate_limited=is_rate_limited(error) or "rate" in err_text.lower(),
                    kind=probe_kind,
                )
                continue
            finally:
                client.close()
            latency_ms = (time.perf_counter() - started) * 1000.0
            host_raw = list(traced.get("raw") or [])
            host_rejected = list(traced.get("rejected") or [])
            host_accepted = list(traced.get("accepted") or [])
            _record_probe(
                data_dir,
                host=host,
                ok=True,
                latency_ms=latency_ms,
                hit_count=len(host_accepted),
                kind=probe_kind,
            )
            raw_count += len(host_raw)
            rejected_count += len(host_rejected)
            default_kind = str(traced.get("default_kind") or "")
            if default_kind:
                steps.append(
                    {
                        "step": "normalize",
                        "detail": f"{host['name']}: default_kind={default_kind}",
                    }
                )
            steps.append(
                {
                    "step": "host",
                    "detail": (
                        f"{host['name']}: raw={len(host_raw)} accepted={len(host_accepted)} "
                        f"rejected={len(host_rejected)}"
                    ),
                }
            )
            for row in host_rejected:
                tagged = dict(row)
                tagged["host_id"] = host["id"]
                tagged["host_name"] = host["name"]
                results.append(tagged)
            for row in host_accepted:
                if not isinstance(row, dict):
                    continue
                tagged = dict(row)
                tagged["host_id"] = host["id"]
                tagged["host_name"] = host["name"]
                summary = _hit_summary(tagged)
                key = _hit_key(tagged)
                if key in seen:
                    results.append(
                        {
                            **summary,
                            "decision": "rejected",
                            "reason": "duplicate guid/title",
                            "notes": [],
                        }
                    )
                    rejected_count += 1
                    continue
                seen.add(key)
                # Public disclosure boundary: no api_token query params / raw Newznab blobs.
                scrubbed = public_indexer_hit(tagged) or {}
                hits.append(scrubbed)
                guid = _text(scrubbed.get("guid") or tagged.get("guid"))
                if not guid:
                    results.append(
                        {
                            **summary,
                            "decision": "skipped",
                            "reason": "missing guid (shown but not requestable)",
                            "notes": [],
                        }
                    )
                else:
                    results.append({**summary, "decision": "accepted", "reason": "", "notes": []})
        if any(is_confident_match(sought, hit) for hit in hits[rung_start:]):
            steps.append({"step": "ladder", "detail": f"confident hit on {rung.get('rung')}"})
            break

    beyond_error = "; ".join(dict.fromkeys(errors)) if errors else None
    if beyond_error:
        steps.append({"step": "error", "detail": beyond_error})
    return {
        "hits": hits,
        "error": beyond_error,
        "plan": plan,
        "plans": walked,
        "steps": steps,
        "results": results,
        "raw_count": raw_count,
        "rejected_count": rejected_count,
    }


def _plan_detail(plan: Mapping[str, Any]) -> str:
    params = plan.get("params") or {}
    shown = ", ".join(
        f"{key}={params.get(key)!r}" for key in params if params.get(key) not in (None, "")
    )
    rung = _text(plan.get("rung"))
    prefix = f"{rung}: " if rung else ""
    return f"{prefix}{_text(plan.get('endpoint'))} {shown}"
