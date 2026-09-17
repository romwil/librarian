"""Gap math: local holes plus Hardcover / Open Library / Comic Vine / MusicBrainz catalogs."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import httpx

from librarian.comicvine import ComicVineClient
from librarian.config import Settings
from librarian.db import Database
from librarian.hardcover import HardcoverClient, HardcoverError
from librarian.kinds import KIND_AUDIOBOOK, KIND_BOOK, KIND_COMIC, KIND_MAGAZINE, KIND_MUSIC
from librarian.musicbrainz import MusicBrainzClient
from librarian.openlibrary import OpenLibraryClient
from librarian.parts import build_part_set, missing_parts, part_set_incomplete

_MONTH = re.compile(r"^(?P<year>\d{4})-(?P<month>0[1-9]|1[0-2])$")
_INT = re.compile(r"^(\d+)$")
_AUDIO_PART = re.compile(r"\b(?:part|cd|disc)\s*(\d+)\b", re.IGNORECASE)
_TRACK = re.compile(r"^(?:(?:track|tr|t)[\s._-]*)?(\d{1,2})\b", re.IGNORECASE)
_INTISH = re.compile(r"^(\d+)(?:\.(\d+))?$")

MAX_BOOK_SERIES = 12
MAX_COMIC_SERIES = 12
MAX_MUSIC_ALBUMS = 8
MAX_MUSIC_ARTISTS = 4


def magazine_month_holes(indexes: Sequence[str]) -> List[str]:
    """Return missing YYYY-MM values strictly between the owned min and max."""
    owned: List[tuple[int, int]] = []
    for raw in indexes:
        match = _MONTH.match(str(raw or "").strip())
        if not match:
            continue
        owned.append((int(match.group("year")), int(match.group("month"))))
    if len(owned) < 2:
        return []
    owned = sorted(set(owned))
    start_y, start_m = owned[0]
    end_y, end_m = owned[-1]
    have = set(owned)
    missing: List[str] = []
    year, month = start_y, start_m
    while (year, month) <= (end_y, end_m):
        if (year, month) not in have:
            missing.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            month = 1
            year += 1
    return missing


def comic_issue_holes(indexes: Sequence[object]) -> List[str]:
    """Return missing integer issue numbers between owned min and max."""
    return integer_holes(indexes)


def integer_holes(indexes: Sequence[object]) -> List[str]:
    owned: List[int] = []
    for raw in indexes:
        text = str(raw or "").strip()
        match = _INT.match(text)
        if not match:
            continue
        owned.append(int(match.group(1)))
    if len(owned) < 2:
        return []
    low, high = min(owned), max(owned)
    have = set(owned)
    return [str(n) for n in range(low, high + 1) if n not in have]


def audiobook_part_holes(filenames: Sequence[str]) -> List[str]:
    """Missing part/cd/disc numbers between owned min and max."""
    parts = []
    for name in filenames:
        match = _AUDIO_PART.search(str(name or ""))
        if match:
            parts.append(match.group(1))
    return integer_holes(parts)


def music_track_holes(filenames: Sequence[str]) -> List[str]:
    """Missing leading track numbers on an owned album."""
    tracks = []
    for name in filenames:
        stem = str(name or "")
        match = _TRACK.match(stem)
        if match:
            tracks.append(str(int(match.group(1))))
    return integer_holes(tracks)


def index_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = _INTISH.match(text)
    if not match:
        return text.lower()
    whole = int(match.group(1))
    frac = match.group(2)
    if not frac or set(frac) == {"0"}:
        return str(whole)
    return f"{whole}.{frac}"


def title_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _neighbor_author(works: Sequence[Mapping[str, Any]]) -> str:
    for work in works:
        author = str(work.get("author") or "").strip()
        if author:
            return author
    return ""


def _owned_keys(works: Sequence[Mapping[str, Any]]) -> Tuple[set[str], set[str]]:
    indexes: set[str] = set()
    titles: set[str] = set()
    for work in works:
        idx = index_key(work.get("series_index"))
        if idx:
            indexes.add(idx)
        keyed = title_key(work.get("title"))
        if keyed:
            titles.add(keyed)
    return indexes, titles


def gaps_for_series(
    db: Database,
    *,
    kind: str,
    series_name: str,
) -> Dict[str, Any]:
    works = db.works_for_series(kind=kind, series_name=series_name)
    indexes = [str(work.get("series_index") or "") for work in works]
    if kind == KIND_MAGAZINE:
        missing = magazine_month_holes(indexes)
    elif kind == KIND_COMIC:
        missing = comic_issue_holes(indexes)
    else:
        missing = []
    return {
        "kind": kind,
        "series_name": series_name,
        "owned": [work["id"] for work in works],
        "owned_indexes": indexes,
        "missing": missing,
        "author": _neighbor_author(works),
        "provenance": "local",
    }


def _file_gaps(db: Database, kind: str, hole_fn, label: str) -> List[Dict[str, Any]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    work_ids: dict[str, list[str]] = defaultdict(list)
    authors: dict[str, str] = {}
    for row in db.files_named_for_kind(kind):
        key = str(row.get("series_name") or row.get("work_title") or "").strip()
        if not key:
            continue
        grouped[key].append(str(row.get("filename") or ""))
        work_id = str(row.get("work_id") or row.get("work_pk") or "")
        if work_id and work_id not in work_ids[key]:
            work_ids[key].append(work_id)
        if key not in authors:
            author = str(row.get("author") or "").strip()
            if author:
                authors[key] = author
    rails: List[Dict[str, Any]] = []
    for name, filenames in grouped.items():
        missing = hole_fn(filenames)
        if missing:
            rails.append(
                {
                    "kind": kind,
                    "series_name": name,
                    "owned": work_ids[name],
                    "owned_indexes": filenames,
                    "missing": missing,
                    "author": authors.get(name, ""),
                    "provenance": "local",
                    "gap_type": label,
                }
            )
    return rails


def multipart_owned_gaps(db: Database) -> List[Dict[str, Any]]:
    """Owned Usenet multipart holes when part_set.total is known (not series_index gaps)."""
    rails: List[Dict[str, Any]] = []
    for work in db.works_with_part_total():
        files = db.files_for_work(str(work["id"]))
        part_set = build_part_set(work, files)
        if not part_set_incomplete(part_set):
            continue
        assert part_set is not None
        missing = missing_parts(
            part_set.get("owned") or [],
            part_set["total"],
            origin=part_set.get("origin"),
        )
        if not missing:
            continue
        base = str(part_set.get("base") or work.get("title") or "").strip()
        rails.append(
            {
                "kind": work["kind"],
                "series_name": base,
                "owned": [str(work["id"])],
                "owned_indexes": [str(n) for n in (part_set.get("owned") or [])],
                "missing": [str(n) for n in missing],
                "author": str(work.get("author") or "").strip(),
                "provenance": "local",
                "gap_type": "multipart",
                "part_set": part_set,
                "work_id": str(work["id"]),
                "title": str(work.get("title") or base),
            }
        )
    return rails


def local_gaps(db: Database) -> List[Dict[str, Any]]:
    rails: List[Dict[str, Any]] = []
    for kind in (KIND_MAGAZINE, KIND_COMIC):
        for name in db.series_names(kind):
            card = gaps_for_series(db, kind=kind, series_name=name)
            if card["missing"]:
                rails.append(card)
    rails.extend(_file_gaps(db, KIND_AUDIOBOOK, audiobook_part_holes, "audiobook_parts"))
    rails.extend(_file_gaps(db, KIND_MUSIC, music_track_holes, "music_tracks"))
    rails.extend(multipart_owned_gaps(db))
    return rails


def _http_client(*, transport: Optional[httpx.BaseTransport] = None) -> httpx.Client:
    return httpx.Client(timeout=12.0, transport=transport, follow_redirects=True)


def catalog_gaps(
    db: Database,
    settings: Settings,
    *,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
    mb_min_interval: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Local holes plus remote catalogs. Fail closed: catalog errors never drop local cards."""
    rails = list(local_gaps(db))
    own = client is None
    http = client or _http_client(transport=transport)
    interval = 0.0 if transport is not None and mb_min_interval is None else (
        1.1 if mb_min_interval is None else mb_min_interval
    )
    try:
        rails.extend(_book_series_catalog(db, settings, http, transport=transport))
        rails.extend(_comic_catalog(db, settings, http, transport=transport))
        rails.extend(_music_catalog(db, http, transport=transport, min_interval=interval))
    except Exception:
        pass
    finally:
        if own:
            http.close()
    return rails


def _missing_from_expected(
    expected: Sequence[Mapping[str, Any]],
    *,
    owned_indexes: set[str],
    owned_titles: set[str],
) -> List[Dict[str, Any]]:
    missing: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for volume in expected:
        index = index_key(volume.get("series_index"))
        titled = title_key(volume.get("title"))
        if index and index in owned_indexes:
            continue
        if titled and titled in owned_titles:
            continue
        dedupe = index or titled
        if not dedupe or dedupe in seen:
            continue
        seen.add(dedupe)
        row = dict(volume)
        row["series_index"] = str(volume.get("series_index") or index)
        missing.append(row)
    return missing


def _merge_expected(*groups: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for volume in group:
            key = index_key(volume.get("series_index")) or title_key(volume.get("title"))
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(dict(volume))
    return merged


def _book_series_catalog(
    db: Database,
    settings: Settings,
    http: httpx.Client,
    *,
    transport: Optional[httpx.BaseTransport] = None,
) -> List[Dict[str, Any]]:
    rails: List[Dict[str, Any]] = []
    token = str(settings.hardcover_api_token or "").strip()
    hardcover = HardcoverClient(token, transport=transport, client=http) if token else None
    openlib = OpenLibraryClient(transport=transport, client=http)
    count = 0
    for kind in (KIND_BOOK, KIND_AUDIOBOOK):
        for name in db.series_names(kind):
            if not str(name or "").strip():
                continue
            if count >= MAX_BOOK_SERIES:
                return rails
            count += 1
            works = db.works_for_series(kind=kind, series_name=name)
            if not works:
                continue
            owned_indexes, owned_titles = _owned_keys(works)
            hardcover_volumes: List[Dict[str, Any]] = []
            if hardcover is not None:
                try:
                    hardcover_volumes = hardcover.lookup_series(name)
                except HardcoverError:
                    hardcover_volumes = []
            ol_volumes: List[Dict[str, Any]] = []
            try:
                ol_volumes = openlib.series_volumes(name)
            except Exception:
                ol_volumes = []
            expected = _merge_expected(hardcover_volumes, ol_volumes)
            missing = _missing_from_expected(
                expected, owned_indexes=owned_indexes, owned_titles=owned_titles
            )
            if not missing:
                continue
            provenance = "hardcover" if hardcover_volumes else "openlibrary"
            if hardcover_volumes and ol_volumes:
                provenance = "hardcover+openlibrary"
            rails.append(
                {
                    "kind": kind,
                    "series_name": name,
                    "owned": [work["id"] for work in works],
                    "owned_indexes": [str(work.get("series_index") or "") for work in works],
                    "missing": missing,
                    "author": _neighbor_author(works),
                    "provenance": provenance,
                    "gap_type": "series_volume",
                }
            )
    return rails


def _comic_catalog(
    db: Database,
    settings: Settings,
    http: httpx.Client,
    *,
    transport: Optional[httpx.BaseTransport] = None,
) -> List[Dict[str, Any]]:
    key = str(settings.comicvine_api_key or "").strip()
    if not key:
        return []
    client = ComicVineClient(key, transport=transport, client=http)
    rails: List[Dict[str, Any]] = []
    for index, name in enumerate(db.series_names(KIND_COMIC)):
        if index >= MAX_COMIC_SERIES:
            break
        works = db.works_for_series(kind=KIND_COMIC, series_name=name)
        if not works:
            continue
        owned_indexes, owned_titles = _owned_keys(works)
        expected = client.series_issues(name)
        missing = _missing_from_expected(
            expected, owned_indexes=owned_indexes, owned_titles=owned_titles
        )
        if not missing:
            continue
        rails.append(
            {
                "kind": KIND_COMIC,
                "series_name": name,
                "owned": [work["id"] for work in works],
                "owned_indexes": [str(work.get("series_index") or "") for work in works],
                "missing": missing,
                "author": _neighbor_author(works),
                "provenance": "comicvine",
                "gap_type": "comic_issue",
            }
        )
    return rails


def _music_files_by_album(db: Database) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in db.files_named_for_kind(KIND_MUSIC):
        name = str(row.get("series_name") or row.get("work_title") or "").strip()
        if not name:
            continue
        bucket = grouped.setdefault(
            name,
            {
                "title": name,
                "author": str(row.get("author") or "").strip(),
                "mbid": "",
                "filenames": [],
                "owned": [],
            },
        )
        bucket["filenames"].append(str(row.get("filename") or ""))
        work_id = str(row.get("work_id") or row.get("work_pk") or "")
        if work_id and work_id not in bucket["owned"]:
            bucket["owned"].append(work_id)
        if not bucket["author"]:
            bucket["author"] = str(row.get("author") or "").strip()
    for work in db.list_works(kind=KIND_MUSIC, limit=200):
        name = str(work.get("series_name") or work.get("title") or "").strip()
        if name not in grouped:
            continue
        mbid = str(work.get("mbid") or "").strip()
        if mbid and not grouped[name]["mbid"]:
            grouped[name]["mbid"] = mbid
        if not grouped[name]["author"]:
            grouped[name]["author"] = str(work.get("author") or "").strip()
    return grouped


def _owned_track_numbers(filenames: Sequence[str]) -> set[str]:
    owned: set[str] = set()
    for name in filenames:
        match = _TRACK.match(str(name or ""))
        if match:
            owned.add(str(int(match.group(1))))
    return owned


def _music_catalog(
    db: Database,
    http: httpx.Client,
    *,
    transport: Optional[httpx.BaseTransport] = None,
    min_interval: float = 1.1,
) -> List[Dict[str, Any]]:
    mb = MusicBrainzClient(transport=transport, client=http, min_interval=min_interval)
    rails: List[Dict[str, Any]] = []
    albums = list(_music_files_by_album(db).values())
    artists_seen: set[str] = set()
    for album in albums[:MAX_MUSIC_ALBUMS]:
        payload = mb.release_tracks(
            title=str(album["title"]),
            artist=str(album.get("author") or ""),
            mbid=str(album.get("mbid") or ""),
        )
        raw_tracks = payload.get("tracks")
        tracks: List[Any] = raw_tracks if isinstance(raw_tracks, list) else []
        owned = _owned_track_numbers(album.get("filenames") or [])
        missing = []
        for track in tracks:
            if not isinstance(track, dict):
                continue
            number = index_key(track.get("number"))
            if not number or number in owned:
                continue
            title = str(track.get("title") or "").strip() or f"{album['title']} {number}"
            missing.append(
                {
                    "title": title,
                    "series_name": album["title"],
                    "series_index": number,
                    "author": album.get("author") or "",
                    "source": "musicbrainz",
                }
            )
        if missing:
            rails.append(
                {
                    "kind": KIND_MUSIC,
                    "series_name": album["title"],
                    "owned": album.get("owned") or [],
                    "owned_indexes": album.get("filenames") or [],
                    "missing": missing,
                    "author": album.get("author") or "",
                    "provenance": "musicbrainz",
                    "gap_type": "music_tracks",
                }
            )
        artist = str(album.get("author") or "").strip()
        if artist:
            artists_seen.add(artist)
    owned_albums = {title_key(item["title"]) for item in albums}
    for artist in list(artists_seen)[:MAX_MUSIC_ARTISTS]:
        if len([item for item in albums if item.get("author") == artist]) < 2:
            continue
        expected = mb.artist_albums(artist)
        missing_albums = []
        for album in expected:
            keyed = title_key(album.get("title"))
            if not keyed or keyed in owned_albums:
                continue
            missing_albums.append(
                {
                    "title": album.get("title"),
                    "series_name": artist,
                    "series_index": "",
                    "author": artist,
                    "year": album.get("year"),
                    "source": "musicbrainz",
                }
            )
            owned_albums.add(keyed)
        if missing_albums:
            rails.append(
                {
                    "kind": KIND_MUSIC,
                    "series_name": artist,
                    "owned": [],
                    "owned_indexes": [],
                    "missing": missing_albums,
                    "author": artist,
                    "provenance": "musicbrainz",
                    "gap_type": "music_album",
                }
            )
    return rails


def unique_gap_cards(cards: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    best: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    order: List[Tuple[str, str, str]] = []
    for raw in cards:
        card = dict(raw)
        hole = str(card.get("missing_index") or "")
        if not hole:
            hole = f"title:{title_key(card.get('title'))}"
        key = (
            str(card.get("kind") or ""),
            str(card.get("series_name") or "").lower(),
            hole,
        )
        if key not in best:
            order.append(key)
            best[key] = card
            continue
        current = best[key]
        if current.get("provenance") == "local" and card.get("provenance") not in ("local", "", None):
            best[key] = card
    return [best[key] for key in order]


def gap_cards(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    for row in rows:
        neighbor_author = str(row.get("author") or "").strip()
        for missing in row.get("missing") or []:
            extra: Dict[str, Any] = {}
            if isinstance(missing, dict):
                index = str(missing.get("series_index") or missing.get("missing_index") or "").strip()
                title = str(missing.get("title") or "").strip()
                author = str(missing.get("author") or neighbor_author or "").strip()
                year = missing.get("year")
                isbn = str(missing.get("isbn") or "").strip()
                extra = {key: value for key, value in missing.items() if key not in {"isbn"}}
            else:
                index = str(missing)
                title = ""
                author = neighbor_author
                year = None
                isbn = ""
            series = str(row.get("series_name") or "").strip()
            title = title or f"{series} {index}".strip()
            owned_indexes = [str(value) for value in (row.get("owned_indexes") or []) if str(value or "").strip()]
            series_missing = []
            for hole in row.get("missing") or []:
                if isinstance(hole, dict):
                    hole_index = str(hole.get("series_index") or hole.get("missing_index") or "").strip()
                else:
                    hole_index = str(hole or "").strip()
                if hole_index:
                    series_missing.append(hole_index)
            card: Dict[str, Any] = {
                "id": f"gap:{row['kind']}:{series}:{index or title_key(title)}",
                "kind": row["kind"],
                "series_name": series,
                "series_index": index,
                "missing_index": index,
                "title": title,
                "provenance": row.get("provenance") or extra.get("source") or "local",
                "owned_indexes": owned_indexes,
                "series_missing": series_missing,
            }
            if row.get("gap_type"):
                card["gap_type"] = row["gap_type"]
            if row.get("part_set"):
                card["part_set"] = dict(row["part_set"])
            if row.get("work_id"):
                card["work_id"] = str(row["work_id"])
            if author:
                card["author"] = author
            if year not in (None, ""):
                if isinstance(year, int):
                    card["year"] = year
                elif str(year).isdigit():
                    card["year"] = int(year)
            if isbn:
                card["isbn"] = isbn
            if row["kind"] == KIND_MAGAZINE:
                match = _MONTH.match(index)
                if match:
                    card["year"] = int(match.group("year"))
            cards.append(card)
    return unique_gap_cards(cards)
