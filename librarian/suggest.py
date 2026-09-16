"""Typeahead suggestions: local catalog first, optional on-disk seed cache.

Cache lives under ``{DATA_DIR}/suggest-cache/``. First boot needs no download —
``GET /api/suggest`` reads SQLite distincts live. Owner refresh rebuilds a
bounded JSON seed (catalog always; optional MusicBrainz expansion from owned
artists). Never invents ISBNs. Fail closed on bad field/kind.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set

from librarian.db import Database
from librarian.kinds import ALL_KINDS

SUGGEST_FIELDS = frozenset({"author", "title", "series", "artist", "album", "year"})
CACHE_DIR_NAME = "suggest-cache"
CACHE_VERSION = 1
MAX_CACHE_VALUES = 5000
MAX_EXTERNAL_ARTISTS = 40
MAX_EXTERNAL_ALBUMS_PER_ARTIST = 40
DEFAULT_LIMIT = 12
MAX_LIMIT = 40
MIN_QUERY_LEN = 0  # empty q returns popular/catalog head
YEAR_DECADE_START = 1950
YEAR_DECADE_END = 2030


def cache_dir(data_dir: Path) -> Path:
    return Path(data_dir) / CACHE_DIR_NAME


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _fold(value: str) -> str:
    return _norm(value).casefold()


def _matches(needle: str, haystack: str) -> bool:
    if not needle:
        return True
    return _fold(needle) in _fold(haystack)


def _clip(values: Iterable[str], *, limit: int = MAX_CACHE_VALUES) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for raw in values:
        text = _norm(raw)
        if not text:
            continue
        key = _fold(text)
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def decade_years() -> List[str]:
    years: List[str] = []
    for year in range(YEAR_DECADE_END, YEAR_DECADE_START - 1, -10):
        years.append(str(year))
    return years


def load_cache_field(data_dir: Path, field: str) -> List[str]:
    if field not in SUGGEST_FIELDS:
        return []
    path = cache_dir(data_dir) / f"{field}.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return []
    if isinstance(payload, dict):
        rows = payload.get("items")
    else:
        rows = payload
    if not isinstance(rows, list):
        return []
    values: List[str] = []
    for row in rows:
        if isinstance(row, str):
            values.append(row)
        elif isinstance(row, Mapping):
            values.append(str(row.get("value") or row.get("label") or ""))
    return _clip(values)


def write_cache(
    data_dir: Path,
    fields: Mapping[str, Sequence[str]],
    *,
    meta: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    root = cache_dir(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    counts: Dict[str, int] = {}
    for field, values in fields.items():
        if field not in SUGGEST_FIELDS:
            continue
        clipped = _clip(values)
        path = root / f"{field}.json"
        path.write_text(
            json.dumps({"version": CACHE_VERSION, "items": clipped}, ensure_ascii=False, indent=0),
            encoding="utf-8",
        )
        counts[field] = len(clipped)
    info = {
        "version": CACHE_VERSION,
        "updated_at": time.time(),
        "counts": counts,
        **dict(meta or {}),
    }
    (root / "meta.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return info


def catalog_snapshot(db: Database) -> Dict[str, List[str]]:
    """Distinct owned-media values for the on-disk seed."""
    return {
        "author": db.suggest_values(field="author", kind="", q="", limit=MAX_CACHE_VALUES),
        "title": db.suggest_values(field="title", kind="", q="", limit=MAX_CACHE_VALUES),
        "series": db.suggest_values(field="series", kind="", q="", limit=MAX_CACHE_VALUES),
        "artist": db.suggest_values(field="artist", kind="music", q="", limit=MAX_CACHE_VALUES),
        "album": db.suggest_values(field="album", kind="music", q="", limit=MAX_CACHE_VALUES),
        "year": _clip(
            list(db.suggest_values(field="year", kind="", q="", limit=MAX_CACHE_VALUES)) + decade_years()
        ),
    }


def _expand_musicbrainz(db: Database) -> Dict[str, List[str]]:
    """Bounded album/artist expansion from owned artists. Soft-fail."""
    from librarian.musicbrainz import MusicBrainzClient, MusicBrainzError

    artists = db.suggest_values(field="artist", kind="music", q="", limit=MAX_EXTERNAL_ARTISTS)
    if not artists:
        return {"artist": [], "album": []}
    client = MusicBrainzClient()
    extra_artists: List[str] = []
    extra_albums: List[str] = []
    try:
        for name in artists[:MAX_EXTERNAL_ARTISTS]:
            extra_artists.append(name)
            try:
                albums = client.artist_albums(name)
            except MusicBrainzError:
                continue
            for row in albums[:MAX_EXTERNAL_ALBUMS_PER_ARTIST]:
                title = _norm(row.get("title") if isinstance(row, Mapping) else "")
                if title:
                    extra_albums.append(title)
                who = _norm(row.get("author") if isinstance(row, Mapping) else name)
                if who:
                    extra_artists.append(who)
    finally:
        client.close()
    return {
        "artist": _clip(extra_artists),
        "album": _clip(extra_albums),
    }


def refresh_suggest_cache(
    db: Database,
    data_dir: Path,
    *,
    include_external: bool = False,
) -> Dict[str, Any]:
    """Rebuild ``suggest-cache`` from catalog; optionally seed MusicBrainz from owned artists."""
    snapshot = catalog_snapshot(db)
    external_counts = {"artist": 0, "album": 0}
    external_error = None
    if include_external:
        try:
            extra = _expand_musicbrainz(db)
            for field in ("artist", "album"):
                before = len(snapshot[field])
                snapshot[field] = _clip(list(snapshot[field]) + list(extra.get(field) or []))
                external_counts[field] = max(0, len(snapshot[field]) - before)
        except Exception as error:  # noqa: BLE001 — owner action; surface soft failure
            external_error = str(error) or error.__class__.__name__
    meta = write_cache(
        data_dir,
        snapshot,
        meta={
            "source": "catalog+musicbrainz" if include_external else "catalog",
            "external": include_external,
            "external_added": external_counts,
            "external_error": external_error,
        },
    )
    return {
        "ok": True,
        "updated_at": meta.get("updated_at"),
        "counts": meta.get("counts") or {},
        "external": include_external,
        "external_added": external_counts,
        "external_error": external_error,
        "path": str(cache_dir(data_dir)),
    }


def suggest_items(
    db: Database,
    data_dir: Path,
    *,
    field: str,
    kind: str = "",
    q: str = "",
    limit: int = DEFAULT_LIMIT,
) -> List[Dict[str, Any]]:
    """Catalog-first suggestions, then on-disk cache. Empty list on bad input."""
    key = str(field or "").strip().lower()
    if key not in SUGGEST_FIELDS:
        return []
    kind_key = str(kind or "").strip().lower()
    if kind_key and kind_key not in ALL_KINDS and kind_key not in {"movie", "tv", "xxx"}:
        kind_key = ""
    try:
        capped = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    except (TypeError, ValueError):
        capped = DEFAULT_LIMIT
    needle = _norm(q)

    catalog = db.suggest_values(field=key, kind=kind_key, q=needle, limit=capped)
    items: List[Dict[str, Any]] = [{"value": value, "meta": "catalog"} for value in catalog]
    seen = {_fold(value) for value in catalog}

    if len(items) < capped:
        for value in load_cache_field(data_dir, key):
            if not _matches(needle, value):
                continue
            fold = _fold(value)
            if fold in seen:
                continue
            seen.add(fold)
            items.append({"value": value, "meta": "cache"})
            if len(items) >= capped:
                break

    if key == "year" and len(items) < capped:
        for value in decade_years():
            if not _matches(needle, value):
                continue
            fold = _fold(value)
            if fold in seen:
                continue
            seen.add(fold)
            items.append({"value": value, "meta": "decade"})
            if len(items) >= capped:
                break

    return items[:capped]
