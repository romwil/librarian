"""NZBFinder plus extra Newznab v2 hosts. Fail closed per host; merge by guid."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

from librarian.config import Settings
from librarian.indexers.query import run_beyond_search
from librarian.nzbfinder import NZBFinderClient, NZBFinderError

NZBFINDER_ID = "nzbfinder"
MAX_EXTRA_INDEXERS = 12


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "on"}


def normalize_extra_indexers(raw: Any) -> List[Dict[str, Any]]:
    """Keep extra hosts as a list of {id, name, url, api_token, enabled}."""
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
        url = _text(item.get("url") or item.get("base_url"))
        if not url:
            continue
        name = _text(item.get("name")) or "Indexer"
        indexer_id = _text(item.get("id"))
        if not indexer_id or indexer_id == NZBFINDER_ID or indexer_id in seen:
            indexer_id = uuid.uuid4().hex
        seen.add(indexer_id)
        out.append(
            {
                "id": indexer_id,
                "name": name[:80],
                "url": url.rstrip("/"),
                "api_token": _text(item.get("api_token")),
                "enabled": _as_bool(item.get("enabled"), True),
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
            }
        )
    return out


def enabled_hosts(settings: Settings) -> List[Dict[str, str]]:
    """Hosts with a URL and token. NZBFinder stays first when configured."""
    hosts: List[Dict[str, str]] = []
    nzb_token = _text(getattr(settings, "nzbfinder_api_token", ""))
    nzb_url = _text(getattr(settings, "nzbfinder_url", ""))
    if nzb_token and nzb_url:
        hosts.append(
            {
                "id": NZBFINDER_ID,
                "name": "NZBFinder",
                "url": nzb_url,
                "api_token": nzb_token,
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
            )
    return NZBFinderClient(
        getattr(settings, "nzbfinder_url", ""),
        getattr(settings, "nzbfinder_api_token", ""),
        transport=transport,
        label="NZBFinder",
    )


def _hit_key(item: Dict[str, Any]) -> str:
    guid = _text(item.get("guid"))
    if guid:
        return f"guid:{guid}"
    title = _text(item.get("title"))
    size = item.get("size")
    return f"title:{title}:size:{size}"


def search_beyond(
    settings: Settings,
    *,
    transport: Optional[Any] = None,
    **fields: Any,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Query every enabled host. One 502 must not blank the others."""
    hosts = enabled_hosts(settings)
    if not hosts:
        return [], "NZBFinder api_token is not configured"
    hits: List[Dict[str, Any]] = []
    errors: List[str] = []
    seen: set[str] = set()
    for host in hosts:
        client = NZBFinderClient(
            host["url"],
            host["api_token"],
            transport=transport,
            label=host["name"],
        )
        try:
            rows = run_beyond_search(client, **fields)
        except NZBFinderError as error:
            errors.append(str(error))
            continue
        finally:
            client.close()
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = _hit_key(row)
            if key in seen:
                continue
            seen.add(key)
            tagged = dict(row)
            tagged["host_id"] = host["id"]
            tagged["host_name"] = host["name"]
            hits.append(tagged)
    beyond_error = "; ".join(errors) if errors else None
    return hits, beyond_error
