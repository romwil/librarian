"""Fill thin catalog works from Hardcover → Open Library → Wikipedia → LLM polish.

Never invents an ISBN. Subjects become genre. Wikimedia art is localized with attribution.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import httpx

from librarian.config import Settings
from librarian.covers import download_image, fetch_cover, looks_like_image
from librarian.db import Database
from librarian.hardcover import HardcoverClient, HardcoverError
from librarian.identify import extract_isbn
from librarian.kinds import KIND_AUDIOBOOK, KIND_BOOK
from librarian.llm import LLMError, client_from_settings
from librarian.openlibrary import OpenLibraryClient
from librarian.wikipedia import fetch_book_page, resolve_wikimedia_art

logger = logging.getLogger(__name__)

ENRICH_KINDS = (KIND_BOOK, KIND_AUDIOBOOK)
BACKLOG_BATCH_DEFAULT = 5
BACKLOG_PAUSE_SECONDS = 1.0


@dataclass
class Enrichment:
    title: str = ""
    author: str = ""
    description: str = ""
    genre: str = ""
    series_name: str = ""
    series_index: str = ""
    year: Optional[int] = None
    cover_url: str = ""
    atmosphere_url: str = ""
    art_attribution: str = ""
    synopsis_source: str = ""
    llm_blurb: str = ""
    source: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {item.name: getattr(self, item.name) for item in fields(self)}

    def empty(self) -> bool:
        return not any(
            (
                self.description,
                self.genre,
                self.series_name,
                self.series_index,
                self.year,
                self.cover_url,
                self.atmosphere_url,
                self.llm_blurb,
            )
        )


def enrichment_from_mapping(data: Mapping[str, Any]) -> Enrichment:
    year = data.get("year")
    parsed_year: Optional[int] = None
    if isinstance(year, int):
        parsed_year = year
    elif str(year or "").isdigit():
        parsed_year = int(year)
    source = str(data.get("source") or "").strip()
    synopsis_source = str(data.get("synopsis_source") or "").strip()
    if not synopsis_source and data.get("description") and source:
        synopsis_source = source.split("+", 1)[0]
    return Enrichment(
        title=str(data.get("title") or "").strip(),
        author=str(data.get("author") or "").strip(),
        description=str(data.get("description") or "").strip(),
        genre=str(data.get("genre") or "").strip(),
        series_name=str(data.get("series_name") or "").strip(),
        series_index=str(data.get("series_index") or "").strip(),
        year=parsed_year,
        cover_url=str(data.get("cover_url") or "").strip(),
        atmosphere_url=str(data.get("atmosphere_url") or "").strip(),
        art_attribution=str(data.get("art_attribution") or "").strip(),
        synopsis_source=synopsis_source,
        llm_blurb=str(data.get("llm_blurb") or "").strip(),
        source=source,
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
            str(work.get("genre") or "").strip(),
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
    """Hardcover first when a token is saved; Open Library then Wikipedia fill holes."""
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
        if not str(work.get("description") or "").strip() and not merged.description:
            wiki = fetch_book_page(
                title,
                author=author,
                year=work.get("year") if isinstance(work.get("year"), int) else merged.year,
                transport=transport,
                client=http,
            )
            if wiki.get("extract"):
                art_url, attribution = resolve_wikimedia_art(
                    wiki, transport=transport, client=http
                )
                merged = _fill_empty(
                    merged,
                    Enrichment(
                        description=str(wiki["extract"]),
                        synopsis_source="wikipedia",
                        atmosphere_url=art_url,
                        art_attribution=attribution,
                        cover_url=art_url if not merged.cover_url else "",
                        source="wikipedia",
                    ),
                )
        cover_ok = bool(str(work.get("cover_path") or "").strip()) and Path(
            str(work.get("cover_path") or "")
        ).is_file()
        if (
            not cover_ok
            and not merged.cover_url
            and not str(work.get("atmosphere_path") or "").strip()
            and not merged.atmosphere_url
        ):
            # Wikimedia art only when HC/OL left cover and atmosphere empty.
            wiki = fetch_book_page(
                title,
                author=author,
                year=work.get("year") if isinstance(work.get("year"), int) else merged.year,
                transport=transport,
                client=http,
            )
            if wiki:
                art_url, attribution = resolve_wikimedia_art(
                    wiki, transport=transport, client=http
                )
                if art_url and attribution:
                    merged = _fill_empty(
                        merged,
                        Enrichment(
                            atmosphere_url=art_url,
                            art_attribution=attribution,
                            cover_url=art_url,
                            source="wikipedia",
                        ),
                    )
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
    if not str(work.get("genre") or "").strip() and not found.genre:
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
    synopsis_source = base.synopsis_source or incoming.synopsis_source
    if not synopsis_source and (base.description or incoming.description):
        synopsis_source = (base.source or incoming.source or "").split("+", 1)[0]
    return Enrichment(
        title=base.title or incoming.title,
        author=base.author or incoming.author,
        description=base.description or incoming.description,
        genre=base.genre or incoming.genre,
        series_name=base.series_name or incoming.series_name,
        series_index=base.series_index or incoming.series_index,
        year=base.year if base.year is not None else incoming.year,
        cover_url=base.cover_url or incoming.cover_url,
        atmosphere_url=base.atmosphere_url or incoming.atmosphere_url,
        art_attribution=base.art_attribution or incoming.art_attribution,
        synopsis_source=synopsis_source,
        llm_blurb=base.llm_blurb or incoming.llm_blurb,
        source=source,
    )


def apply_enrichment(
    db: Database,
    work: Mapping[str, Any],
    found: Enrichment,
    *,
    data_dir: Path,
    settings: Optional[Settings] = None,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """Write catalog fields that are still empty. Never invents or replaces an ISBN."""
    updated = dict(work)
    changed = False
    if found.description and not str(updated.get("description") or "").strip():
        updated["description"] = found.description
        if found.synopsis_source:
            updated["synopsis_source"] = found.synopsis_source
        elif found.source:
            updated["synopsis_source"] = found.source.split("+", 1)[0]
        changed = True
    if found.genre and not str(updated.get("genre") or "").strip():
        updated["genre"] = found.genre
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

    raw_folder = str(updated.get("folder_path") or "").strip()
    folder_path = Path(raw_folder) if raw_folder else None
    dest_folder = (
        folder_path
        if folder_path is not None and folder_path.is_dir()
        else Path(data_dir) / "covers" / str(updated["id"])
    )

    cover = str(updated.get("cover_path") or "").strip()
    cover_ok = bool(cover) and Path(cover).is_file()
    if not cover_ok and (found.cover_url or extract_isbn(str(updated.get("isbn") or ""))):
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
            cover_ok = True

    if found.atmosphere_url and found.art_attribution:
        atmosphere = dest_folder / "atmosphere.jpg"
        if not atmosphere.is_file():
            data = download_image(found.atmosphere_url, transport=transport, client=client)
            if data and looks_like_image(data):
                dest_folder.mkdir(parents=True, exist_ok=True)
                atmosphere.write_bytes(data)
                updated["atmosphere_path"] = str(atmosphere)
                updated["art_attribution"] = found.art_attribution
                changed = True
                if not cover_ok:
                    cover_dest = dest_folder / "cover.jpg"
                    if not cover_dest.is_file():
                        cover_dest.write_bytes(data)
                        updated["cover_path"] = str(cover_dest)
                        changed = True
        elif not str(updated.get("atmosphere_path") or "").strip():
            updated["atmosphere_path"] = str(atmosphere)
            if found.art_attribution and not str(updated.get("art_attribution") or "").strip():
                updated["art_attribution"] = found.art_attribution
            changed = True

    if settings is not None and not str(updated.get("llm_blurb") or "").strip():
        source_text = str(updated.get("description") or found.description or "").strip()
        if source_text:
            llm = client_from_settings(settings, transport=transport)
            if llm is not None:
                try:
                    blurb = llm.polish_blurb(
                        title=str(updated.get("title") or ""),
                        author=str(updated.get("author") or ""),
                        source_text=source_text,
                    )
                except LLMError as error:
                    logger.debug("LLM polish skipped: %s", error)
                    blurb = ""
                finally:
                    llm.close()
                if blurb:
                    updated["llm_blurb"] = blurb
                    if not str(updated.get("synopsis_source") or "").strip():
                        updated["synopsis_source"] = "llm"
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
            db,
            work,
            found,
            data_dir=data_dir,
            settings=settings,
            transport=transport,
            client=http,
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
                    db,
                    work,
                    found,
                    data_dir=data_dir,
                    settings=settings,
                    transport=transport,
                    client=http,
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


def enrich_backlog_batch(
    db: Database,
    settings: Settings,
    *,
    data_dir: Path,
    limit: int = BACKLOG_BATCH_DEFAULT,
    transport: Optional[httpx.BaseTransport] = None,
    pause_seconds: float = BACKLOG_PAUSE_SECONDS,
) -> Dict[str, Any]:
    """Paced trickle for historical holes. Small batches; never invents ISBN."""
    backlog = db.works_needing_enrichment(limit=max(1, int(limit)))
    if not backlog:
        return {"status": "completed", "enriched": 0, "remaining": 0}
    enriched = 0
    errors = 0
    http = _http_client(transport=transport)
    try:
        for idx, work in enumerate(backlog):
            try:
                found = lookup_enrichment(work, settings, transport=transport, client=http)
                row = apply_enrichment(
                    db,
                    work,
                    found,
                    data_dir=data_dir,
                    settings=settings,
                    transport=transport,
                    client=http,
                )
                if _catalog_changed(work, row):
                    enriched += 1
            except Exception:
                errors += 1
                logger.exception("Enrich backlog failed for %s", work.get("id"))
            if idx + 1 < len(backlog) and pause_seconds > 0:
                time.sleep(pause_seconds)
    finally:
        http.close()
    remaining = db.count_works_needing_enrichment()
    return {
        "status": "completed",
        "enriched": enriched,
        "errors": errors,
        "batch_size": len(backlog),
        "remaining": remaining,
        "has_more": remaining > 0,
    }


def _catalog_changed(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    keys = (
        "description",
        "genre",
        "series_name",
        "series_index",
        "year",
        "cover_path",
        "atmosphere_path",
        "art_attribution",
        "synopsis_source",
        "llm_blurb",
    )
    return any(before.get(key) != after.get(key) for key in keys)
