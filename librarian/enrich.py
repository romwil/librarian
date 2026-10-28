"""Fill thin catalog works from Hardcover → Open Library → Wikipedia → LLM polish.

Never invents an ISBN. Subjects become genre. Wikimedia art is localized with attribution.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Protocol

import httpx

from librarian.config import Settings
from librarian.covers import (
    assert_safe_cover_url,
    cover_file_ok,
    download_image,
    fetch_cover,
    looks_like_image,
)
from librarian.db import Database
from librarian.hardcover import HardcoverClient, HardcoverError
from librarian.identify import extract_isbn
from librarian.identity import resolve_work
from librarian.identity.authors import author_match_key, display_name, sort_name
from librarian.identity.isbn import canonical_isbn13
from librarian.identity.titles import title_match_key, title_sort
from librarian.kinds import ALL_KINDS, KIND_AUDIOBOOK, KIND_BOOK, KIND_MAGAZINE
from librarian.llm import LLMError, client_from_settings
from librarian.naming.magazine import (
    extract_magazine_cover,
    magazine_identity_matches,
    parse_magazine,
)
from librarian.openlibrary import OpenLibraryClient
from librarian.wikipedia import fetch_book_page, resolve_wikimedia_art

logger = logging.getLogger(__name__)

ENRICH_KINDS = (KIND_BOOK, KIND_AUDIOBOOK)
ENRICH_LIST_PAGE = 2000
BACKLOG_BATCH_DEFAULT = 5
BACKLOG_PAUSE_SECONDS = 1.0

COVER_PERMISSION_COPY = (
    "Couldn't write cover art — a shelf folder is locked for the lamp. "
    "Enrich kept going where it could; covers may land under the cover cache. "
    "On Automat, library folders should be writable by PUID/PGID (often 99:100)."
)

# Shelf / identify fallback written when no creator was known — not a real author.
_UNKNOWN_AUTHOR_MARKERS = frozenset(
    {
        "unknown author",
        "unknown authors",
        "author unknown",
        "anonymous",
        "n/a",
        "none",
        "null",
    }
)


def author_missing(author: Any) -> bool:
    """True when catalog author is empty or a known identify/migrate placeholder."""
    text = str(author or "").strip()
    if not text:
        return True
    return text.casefold() in _UNKNOWN_AUTHOR_MARKERS


def lookup_author(work: Mapping[str, Any]) -> str:
    """Author safe to send to Hardcover / Open Library / Audnexus (never a placeholder)."""
    author = str(work.get("author") or "").strip()
    return "" if author_missing(author) else author


def friendly_enrich_error(error: BaseException, *, title: str = "") -> str:
    """Household copy for enrich failures (never raw Errno 13)."""
    text = str(error or "").strip()
    permission = isinstance(error, PermissionError) or "[Errno 13]" in text or "Permission denied" in text
    if permission:
        if title:
            return (
                f"Couldn't write cover for {title} — shelf folder is locked; "
                "skipped that art and kept going."
            )
        return COVER_PERMISSION_COPY
    if not text:
        return "Enrich failed."
    if len(text) > 180 or "traceback" in text.lower():
        return "Something went wrong while enriching. Check the lamp logs."
    return text


def owned_cover_folder(data_dir: Path, work_id: str) -> Path:
    """DATA_DIR cover cache keyed by work id — always writable by the lamp."""
    return Path(data_dir) / "covers" / str(work_id)


def work_cover_folder(work: Mapping[str, Any], data_dir: Path) -> Path:
    """Prefer the shelf folder when present; else the owned cover cache."""
    raw_folder = str(work.get("folder_path") or "").strip()
    folder_path = Path(raw_folder) if raw_folder else None
    if folder_path is not None and folder_path.is_dir():
        return folder_path
    return owned_cover_folder(data_dir, str(work.get("id") or "unknown"))


def fetch_cover_with_fallback(
    work: Mapping[str, Any],
    data_dir: Path,
    identity: Mapping[str, Any],
    *,
    indexer_cover_url: str = "",
    hardcover_token: str = "",
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
    require_safe_url: bool = True,
    replace: bool = False,
) -> Optional[Path]:
    """Write cover to the shelf folder, or fall back to DATA_DIR/covers/{id}."""
    preferred = work_cover_folder(work, data_dir)
    owned = owned_cover_folder(data_dir, str(work.get("id") or "unknown"))
    written = fetch_cover(
        preferred,
        identity,
        indexer_cover_url=indexer_cover_url,
        hardcover_token=hardcover_token,
        transport=transport,
        client=client,
        require_safe_url=require_safe_url,
        replace=replace,
    )
    if written is not None:
        return written
    try:
        same = preferred.resolve() == owned.resolve()
    except OSError:
        same = preferred == owned
    if same:
        return None
    return fetch_cover(
        owned,
        identity,
        indexer_cover_url=indexer_cover_url,
        hardcover_token=hardcover_token,
        transport=transport,
        client=client,
        require_safe_url=require_safe_url,
        replace=replace,
    )


def write_image_with_fallback(
    dest_folder: Path,
    owned_folder: Path,
    filename: str,
    data: bytes,
) -> Optional[Path]:
    """Write an image bytes to dest_folder, falling back to owned_folder on OSError."""
    for folder in (dest_folder, owned_folder):
        path = folder / filename
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return path
        except OSError:
            logger.warning("Cannot write %s under %s", filename, folder, exc_info=True)
            try:
                if dest_folder.resolve() == owned_folder.resolve():
                    break
            except OSError:
                if dest_folder == owned_folder:
                    break
            continue
    return None


class EnrichProgressSink(Protocol):
    def start(self, *, total: int, phase: str = "scanning") -> None: ...

    def log(self, line: str) -> None: ...

    def tick(
        self,
        *,
        phase: str = "",
        current_title: str = "",
        done: Optional[int] = None,
        total: Optional[int] = None,
        updated: Optional[int] = None,
        skipped: Optional[int] = None,
        errors: Optional[int] = None,
        log: str = "",
    ) -> None: ...

    def complete(self, result: Mapping[str, Any]) -> None: ...

    def fail(self, error: str) -> None: ...


# Rank order for Enrichment.identifier_strength when two results merge — the higher
# survives. "strong" means a direct identifier lookup (ISBN/ASIN/explicit OL work key);
# "weak" means a fuzzy title+author search hit.
_STRENGTH_RANK = {"": 0, "weak": 1, "strong": 2}


@dataclass
class Enrichment:
    title: str = ""
    subtitle: str = ""
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
    match_key: str = ""
    match_confidence: Optional[float] = None
    # Canonical identity written to work_identifiers — never invented, only copied
    # from a real catalog hit.
    ol_work_key: str = ""
    hardcover_id: str = ""
    isbn13s: List[str] = field(default_factory=list)
    asin: str = ""
    narrator: str = ""
    # "" (none), "weak" (title search), or "strong" (direct identifier lookup). Only
    # "strong" may correct an existing, non-blank catalog field.
    identifier_strength: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {item.name: getattr(self, item.name) for item in fields(self)}

    def empty(self) -> bool:
        return not any(
            (
                self.author,
                self.description,
                self.genre,
                self.series_name,
                self.series_index,
                self.year,
                self.cover_url,
                self.atmosphere_url,
                self.llm_blurb,
                self.subtitle,
                self.ol_work_key,
                self.hardcover_id,
                self.isbn13s,
                self.asin,
                self.narrator,
            )
        )

    def is_strong(self) -> bool:
        return self.identifier_strength == "strong"


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
    confidence = data.get("match_confidence")
    parsed_confidence: Optional[float] = None
    if isinstance(confidence, (int, float)):
        parsed_confidence = float(confidence)
    elif str(confidence or "").strip():
        try:
            parsed_confidence = float(confidence)
        except ValueError:
            parsed_confidence = None
    raw_isbn13s = data.get("isbn13s") or ()
    if isinstance(raw_isbn13s, str):
        raw_isbn13s = (raw_isbn13s,)
    isbn13s: List[str] = []
    for value in raw_isbn13s:
        canonical = canonical_isbn13(value)
        if canonical and canonical not in isbn13s:
            isbn13s.append(canonical)
    return Enrichment(
        title=str(data.get("title") or "").strip(),
        subtitle=str(data.get("subtitle") or "").strip(),
        author=str(data.get("author") or "").strip(),
        description=str(data.get("description") or "").strip(),
        genre=str(data.get("genre") or "").strip(),
        series_name=str(data.get("series_name") or "").strip(),
        series_index=str(data.get("series_index") or "").strip(),
        year=parsed_year,
        cover_url=str(data.get("cover_url") or data.get("cover") or "").strip(),
        atmosphere_url=str(data.get("atmosphere_url") or "").strip(),
        art_attribution=str(data.get("art_attribution") or "").strip(),
        synopsis_source=synopsis_source,
        llm_blurb=str(data.get("llm_blurb") or "").strip(),
        source=source,
        match_key=str(data.get("match_key") or "").strip(),
        match_confidence=parsed_confidence,
        ol_work_key=str(data.get("ol_work") or data.get("ol_work_key") or "").strip(),
        hardcover_id=str(data.get("hardcover_id") or "").strip(),
        isbn13s=isbn13s,
        asin=str(data.get("asin") or "").strip().upper(),
        narrator=str(data.get("narrator") or "").strip(),
    )


def missing_enrichment_count(work: Mapping[str, Any]) -> int:
    """How many Enrich fields are still empty. Not a sticky `enriched` flag.

    Fields match `is_thin`: author, description, year, on-disk cover, genre.
    Comics/music score 0 (Enrich does not fill them).
    """
    if str(work.get("kind") or "") not in ENRICH_KINDS:
        return 0
    missing = 0
    if author_missing(work.get("author")):
        missing += 1
    if not str(work.get("description") or "").strip():
        missing += 1
    if work.get("year") in (None, ""):
        missing += 1
    if not cover_file_ok(work):
        missing += 1
    if not str(work.get("genre") or "").strip():
        missing += 1
    return missing


def is_thin(work: Mapping[str, Any]) -> bool:
    return missing_enrichment_count(work) > 0


def _http_client(*, transport: Optional[httpx.BaseTransport] = None) -> httpx.Client:
    return httpx.Client(timeout=20.0, transport=transport, follow_redirects=True)


def _lookup_audnexus_identity(
    work: Mapping[str, Any],
    settings: Settings,
    *,
    title: str,
    author: str,
    transport: Optional[httpx.BaseTransport] = None,
    data_dir: Path,
) -> Optional[Enrichment]:
    """ASIN + narrator from Audnexus for a confident match only. Never the isbn column."""
    from librarian.audnexus import (
        AudnexusCache,
        AudnexusClient,
        AudnexusError,
        match_audiobook_tokens,
    )

    aud = None
    try:
        # Built from the caller's own data_dir — never the settings/env fallback to
        # /config that client_from_settings() would otherwise use.
        aud = AudnexusClient(
            cache=AudnexusCache(Path(data_dir) / "audnexus_cache.sqlite"),
            transport=transport,
            region=str(getattr(settings, "audnexus_region", "us") or "us"),
        )
        matched = match_audiobook_tokens(
            {
                "title": title,
                "author": author,
                "asin": str(work.get("asin") or ""),
                "narrator": str(work.get("narrator") or ""),
                "series_name": str(work.get("series_name") or ""),
                "series_index": str(work.get("series_index") or ""),
                "year": work.get("year") if isinstance(work.get("year"), int) else None,
            },
            client=aud,
            limit=3,
        )
    except AudnexusError:
        return None
    except Exception:
        logger.debug("Audnexus auto-lookup skipped", exc_info=True)
        return None
    finally:
        if aud is not None:
            aud.close()
    identity = matched.get("identity") if isinstance(matched, dict) else None
    if not identity:
        return None
    asin = str(identity.get("asin") or "").strip().upper()
    narrator = str(identity.get("narrator") or "").strip()
    if not asin and not narrator:
        return None
    return Enrichment(asin=asin, narrator=narrator, source="audnexus", identifier_strength="strong")


def lookup_enrichment(
    work: Mapping[str, Any],
    settings: Settings,
    *,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
    data_dir: Optional[Path] = None,
) -> Enrichment:
    """Hardcover first when a token is saved; Open Library then Wikipedia fill holes.

    ``data_dir`` gates the Audnexus audiobook lookup (its cache is a real SQLite file
    under DATA_DIR) — omit it and that lookup is skipped rather than defaulting to
    ``/config``.
    """
    isbn = extract_isbn(str(work.get("isbn") or ""))
    title = str(work.get("title") or "").strip()
    kind = str(work.get("kind") or "").strip()
    # Placeholder "Unknown Author" must not be sent — OL/Audible treat it as a filter
    # and return zero hits for otherwise matchable titles.
    author = lookup_author(work)
    own = client is None
    http = client or _http_client(transport=transport)
    merged = Enrichment()
    try:
        token = str(settings.hardcover_api_token or "").strip()
        if token:
            hardcover = HardcoverClient(token, transport=transport, client=http)
            try:
                if isbn:
                    raw = hardcover.lookup_by_isbn(isbn)
                    strength = "strong" if raw else ""
                else:
                    raw = hardcover.lookup_by_title(title, author)
                    strength = "weak" if raw else ""
            except HardcoverError:
                raw, strength = {}, ""
            hc_found = enrichment_from_mapping(raw)
            hc_found.identifier_strength = strength
            merged = _fill_empty(merged, hc_found)
        if merged.empty() or _still_needs(merged, work):
            openlib = OpenLibraryClient(transport=transport, client=http)
            work_year = work.get("year") if isinstance(work.get("year"), int) else None
            # ISBN editions are often stubs (year/cover URL, no blurb). Title search
            # hits the work record — fall through when the ISBN payload still has holes.
            if isbn:
                ol_isbn_raw = openlib.lookup_by_isbn(isbn)
                ol_isbn_found = enrichment_from_mapping(ol_isbn_raw)
                ol_isbn_found.identifier_strength = "strong" if ol_isbn_raw else ""
                merged = _fill_empty(merged, ol_isbn_found)
            if title and (not isbn or _still_needs(merged, work)):
                ol_title_raw = openlib.lookup_by_title(title, author, year=work_year)
                ol_title_found = enrichment_from_mapping(ol_title_raw)
                ol_title_found.identifier_strength = "weak" if ol_title_raw else ""
                merged = _fill_empty(merged, ol_title_found)
        if kind == KIND_AUDIOBOOK:
            # Print jackets from HC/OL must not beat square Audnexus art in fetch_cover.
            merged.cover_url = ""
            have_asin = bool(str(work.get("asin") or "").strip())
            have_narrator = bool(str(work.get("narrator") or "").strip())
            if data_dir is not None and not (have_asin and have_narrator):
                audnexus_found = _lookup_audnexus_identity(
                    work, settings, title=title, author=author, transport=transport,
                    data_dir=data_dir,
                )
                if audnexus_found is not None:
                    merged = _fill_empty(merged, audnexus_found)
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
                        source="wikipedia",
                    ),
                )
        cover_ok = cover_file_ok(work)
        if (
            not cover_ok
            and not merged.cover_url
            and not str(work.get("atmosphere_path") or "").strip()
            and not merged.atmosphere_url
        ):
            # Wikimedia art is atmosphere / last-resort — never a kind-specific jacket URL.
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
                            source="wikipedia",
                        ),
                    )
        return merged
    finally:
        if own:
            http.close()


def _still_needs(found: Enrichment, work: Mapping[str, Any]) -> bool:
    if author_missing(work.get("author")) and not found.author:
        return True
    if not str(work.get("description") or "").strip() and not found.description:
        return True
    if work.get("year") in (None, "") and found.year is None:
        return True
    if not cover_file_ok(work) and not found.cover_url:
        return True
    if not str(work.get("series_name") or "").strip() and not found.series_name:
        return True
    if not str(work.get("genre") or "").strip() and not found.genre:
        return True
    return False


def _fill_empty(base: Enrichment, incoming: Enrichment) -> Enrichment:
    if incoming.empty() and not incoming.title and not incoming.author:
        return base
    source = incoming.source or base.source
    if base.source and incoming.source and incoming.source != base.source:
        source = f"{base.source}+{incoming.source}"
    elif base.source and not incoming.source:
        source = base.source
    synopsis_source = base.synopsis_source or incoming.synopsis_source
    if not synopsis_source and (base.description or incoming.description):
        synopsis_source = (base.source or incoming.source or "").split("+", 1)[0]
    merged_isbn13s = list(base.isbn13s)
    for value in incoming.isbn13s:
        if value not in merged_isbn13s:
            merged_isbn13s.append(value)
    identifier_strength = base.identifier_strength
    if _STRENGTH_RANK.get(incoming.identifier_strength, 0) > _STRENGTH_RANK.get(
        identifier_strength, 0
    ):
        identifier_strength = incoming.identifier_strength
    return Enrichment(
        title=base.title or incoming.title,
        subtitle=base.subtitle or incoming.subtitle,
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
        match_key=base.match_key or incoming.match_key,
        match_confidence=(
            base.match_confidence
            if base.match_confidence is not None
            else incoming.match_confidence
        ),
        ol_work_key=base.ol_work_key or incoming.ol_work_key,
        hardcover_id=base.hardcover_id or incoming.hardcover_id,
        isbn13s=merged_isbn13s,
        asin=base.asin or incoming.asin,
        narrator=base.narrator or incoming.narrator,
        identifier_strength=identifier_strength,
    )


def _resolve_audiobook_book_work(
    db: Database, work_id: str, *, title: str, author: str, asin: str
) -> Optional[str]:
    """Canonical book work for an audiobook's ASIN, via the identity resolver.

    ``resolve_work`` is built to run *before* a row is inserted; called here on an
    already-shelved audiobook, its own row is one of the candidates it searches, so a
    real book sibling makes the normalized step ambiguous (two matches, not one) and
    it returns ``None``. The book-only fallback below applies the same normalized
    title+author rule, just scoped so this row can never match itself.
    """
    candidate = {"kind": KIND_AUDIOBOOK, "title": title, "author": author, "asin": asin}
    try:
        resolved = resolve_work(db, candidate)
    except Exception:
        resolved = None
    if resolved and resolved != work_id:
        return resolved
    title_key = title_match_key(title)
    author_key = author_match_key(author, db)
    if not title_key or not author_key:
        return None
    with db._connect() as conn:
        rows = conn.execute("SELECT id, title, author FROM works WHERE kind = ?", (KIND_BOOK,)).fetchall()
    matches = [
        str(row["id"])
        for row in rows
        if title_match_key(row["title"]) == title_key
        and author_match_key(row["author"], db) == author_key
    ]
    return matches[0] if len(matches) == 1 else None


def _write_identifiers(
    db: Database,
    work_id: str,
    found: Enrichment,
    *,
    asin_work_id: Optional[str] = None,
) -> None:
    """Record every canonical identifier a lookup turned up. Never gated on a lock —
    identifiers are reference data, not a hand-typed catalog field.
    """
    if found.ol_work_key:
        try:
            db.upsert_work_identifier(scheme="ol_work", value=found.ol_work_key, work_id=work_id)
        except ValueError:
            logger.debug("Skipped malformed ol_work identifier for %s", work_id)
    if found.hardcover_id:
        try:
            db.upsert_work_identifier(
                scheme="hardcover", value=str(found.hardcover_id), work_id=work_id
            )
        except ValueError:
            logger.debug("Skipped malformed hardcover identifier for %s", work_id)
    for isbn13 in found.isbn13s:
        try:
            db.upsert_work_identifier(scheme="isbn13", value=isbn13, work_id=work_id)
        except ValueError:
            logger.debug("Skipped malformed isbn13 identifier for %s", work_id)
    if found.asin:
        try:
            db.upsert_work_identifier(
                scheme="asin", value=found.asin.upper(), work_id=asin_work_id or work_id
            )
        except ValueError:
            logger.debug("Skipped malformed asin identifier for %s", work_id)


def apply_enrichment(
    db: Database,
    work: Mapping[str, Any],
    found: Enrichment,
    *,
    data_dir: Path,
    settings: Optional[Settings] = None,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
    replace: bool = False,
) -> Dict[str, Any]:
    """Write catalog fields that are still empty. Never invents an ISBN.

    When ``replace`` is True (Fix match), overwrite description / genre / year /
    synopsis fields from the chosen enrichment.

    A strong identifier match (direct ISBN/ASIN/OL-work lookup, not a fuzzy title
    search) may additionally *correct* title, subtitle, author display, series, and
    year — even when they already hold a value — unless ``work['metadata_locked']``
    is set, in which case those fields are left exactly as the owner typed them.
    Canonical identifiers (Open Library work key, Hardcover id, edition ISBNs, ASIN)
    are always written to ``work_identifiers``, locked or not.
    """
    updated = dict(work)
    changed = False
    subtitle_write: Optional[str] = None
    locked = bool(updated.get("metadata_locked"))
    strong = found.is_strong() and not locked

    if strong:
        title_or_author_changed = False
        new_title = found.title.strip()
        if new_title and new_title != str(updated.get("title") or "").strip():
            updated["title"] = new_title
            changed = True
            title_or_author_changed = True
        new_subtitle = found.subtitle.strip()
        if new_subtitle and new_subtitle != str(work.get("subtitle") or "").strip():
            subtitle_write = new_subtitle
            changed = True
        new_author = display_name(found.author) if found.author else ""
        if new_author and new_author != str(updated.get("author") or "").strip():
            updated["author"] = new_author
            changed = True
            title_or_author_changed = True
        new_series_name = found.series_name.strip()
        if new_series_name and new_series_name != str(updated.get("series_name") or "").strip():
            updated["series_name"] = new_series_name
            changed = True
        new_series_index = found.series_index.strip()
        if new_series_index and new_series_index != str(updated.get("series_index") or "").strip():
            updated["series_index"] = new_series_index
            changed = True
        if found.year is not None and found.year != updated.get("year"):
            updated["year"] = found.year
            changed = True
        if title_or_author_changed:
            updated["title_sort"] = title_sort(updated.get("title"))
            updated["author_sort"] = sort_name(updated.get("author"))

    if found.author and (replace or author_missing(updated.get("author"))):
        updated["author"] = found.author
        changed = True
    if found.description and (replace or not str(updated.get("description") or "").strip()):
        updated["description"] = found.description
        if found.synopsis_source:
            updated["synopsis_source"] = found.synopsis_source
        elif found.source:
            updated["synopsis_source"] = found.source.split("+", 1)[0]
        if replace:
            updated["llm_blurb"] = ""
        changed = True
    if found.genre and (replace or not str(updated.get("genre") or "").strip()):
        updated["genre"] = found.genre
        changed = True
    if found.series_name and (replace or not str(updated.get("series_name") or "").strip()):
        updated["series_name"] = found.series_name
        changed = True
    if found.series_index and (replace or not str(updated.get("series_index") or "").strip()):
        updated["series_index"] = found.series_index
        changed = True
    if found.year is not None and (replace or updated.get("year") in (None, "")):
        updated["year"] = found.year
        changed = True
    if found.asin and not str(updated.get("asin") or "").strip():
        # ASIN lives in its own column (and as a work_identifiers row below) — never isbn.
        updated["asin"] = found.asin.upper()
        changed = True
    if found.narrator and not str(updated.get("narrator") or "").strip():
        updated["narrator"] = found.narrator
        changed = True
    if (
        not extract_isbn(str(updated.get("isbn") or ""))
        and found.isbn13s
        and found.title
        and found.author
        and title_match_key(found.title) == title_match_key(updated.get("title"))
        and author_match_key(found.author, db) == author_match_key(updated.get("author"), db)
    ):
        # Title+author search may only fill a missing ISBN when both agree with the
        # catalog row — never when the hit could be a different edition or book.
        updated["isbn"] = found.isbn13s[0]
        changed = True

    identifier_target = str(updated.get("id") or work.get("id") or "")
    if identifier_target:
        asin_target = identifier_target
        if found.asin and str(updated.get("kind") or "") == KIND_AUDIOBOOK:
            asin_target = _resolve_audiobook_book_work(
                db,
                identifier_target,
                title=str(updated.get("title") or ""),
                author=str(updated.get("author") or ""),
                asin=found.asin,
            ) or identifier_target
        _write_identifiers(db, identifier_target, found, asin_work_id=asin_target)

    raw_folder = str(updated.get("folder_path") or "").strip()
    folder_path = Path(raw_folder) if raw_folder else None
    owned_folder = owned_cover_folder(data_dir, str(updated["id"]))
    dest_folder = (
        folder_path
        if folder_path is not None and folder_path.is_dir()
        else owned_folder
    )

    cover_ok = cover_file_ok(updated)
    isbn = extract_isbn(str(updated.get("isbn") or ""))
    title = str(updated.get("title") or "").strip()
    if (not cover_ok or replace) and (found.cover_url or isbn or title):
        written = fetch_cover_with_fallback(
            updated,
            data_dir,
            {
                "isbn": updated.get("isbn") or "",
                "title": updated.get("title") or "",
                "author": updated.get("author") or "",
                "kind": updated.get("kind") or "",
                "asin": updated.get("asin") or "",
                "narrator": updated.get("narrator") or "",
                "year": updated.get("year") if isinstance(updated.get("year"), int) else None,
            },
            indexer_cover_url=found.cover_url,
            hardcover_token=str(getattr(settings, "hardcover_api_token", "") or ""),
            transport=transport,
            client=client,
            require_safe_url=True,
            replace=replace,
        )
        if written is not None:
            updated["cover_path"] = str(written)
            changed = True
            cover_ok = True

    if found.atmosphere_url and found.art_attribution:
        atmosphere = dest_folder / "atmosphere.jpg"
        if not atmosphere.is_file():
            data = download_image(
                found.atmosphere_url,
                transport=transport,
                client=client,
                require_safe_url=True,
            )
            if data and looks_like_image(data):
                written_atmo = write_image_with_fallback(
                    dest_folder, owned_folder, "atmosphere.jpg", data
                )
                if written_atmo is not None:
                    updated["atmosphere_path"] = str(written_atmo)
                    updated["art_attribution"] = found.art_attribution
                    changed = True
                    if not cover_ok:
                        cover_candidate = written_atmo.parent / "cover.jpg"
                        if not cover_candidate.is_file():
                            cover_written = write_image_with_fallback(
                                written_atmo.parent, owned_folder, "cover.jpg", data
                            )
                            if cover_written is not None:
                                updated["cover_path"] = str(cover_written)
                                changed = True
        elif not str(updated.get("atmosphere_path") or "").strip():
            updated["atmosphere_path"] = str(atmosphere)
            if found.art_attribution and not str(updated.get("art_attribution") or "").strip():
                updated["art_attribution"] = found.art_attribution
            changed = True

    if settings is not None and (replace or not str(updated.get("llm_blurb") or "").strip()):
        source_text = str(updated.get("description") or found.description or "").strip()
        if source_text and (replace or not str(updated.get("llm_blurb") or "").strip()):
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
    if subtitle_write is not None:
        db.set_work_subtitle(str(row["id"]), subtitle_write)
        row = db.get_work(str(row["id"])) or row
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
        found = lookup_enrichment(work, settings, transport=transport, client=http, data_dir=data_dir)
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
        "match_key": found.match_key,
        "match_confidence": found.match_confidence,
    }


def enrich_library(
    db: Database,
    settings: Settings,
    *,
    data_dir: Path,
    transport: Optional[httpx.BaseTransport] = None,
    progress: Optional[EnrichProgressSink] = None,
) -> Dict[str, Any]:
    thin: list[Dict[str, Any]] = []
    skipped = 0
    for kind in ENRICH_KINDS:
        offset = 0
        while True:
            batch = db.list_works(kind=kind, limit=ENRICH_LIST_PAGE, offset=offset)
            if not batch:
                break
            for work in batch:
                if not is_thin(work):
                    skipped += 1
                    continue
                thin.append(work)
            if len(batch) < ENRICH_LIST_PAGE:
                break
            offset += len(batch)
    thin.sort(
        key=lambda work: (
            -missing_enrichment_count(work),
            str(work.get("title") or "").casefold(),
        )
    )
    complete = skipped
    total = len(thin)
    if progress is not None:
        progress.start(total=total, phase="enriching" if total else "done")
        if total and complete:
            progress.log(
                f"Skipping {complete} complete volume{'s' if complete != 1 else ''}; "
                f"enriching {total} starting with the emptiest."
            )
        elif total:
            progress.log(
                f"Found {total} thin volume{'s' if total != 1 else ''} to enrich, emptiest first."
            )
        else:
            progress.log("No thin volumes — shelves look complete.")

    scanned = 0
    updated = 0
    errors = 0
    sources: Dict[str, int] = {}
    http = _http_client(transport=transport)
    try:
        for work in thin:
            title = str(work.get("title") or "Untitled").strip() or "Untitled"
            scanned += 1
            if progress is not None:
                progress.tick(
                    phase="enriching",
                    current_title=title,
                    done=scanned,
                    total=total,
                    updated=updated,
                    skipped=skipped,
                    errors=errors,
                    log=f"Looking up {title}…",
                )
            try:
                found = lookup_enrichment(work, settings, transport=transport, client=http, data_dir=data_dir)
                row = apply_enrichment(
                    db,
                    work,
                    found,
                    data_dir=data_dir,
                    settings=settings,
                    transport=transport,
                    client=http,
                )
            except Exception as error:
                errors += 1
                logger.exception("Enrich failed for %s", work.get("id"))
                if progress is not None:
                    progress.tick(
                        updated=updated,
                        skipped=skipped,
                        errors=errors,
                        log=friendly_enrich_error(error, title=title),
                    )
                continue
            if _catalog_changed(work, row):
                updated += 1
                key = found.source or "none"
                sources[key] = sources.get(key, 0) + 1
                if progress is not None:
                    progress.tick(
                        updated=updated,
                        skipped=skipped,
                        errors=errors,
                        log=f"Filled {title} from {key}.",
                    )
            else:
                skipped += 1
                if progress is not None:
                    progress.tick(
                        updated=updated,
                        skipped=skipped,
                        errors=errors,
                        log=f"No new fields for {title}.",
                    )
    finally:
        http.close()
    result = {
        "scanned": scanned,
        "updated": updated,
        "skipped": skipped,
        "complete": complete,
        "errors": errors,
        "sources": sources,
    }
    if progress is not None:
        progress.complete(result)
    return result


def enrich_backlog_batch(
    db: Database,
    settings: Settings,
    *,
    data_dir: Path,
    limit: int = BACKLOG_BATCH_DEFAULT,
    transport: Optional[httpx.BaseTransport] = None,
    pause_seconds: float = BACKLOG_PAUSE_SECONDS,
    progress: Optional[EnrichProgressSink] = None,
) -> Dict[str, Any]:
    """Paced trickle for historical holes. Small batches; never invents ISBN."""
    backlog = db.works_needing_enrichment(limit=max(1, int(limit)))
    if not backlog:
        result = {"status": "completed", "enriched": 0, "remaining": 0}
        if progress is not None:
            progress.start(total=0, phase="done")
            progress.log("Trickle: nothing left to enrich.")
            progress.complete({**result, "scanned": 0, "updated": 0, "skipped": 0})
        return result
    if progress is not None:
        progress.start(total=len(backlog), phase="trickle")
        progress.log(f"Trickle batch of {len(backlog)}, emptiest first.")
    enriched = 0
    errors = 0
    http = _http_client(transport=transport)
    try:
        for idx, work in enumerate(backlog):
            title = str(work.get("title") or "Untitled").strip() or "Untitled"
            if progress is not None:
                progress.tick(
                    phase="trickle",
                    current_title=title,
                    done=idx + 1,
                    total=len(backlog),
                    updated=enriched,
                    errors=errors,
                    log=f"Trickle: {title}…",
                )
            try:
                found = lookup_enrichment(work, settings, transport=transport, client=http, data_dir=data_dir)
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
                    if progress is not None:
                        progress.tick(
                            updated=enriched,
                            log=f"Trickle filled {title} from {found.source or 'catalog'}.",
                        )
            except Exception as error:
                errors += 1
                logger.exception("Enrich backlog failed for %s", work.get("id"))
                if progress is not None:
                    progress.tick(
                        errors=errors,
                        log=friendly_enrich_error(error, title=title),
                    )
            if idx + 1 < len(backlog) and pause_seconds > 0:
                time.sleep(pause_seconds)
    finally:
        http.close()
    remaining = db.count_works_needing_enrichment()
    result = {
        "status": "completed",
        "enriched": enriched,
        "errors": errors,
        "batch_size": len(backlog),
        "remaining": remaining,
        "has_more": remaining > 0,
        "scanned": len(backlog),
        "updated": enriched,
        "skipped": max(0, len(backlog) - enriched - errors),
    }
    if progress is not None:
        progress.complete(result)
    return result


MAGAZINE_BACKLOG_BATCH_DEFAULT = BACKLOG_BATCH_DEFAULT


def correct_magazine_work(db: Database, work: Mapping[str, Any], *, data_dir: Path) -> Dict[str, Any]:
    """Re-derive masthead/issue/year from the filename and ensure a first-page cover.

    No external magazine API — a fresh ``parse_magazine`` re-parse of the folder name
    is only trusted to correct a field when it names the same publication and issue
    the work already has (``magazine_identity_matches``), the magazine stand-in for a
    strong identifier match. Comics keep Comic Vine and are untouched here.
    """
    if str(work.get("kind") or "") != KIND_MAGAZINE:
        return dict(work)
    updated = dict(work)
    changed = False
    locked = bool(updated.get("metadata_locked"))

    raw_folder = str(updated.get("folder_path") or "").strip()
    folder = Path(raw_folder) if raw_folder else None
    stem = folder.name if folder is not None else str(updated.get("title") or "")
    parsed = parse_magazine(stem, hinted=KIND_MAGAZINE, isbn=str(updated.get("isbn") or ""))
    if parsed is not None and not locked and magazine_identity_matches(updated, parsed):
        if parsed.title and parsed.title != str(updated.get("title") or "").strip():
            updated["title"] = parsed.title
            changed = True
        if parsed.series_name and parsed.series_name != str(updated.get("series_name") or "").strip():
            updated["series_name"] = parsed.series_name
            changed = True
        if parsed.series_index and parsed.series_index != str(updated.get("series_index") or "").strip():
            updated["series_index"] = parsed.series_index
            changed = True
        if parsed.year and parsed.year != updated.get("year"):
            updated["year"] = parsed.year
            changed = True

    if folder is not None and folder.is_dir() and not cover_file_ok(updated):
        written = extract_magazine_cover(folder)
        if written is not None:
            updated["cover_path"] = str(written)
            changed = True

    if not changed:
        return dict(work)
    return db.upsert_work(updated)


def _magazines_needing_correction(db: Database, *, limit: int) -> List[Dict[str, Any]]:
    """Magazines missing a cover file — cheap (no HTTP) and safe to batch every trickle."""
    limit_n = max(1, int(limit))
    offset = 0
    found: List[Dict[str, Any]] = []
    while len(found) < limit_n:
        batch = db.list_works(kind=KIND_MAGAZINE, limit=200, offset=offset)
        if not batch:
            break
        for work in batch:
            if not cover_file_ok(work):
                found.append(work)
                if len(found) >= limit_n:
                    break
        if len(batch) < 200:
            break
        offset += len(batch)
    return found[:limit_n]


def enrich_corrections_backlog_batch(
    db: Database,
    settings: Settings,
    *,
    data_dir: Path,
    limit: int = BACKLOG_BATCH_DEFAULT,
    transport: Optional[httpx.BaseTransport] = None,
    pause_seconds: float = BACKLOG_PAUSE_SECONDS,
    progress: Optional[EnrichProgressSink] = None,
) -> Dict[str, Any]:
    """Poller trickle entry point: book/audiobook enrich+corrections, then magazine covers.

    Books and audiobooks get the full ``enrich_backlog_batch`` pass (identifiers,
    strong-match corrections, ISBN backfill, Audnexus ASIN/narrator). Magazines have no
    external API, so their correction here is local-only: re-parse the filename and
    make sure a first-page cover exists.
    """
    result = dict(
        enrich_backlog_batch(
            db,
            settings,
            data_dir=data_dir,
            limit=limit,
            transport=transport,
            pause_seconds=pause_seconds,
            progress=progress,
        )
    )
    magazines = _magazines_needing_correction(db, limit=limit)
    magazine_updated = 0
    for work in magazines:
        try:
            row = correct_magazine_work(db, work, data_dir=data_dir)
        except Exception:
            logger.exception("Magazine correction failed for %s", work.get("id"))
            continue
        if _catalog_changed(work, row):
            magazine_updated += 1
    result["magazines_scanned"] = len(magazines)
    result["magazines_updated"] = magazine_updated
    result["enriched"] = int(result.get("enriched") or 0) + magazine_updated
    return result


def clear_enrichment(db: Database, work_id: str) -> Dict[str, Any]:
    """Undo enrich: clear blurb fields written by Open Library / Wikipedia / LLM."""
    work = db.get_work(work_id)
    if work is None:
        raise ValueError("Work not found")
    updated = dict(work)
    updated["description"] = ""
    updated["synopsis_source"] = ""
    updated["llm_blurb"] = ""
    return db.upsert_work(updated)


_METADATA_FIELDS = (
    "title",
    "author",
    "year",
    "description",
    "genre",
    "series_name",
    "series_index",
    "kind",
    "synopsis_source",
    "llm_blurb",
)

# Hand-editing any of these is what a strong identifier match could otherwise correct
# automatically. Touching one here locks the whole work (``works.metadata_locked`` is
# one flag, not per-field) so a later trickle pass leaves them exactly as typed.
_LOCK_TRIGGER_FIELDS = ("title", "author", "year", "series_name", "series_index")


def update_work_metadata(
    db: Database,
    work_id: str,
    fields: Mapping[str, Any],
    *,
    data_dir: Path,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """Owner/op manual catalog edit. Never invents or replaces an ISBN."""
    work = db.get_work(work_id)
    if work is None:
        raise ValueError("Work not found")
    updated = dict(work)
    for key in _METADATA_FIELDS:
        if key not in fields:
            continue
        value = fields[key]
        if key == "year":
            if value in (None, ""):
                updated["year"] = None
            elif isinstance(value, int):
                updated["year"] = value
            elif str(value).strip().isdigit():
                updated["year"] = int(str(value).strip())
            else:
                raise ValueError("Year must be a number")
            continue
        if key == "kind":
            kind = str(value or "").strip()
            if kind not in ALL_KINDS:
                raise ValueError("Unsupported kind")
            updated["kind"] = kind
            continue
        updated[key] = str(value or "").strip() if value is not None else ""

    if any(
        key in fields and updated.get(key) != work.get(key) for key in _LOCK_TRIGGER_FIELDS
    ):
        updated["metadata_locked"] = 1

    cover_url = str(fields.get("cover_url") or "").strip()
    if cover_url:
        cover_url = assert_safe_cover_url(cover_url)
        existing = str(updated.get("cover_path") or "").strip()
        if existing:
            try:
                Path(existing).unlink(missing_ok=True)
            except OSError:
                pass
        written = fetch_cover_with_fallback(
            updated,
            data_dir,
            {"isbn": updated.get("isbn") or "", "title": updated.get("title") or ""},
            indexer_cover_url=cover_url,
            transport=transport,
            client=client,
            require_safe_url=True,
        )
        if written is not None:
            updated["cover_path"] = str(written)

    if not str(updated.get("title") or "").strip():
        raise ValueError("Title is required")
    return db.upsert_work(updated)


def list_match_candidates(
    work: Mapping[str, Any],
    *,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
    limit: int = 8,
    settings: Optional[Settings] = None,
) -> List[Dict[str, Any]]:
    kind = str(work.get("kind") or "").strip().lower()
    if kind == "comic":
        return list_comicvine_match_candidates(
            work, transport=transport, client=client, limit=limit, settings=settings
        )
    if kind == "audiobook":
        from librarian.audnexus import list_audnexus_candidates

        return list_audnexus_candidates(work, settings=settings, transport=transport, limit=limit)
    title = str(work.get("title") or "").strip()
    author = lookup_author(work)
    year = work.get("year") if isinstance(work.get("year"), int) else None
    own = client is None
    http = client or _http_client(transport=transport)
    try:
        openlib = OpenLibraryClient(transport=transport, client=http)
        return openlib.search_title_candidates(title, author, year=year, limit=limit)
    finally:
        if own:
            http.close()


def list_comicvine_match_candidates(
    work: Mapping[str, Any],
    *,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
    limit: int = 8,
    settings: Optional[Settings] = None,
) -> List[Dict[str, Any]]:
    from librarian.comicvine import ComicVineClient

    key = str(getattr(settings, "comicvine_api_key", "") or "").strip() if settings else ""
    if not key:
        return list(work.get("match_candidates") or [])[:limit]
    series = str(work.get("series_name") or work.get("title") or "").strip()
    issue = str(work.get("series_index") or "").strip()
    if not series:
        return []
    volume_year = work.get("volume_year") if isinstance(work.get("volume_year"), int) else None
    cover_year = work.get("year") if isinstance(work.get("year"), int) else None
    own = client is None
    http = client or _http_client(transport=transport)
    try:
        cv = ComicVineClient(key, transport=transport, client=http, rate_limit=False)
        matched = cv.match_issue(series, issue, volume_year=volume_year, cover_year=cover_year)
    finally:
        if own:
            http.close()
    out: List[Dict[str, Any]] = []
    for row in matched.get("candidates") or []:
        out.append(
            {
                "match_key": row.get("match_key") or f"cv:volume:{row.get('volume_id')}",
                "title": row.get("issue_title")
                or f"{row.get('series_name')} #{row.get('series_index') or issue}".strip(" #"),
                "author": row.get("publisher") or "",
                "year": row.get("start_year"),
                "publisher": row.get("publisher") or "",
                "series_name": row.get("series_name"),
                "series_index": row.get("series_index") or issue,
                "volume_year": row.get("start_year"),
                "match_confidence": row.get("match_score"),
                "source": "comicvine",
            }
        )
        if len(out) >= limit:
            break
    return out


def _write_matched_cover(
    db: Database,
    work: Mapping[str, Any],
    *,
    data_dir: Path,
    cover_url: str = "",
    identity: Optional[Mapping[str, Any]] = None,
    transport: Optional[httpx.BaseTransport] = None,
    replace: bool = False,
) -> Dict[str, Any]:
    """Download an allowlisted cover for Fix-match / import. May replace a local file."""
    payload = dict(work)
    if not replace and cover_file_ok(payload):
        return dict(work)
    written = fetch_cover_with_fallback(
        payload,
        data_dir,
        identity
        or {
            "kind": payload.get("kind") or "",
            "title": payload.get("title") or "",
            "author": payload.get("author") or "",
            "asin": payload.get("asin") or "",
            "cover": cover_url,
        },
        indexer_cover_url=cover_url,
        transport=transport,
        require_safe_url=True,
        replace=replace,
    )
    if written is not None:
        payload["cover_path"] = str(written)
        return db.upsert_work(payload)
    if replace and str(work.get("cover_path") or "") != str(payload.get("cover_path") or ""):
        return db.upsert_work(payload)
    return dict(work)


def apply_comicvine_match(
    db: Database,
    settings: Settings,
    work_id: str,
    match_key: str,
    *,
    data_dir: Path,
    transport: Optional[httpx.BaseTransport] = None,
) -> Dict[str, Any]:
    """Apply a chosen ComicVine volume/issue to a comic work identity."""
    from librarian.comicvine import ComicVineClient

    work = db.get_work(work_id)
    if work is None:
        raise ValueError("Work not found")
    if str(work.get("kind") or "") != "comic":
        raise ValueError("Only comics can be Comic Vine matched")
    key = str(match_key or "").strip()
    if not key.startswith("cv:"):
        raise ValueError("Match key is required")
    api_key = str(settings.comicvine_api_key or "").strip()
    if not api_key:
        raise ValueError("Comic Vine key is not configured")

    volume_id = None
    issue_id = None
    parts = key.split(":")
    # cv:volume:123 or cv:volume:123:issue:456
    for index, part in enumerate(parts):
        if part == "volume" and index + 1 < len(parts) and str(parts[index + 1]).isdigit():
            volume_id = int(parts[index + 1])
        if part == "issue" and index + 1 < len(parts) and str(parts[index + 1]).isdigit():
            issue_id = int(parts[index + 1])

    http = _http_client(transport=transport)
    try:
        cv = ComicVineClient(api_key, transport=transport, client=http, rate_limit=False)
        detail: Dict[str, Any] = {}
        volume: Dict[str, Any] = {}
        if volume_id is not None:
            volume = cv.volume_detail(volume_id)
        if issue_id is not None:
            detail = cv.issue_detail(issue_id)
        elif volume and work.get("series_index"):
            want = str(work.get("series_index") or "")
            for row in volume.get("issues") or []:
                if str(row.get("series_index") or "") == want and row.get("issue_id"):
                    detail = cv.issue_detail(int(row["issue_id"]))
                    break
    finally:
        http.close()

    if not detail and not volume:
        raise ValueError("Comic Vine match not found")

    series_name = str(detail.get("series_name") or volume.get("name") or work.get("series_name") or "").strip()
    series_index = str(detail.get("series_index") or work.get("series_index") or "").strip()
    title = str(detail.get("title") or "").strip() or (
        f"{series_name} #{series_index}" if series_name and series_index else series_name
    )
    patch = {
        **work,
        "title": title,
        "author": detail.get("author") or detail.get("writer") or volume.get("publisher") or work.get("author"),
        "series_name": series_name,
        "series_index": series_index,
        "publisher": detail.get("publisher") or volume.get("publisher") or work.get("publisher"),
        "year": detail.get("year") or volume.get("start_year") or work.get("year"),
        "volume_year": volume.get("start_year") or work.get("volume_year"),
        "description": detail.get("description") or work.get("description"),
        "web": detail.get("web") or work.get("web"),
        "penciller": detail.get("penciller") or "",
        "inker": detail.get("inker") or "",
        "colorist": detail.get("colorist") or "",
        "cover_artist": detail.get("cover_artist") or "",
        "letterer": detail.get("letterer") or "",
        "comicvine_volume_id": volume.get("volume_id") or volume_id,
        "comicvine_issue_id": detail.get("issue_id") or issue_id,
        "match_confidence": 1.0,
        "review_state": "none",
        "review_reason": None,
        "confidence": "high",
    }
    updated = db.upsert_work(patch)
    cover_url = str(detail.get("cover_url") or "").strip()
    updated = _write_matched_cover(
        db,
        updated,
        data_dir=data_dir,
        cover_url=cover_url,
        identity={"kind": "comic", "title": title, "cover": cover_url},
        transport=transport,
        replace=True,
    )
    return {
        "work": updated,
        "updated": True,
        "source": "comicvine",
        "match_key": key,
        "match_confidence": 1.0,
    }


def apply_audnexus_match(
    db: Database,
    settings: Settings,
    work_id: str,
    match_key: str,
    *,
    data_dir: Path,
    transport: Optional[httpx.BaseTransport] = None,
) -> Dict[str, Any]:
    """Apply a chosen Audnexus ASIN as catalog identity for an audiobook."""
    from librarian.audnexus import (
        AudnexusError,
        book_to_candidate,
        client_from_settings,
        identity_from_candidate,
        is_valid_asin,
    )

    work = db.get_work(work_id)
    if work is None:
        raise ValueError("Work not found")
    if str(work.get("kind") or "") != "audiobook":
        raise ValueError("Only audiobooks can apply an Audnexus match")
    key = str(match_key or "").strip()
    asin = key.split(":", 1)[-1].upper() if key.lower().startswith("asin:") else key.upper()
    if not is_valid_asin(asin):
        raise ValueError("Match key is required")
    client = client_from_settings(settings, transport=transport)
    try:
        raw = client.book(asin)
        if not raw:
            raise ValueError("Audnexus match not found")
        candidate = identity_from_candidate({**book_to_candidate(raw), "score": 1.0})
    except AudnexusError as error:
        raise ValueError(str(error)) from error
    finally:
        client.close()
    updated = {
        **work,
        "title": candidate.get("title") or work.get("title"),
        "author": candidate.get("author") or work.get("author"),
        "series_name": candidate.get("series_name") or work.get("series_name"),
        "series_index": candidate.get("series_index") or work.get("series_index"),
        "year": candidate.get("year") if candidate.get("year") is not None else work.get("year"),
        "asin": candidate.get("asin") or asin,
        "isbn": candidate.get("asin") or asin,
        "narrator": candidate.get("narrator") or work.get("narrator"),
        "description": candidate.get("description") or work.get("description"),
        "review_reason": None,
        "review_state": "none",
    }
    saved = db.upsert_work(updated)
    cover_url = str(candidate.get("cover") or candidate.get("cover_url") or "").strip()
    saved = _write_matched_cover(
        db,
        saved,
        data_dir=data_dir,
        cover_url=cover_url,
        identity={
            "kind": "audiobook",
            "title": saved.get("title") or "",
            "author": saved.get("author") or "",
            "asin": saved.get("asin") or asin,
            "cover": cover_url,
        },
        transport=transport,
        replace=True,
    )
    return {
        "work": saved,
        "updated": True,
        "source": "audnexus",
        "match_key": f"asin:{asin}",
        "match_confidence": 1.0,
        "thin": is_thin(saved),
    }


def apply_openlibrary_match(
    db: Database,
    settings: Settings,
    work_id: str,
    match_key: str,
    *,
    data_dir: Path,
    transport: Optional[httpx.BaseTransport] = None,
) -> Dict[str, Any]:
    """Apply a chosen Open Library work as enrichment, overwriting prior blurbs."""
    work = db.get_work(work_id)
    if work is None:
        raise ValueError("Work not found")
    if str(work.get("kind") or "") not in ENRICH_KINDS:
        raise ValueError("Only books and audiobooks can be matched")
    key = str(match_key or "").strip()
    if not key:
        raise ValueError("Match key is required")
    http = _http_client(transport=transport)
    try:
        openlib = OpenLibraryClient(transport=transport, client=http)
        raw = openlib.lookup_by_key(key)
        if not raw:
            raise ValueError("Open Library match not found")
        found = enrichment_from_mapping(raw)
        if not found.synopsis_source and found.description:
            found.synopsis_source = "openlibrary"
        updated = apply_enrichment(
            db,
            work,
            found,
            data_dir=data_dir,
            settings=settings,
            transport=transport,
            client=http,
            replace=True,
        )
    finally:
        http.close()
    return {
        "work": updated,
        "updated": _catalog_changed(work, updated),
        "source": found.source or "openlibrary",
        "match_key": found.match_key or key,
        "match_confidence": found.match_confidence,
        "thin": is_thin(updated),
    }


def _catalog_changed(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    keys = (
        "author",
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
