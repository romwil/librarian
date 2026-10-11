"""OPDS 1.2 Atom feeds for shelved books, magazines, and comics."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlencode
from xml.sax.saxutils import escape

from librarian.db import Database
from librarian.ingest import PathDenied, confined_serve_path
from librarian.opds_tokens import create_file_token

OPDS_KINDS = ("book", "magazine", "comic")
KIND_TITLES = {"book": "Books", "magazine": "Magazines", "comic": "Comics"}
PAGE_SIZE = 48

NAVIGATION_TYPE = "application/atom+xml;profile=opds-catalog;kind=navigation"
ACQUISITION_TYPE = "application/atom+xml;profile=opds-catalog;kind=acquisition"
SEARCH_TYPE = "application/opensearchdescription+xml"

# Formats ebook readers acquire. Covers and sidecars stay off the card.
ACQUISITION_TYPES = {
    ".epub": "application/epub+zip",
    ".pdf": "application/pdf",
    ".cbz": "application/vnd.comicbook+zip",
    ".cbr": "application/vnd.comicbook+rar",
    ".mobi": "application/x-mobipocket-ebook",
    ".azw": "application/vnd.amazon.ebook",
    ".azw3": "application/vnd.amazon.ebook",
    ".fb2": "application/x-fictionbook+xml",
}

ATOM = "http://www.w3.org/2005/Atom"


def atom_time(ts: Any) -> str:
    try:
        value = float(ts or 0)
    except (TypeError, ValueError):
        value = 0
    if value <= 0:
        value = time_now()
    return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def time_now() -> float:
    return datetime.now(timezone.utc).timestamp()


def with_query(url: str, **params: Any) -> str:
    cleaned = {key: value for key, value in params.items() if value is not None and value != ""}
    if not cleaned:
        return url
    joiner = "&" if "?" in url else "?"
    return f"{url}{joiner}{urlencode(cleaned)}"


def _text(value: Any) -> str:
    return escape(str(value or ""), {'"': "&quot;"})


def atom_link(rel: str, href: str, type_: str, *, title: str = "") -> str:
    extra = f' title="{_text(title)}"' if title else ""
    return f'<link rel="{_text(rel)}" href="{_text(href)}" type="{_text(type_)}"{extra}/>'


def atom_entry(title: str, entry_id: str, updated: str, inner: str) -> str:
    return (
        "<entry>"
        f"<title>{_text(title)}</title>"
        f"<id>{_text(entry_id)}</id>"
        f"<updated>{_text(updated)}</updated>"
        f"{inner}"
        "</entry>"
    )


def feed_document(
    *,
    title: str,
    feed_id: str,
    updated: str,
    links: Iterable[str],
    entries: Iterable[str],
) -> str:
    body = "".join(links) + "".join(entries)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<feed xmlns="{ATOM}" xmlns:opds="http://opds-spec.org/2010/catalog" '
        'xmlns:dcterms="http://purl.org/dc/terms/">'
        f"<id>{_text(feed_id)}</id>"
        f"<title>{_text(title)}</title>"
        f"<updated>{_text(updated)}</updated>"
        "<author><name>Librarian</name></author>"
        f"{body}"
        "</feed>"
    )


def search_description(*, short_name: str, template: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<OpenSearchDescription xmlns="http://a9.com/-/spec/opensearch/1.1/">'
        f"<ShortName>{_text(short_name)}</ShortName>"
        "<Description>Shelved books, magazines, and comics</Description>"
        f'<Url type="{ACQUISITION_TYPE}" template="{_text(template)}"/>'
        "</OpenSearchDescription>"
    )


def shelved_author_page(db: Database, author: str, *, offset: int = 0) -> dict[str, Any]:
    """Books, magazines, and comics by this author. Other kinds stay off the feed."""
    items: list[dict[str, Any]] = []
    for kind in OPDS_KINDS:
        skip = 0
        while True:
            page = db.browse_works(kind=kind, author=author, offset=skip, limit=100, sort="title")
            items.extend(page["items"])
            skip += int(page["limit"])
            if skip >= int(page["total"]):
                break
    items.sort(key=lambda work: str(work.get("title") or "").casefold())
    skip = max(0, int(offset))
    return {
        "items": items[skip : skip + PAGE_SIZE],
        "total": len(items),
        "offset": skip,
        "limit": PAGE_SIZE,
    }


def shelved_page(
    db: Database,
    *,
    kind: Optional[str] = None,
    author: Optional[str] = None,
    offset: int = 0,
) -> dict[str, Any]:
    """Shelved reading works only. Audiobooks and review slips stay out."""
    return db.browse_works(
        kind=kind,
        author=author,
        offset=max(0, int(offset)),
        limit=PAGE_SIZE,
        sort="author",
    )


def reading_authors(db: Database) -> list[str]:
    names: dict[str, str] = {}
    for kind in OPDS_KINDS:
        offset = 0
        while True:
            page = db.browse_works(kind=kind, offset=offset, limit=100, sort="author")
            for work in page["items"]:
                name = str(work.get("author") or "").strip()
                if name:
                    names.setdefault(name.casefold(), name)
            offset += int(page["limit"])
            if offset >= int(page["total"]):
                break
    return sorted(names.values(), key=str.casefold)


def acquisition_links(
    db: Database,
    work: dict[str, Any],
    *,
    data_dir: Path,
    download_base: str,
) -> list[dict[str, str]]:
    """One open acquisition URL per jailed reading file, each with its own token."""
    links: list[dict[str, str]] = []
    work_id = str(work.get("id") or "")
    for row in db.files_for_work(work_id):
        raw = str(row.get("path") or "")
        suffix = Path(raw).suffix.lower()
        media = ACQUISITION_TYPES.get(suffix)
        if not media:
            continue
        try:
            confined_serve_path(raw, data_dir=data_dir, must_exist=True)
        except PathDenied:
            continue
        file_id = str(row.get("id") or "")
        if not file_id:
            continue
        token = create_file_token(work_id, file_id, data_dir=data_dir)
        href = with_query(f"{download_base}/api/works/{work_id}/download", file=file_id, token=token)
        title = suffix.lstrip(".").upper() or "Download"
        links.append({"href": href, "type": media, "title": title})
    return links


def work_entry(
    db: Database,
    work: dict[str, Any],
    *,
    data_dir: Path,
    download_base: str,
) -> Optional[str]:
    links = acquisition_links(db, work, data_dir=data_dir, download_base=download_base)
    if not links:
        return None
    author = str(work.get("author") or "").strip()
    inner = ""
    if author:
        inner += f"<author><name>{_text(author)}</name></author>"
    year = work.get("year")
    if year:
        inner += f"<dcterms:issued>{_text(year)}</dcterms:issued>"
    isbn = str(work.get("isbn") or "").strip()
    if isbn:
        inner += f"<dcterms:identifier>{_text('urn:isbn:' + isbn)}</dcterms:identifier>"
    summary = str(work.get("description") or "").strip()
    series = str(work.get("series_name") or "").strip()
    index = str(work.get("series_index") or "").strip()
    if series:
        series_line = f"{series} {index}".strip()
        summary = f"{series_line}. {summary}".strip() if summary else series_line
    if summary:
        inner += f"<summary>{_text(summary[:2000])}</summary>"
    for link in links:
        inner += atom_link(
            "http://opds-spec.org/acquisition",
            link["href"],
            link["type"],
            title=link["title"],
        )
    return atom_entry(
        str(work.get("title") or "Untitled"),
        f"urn:librarian:work:{work.get('id')}",
        atom_time(work.get("updated_at")),
        inner,
    )


def acquisition_feed(
    db: Database,
    works: Iterable[dict[str, Any]],
    *,
    title: str,
    feed_id: str,
    self_href: str,
    start_href: str,
    data_dir: Path,
    download_base: str,
    next_href: str = "",
) -> str:
    entries: list[str] = []
    updated = atom_time(None)
    for work in works:
        if str(work.get("kind") or "") not in OPDS_KINDS:
            continue
        entry = work_entry(db, work, data_dir=data_dir, download_base=download_base)
        if entry is None:
            continue
        entries.append(entry)
        updated = atom_time(work.get("updated_at"))
    links = [
        atom_link("self", self_href, ACQUISITION_TYPE),
        atom_link("start", start_href, NAVIGATION_TYPE),
    ]
    if next_href:
        links.append(atom_link("next", next_href, ACQUISITION_TYPE))
    return feed_document(
        title=title,
        feed_id=feed_id,
        updated=updated,
        links=links,
        entries=entries,
    )
