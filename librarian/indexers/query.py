"""Kind-aware NZBFinder v2 query plans and job metadata.

Uses documented v2 fields from the in-repo capabilities fixture:
search: query, cat, limit, offset (plus maxage/subs unused here)
books: author, title, isbn (plus cat/limit)
No music endpoint is advertised, so music/audiobook/comic use search + cat.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from librarian.kinds import (
    EXTRA_KINDS,
    KIND_AUDIOBOOK,
    KIND_BOOK,
    KIND_COMIC,
    KIND_MAGAZINE,
    KIND_MOVIE,
    KIND_MUSIC,
    KIND_TV,
    KIND_XXX,
    REQUEST_KINDS,
    search_category_for_kind,
)

SOUGHT_KEYS = (
    "kind",
    "q",
    "title",
    "author",
    "isbn",
    "series",
    "issue",
    "artist",
    "album",
    "year",
)

_TOKEN_QUERY = re.compile(r"^(api_token|apikey)$", re.IGNORECASE)
_YEAR = re.compile(r"^(19|20)\d{2}$")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _join(*parts: Any) -> str:
    return " ".join(part for part in (_text(p) for p in parts) if part)


def _year_text(value: Any) -> str:
    text = _text(value)
    return text if _YEAR.match(text) else ""


def prune_sought_for_kind(kind: str, fields: Dict[str, Any]) -> Dict[str, str]:
    """Drop fields that do not apply to this kind (e.g. book ISBN on music)."""
    allowed = {
        "": {"q", "kind"},
        KIND_BOOK: {"q", "kind", "title", "author", "isbn", "year"},
        KIND_MAGAZINE: {"q", "kind", "title", "author", "isbn", "year"},
        KIND_COMIC: {"q", "kind", "series", "issue", "year"},
        KIND_MUSIC: {"q", "kind", "artist", "album", "year"},
        KIND_AUDIOBOOK: {"q", "kind", "title", "author", "isbn", "year"},
        KIND_MOVIE: {"q", "kind", "title", "year"},
        KIND_TV: {"q", "kind", "title", "year"},
        KIND_XXX: {"q", "kind", "title", "year"},
    }.get(kind, {"q", "kind"})
    out = {key: "" for key in SOUGHT_KEYS}
    out["kind"] = kind if kind in REQUEST_KINDS else ""
    for key in SOUGHT_KEYS:
        if key in allowed:
            out[key] = _text(fields.get(key))
    return out


def clean_sought(fields: Optional[Dict[str, Any]] = None, **extra: Any) -> Dict[str, str]:
    data = dict(fields or {})
    data.update(extra)
    kind = _text(data.get("kind")).lower()
    if kind not in REQUEST_KINDS:
        kind = ""
    if kind == KIND_MUSIC:
        data["album"] = _text(data.get("album") or data.get("title"))
        data["artist"] = _text(data.get("artist") or data.get("author"))
        data["isbn"] = ""
    if kind == KIND_COMIC and not _text(data.get("series")) and _text(data.get("title")):
        data["q"] = _text(data.get("q") or data.get("title"))
    cleaned = prune_sought_for_kind(kind, data)
    if kind in {KIND_BOOK, KIND_MAGAZINE, KIND_AUDIOBOOK} and not cleaned["title"] and cleaned["q"]:
        cleaned["title"] = cleaned["q"]
    if kind == KIND_COMIC and not cleaned["series"] and cleaned["q"]:
        cleaned["series"] = cleaned["q"]
    if kind == KIND_MUSIC and not cleaned["album"]:
        cleaned["album"] = cleaned["q"]
        cleaned["isbn"] = ""
    cleaned["year"] = _year_text(cleaned.get("year"))
    return {key: value for key, value in cleaned.items() if value or key == "kind"}


def plan_beyond_search(
    *,
    kind: str = "",
    q: str = "",
    title: str = "",
    author: str = "",
    isbn: str = "",
    series: str = "",
    issue: str = "",
    artist: str = "",
    album: str = "",
    year: str = "",
    limit: int = 25,
    offset: int = 0,
) -> Optional[Dict[str, Any]]:
    """Return an endpoint + params plan, or None when there is nothing to seek."""
    sought = clean_sought(
        {
            "kind": kind,
            "q": q,
            "title": title,
            "author": author,
            "isbn": isbn,
            "series": series,
            "issue": issue,
            "artist": artist,
            "album": album,
            "year": year,
        }
    )
    kind = sought.get("kind") or ""
    year_bit = sought.get("year") or ""
    if kind in {KIND_BOOK, KIND_MAGAZINE}:
        book_title = sought.get("title") or ""
        if year_bit and not sought.get("isbn") and year_bit not in book_title:
            book_title = _join(book_title, year_bit)
        params = {
            "title": book_title,
            "author": sought.get("author") or "",
            "isbn": sought.get("isbn") or "",
            "cat": search_category_for_kind(kind),
            "limit": limit,
        }
        if not any(params[key] for key in ("title", "author", "isbn")):
            return None
        return {"endpoint": "books", "params": params, "sought": sought}
    if kind == KIND_COMIC:
        query = _join(sought.get("series"), sought.get("issue"), year_bit)
        if not query:
            query = sought.get("q") or ""
        if not query:
            return None
        return {
            "endpoint": "search",
            "params": {"query": query, "cat": "7030", "limit": limit, "offset": offset},
            "sought": sought,
        }
    if kind == KIND_MUSIC:
        query = _join(sought.get("artist"), sought.get("album"), year_bit)
        if not query:
            query = sought.get("q") or ""
        if not query:
            return None
        return {
            "endpoint": "search",
            "params": {"query": query, "cat": "3000", "limit": limit, "offset": offset},
            "sought": sought,
        }
    if kind == KIND_AUDIOBOOK:
        query = _join(sought.get("author"), sought.get("title"), sought.get("isbn"), year_bit)
        if not query:
            query = sought.get("q") or ""
        if not query:
            return None
        return {
            "endpoint": "search",
            "params": {"query": query, "cat": "3030", "limit": limit, "offset": offset},
            "sought": sought,
        }
    if kind in EXTRA_KINDS:
        query = _join(sought.get("q"), sought.get("title"), year_bit)
        if not query:
            return None
        return {
            "endpoint": "search",
            "params": {
                "query": query,
                "cat": search_category_for_kind(kind),
                "limit": limit,
                "offset": offset,
            },
            "sought": sought,
        }
    query = _join(
        sought.get("q"),
        sought.get("title"),
        sought.get("author"),
        sought.get("isbn"),
        sought.get("series"),
        sought.get("issue"),
        sought.get("artist"),
        sought.get("album"),
        year_bit,
    )
    if not query:
        return None
    return {
        "endpoint": "search",
        "params": {"query": query, "cat": None, "limit": limit, "offset": offset},
        "sought": sought,
    }


def default_kind_for_plan(plan: Optional[Dict[str, Any]]) -> str:
    """Kind to assume when an indexer omits Newznab category on a typed endpoint."""
    if not plan:
        return ""
    sought_kind = _text((plan.get("sought") or {}).get("kind"))
    endpoint = _text(plan.get("endpoint"))
    if endpoint == "books":
        if sought_kind == KIND_MAGAZINE:
            return KIND_MAGAZINE
        return KIND_BOOK
    if sought_kind in REQUEST_KINDS and sought_kind not in EXTRA_KINDS:
        return sought_kind
    return ""


def run_beyond_search(client: Any, **fields: Any) -> List[Dict[str, Any]]:
    return run_beyond_search_traced(client, **fields)["accepted"]


def run_beyond_search_traced(client: Any, **fields: Any) -> Dict[str, Any]:
    """Run a beyond plan and return accepted hits plus rejected/raw diagnostics."""
    plan = plan_beyond_search(**fields)
    empty = {
        "plan": plan,
        "accepted": [],
        "rejected": [],
        "raw": [],
        "default_kind": "",
        "notes": [],
    }
    if plan is None:
        empty["notes"] = ["nothing to seek"]
        return empty
    default_kind = default_kind_for_plan(plan)
    if plan["endpoint"] == "books":
        params = plan["params"]
        if hasattr(client, "books_traced"):
            traced = client.books_traced(
                title=params.get("title") or "",
                author=params.get("author") or "",
                isbn=params.get("isbn") or "",
                cat=params.get("cat"),
                limit=int(params.get("limit") or 25),
                default_kind=default_kind or KIND_BOOK,
            )
        else:
            rows = client.books(
                title=params.get("title") or "",
                author=params.get("author") or "",
                isbn=params.get("isbn") or "",
                cat=params.get("cat"),
                limit=int(params.get("limit") or 25),
            )
            traced = {"accepted": rows, "rejected": [], "raw": [], "default_kind": default_kind}
        return {
            "plan": plan,
            "accepted": traced.get("accepted") or [],
            "rejected": traced.get("rejected") or [],
            "raw": traced.get("raw") or [],
            "default_kind": traced.get("default_kind") or default_kind,
            "notes": [],
        }
    params = plan["params"]
    keep_untyped = (plan.get("sought") or {}).get("kind") in EXTRA_KINDS
    if hasattr(client, "search_traced"):
        traced = client.search_traced(
            str(params.get("query") or ""),
            cat=params.get("cat"),
            kind=(plan.get("sought") or {}).get("kind") or "",
            limit=int(params.get("limit") or 25),
            offset=int(params.get("offset") or 0),
            keep_untyped=keep_untyped,
        )
    else:
        rows = client.search(
            str(params.get("query") or ""),
            cat=params.get("cat"),
            limit=int(params.get("limit") or 25),
            offset=int(params.get("offset") or 0),
            keep_untyped=keep_untyped,
        )
        traced = {"accepted": rows, "rejected": [], "raw": [], "default_kind": default_kind}
    if not keep_untyped:
        return {
            "plan": plan,
            "accepted": traced.get("accepted") or [],
            "rejected": traced.get("rejected") or [],
            "raw": traced.get("raw") or [],
            "default_kind": traced.get("default_kind") or default_kind,
            "notes": [],
        }
    from librarian.kinds import kind_from_newznab

    out = []
    want = (plan.get("sought") or {}).get("kind")
    for row in traced.get("accepted") or []:
        tagged = dict(row)
        kind = kind_from_newznab(tagged.get("category"), extra=True) or want
        if kind in EXTRA_KINDS:
            tagged["kind"] = kind
            out.append(tagged)
    return {
        "plan": plan,
        "accepted": out,
        "rejected": traced.get("rejected") or [],
        "raw": traced.get("raw") or [],
        "default_kind": traced.get("default_kind") or default_kind,
        "notes": [],
    }


def strip_secret_query(url: str) -> str:
    """Drop api_token/apikey from a stored URL. Never persist indexer secrets."""
    raw = _text(url)
    if not raw:
        return ""
    parts = urlsplit(raw)
    kept = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if not _TOKEN_QUERY.match(key)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))


def retrieved_from_hit(item: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Structured indexer fields only — never invent identifiers."""
    hit = item or {}
    isbn = _text(hit.get("isbn"))
    year = hit.get("year")
    retrieved: Dict[str, Any] = {}
    for key in ("author", "book_title", "isbn", "cover", "category_name", "poster", "series", "series_name"):
        value = _text(hit.get(key))
        if value:
            retrieved[key] = value
    if isbn:
        retrieved["isbn"] = isbn
    if isinstance(year, int) or _year_text(year):
        retrieved["year"] = int(year) if str(year).isdigit() else year
    title = _text(hit.get("book_title"))
    if title:
        retrieved["title"] = title
    return retrieved


def selected_from_hit(item: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    hit = item or {}
    category = hit.get("category")
    cats = hit.get("cats")
    if not cats and category not in (None, ""):
        cats = [category]
    selected = {
        "guid": _text(hit.get("guid")),
        "title": _text(hit.get("title")),
        "download_url": strip_secret_query(_text(hit.get("download_url"))),
        "link": strip_secret_query(_text(hit.get("link"))),
        "category": category,
        "cats": cats or [],
        "size": hit.get("size"),
        "poster": _text(hit.get("poster")),
        "cover": strip_secret_query(_text(hit.get("cover"))),
        "category_name": _text(hit.get("category_name")),
        "author": _text(hit.get("author")),
        "isbn": _text(hit.get("isbn")),
        "book_title": _text(hit.get("book_title")),
        "pub_date": _text(hit.get("pub_date")),
        "host_id": _text(hit.get("host_id")),
        "host_name": _text(hit.get("host_name")),
        "kind": _text(hit.get("kind")),
        "tmdb_id": hit.get("tmdb_id"),
        "tvdb_id": hit.get("tvdb_id"),
        "imdb_id": _text(hit.get("imdb_id")),
    }
    return {key: value for key, value in selected.items() if value not in (None, "", [])}


def catalog_title(sought: Dict[str, Any], selected: Dict[str, Any], retrieved: Dict[str, Any]) -> str:
    """Human title for the job/work — never the Usenet dump name when we have better."""
    kind = _text(sought.get("kind") or selected.get("kind"))
    if kind == KIND_COMIC:
        series = _text(sought.get("series") or retrieved.get("series") or retrieved.get("series_name"))
        issue = _text(sought.get("issue"))
        if series and issue:
            return f"{series} #{issue.lstrip('0') or issue}"
        if series:
            return series
    if kind == KIND_MUSIC:
        album = _text(sought.get("album") or retrieved.get("title") or retrieved.get("book_title"))
        if album:
            return album
    bookish = _text(
        sought.get("title")
        or retrieved.get("book_title")
        or retrieved.get("title")
        or selected.get("book_title")
    )
    if bookish:
        return bookish
    return _text(selected.get("title") or sought.get("q"))


def catalog_author(sought: Dict[str, Any], selected: Dict[str, Any], retrieved: Dict[str, Any]) -> str:
    return _text(
        sought.get("author")
        or sought.get("artist")
        or retrieved.get("author")
        or selected.get("author")
    )


def build_job_payload(
    *,
    sought: Optional[Dict[str, Any]] = None,
    selected: Optional[Dict[str, Any]] = None,
    retrieved: Optional[Dict[str, Any]] = None,
    details: Optional[Dict[str, Any]] = None,
    candidates: Optional[List[Dict[str, Any]]] = None,
    rank_method: str = "",
    rank_reason: str = "",
) -> Dict[str, Any]:
    """Persist what was sought, what was picked, alternates, and indexer metadata."""
    sought_clean = clean_sought(sought or {})
    selected_clean = selected_from_hit(selected or {})
    retrieved_clean = retrieved_from_hit(selected or {})
    retrieved_clean.update(retrieved_from_hit(retrieved or {}))
    retrieved_clean.update(retrieved_from_hit(details or {}))
    detail_hit = selected_from_hit(details or {})
    if detail_hit:
        retrieved_clean["details"] = detail_hit
    title = catalog_title(sought_clean, selected_clean, retrieved_clean)
    author = catalog_author(sought_clean, selected_clean, retrieved_clean)
    isbn = _text(sought_clean.get("isbn") or retrieved_clean.get("isbn") or selected_clean.get("isbn"))
    if sought_clean.get("kind") == KIND_MUSIC:
        isbn = ""
    kind = _text(sought_clean.get("kind") or selected_clean.get("kind"))
    remembered: List[Dict[str, Any]] = []
    if isinstance(candidates, list):
        from librarian.indexers.rank import remember_candidates

        remembered = remember_candidates(candidates)
    payload = {
        "sought": sought_clean,
        "selected": selected_clean,
        "retrieved": retrieved_clean,
        "candidates": remembered,
        "rank_method": _text(rank_method),
        "rank_reason": _text(rank_reason),
        "title": title,
        "author": author,
        "isbn": isbn,
        "kind": kind,
        "guid": _text(selected_clean.get("guid")),
        "download_url": _text(selected_clean.get("download_url")),
        "category": selected_clean.get("category"),
        "cover": _text(selected_clean.get("cover") or retrieved_clean.get("cover")),
        "book_title": _text(retrieved_clean.get("book_title") or selected_clean.get("book_title")),
        "series": _text(sought_clean.get("series")),
        "issue": _text(sought_clean.get("issue")),
        "artist": _text(sought_clean.get("artist")),
        "album": _text(sought_clean.get("album")),
        "year": sought_clean.get("year") or retrieved_clean.get("year") or "",
    }
    return payload
