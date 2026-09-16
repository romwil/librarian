"""Fill thin catalog works from Hardcover, then Open Library. Never invents an ISBN."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import httpx

from librarian.config import Settings
from librarian.covers import fetch_cover
from librarian.db import Database
from librarian.hardcover import HardcoverClient, HardcoverError
from librarian.identify import extract_isbn
from librarian.kinds import KIND_AUDIOBOOK, KIND_BOOK
from librarian.openlibrary import OpenLibraryClient

ENRICH_KINDS = (KIND_BOOK, KIND_AUDIOBOOK)


@dataclass
class Enrichment:
    title: str = ""
    author: str = ""
    description: str = ""
    series_name: str = ""
    series_index: str = ""
    year: Optional[int] = None
    cover_url: str = ""
    source: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {item.name: getattr(self, item.name) for item in fields(self)}

    def empty(self) -> bool:
        return not any(
            (
                self.description,
                self.series_name,
                self.series_index,
                self.year,
                self.cover_url,
            )
        )


def enrichment_from_mapping(data: Mapping[str, Any]) -> Enrichment:
    year = data.get("year")
    parsed_year: Optional[int] = None
    if isinstance(year, int):
        parsed_year = year
    elif str(year or "").isdigit():
        parsed_year = int(year)
    return Enrichment(
        title=str(data.get("title") or "").strip(),
        author=str(data.get("author") or "").strip(),
        description=str(data.get("description") or "").strip(),
        series_name=str(data.get("series_name") or "").strip(),
        series_index=str(data.get("series_index") or "").strip(),
        year=parsed_year,
        cover_url=str(data.get("cover_url") or "").strip(),
        source=str(data.get("source") or "").strip(),
    )


def is_thin(work: Mapping[str, Any]) -> bool:
    kind = str(work.get("kind") or "")
    if kind not in ENRICH_KINDS:
        return False
    cover = str(work.get("cover_path") or "").strip()
    cover_ok = bool(cover) and Path(cover).is_file()
    return not all(
        (
            str(work.get("description") or "").strip(),
            work.get("year") not in (None, ""),
            cover_ok,
        )
    )


def _http_client(*, transport: Optional[httpx.BaseTransport] = None) -> httpx.Client:
    return httpx.Client(timeout=20.0, transport=transport, follow_redirects=True)


def lookup_enrichment(
    work: Mapping[str, Any],
    settings: Settings,
    *,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
) -> Enrichment:
    """Hardcover first when a token is saved; Open Library fills remaining holes."""
    isbn = extract_isbn(str(work.get("isbn") or ""))
    title = str(work.get("title") or "").strip()
    author = str(work.get("author") or "").strip()
    own = client is None
    http = client or _http_client(transport=transport)
    merged = Enrichment()
    try:
        token = str(settings.hardcover_api_token or "").strip()
        if token:
            hardcover = HardcoverClient(token, transport=transport, client=http)
            try:
                raw = hardcover.lookup_by_isbn(isbn) if isbn else hardcover.lookup_by_title(title, author)
            except HardcoverError:
                raw = {}
            merged = _fill_empty(merged, enrichment_from_mapping(raw))
        if merged.empty() or _still_needs(merged, work):
            openlib = OpenLibraryClient(transport=transport, client=http)
            raw = openlib.lookup_by_isbn(isbn) if isbn else openlib.lookup_by_title(title, author)
            merged = _fill_empty(merged, enrichment_from_mapping(raw))
        return merged
    finally:
        if own:
            http.close()


def _still_needs(found: Enrichment, work: Mapping[str, Any]) -> bool:
    if not str(work.get("description") or "").strip() and not found.description:
        return True
    if work.get("year") in (None, "") and found.year is None:
        return True
    cover = str(work.get("cover_path") or "").strip()
    if not (cover and Path(cover).is_file()) and not found.cover_url:
        return True
    if not str(work.get("series_name") or "").strip() and not found.series_name:
        return True
    return False


def _fill_empty(base: Enrichment, incoming: Enrichment) -> Enrichment:
    if incoming.empty() and not incoming.title:
        return base
    source = incoming.source or base.source
    if base.source and incoming.source and incoming.source != base.source:
        source = f"{base.source}+{incoming.source}"
    elif base.source and not incoming.source:
        source = base.source
    return Enrichment(
        title=base.title or incoming.title,
        author=base.author or incoming.author,
        description=base.description or incoming.description,
        series_name=base.series_name or incoming.series_name,
        series_index=base.series_index or incoming.series_index,
        year=base.year if base.year is not None else incoming.year,
        cover_url=base.cover_url or incoming.cover_url,
        source=source,
    )


def apply_enrichment(
    db: Database,
    work: Mapping[str, Any],
    found: Enrichment,
    *,
    data_dir: Path,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """Write catalog fields that are still empty. Never invents or replaces an ISBN."""
    updated = dict(work)
    changed = False
    if found.description and not str(updated.get("description") or "").strip():
        updated["description"] = found.description
        changed = True
    if found.series_name and not str(updated.get("series_name") or "").strip():
        updated["series_name"] = found.series_name
        changed = True
    if found.series_index and not str(updated.get("series_index") or "").strip():
        updated["series_index"] = found.series_index
        changed = True
    if found.year is not None and updated.get("year") in (None, ""):
        updated["year"] = found.year
        changed = True

    cover = str(updated.get("cover_path") or "").strip()
    cover_ok = bool(cover) and Path(cover).is_file()
    if not cover_ok and (found.cover_url or extract_isbn(str(updated.get("isbn") or ""))):
        raw_folder = str(updated.get("folder_path") or "").strip()
        folder_path = Path(raw_folder) if raw_folder else None
        dest_folder = (
            folder_path
            if folder_path is not None and folder_path.is_dir()
            else Path(data_dir) / "covers" / str(updated["id"])
        )
        written = fetch_cover(
            dest_folder,
            {"isbn": updated.get("isbn") or "", "title": updated.get("title") or ""},
            indexer_cover_url=found.cover_url,
            transport=transport,
            client=client,
        )
        if written is not None:
            updated["cover_path"] = str(written)
            changed = True

    if not changed:
        return dict(work)
    row = db.upsert_work(updated)
    return row


def enrich_work(
    db: Database,
    settings: Settings,
    work_id: str,
    *,
    data_dir: Path,
    transport: Optional[httpx.BaseTransport] = None,
) -> Dict[str, Any]:
    work = db.get_work(work_id)
    if work is None:
        raise ValueError("Work not found")
    if str(work.get("kind") or "") not in ENRICH_KINDS:
        raise ValueError("Only books and audiobooks can be enriched")
    http = _http_client(transport=transport)
    try:
        found = lookup_enrichment(work, settings, transport=transport, client=http)
        updated = apply_enrichment(
            db, work, found, data_dir=data_dir, transport=transport, client=http
        )
    finally:
        http.close()
    return {
        "work": updated,
        "updated": _catalog_changed(work, updated),
        "source": found.source,
        "thin": is_thin(updated),
    }


def enrich_library(
    db: Database,
    settings: Settings,
    *,
    data_dir: Path,
    transport: Optional[httpx.BaseTransport] = None,
) -> Dict[str, Any]:
    scanned = 0
    updated = 0
    skipped = 0
    sources: Dict[str, int] = {}
    http = _http_client(transport=transport)
    try:
        for kind in ENRICH_KINDS:
            for work in db.list_works(kind=kind, limit=2000):
                if not is_thin(work):
                    skipped += 1
                    continue
                scanned += 1
                found = lookup_enrichment(work, settings, transport=transport, client=http)
                row = apply_enrichment(
                    db, work, found, data_dir=data_dir, transport=transport, client=http
                )
                if _catalog_changed(work, row):
                    updated += 1
                    key = found.source or "none"
                    sources[key] = sources.get(key, 0) + 1
                else:
                    skipped += 1
    finally:
        http.close()
    return {
        "scanned": scanned,
        "updated": updated,
        "skipped": skipped,
        "sources": sources,
    }


def _catalog_changed(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    keys = ("description", "series_name", "series_index", "year", "cover_path")
    return any(before.get(key) != after.get(key) for key in keys)
