"""Newznab RSS subscriptions. New items become Asked jobs — confirm before SAB."""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict, List, Optional

import httpx

from librarian.config import Settings
from librarian.covers import DEFAULT_USER_AGENT
from librarian.db import Database
from librarian.indexers.kind_map import REFUSED_FAMILIES
from librarian.indexers.query import build_job_payload, strip_secret_query
from librarian.kinds import ALL_KINDS
from librarian.nzbfinder import normalize_item

logger = logging.getLogger(__name__)

MAX_NEW_PER_POLL = 20


class RSSError(RuntimeError):
    """RSS HTTP or parse failure. Messages must never include tokens."""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(value: Any) -> str:
    return str(value or "").strip()


def mask_rss_url(url: str) -> str:
    return strip_secret_query(url)


def public_rss_feed(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row.get("id"),
        "name": row.get("name") or "RSS",
        "url": mask_rss_url(str(row.get("url") or "")),
        "kind": row.get("kind") or "book",
        "enabled": bool(row.get("enabled")),
        "last_guid": row.get("last_guid") or "",
        "last_error": row.get("last_error") or "",
        "last_poll_at": row.get("last_poll_at"),
    }


def _child_text(elem: ET.Element, name: str) -> str:
    for child in list(elem):
        if _local(child.tag) == name:
            return (child.text or "").strip()
    return ""


def _enclosure_url(elem: ET.Element) -> str:
    for child in list(elem):
        if _local(child.tag) != "enclosure":
            continue
        return str(child.attrib.get("url") or "")
    return ""


def parse_rss_xml(raw: str) -> List[Dict[str, Any]]:
    """Parse Newznab/RSS XML into normalize_item dicts.

    Movie/TV/XXX cats get a display kind from the map; RSS poll still refuses
    those families via REFUSED_FAMILIES before they become Asked jobs.
    """
    text = (raw or "").strip()
    if not text:
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise RSSError("RSS feed is not valid XML") from error
    items: List[ET.Element] = []
    if _local(root.tag) == "item":
        items = [root]
    else:
        items = [elem for elem in root.iter() if _local(elem.tag) == "item"]
    out: List[Dict[str, Any]] = []
    for elem in items:
        attrs = []
        for child in list(elem):
            if _local(child.tag) != "attr":
                continue
            attrs.append(
                {
                    "name": child.attrib.get("name") or "",
                    "value": child.attrib.get("value") or "",
                }
            )
        guid = _child_text(elem, "guid")
        payload = {
            "title": _child_text(elem, "title"),
            "guid": guid,
            "link": _child_text(elem, "link"),
            "pubDate": _child_text(elem, "pubDate"),
            "category": _child_text(elem, "category"),
            "enclosure": {"url": _enclosure_url(elem)},
            "attr": attrs,
        }
        out.append(normalize_item(payload))
    return out


def fetch_rss(url: str, *, transport: Optional[httpx.BaseTransport] = None) -> str:
    target = _text(url)
    if not target:
        raise RSSError("RSS URL is empty")
    client = httpx.Client(timeout=30.0, transport=transport, follow_redirects=True)
    try:
        response = client.get(target, headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml"})
    except httpx.HTTPError as error:
        raise RSSError("RSS feed could not be reached") from error
    finally:
        client.close()
    if response.status_code >= 400:
        raise RSSError(f"RSS HTTP {response.status_code}")
    return response.text or ""


def _item_guid(item: Dict[str, Any]) -> str:
    return _text(item.get("guid"))


def _accept_item(item: Dict[str, Any], feed_kind: str) -> bool:
    kind = item.get("kind")
    cat = item.get("category")
    cat_int: Optional[int]
    try:
        cat_int = int(str(cat).strip())
    except (TypeError, ValueError):
        cat_int = None
    if cat_int is not None:
        family = (cat_int // 1000) * 1000
        if family in REFUSED_FAMILIES:
            return False
    if kind and kind != feed_kind:
        return False
    if not kind:
        item["kind"] = feed_kind
    return True


def _asked_job(item: Dict[str, Any], feed: Dict[str, Any]) -> Dict[str, Any]:
    kind = _text(item.get("kind") or feed.get("kind"))
    payload = build_job_payload(
        sought={"kind": kind, "q": _text(item.get("title")), "title": _text(item.get("book_title") or item.get("title"))},
        selected=item,
    )
    payload["source"] = "rss"
    payload["feed_id"] = feed.get("id")
    payload["host_name"] = feed.get("name") or "RSS"
    return {
        "status": "asked",
        "indexer_guid": payload.get("guid") or _item_guid(item),
        "title": payload.get("title") or item.get("title"),
        "kind": kind,
        "requested_by": "rss",
        "payload": payload,
    }


def poll_feed(
    db: Database,
    feed: Dict[str, Any],
    *,
    fetch: Optional[Callable[[str], str]] = None,
    transport: Optional[httpx.BaseTransport] = None,
) -> int:
    """Insert Asked jobs for new guids. TV/movies refused. Idempotent on last_guid."""
    url = _text(feed.get("url"))
    kind = _text(feed.get("kind"))
    if kind not in ALL_KINDS:
        db.upsert_rss_feed({**feed, "last_error": "RSS kind is not a Librarian shelf", "last_poll_at": time.time()})
        return 0
    last_guid = _text(feed.get("last_guid"))
    created = 0
    try:
        raw = fetch(url) if fetch else fetch_rss(url, transport=transport)
        items = parse_rss_xml(raw)
    except RSSError as error:
        db.upsert_rss_feed({**feed, "last_error": str(error), "last_poll_at": time.time()})
        return 0
    newest = _item_guid(items[0]) if items else last_guid
    for item in items:
        guid = _item_guid(item)
        if last_guid and guid == last_guid:
            break
        if created >= MAX_NEW_PER_POLL:
            break
        if not guid:
            continue
        if not _accept_item(item, kind):
            continue
        if db.get_job_by_indexer_guid(guid):
            continue
        db.create_job(_asked_job(item, feed))
        created += 1
    db.upsert_rss_feed(
        {
            **feed,
            "last_guid": newest or last_guid,
            "last_error": "",
            "last_poll_at": time.time(),
        }
    )
    return created


def poll_rss_feeds(
    db: Database,
    settings: Settings,
    *,
    fetch: Optional[Callable[[str], str]] = None,
    transport: Optional[httpx.BaseTransport] = None,
) -> int:
    del settings  # RSS URLs live on the feed row; settings kept for poller signature.
    total = 0
    for feed in db.list_rss_feeds():
        if not feed.get("enabled"):
            continue
        try:
            total += poll_feed(db, feed, fetch=fetch, transport=transport)
        except Exception:
            logger.exception("RSS poll failed for feed %s", feed.get("id"))
    return total


def create_rss_feed(db: Database, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = _text(payload.get("url"))
    if not url:
        raise ValueError("RSS URL is required")
    kind = _text(payload.get("kind")).lower() or "book"
    if kind not in ALL_KINDS:
        raise ValueError("RSS kind must be book, magazine, comic, audiobook, or music")
    name = _text(payload.get("name")) or "RSS"
    enabled = payload.get("enabled")
    if enabled is None:
        enabled = True
    row = db.upsert_rss_feed(
        {
            "name": name,
            "url": url,
            "kind": kind,
            "enabled": enabled,
        }
    )
    return public_rss_feed(row)


def update_rss_feed(db: Database, feed_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    existing = db.get_rss_feed(feed_id)
    if existing is None:
        raise ValueError("RSS feed not found")
    kind = _text(payload.get("kind") if payload.get("kind") is not None else existing.get("kind")).lower()
    if kind not in ALL_KINDS:
        raise ValueError("RSS kind must be book, magazine, comic, audiobook, or music")
    url = _text(payload.get("url") if payload.get("url") is not None else existing.get("url"))
    if not url:
        raise ValueError("RSS URL is required")
    enabled = existing.get("enabled")
    if "enabled" in payload:
        enabled = payload.get("enabled")
    row = db.upsert_rss_feed(
        {
            "id": feed_id,
            "name": _text(payload.get("name") if payload.get("name") is not None else existing.get("name")) or "RSS",
            "url": url,
            "kind": kind,
            "enabled": enabled,
            "created_at": existing.get("created_at"),
        }
    )
    return public_rss_feed(row)
