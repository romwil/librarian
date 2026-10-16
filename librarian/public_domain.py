"""Public-domain lane: Project Gutenberg and Standard Ebooks.

A hit is returned only when the query clearly names that edition (exact title,
or a check-digit ISBN carried on the record). Author, series, and narrator
queries are not an edition. Shelving writes the epub onto the book shelves.
It does not call SABnzbd and does not open a Hold slip.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlsplit

import httpx

from librarian.audiobook_match import match_catalog_work
from librarian.db import Database
from librarian.identify import isbn_match_keys, tidy_title
from librarian.owned import ShelfIndex
from librarian.search_modes import normalize_search_mode

GUTENDEX_URL = "https://gutendex.com/books"
STANDARD_EBOOKS_OPDS = "https://standardebooks.org/feeds/opds/all"

_ALLOWED_DOWNLOAD_HOSTS = frozenset(
    {
        "gutenberg.org",
        "www.gutenberg.org",
        "standardebooks.org",
        "www.standardebooks.org",
    }
)
_MAX_EPUB_BYTES = 40 * 1024 * 1024


class PublicDomainError(ValueError):
    """Caller-facing public-domain failure. Never includes tokens."""


def _norm_title(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _author_key(value: Any) -> str:
    tokens = re.findall(r"[a-z0-9]+", str(value or "").lower())
    return " ".join(sorted(tokens))


def _safe_segment(value: Any) -> str:
    text = re.sub(r"[\\/]+", " ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:120] or "Untitled"


def download_host_allowed(url: str) -> bool:
    parts = urlsplit(str(url or "").strip())
    if parts.scheme not in {"https", "http"}:
        return False
    host = (parts.hostname or "").lower()
    if host not in _ALLOWED_DOWNLOAD_HOSTS:
        return False
    path = (parts.path or "").lower()
    return ".epub" in path


def clear_editions(query: str, mode: str, editions: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """One edition from this catalog, or none when the query is not that edition."""
    key = normalize_search_mode(mode) or "title"
    if key not in {"title", "isbn"}:
        return []
    needle = str(query or "").strip()
    if not needle:
        return []
    rows = [dict(row) for row in editions if isinstance(row, Mapping)]
    if key == "isbn":
        want = set(isbn_match_keys(needle))
        if not want:
            return []
        hits = [
            row
            for row in rows
            if want.intersection(isbn_match_keys(str(row.get("isbn") or "")))
            and str(row.get("download_url") or "").strip()
        ]
        titles = {_norm_title(row.get("title")) for row in hits}
        titles.discard("")
        if len(titles) == 1 and hits:
            return [hits[0]]
        return []
    want_title = _norm_title(needle)
    if not want_title:
        return []
    hits = [
        row
        for row in rows
        if _norm_title(row.get("title")) == want_title and str(row.get("download_url") or "").strip()
    ]
    if not hits:
        return []
    authors = {_author_key(row.get("author")) for row in hits}
    authors.discard("")
    if len(authors) > 1:
        return []
    return [hits[0]]


def match_public_domain(
    query: str,
    mode: str,
    *,
    gutenberg: List[Mapping[str, Any]],
    standard_ebooks: List[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Clear Gutenberg hit, then a clear Standard Ebooks hit. Never a fuzzy pile."""
    key = normalize_search_mode(mode)
    if key in {"author", "series", "narrator"}:
        return []
    mode_key = key or "title"
    found: List[Dict[str, Any]] = []
    found.extend(clear_editions(query, mode_key, gutenberg))
    found.extend(clear_editions(query, mode_key, standard_ebooks))
    return found


def parse_gutendex(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    results = payload.get("results") if isinstance(payload, Mapping) else None
    editions: List[Dict[str, Any]] = []
    for row in results or []:
        if not isinstance(row, Mapping):
            continue
        formats = row.get("formats") if isinstance(row.get("formats"), Mapping) else {}
        url = _epub_format_url(formats)
        authors = row.get("authors") if isinstance(row.get("authors"), list) else []
        author = ""
        if authors and isinstance(authors[0], Mapping):
            author = str(authors[0].get("name") or "")
        editions.append(
            {
                "source": "gutenberg",
                "id": str(row.get("id") or ""),
                "title": str(row.get("title") or ""),
                "author": author,
                "isbn": "",
                "download_url": url,
                "kind": "book",
            }
        )
    return editions


def _epub_format_url(formats: Mapping[str, Any]) -> str:
    preferred = ""
    fallback = ""
    for fmt, link in formats.items():
        href = str(link or "")
        if "epub" not in str(fmt).lower() or not href.startswith("http"):
            continue
        if "images" not in str(fmt).lower() and not preferred:
            preferred = href
        elif not fallback:
            fallback = href
    return preferred or fallback


def parse_standard_ebooks(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    publications = payload.get("publications") if isinstance(payload, Mapping) else None
    editions: List[Dict[str, Any]] = []
    for row in publications or []:
        if not isinstance(row, Mapping):
            continue
        meta = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
        authors = meta.get("author") if isinstance(meta.get("author"), list) else []
        author = ""
        if authors and isinstance(authors[0], Mapping):
            author = str(authors[0].get("name") or "")
        identifier = str(meta.get("identifier") or "")
        editions.append(
            {
                "source": "standard_ebooks",
                "id": identifier.rsplit("/", 1)[-1],
                "title": str(meta.get("title") or ""),
                "author": author,
                "isbn": "",
                "download_url": _opds_epub_url(row.get("links")),
                "kind": "book",
            }
        )
    return editions


def _opds_epub_url(links: Any) -> str:
    chosen = ""
    for link in links or []:
        if not isinstance(link, Mapping):
            continue
        href = str(link.get("href") or "")
        kind = str(link.get("type") or "")
        label = str(link.get("title") or "")
        if "epub" not in kind.lower() or not href.startswith("http"):
            continue
        if "kepub" in kind.lower() or "advanced" in label.lower():
            continue
        chosen = href
        if "recommended" in label.lower():
            return href
    return chosen


def _get_json(
    url: str,
    params: Mapping[str, str],
    *,
    transport: Optional[httpx.BaseTransport] = None,
    headers: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    with httpx.Client(transport=transport, timeout=12.0, follow_redirects=False) as client:
        response = client.get(url, params=dict(params), headers=dict(headers or {}))
        response.raise_for_status()
        data = response.json()
    return data if isinstance(data, dict) else {}


def search_public_domain(
    query: str,
    *,
    mode: str = "",
    transport: Optional[httpx.BaseTransport] = None,
) -> List[Dict[str, Any]]:
    """Query both catalogs and keep a hit only when it is clearly that edition."""
    key = normalize_search_mode(mode)
    if key in {"author", "series", "narrator"}:
        return []
    # Pytest boots with this flag. Live catalog calls stay out of that suite
    # unless a test passes its own transport.
    if transport is None and os.environ.get("LIBRARIAN_SKIP_APP_BOOT") == "1":
        return []
    text = str(query or "").strip()
    if not text:
        return []
    if key == "isbn" and not isbn_match_keys(text):
        return []
    gutenberg: List[Dict[str, Any]] = []
    standard: List[Dict[str, Any]] = []
    try:
        gutenberg = parse_gutendex(_get_json(GUTENDEX_URL, {"search": text}, transport=transport))
    except (httpx.HTTPError, ValueError):
        gutenberg = []
    try:
        standard = parse_standard_ebooks(
            _get_json(
                STANDARD_EBOOKS_OPDS,
                {"query": text, "per-page": "8"},
                transport=transport,
                headers={"Accept": "application/opds+json"},
            )
        )
    except (httpx.HTTPError, ValueError):
        standard = []
    return match_public_domain(text, key or "title", gutenberg=gutenberg, standard_ebooks=standard)


def _guard_redirect(request: httpx.Request) -> None:
    if not download_host_allowed(str(request.url)):
        raise PublicDomainError("That download is not a Gutenberg or Standard Ebooks epub")


def fetch_epub(url: str, *, transport: Optional[httpx.BaseTransport] = None) -> bytes:
    if not download_host_allowed(url):
        raise PublicDomainError("That download is not a Gutenberg or Standard Ebooks epub")
    with httpx.Client(
        transport=transport,
        timeout=30.0,
        follow_redirects=True,
        event_hooks={"request": [_guard_redirect]},
    ) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            chunks: List[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > _MAX_EPUB_BYTES:
                    raise PublicDomainError("Edition is too large to shelve directly")
                chunks.append(chunk)
    data = b"".join(chunks)
    if not data.startswith(b"PK"):
        raise PublicDomainError("That download is not an epub")
    return data


def shelve_edition(
    db: Database,
    settings: Any,
    edition: Mapping[str, Any],
    *,
    transport: Optional[httpx.BaseTransport] = None,
) -> Dict[str, Any]:
    """Write one public-domain epub onto the shelves. No SABnzbd, no Hold slip."""
    title = tidy_title(str(edition.get("title") or ""))
    author = tidy_title(str(edition.get("author") or ""))
    isbn = str(edition.get("isbn") or "").strip()
    url = str(edition.get("download_url") or "").strip()
    source = str(edition.get("source") or "").strip()
    if source not in {"gutenberg", "standard_ebooks"}:
        raise PublicDomainError("Unknown public-domain source")
    if not title:
        raise PublicDomainError("Title is required")
    if not download_host_allowed(url):
        raise PublicDomainError("That download is not a Gutenberg or Standard Ebooks epub")
    shelves = ShelfIndex(db)
    owned = match_catalog_work(
        {"title": title, "author": author, "isbn": isbn, "kind": "book"},
        shelves.books,
    )
    if owned and owned.get("id"):
        return {
            "already_on_shelf": True,
            "work_id": owned.get("id"),
            "jobs_created": 0,
            "review_state": "none",
        }
    root = Path(str(getattr(settings, "books_root", "") or ""))
    if not str(root):
        raise PublicDomainError("Books root is not set")
    payload = fetch_epub(url, transport=transport)
    folder = root / _safe_segment(author or "Unknown") / _safe_segment(title)
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{_safe_segment(title)}.epub"
    path = folder / filename
    path.write_bytes(payload)
    publisher = "Project Gutenberg" if source == "gutenberg" else "Standard Ebooks"
    work = db.upsert_work(
        {
            "kind": "book",
            "title": title,
            "author": author,
            "isbn": isbn or None,
            "publisher": publisher,
            "folder_path": str(folder),
            "review_state": "none",
        }
    )
    db.add_file(
        {
            "work_id": work["id"],
            "path": str(path),
            "filename": filename,
            "kind": "book",
            "size": len(payload),
        }
    )
    return {
        "already_on_shelf": False,
        "work_id": work.get("id"),
        "jobs_created": 0,
        "review_state": str(work.get("review_state") or "none"),
    }
