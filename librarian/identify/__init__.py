"""Identify completed downloads. Auto-organize only when confident.

The recognition stack lives here; its parts are split out:

- ``librarian.naming``: release / shelf / scan name parsing and the ``Identity`` record.
- ``librarian.identify.inspect``: complete-folder checks and payload grouping.
- ``librarian.identify.paths``: SAB storage path mapping and library destination layout.
- ``librarian.identify.llm``: the LLM identify step.

Every name importable from the old single-module ``librarian.identify`` is
still importable from here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from librarian.identify.inspect import (
    _compatible_alternate_formats as _compatible_alternate_formats,
)
from librarian.identify.inspect import (
    _diagnosis_path_clear as _diagnosis_path_clear,
)
from librarian.identify.inspect import (
    _folder_has_payload_quick as _folder_has_payload_quick,
)
from librarian.identify.inspect import (
    _is_archive_file as _is_archive_file,
)
from librarian.identify.inspect import (
    _is_junk_file as _is_junk_file,
)
from librarian.identify.inspect import (
    _kind_from_payload as _kind_from_payload,
)
from librarian.identify.inspect import (
    _looks_like_library_root as _looks_like_library_root,
)
from librarian.identify.inspect import (
    _normalized_payload_stem as _normalized_payload_stem,
)
from librarian.identify.inspect import (
    _unexpected_extra_files as _unexpected_extra_files,
)
from librarian.identify.inspect import (
    collection_dump_meta as collection_dump_meta,
)
from librarian.identify.inspect import (
    diagnose_review_folder as diagnose_review_folder,
)
from librarian.identify.inspect import (
    expand_organize_payload as expand_organize_payload,
)
from librarian.identify.inspect import (
    expected_payload_ok as expected_payload_ok,
)
from librarian.identify.inspect import (
    ingest_targets_for_mixed_payload as ingest_targets_for_mixed_payload,
)
from librarian.identify.inspect import (
    ingest_targets_for_multi_title_payload as ingest_targets_for_multi_title_payload,
)
from librarian.identify.inspect import (
    inspect_complete_folder as inspect_complete_folder,
)
from librarian.identify.inspect import (
    is_mixed_comic_ebook_payload as is_mixed_comic_ebook_payload,
)
from librarian.identify.inspect import (
    list_payload_files as list_payload_files,
)
from librarian.identify.inspect import (
    match_payload_files_to_identity as match_payload_files_to_identity,
)
from librarian.identify.inspect import (
    partition_comic_ebook_files as partition_comic_ebook_files,
)
from librarian.identify.inspect import (
    suggest_payload_folder as suggest_payload_folder,
)
from librarian.identify.inspect import (
    unexpected_extra_files as unexpected_extra_files,
)
from librarian.identify.llm import (
    _apply_post_llm_review as _apply_post_llm_review,
)
from librarian.identify.llm import (
    apply_llm_identity as apply_llm_identity,
)
from librarian.identify.llm import (
    identify_evidence as identify_evidence,
)
from librarian.identify.paths import (
    COMPLETE_ROOT_FALLBACKS as COMPLETE_ROOT_FALLBACKS,
)
from librarian.identify.paths import (
    CONTAINER_DATA_PREFIX as CONTAINER_DATA_PREFIX,
)
from librarian.identify.paths import (
    DOWNLOADS_PREFIXES as DOWNLOADS_PREFIXES,
)
from librarian.identify.paths import (
    HOST_DATA_PREFIX as HOST_DATA_PREFIX,
)
from librarian.identify.paths import (
    _complete_roots as _complete_roots,
)
from librarian.identify.paths import (
    _guess_relative as _guess_relative,
)
from librarian.identify.paths import (
    _music_discnumber as _music_discnumber,
)
from librarian.identify.paths import (
    _music_track_filename as _music_track_filename,
)
from librarian.identify.paths import (
    _safe_source_filename as _safe_source_filename,
)
from librarian.identify.paths import (
    _storage_relatives as _storage_relatives,
)
from librarian.identify.paths import (
    _unique_paths as _unique_paths,
)
from librarian.identify.paths import (
    dest_layout as dest_layout,
)
from librarian.identify.paths import (
    existing_album_folder as existing_album_folder,
)
from librarian.identify.paths import (
    music_state_for_folder as music_state_for_folder,
)
from librarian.identify.paths import (
    path_layout_note as path_layout_note,
)
from librarian.identify.paths import (
    resolve_storage_path as resolve_storage_path,
)
from librarian.identify.paths import (
    safe_path_part as safe_path_part,
)
from librarian.identify.paths import (
    usable_folder as usable_folder,
)
from librarian.kinds import (
    ALL_KINDS,
    KIND_AUDIOBOOK,
    KIND_BOOK,
    KIND_COMIC,
    KIND_MAGAZINE,
    KIND_MUSIC,
    kind_from_newznab,
)
from librarian.naming.extensions import (
    ARCHIVE_EXTENSIONS as ARCHIVE_EXTENSIONS,
)
from librarian.naming.extensions import (
    BOOK_FORMAT_EXTENSIONS as BOOK_FORMAT_EXTENSIONS,
)
from librarian.naming.extensions import (
    COMIC_ARCHIVE_EXTENSIONS as COMIC_ARCHIVE_EXTENSIONS,
)
from librarian.naming.extensions import (
    EBOOK_FORMAT_EXTENSIONS as EBOOK_FORMAT_EXTENSIONS,
)
from librarian.naming.extensions import (
    JUNK_EXTENSIONS as JUNK_EXTENSIONS,
)
from librarian.naming.extensions import (
    JUNK_NAMES as JUNK_NAMES,
)
from librarian.naming.extensions import (
    MEDIA_EXTENSIONS as MEDIA_EXTENSIONS,
)
from librarian.naming.extensions import (
    SIDECAR_NAMES as SIDECAR_NAMES,
)
from librarian.naming.identity import Identity as Identity
from librarian.naming.isbn import (
    extract_isbn as extract_isbn,
)
from librarian.naming.isbn import (
    isbn10_to_isbn13 as isbn10_to_isbn13,
)
from librarian.naming.isbn import (
    isbn13_to_isbn10 as isbn13_to_isbn10,
)
from librarian.naming.isbn import (
    isbn_match_keys as isbn_match_keys,
)
from librarian.naming.isbn import (
    validated_isbn as validated_isbn,
)
from librarian.naming.release import (
    parse_usenet_name as parse_usenet_name,
)
from librarian.naming.release import (
    release_file_fields as filename_identity,
)
from librarian.naming.tokens import (
    MBID,
)
from librarian.naming.tokens import (
    filename_stem as filename_stem,
)
from librarian.naming.tokens import (
    looks_like_dump_title as looks_like_dump_title,
)
from librarian.naming.tokens import (
    tidy_title as tidy_title,
)
from librarian.naming.tokens import (
    usenet_basename as usenet_basename,
)
from librarian.review_reasons import (
    REVIEW_AUDNEXUS_AMBIGUOUS as REVIEW_AUDNEXUS_AMBIGUOUS,
)
from librarian.review_reasons import (
    REVIEW_AUDNEXUS_UNMATCHED as REVIEW_AUDNEXUS_UNMATCHED,
)
from librarian.review_reasons import (
    REVIEW_COLLISION as REVIEW_COLLISION,
)
from librarian.review_reasons import (
    REVIEW_COMICVINE_AMBIGUOUS as REVIEW_COMICVINE_AMBIGUOUS,
)
from librarian.review_reasons import (
    REVIEW_COMICVINE_UNMATCHED as REVIEW_COMICVINE_UNMATCHED,
)
from librarian.review_reasons import (
    REVIEW_CONVERT as REVIEW_CONVERT,
)
from librarian.review_reasons import (
    REVIEW_EXTRA as REVIEW_EXTRA,
)
from librarian.review_reasons import (
    REVIEW_LOW as REVIEW_LOW,
)
from librarian.review_reasons import (
    REVIEW_MISSING_FOLDER as REVIEW_MISSING_FOLDER,
)
from librarian.review_reasons import (
    REVIEW_NO_PAYLOAD as REVIEW_NO_PAYLOAD,
)
from librarian.review_reasons import (
    REVIEW_UNEXPECTED as REVIEW_UNEXPECTED,
)
from librarian.review_reasons import (
    REVIEW_UNKNOWN as REVIEW_UNKNOWN,
)
from librarian.review_reasons import (
    REVIEW_UNPACK_STUCK as REVIEW_UNPACK_STUCK,
)
from librarian.review_reasons import (
    UNPACK_STUCK as UNPACK_STUCK,
)


def fill_identity_holes(identity: Identity, layer: Optional[Mapping[str, Any]]) -> Identity:
    """Copy non-empty fields from a weaker layer without overwriting stronger values."""
    if not layer:
        return identity
    fields = (
        "title",
        "author",
        "series_name",
        "series_index",
        "isbn",
        "asin",
        "mbid",
        "album",
        "track_title",
        "tracknumber",
        "discnumber",
        "recording_mbid",
        "publisher",
        "description",
        "genre",
        "narrator",
        "comic_format",
        "comic_subtitle",
        "comic_variant",
        "penciller",
        "inker",
        "colorist",
        "cover_artist",
        "letterer",
        "cover",
        "web",
    )
    for key in fields:
        incoming = layer.get(key)
        if incoming in (None, ""):
            continue
        current = getattr(identity, key, None)
        if current in (None, ""):
            setattr(identity, key, incoming)
    year = layer.get("year")
    if identity.year is None and str(year or "").isdigit():
        identity.year = int(year)
    volume_year = layer.get("volume_year")
    if identity.volume_year is None and str(volume_year or "").isdigit():
        identity.volume_year = int(volume_year)
    for int_key in ("comicvine_volume_id", "comicvine_issue_id", "month", "day"):
        incoming = layer.get(int_key)
        if getattr(identity, int_key, None) is None and str(incoming or "").lstrip("-").isdigit():
            setattr(identity, int_key, int(incoming))
    score = layer.get("match_confidence")
    if score is None:
        score = layer.get("match_score")
    if identity.match_confidence is None and score is not None:
        try:
            identity.match_confidence = float(score)
        except (TypeError, ValueError):
            pass
    candidates = layer.get("match_candidates")
    if candidates and not identity.match_candidates:
        identity.match_candidates = list(candidates) if isinstance(candidates, list) else []
    kind = str(layer.get("kind") or "").strip().lower()
    if kind in ALL_KINDS and identity.kind not in ALL_KINDS:
        identity.kind = kind
    if identity.album and not identity.series_name:
        identity.series_name = identity.album
    if identity.kind == KIND_MUSIC and identity.series_name and not identity.title:
        identity.title = identity.series_name
    if identity.kind in (KIND_COMIC, KIND_MAGAZINE) and identity.series_name and identity.series_index and not identity.title:
        identity.title = f"{identity.series_name} #{identity.series_index}"
    return identity


def identity_from_indexer(item: Dict[str, Any]) -> Identity:
    """Layer 1: Find sought / selected / retrieved catalog fields. Not the Usenet dump name."""
    sought = item.get("sought") if isinstance(item.get("sought"), dict) else {}
    retrieved = item.get("retrieved") if isinstance(item.get("retrieved"), dict) else {}
    selected = item.get("selected") if isinstance(item.get("selected"), dict) else {}
    requested = str(sought.get("kind") or item.get("kind") or selected.get("kind") or "").strip().lower()
    category = item.get("category") or selected.get("category") or item.get("cat")
    if requested not in ALL_KINDS:
        requested = kind_from_newznab(category) or ""
    catalog = str(
        sought.get("title")
        or sought.get("album")
        or retrieved.get("book_title")
        or retrieved.get("title")
        or retrieved.get("album")
        or item.get("book_title")
        or item.get("title")
        or item.get("album")
        or ""
    ).strip()
    series = tidy_title(
        str(sought.get("series") or retrieved.get("series") or retrieved.get("series_name") or "")
    )
    issue = str(sought.get("issue") or retrieved.get("issue") or item.get("issue") or "").strip()
    if requested == KIND_COMIC and series and issue:
        catalog = f"{series} #{str(int(issue)) if issue.isdigit() else issue}"
    author = tidy_title(
        str(
            sought.get("author")
            or sought.get("artist")
            or retrieved.get("author")
            or retrieved.get("artist")
            or item.get("author")
            or item.get("artist")
            or ""
        )
    )
    isbn_raw = sought.get("isbn") or retrieved.get("isbn") or item.get("isbn") or ""
    if requested == KIND_MUSIC:
        isbn_raw = ""
    isbn = extract_isbn(str(isbn_raw or ""))
    if requested != KIND_MUSIC and not isbn:
        isbn = extract_isbn(catalog)
    album = tidy_title(str(sought.get("album") or retrieved.get("album") or item.get("album") or ""))
    year_raw = str(sought.get("year") or retrieved.get("year") or item.get("year") or "").strip()
    identity = Identity(
        kind=requested if requested in ALL_KINDS else "",
        title=catalog,
        author=author,
        series_name=series or album,
        series_index=str(int(issue)) if issue.isdigit() else issue,
        year=int(year_raw) if year_raw.isdigit() else None,
        isbn=isbn,
        album=album,
        mbid=str(sought.get("mbid") or retrieved.get("mbid") or item.get("mbid") or "").strip(),
        confidence="low",
        rationale="indexer fields",
        query_terms=[part for part in (author, catalog, isbn, series, issue) if part],
        source="indexer",
    )
    if identity.kind == KIND_MUSIC and identity.album and not identity.title:
        identity.title = identity.album
    if identity.kind in (KIND_COMIC, KIND_MAGAZINE) and identity.series_name and identity.series_index and not identity.title:
        identity.title = f"{identity.series_name} #{identity.series_index}"
    _apply_stack_confidence(identity)
    identity.source = "indexer"
    return identity


def _apply_stack_confidence(identity: Identity) -> Identity:
    if identity.kind == KIND_BOOK and identity.isbn and identity.author and identity.title:
        identity.confidence = "high"
        identity.rationale = identity.rationale or "ISBN + author + title"
        identity.review_reason = None
    elif identity.kind == KIND_COMIC and identity.series_name and identity.series_index:
        score = identity.match_confidence
        if score is not None:
            if score >= 0.85:
                identity.confidence = "high"
                identity.rationale = identity.rationale or "comicvine match ≥0.85"
                if identity.review_reason in (
                    REVIEW_COMICVINE_AMBIGUOUS,
                    REVIEW_COMICVINE_UNMATCHED,
                    REVIEW_LOW,
                    None,
                ):
                    identity.review_reason = None
            elif score >= 0.65:
                identity.confidence = "low"
                identity.rationale = identity.rationale or "comicvine ambiguous"
                identity.review_reason = identity.review_reason or REVIEW_COMICVINE_AMBIGUOUS
            else:
                identity.confidence = "low"
                identity.rationale = identity.rationale or "comicvine unmatched"
                identity.review_reason = identity.review_reason or REVIEW_COMICVINE_UNMATCHED
        else:
            # No ComicVine key / lookup — legacy series+issue gate.
            identity.confidence = "high"
            identity.rationale = identity.rationale or "series + issue"
            identity.review_reason = None
    elif identity.kind == KIND_MAGAZINE and identity.series_name and identity.series_index:
        identity.confidence = "high"
        identity.rationale = identity.rationale or "series + issue"
        identity.review_reason = None
    elif identity.kind == KIND_MUSIC and identity.author and (identity.album or identity.series_name or identity.title):
        identity.confidence = "high"
        identity.rationale = identity.rationale or "artist + album"
        identity.review_reason = None
        if not identity.album:
            identity.album = identity.series_name or identity.title
        if not identity.series_name:
            identity.series_name = identity.album
        if not identity.title:
            identity.title = identity.album
    elif identity.kind == KIND_AUDIOBOOK and identity.asin and identity.author and identity.title:
        # ASIN-resolved identity (Audnexus). Filename author+title alone is no longer enough.
        identity.confidence = "high"
        identity.rationale = identity.rationale or "audiobook ASIN + author + title"
        identity.review_reason = None
    elif identity.kind == KIND_AUDIOBOOK and identity.author and identity.title:
        # Provisional until Audnexus scoring runs in identify_completed.
        identity.confidence = "low"
        identity.rationale = identity.rationale or "audiobook author + title (pending Audnexus)"
    else:
        identity.confidence = "low"
    return identity


def identify_completed(
    folder: Path,
    *,
    indexer_item: Optional[Dict[str, Any]] = None,
    category: object = None,
    llm_client: Any = None,
    settings: Any = None,
    catalog_lookup: Optional[Callable[[Identity], Optional[Mapping[str, Any]]]] = None,
    catalog_transport: Any = None,
) -> Dict[str, Any]:
    """Identify a completed folder via the recognition stack. Unexpected results go to Review.

    Ingest / watch-folder callers must use this same function (then organize_identified).
    Layers, strongest first: sought/selected/retrieved → embedded metadata →
    kind-specific filename parse → catalog lookup with a real key. Later layers fill holes only.
    """
    files = expand_organize_payload(folder)
    item = dict(indexer_item or {})
    if category is not None:
        item["category"] = category or item.get("category")
    sought = item.get("sought") if isinstance(item.get("sought"), dict) else {}
    sought_kind = str(sought.get("kind") or "").strip().lower()

    if indexer_item:
        identity = identity_from_indexer(item)
    else:
        identity = Identity(kind="", title="", confidence="low", source="empty")

    if not files:
        if not identity.title:
            identity = fill_identity_holes(
                identity, parse_usenet_name(folder.name, category=item.get("category"), kind=identity.kind).as_dict()
            )
        inspection = inspect_complete_folder(folder)
        problem = inspection.get("problem") or REVIEW_NO_PAYLOAD
        identity.review_reason = str(problem)
        identity.confidence = "low"
        return {"identity": identity.as_dict(), "files": [], "auto_organize": False}

    embedded = embedded_identity(folder, files, kind=identity.kind)
    if (
        str(embedded.get("kind") or "") == KIND_AUDIOBOOK
        and identity.kind == KIND_MUSIC
        and sought_kind != KIND_MUSIC
    ):
        identity.kind = KIND_AUDIOBOOK
    fill_identity_holes(identity, embedded)

    filename_layer = filename_identity(folder, files, kind=identity.kind, category=item.get("category"))
    if identity.isbn:
        filename_layer.pop("title", None)
        filename_layer.pop("author", None)
        filename_layer.pop("isbn", None)
    fill_identity_holes(identity, filename_layer)

    if identity.kind not in ALL_KINDS:
        inferred = kind_from_newznab(item.get("category")) or _kind_from_payload(files, folder)
        if inferred:
            identity.kind = inferred

    has_key = bool(extract_isbn(identity.isbn)) or bool(MBID.match(str(identity.mbid or ""))) or bool(
        MBID.match(str(identity.recording_mbid or ""))
    )
    if catalog_lookup is not None and has_key:
        try:
            fill_identity_holes(identity, catalog_lookup(identity) or {})
        except Exception:
            pass
    elif settings is not None:
        fill_identity_holes(identity, catalog_fill(identity, settings, transport=catalog_transport))

    if identity.kind == KIND_AUDIOBOOK and settings is not None:
        _apply_audnexus_match(identity, settings, transport=catalog_transport)

    identity.source = identity.source or "stack"
    _apply_review_gates(identity, files)

    identity, files = apply_llm_identity(
        identity, folder, indexer_item=indexer_item, files=files, llm_client=llm_client
    )

    from librarian.slip_gate import sign_path_clear_book

    sign_path_clear_book(identity, folder, files)
    auto = identity.confidence == "high" and not identity.review_reason
    return {
        "identity": identity.as_dict(),
        "files": [str(path) for path in files],
        "auto_organize": auto,
    }


def embedded_identity(folder: Path, files: Sequence[Path], *, kind: str = "") -> Dict[str, Any]:
    """Layer 2: OPF / ComicInfo / audio tags / cheap PDF info. Does not invent identifiers."""
    from librarian.metadata import (
        read_audio_tags,
        read_cbz_comicinfo,
        read_epub_opf,
        read_folder_metadata,
        read_pdf_info,
    )

    merged: Dict[str, Any] = {}
    sidecar = read_folder_metadata(Path(folder)) if Path(folder).is_dir() else {}
    merged.update(sidecar)
    hinted = str(kind or "").strip().lower()
    for path in files:
        suffix = path.suffix.lower()
        layer: Dict[str, Any] = {}
        if suffix == ".epub":
            layer = read_epub_opf(path)
        elif suffix == ".cbz":
            layer = read_cbz_comicinfo(path)
        elif suffix == ".pdf":
            layer = read_pdf_info(path)
        elif suffix in {".flac", ".mp3", ".m4a", ".m4b", ".ogg", ".opus", ".mp4", ".aac"}:
            layer = read_audio_tags(path)
        for key, value in layer.items():
            if value in (None, "") or merged.get(key) not in (None, ""):
                continue
            merged[key] = value
        if hinted in (KIND_MUSIC, KIND_AUDIOBOOK, "") and layer.get("album") and not merged.get("album"):
            merged["album"] = layer["album"]
    return merged


def catalog_fill(identity: Identity, settings: Any, *, transport: Any = None) -> Dict[str, Any]:
    """Layer 4: Hardcover/OL by ISBN, MusicBrainz by MBID or artist+album, Comic Vine if keyed.

    Fail closed on HTTP errors. Never writes an ISBN from a title-only match. Never invents an MBID.
    Audiobooks use Audnexus (see ``_apply_audnexus_match``) — not Hardcover/Open Library.
    """
    kind = identity.kind
    if kind == KIND_AUDIOBOOK:
        return {}
    if kind in (KIND_BOOK, KIND_MAGAZINE) and identity.isbn:
        if identity.title and identity.author:
            return {}
        return _catalog_isbn(identity, settings, transport=transport)
    if kind == KIND_MUSIC:
        return _catalog_music(identity, settings, transport=transport)
    if kind == KIND_COMIC:
        return _catalog_comic(identity, settings, transport=transport)
    return {}


def _apply_audnexus_match(identity: Identity, settings: Any, *, transport: Any = None) -> None:
    """Score Audnexus candidates for audiobooks. Sets review bands; no remux until resolved."""
    if identity.kind != KIND_AUDIOBOOK or settings is None:
        return
    try:
        from librarian.audnexus import (
            AudnexusError,
            client_from_settings,
            identity_from_candidate,
            match_audiobook_tokens,
        )
    except Exception:
        return
    tokens = {
        "title": identity.title,
        "author": identity.author,
        "asin": identity.asin or identity.isbn,
        "narrator": identity.narrator,
        "series_name": identity.series_name,
        "series_index": identity.series_index,
        "year": identity.year,
    }
    client = client_from_settings(settings, transport=transport)
    try:
        matched = match_audiobook_tokens(tokens, client=client)
    except AudnexusError:
        if not identity.review_reason:
            identity.review_reason = REVIEW_AUDNEXUS_UNMATCHED
            identity.confidence = "low"
        return
    finally:
        client.close()

    candidates = list(matched.get("candidates") or [])
    identity.match_candidates = candidates[:8]
    identity.match_confidence = float(matched.get("score") or 0)
    reason = matched.get("review_reason")
    best = matched.get("best")
    if reason is None and best:
        filled = identity_from_candidate(best)
        fill_identity_holes(identity, filled)
        # Strong fields from authority win for title/author/asin once auto-matched.
        for key in ("title", "author", "asin", "series_name", "series_index", "description", "narrator", "cover"):
            value = filled.get(key)
            if value not in (None, ""):
                setattr(identity, key, value)
        if filled.get("year") is not None:
            identity.year = filled["year"]
        identity.isbn = identity.asin or identity.isbn
        identity.confidence = "high"
        identity.rationale = "Audnexus ASIN match"
        identity.review_reason = None
        identity.source = "audnexus"
        return
    identity.confidence = "low"
    identity.review_reason = reason or REVIEW_AUDNEXUS_UNMATCHED
    if best and not identity.asin:
        # Surface best guess into the Review form without auto-filing.
        hint = identity_from_candidate(best)
        if not identity.title and hint.get("title"):
            identity.title = str(hint["title"])
        if not identity.author and hint.get("author"):
            identity.author = str(hint["author"])


def _catalog_isbn(identity: Identity, settings: Any, *, transport: Any = None) -> Dict[str, Any]:
    isbn = extract_isbn(identity.isbn)
    if not isbn:
        return {}
    merged: Dict[str, Any] = {}
    try:
        from librarian.hardcover import HardcoverClient, HardcoverError

        token = str(getattr(settings, "hardcover_api_token", "") or "").strip()
        if token:
            client = HardcoverClient(token, transport=transport)
            try:
                merged = dict(client.lookup_by_isbn(isbn) or {})
            except HardcoverError:
                merged = {}
            finally:
                client.close()
    except Exception:
        merged = {}
    if not merged.get("title") or not merged.get("author"):
        try:
            from librarian.openlibrary import OpenLibraryClient

            client = OpenLibraryClient(transport=transport)
            try:
                found = client.lookup_by_isbn(isbn) or {}
            finally:
                client.close()
            for key, value in found.items():
                if value not in (None, "") and merged.get(key) in (None, ""):
                    merged[key] = value
        except Exception:
            pass
    merged.pop("isbn", None)
    return merged


def _catalog_music(identity: Identity, settings: Any, *, transport: Any = None) -> Dict[str, Any]:
    mbid = str(identity.mbid or "").strip()
    recording = str(identity.recording_mbid or "").strip()
    if mbid and not MBID.match(mbid):
        mbid = ""
    if recording and not MBID.match(recording):
        recording = ""
    if not mbid and not recording:
        return {}
    try:
        from librarian.musicbrainz import MusicBrainzClient, MusicBrainzError

        client = MusicBrainzClient(transport=transport, min_interval=0)
        try:
            found = client.lookup_release(
                artist=identity.author,
                album=identity.album or identity.series_name or identity.title,
                mbid=mbid,
                recording_mbid=recording,
            )
        except MusicBrainzError:
            found = {}
        finally:
            client.close()
    except Exception:
        return {}
    found.pop("isbn", None)
    return found or {}


def _catalog_comic(identity: Identity, settings: Any, *, transport: Any = None) -> Dict[str, Any]:
    key = str(getattr(settings, "comicvine_api_key", "") or "").strip()
    if not key or not (identity.series_name and identity.series_index):
        return {}
    try:
        import os

        from librarian.comicvine import ComicVineClient, ComicVineError

        cache_path = Path(os.environ.get("DATA_DIR", "/config")) / "comicvine-cache.db"
        client = ComicVineClient(
            key,
            transport=transport,
            cache_path=cache_path,
            rate_limit=transport is None,
        )
        try:
            matched = client.match_issue(
                identity.series_name,
                identity.series_index,
                volume_year=identity.volume_year,
                cover_year=identity.year,
            )
        except ComicVineError:
            return {
                "match_confidence": 0.0,
                "match_candidates": [],
                "review_reason": REVIEW_COMICVINE_UNMATCHED,
            }
        finally:
            client.close()
    except Exception:
        return {}

    best = matched.get("best") if isinstance(matched.get("best"), dict) else {}
    score = float(matched.get("match_score") or 0)
    candidates = list(matched.get("candidates") or [])
    out: Dict[str, Any] = {
        "match_confidence": score,
        "match_candidates": candidates,
    }
    if best:
        for key_name in (
            "title",
            "author",
            "year",
            "publisher",
            "description",
            "web",
            "penciller",
            "inker",
            "colorist",
            "cover_artist",
            "letterer",
            "month",
            "day",
        ):
            if best.get(key_name) not in (None, ""):
                out[key_name] = best[key_name]
        if best.get("volume_year") not in (None, ""):
            out["volume_year"] = best["volume_year"]
        if best.get("volume_id") not in (None, ""):
            out["comicvine_volume_id"] = best["volume_id"]
        if best.get("issue_id") not in (None, ""):
            out["comicvine_issue_id"] = best["issue_id"]
        if best.get("series_name"):
            out["series_name"] = best["series_name"]
        if best.get("series_index"):
            out["series_index"] = best["series_index"]
        if best.get("cover_url"):
            out["cover"] = best["cover_url"]

    band = str(matched.get("band") or "low")
    if band == "high":
        out["confidence"] = "high"
        out["rationale"] = "comicvine match ≥0.85"
    elif band == "mid":
        out["confidence"] = "low"
        out["review_reason"] = REVIEW_COMICVINE_AMBIGUOUS
        out["rationale"] = "comicvine ambiguous volume"
    else:
        out["confidence"] = "low"
        out["review_reason"] = REVIEW_COMICVINE_UNMATCHED
        out["rationale"] = "comicvine unmatched"
    return out


def _apply_review_gates(identity: Identity, files: Sequence[Path]) -> None:
    if is_mixed_comic_ebook_payload(files):
        identity.review_reason = REVIEW_EXTRA
        identity.confidence = "low"
        return
    extra = _unexpected_extra_files(files)
    if extra and identity.kind not in (KIND_MUSIC, KIND_AUDIOBOOK, KIND_MAGAZINE):
        identity.review_reason = REVIEW_EXTRA
        identity.confidence = "low"
        return

    if identity.kind not in ALL_KINDS:
        identity.review_reason = identity.review_reason or REVIEW_UNEXPECTED
        identity.confidence = "low"
        return

    _apply_stack_confidence(identity)

    if identity.kind == KIND_BOOK:
        suffixes = {path.suffix.lower() for path in files}
        if suffixes == {".pdf"}:
            identity.review_reason = identity.review_reason or REVIEW_CONVERT
            identity.confidence = "low"
        if identity.confidence != "high" or not (identity.isbn and identity.author and identity.title):
            if not identity.review_reason:
                identity.review_reason = REVIEW_LOW if identity.title else REVIEW_UNKNOWN
                identity.confidence = "low"
                identity.isbn = extract_isbn(identity.isbn)

    if identity.kind in (KIND_COMIC, KIND_MAGAZINE):
        if not (identity.series_name and identity.series_index):
            identity.review_reason = identity.review_reason or REVIEW_UNKNOWN
            identity.confidence = "low"
        suffixes = {path.suffix.lower() for path in files}
        # Final shelf is CBZ only — CBR and PDF comics must remux before auto-organize.
        if identity.kind == KIND_COMIC:
            has_cbz = ".cbz" in suffixes
            needs_cbz = (".cbr" in suffixes or ".pdf" in suffixes) and not has_cbz
            if needs_cbz:
                identity.review_reason = identity.review_reason or REVIEW_CONVERT
                identity.confidence = "low"
            if identity.review_reason in (REVIEW_COMICVINE_AMBIGUOUS, REVIEW_COMICVINE_UNMATCHED):
                identity.confidence = "low"

    if identity.kind == KIND_AUDIOBOOK and not (identity.author and identity.title):
        identity.review_reason = identity.review_reason or REVIEW_UNKNOWN
        identity.confidence = "low"
    elif identity.kind == KIND_AUDIOBOOK and identity.review_reason in (
        REVIEW_AUDNEXUS_AMBIGUOUS,
        REVIEW_AUDNEXUS_UNMATCHED,
    ):
        identity.confidence = "low"
    elif identity.kind == KIND_AUDIOBOOK and identity.confidence != "high":
        identity.review_reason = identity.review_reason or (
            REVIEW_AUDNEXUS_UNMATCHED if not identity.asin else REVIEW_LOW
        )
        identity.confidence = "low"
    if identity.kind == KIND_MUSIC and identity.confidence != "high":
        identity.review_reason = identity.review_reason or (REVIEW_LOW if identity.title else REVIEW_UNKNOWN)
        identity.confidence = "low"

    if identity.kind == KIND_BOOK and identity.confidence != "high":
        identity.isbn = extract_isbn(identity.isbn)

