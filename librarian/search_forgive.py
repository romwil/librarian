"""Search that forgives — local typo tolerance + did-you-mean from the shelves."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Sequence

_TOKEN = re.compile(r"[A-Za-z0-9]+")


def forgive_fts_query(q: str) -> str:
    """Prefix-tolerant FTS5 query (token*) so short typos still find shelves."""
    tokens = _TOKEN.findall(q or "")
    if not tokens:
        return ""
    return " AND ".join(f'"{token}"*' for token in tokens)


def _score(needle: str, candidate: str) -> float:
    left = (needle or "").casefold().strip()
    right = (candidate or "").casefold().strip()
    if not left or not right:
        return 0.0
    if left in right or right in left:
        return 0.92
    return SequenceMatcher(None, left, right).ratio()


def did_you_mean(
    titles: Sequence[str],
    query: str,
    *,
    limit: int = 3,
    min_score: float = 0.58,
) -> List[str]:
    """Suggest close shelf titles when search is empty or sparse."""
    needle = str(query or "").strip()
    if not needle:
        return []
    ranked: List[tuple[float, str]] = []
    seen = set()
    for raw in titles or ():
        title = str(raw or "").strip()
        if not title:
            continue
        key = title.casefold()
        if key in seen:
            continue
        seen.add(key)
        score = _score(needle, title)
        if score >= min_score:
            ranked.append((score, title))
    ranked.sort(key=lambda item: (-item[0], item[1].casefold()))
    return [title for _, title in ranked[: max(1, int(limit or 3))]]


def search_with_forgiveness(
    db: Any,
    query: str,
    *,
    limit: int = 24,
    kind: Optional[str] = None,
) -> Dict[str, Any]:
    """Exact FTS, then prefix forgive, then did-you-mean from catalog titles."""
    q = str(query or "").strip()
    if not q:
        return {"local": [], "did_you_mean": [], "forgave": False}
    local = list(db.search_works(q, limit=limit, kind=kind) or [])
    forgave = False
    if not local:
        soft = forgive_fts_query(q)
        if soft:
            local = list(db.search_works_raw(soft, limit=limit, kind=kind) or [])
            forgave = bool(local)
    suggestions: List[str] = []
    if len(local) < 3:
        titles: List[str] = []
        if hasattr(db, "suggest_values"):
            titles = list(db.suggest_values(field="title", kind=kind or "", q="", limit=200) or [])
        suggestions = did_you_mean(titles, q, limit=3)
        local_titles = {str(row.get("title") or "").casefold() for row in local}
        suggestions = [item for item in suggestions if item.casefold() not in local_titles]
    return {"local": local, "did_you_mean": suggestions, "forgave": forgave}
