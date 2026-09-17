"""Discover: peruse indexer category feeds from capabilities.

Uses the host's category tree (not a single generic RSS per kind). Latest-in-cat
is a named trending/latest caps path if present, else category RSS
(`/rss/category?id=` on NZBFinder, then classic `/rss?t=` / `/api?t=search`).
TV/movies/XXX stay hidden unless Show categories is on. No HTML scrape.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from librarian.indexers.hosts import _hit_key, enabled_hosts
from librarian.indexers.query import selected_from_hit
from librarian.kinds import (
    ALL_KINDS,
    EXTRA_KINDS,
    REQUEST_KINDS,
    kind_from_caps_cat,
    kind_from_newznab,
)
from librarian.nzbfinder import NZBFinderClient, NZBFinderError
from librarian.rss import RSSError, parse_rss_xml

CAPS_TTL_SECONDS = 300.0
LATEST_TTL_SECONDS = 90.0
PER_FEED_LIMIT = 12
CATEGORY_BROWSE_LIMIT = 50
MAX_LIMIT = 100
MAX_FEEDS = 16
TRENDING_KEYS = ("trending", "latest", "recent")

_CACHE: Dict[str, Tuple[float, Any]] = {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _cache_get(key: str, ttl: float) -> Any:
    row = _CACHE.get(key)
    if not row:
        return None
    stamped, value = row
    if time.time() - stamped > ttl:
        _CACHE.pop(key, None)
        return None
    return value


def _cache_put(key: str, value: Any) -> Any:
    _CACHE[key] = (time.time(), value)
    return value


def clear_discover_cache() -> None:
    _CACHE.clear()


def resolve_feed_limit(*, cat: str = "", limit: Optional[int] = None) -> int:
    """Rails use a short slice; a selected category browses more items."""
    if limit is not None:
        try:
            n = int(limit)
        except (TypeError, ValueError):
            n = CATEGORY_BROWSE_LIMIT if _text(cat) else PER_FEED_LIMIT
        return max(1, min(n, MAX_LIMIT))
    if _text(cat):
        return CATEGORY_BROWSE_LIMIT
    return PER_FEED_LIMIT


def _searching_available(block: Any) -> bool:
    if not isinstance(block, dict):
        return False
    return str(block.get("available") or "").strip().lower() == "yes"


def trending_path(caps: Any) -> str:
    """Named v2 latest/trending path from caps searching, else search."""
    searching = caps.get("searching") if isinstance(caps, dict) else None
    if not isinstance(searching, dict):
        return "search"
    for key in TRENDING_KEYS:
        if _searching_available(searching.get(key)):
            return key
    return "search"


def _iter_subcategories(raw: Any) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    if isinstance(raw, dict):
        for key, name in raw.items():
            cat = _as_int(key)
            if cat is None:
                continue
            out.append((cat, _text(name) or str(cat)))
        return out
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            cat = _as_int(item.get("id") or item.get("category"))
            if cat is None:
                continue
            out.append((cat, _text(item.get("name") or item.get("description")) or str(cat)))
    return out


def category_feeds(caps: Any, *, extra: bool = False) -> List[Dict[str, Any]]:
    """Leaf feeds from a capabilities category tree. Does not invent names."""
    if not isinstance(caps, dict):
        return []
    categories = caps.get("categories") or []
    if not isinstance(categories, list):
        return []
    feeds: List[Dict[str, Any]] = []
    seen: set[int] = set()
    for row in categories:
        if not isinstance(row, dict):
            continue
        parent_id = _as_int(row.get("id"))
        parent_name = _text(row.get("name")) or str(parent_id or "")
        subs = _iter_subcategories(row.get("subcategories") or row.get("subcat") or [])
        if subs:
            for cat_id, name in subs:
                kind = kind_from_caps_cat(cat_id, parent=parent_id, extra=extra)
                if not kind or kind not in REQUEST_KINDS:
                    continue
                if kind in EXTRA_KINDS and not extra:
                    continue
                if cat_id in seen:
                    continue
                seen.add(cat_id)
                feeds.append(
                    {
                        "id": str(cat_id),
                        "name": name,
                        "kind": kind,
                        "parent_id": str(parent_id) if parent_id is not None else "",
                        "parent_name": parent_name,
                    }
                )
            continue
        if parent_id is None:
            continue
        kind = kind_from_caps_cat(parent_id, extra=extra)
        if not kind or kind not in REQUEST_KINDS:
            continue
        if kind in EXTRA_KINDS and not extra:
            continue
        if parent_id in seen:
            continue
        seen.add(parent_id)
        feeds.append(
            {
                "id": str(parent_id),
                "name": parent_name,
                "kind": kind,
                "parent_id": "",
                "parent_name": "",
            }
        )
    return feeds


def _wanted_feeds(feeds: List[Dict[str, Any]], *, kind: str = "", cat: str = "") -> List[Dict[str, Any]]:
    wanted_cat = _text(cat)
    wanted_kind = _text(kind).lower()
    rows = feeds
    if wanted_kind:
        rows = [row for row in rows if row.get("kind") == wanted_kind]
    if wanted_cat:
        rows = [row for row in rows if row.get("id") == wanted_cat]
    elif not wanted_kind:
        library = [row for row in rows if row.get("kind") not in EXTRA_KINDS]
        extra_rows = [row for row in rows if row.get("kind") in EXTRA_KINDS]
        rows = library + extra_rows
    return rows[:MAX_FEEDS]


def _retag_kind(item: Dict[str, Any], *, extra: bool, feed_kind: str) -> Optional[str]:
    """Map item cats to a kind; extras feeds stay movie/tv/xxx, not book."""
    kind = kind_from_newznab(item.get("category"), extra=extra)
    if not kind and extra:
        for cat in item.get("cats") or []:
            kind = kind_from_newznab(cat, extra=True)
            if kind:
                break
    if feed_kind in EXTRA_KINDS and extra:
        # A Movies/TV/XXX feed wins over a library kind (book/music) from a
        # stray secondary category — display the honest media kind.
        if kind in EXTRA_KINDS:
            return kind
        return feed_kind
    if kind:
        return kind
    if feed_kind in ALL_KINDS and not kind_from_newznab(item.get("category"), extra=True):
        if kind_from_newznab(item.get("category"), extra=False) is None:
            return feed_kind
    return kind


def public_discover_hit(
    item: Dict[str, Any],
    *,
    host: Dict[str, str],
    feed: Dict[str, Any],
    extra: bool,
) -> Optional[Dict[str, Any]]:
    tagged = dict(item)
    kind = _retag_kind(tagged, extra=extra, feed_kind=_text(feed.get("kind")))
    if not kind or kind not in REQUEST_KINDS:
        return None
    if kind in EXTRA_KINDS and not extra:
        return None
    tagged["kind"] = kind
    tagged["host_id"] = host["id"]
    tagged["host_name"] = host["name"]
    if not tagged.get("category_name"):
        tagged["category_name"] = feed.get("name") or ""
    selected = selected_from_hit(tagged)
    if extra:
        for key in ("tmdb_id", "tvdb_id", "imdb_id"):
            value = tagged.get(key)
            if value not in (None, ""):
                selected[key] = value
    selected["kind"] = kind
    selected["title"] = selected.get("title") or _text(tagged.get("title"))
    if not selected.get("guid") and not selected.get("title"):
        return None
    return selected


def fetch_feed_items(
    client: NZBFinderClient,
    feed: Dict[str, Any],
    *,
    path: str = "search",
    limit: int = PER_FEED_LIMIT,
) -> List[Dict[str, Any]]:
    cat = _text(feed.get("id"))
    feed_limit = resolve_feed_limit(limit=limit)
    try:
        items = client.latest(cat, limit=feed_limit, path=path)
        if items:
            return items[:feed_limit]
    except NZBFinderError:
        items = []
    try:
        raw = client.fetch_rss_category(cat, limit=feed_limit)
        return parse_rss_xml(raw)[:feed_limit]
    except (NZBFinderError, RSSError):
        if items:
            return items[:feed_limit]
        raise
    return items[:feed_limit]


def _host_caps(client: NZBFinderClient, host_id: str) -> Any:
    key = f"caps:{host_id}"
    cached = _cache_get(key, CAPS_TTL_SECONDS)
    if cached is not None:
        return cached
    return _cache_put(key, client.capabilities())


def _host_feed_items(
    client: NZBFinderClient,
    host_id: str,
    feed: Dict[str, Any],
    *,
    path: str,
    limit: int = PER_FEED_LIMIT,
) -> List[Dict[str, Any]]:
    feed_limit = resolve_feed_limit(limit=limit)
    key = f"latest:{host_id}:{feed.get('id')}:{feed_limit}"
    cached = _cache_get(key, LATEST_TTL_SECONDS)
    if cached is not None:
        return cached
    return _cache_put(key, fetch_feed_items(client, feed, path=path, limit=feed_limit))


def merge_category_lists(*groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for group in groups:
        for row in group:
            cat_id = _text(row.get("id"))
            if not cat_id or cat_id in seen:
                continue
            seen.add(cat_id)
            out.append(row)
    return out


def discover_beyond(
    settings: Any,
    *,
    kind: str = "",
    cat: str = "",
    limit: Optional[int] = None,
    extra: Optional[bool] = None,
    transport: Optional[Any] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Optional[str]]:
    """Fetch allowed category feeds from every enabled host. Fail closed per host."""
    allow_extra = bool(settings.show_extra_categories) if extra is None else bool(extra)
    feed_limit = resolve_feed_limit(cat=cat, limit=limit)
    hosts = enabled_hosts(settings)
    if not hosts:
        return [], [], "NZBFinder api_token is not configured"
    hits: List[Dict[str, Any]] = []
    categories: List[Dict[str, Any]] = []
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
            try:
                caps = _host_caps(client, host["id"])
            except NZBFinderError as error:
                errors.append(str(error))
                continue
            host_feeds = category_feeds(caps, extra=allow_extra)
            categories = merge_category_lists(categories, host_feeds)
            wanted = _wanted_feeds(host_feeds, kind=kind, cat=cat)
            path = trending_path(caps)
            for feed in wanted:
                try:
                    rows = _host_feed_items(client, host["id"], feed, path=path, limit=feed_limit)
                except (NZBFinderError, RSSError) as error:
                    errors.append(str(error))
                    continue
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    public = public_discover_hit(row, host=host, feed=feed, extra=allow_extra)
                    if public is None:
                        continue
                    if kind and public.get("kind") != kind:
                        continue
                    key = _hit_key(public)
                    if key in seen:
                        continue
                    seen.add(key)
                    hits.append(public)
        finally:
            client.close()
    beyond_error = "; ".join(errors) if errors else None
    return hits, categories, beyond_error
