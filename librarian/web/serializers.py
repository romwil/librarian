"""Public work shaping for API responses.

Hall / browse / work detail use an allowlist so storage-engine fields never
reach readers (or XSS / extension / log sinks). Owner/op Review & Maintain use
``public_work_admin`` when a folder path is required for desk tooling.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Sequence

from librarian.delight import cover_story

# Catalog metadata + computed presentation — never filesystem paths.
_PUBLIC_WORK_KEYS: tuple[str, ...] = (
    "id",
    "kind",
    "title",
    "author",
    "series_name",
    "series_index",
    "year",
    "isbn",
    "mbid",
    "asin",
    "narrator",
    "description",
    "publisher",
    "genre",
    "abs_item_id",
    "synopsis_source",
    "llm_blurb",
    "art_attribution",
    "review_state",
    "review_reason",
    "music_state",
    "part_total",
    "part_style",
    "part_base",
    "part_origin",
    "created_at",
    "updated_at",
    "progress",
    "job_status",
)

# Owner/op desk fields that may include layout paths for Review tooling.
_ADMIN_WORK_EXTRA_KEYS: tuple[str, ...] = (
    "folder_path",
    "repair_fail_count",
    "indexer_guid",
)

# Storage / media paths — never emit on any public or admin work shape.
_PATH_KEYS = frozenset({"cover_path", "atmosphere_path", "folder_path"})


def _pick(row: Dict[str, Any], keys: Sequence[str]) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    for key in keys:
        if key in row:
            data[key] = row[key]
    return data


def public_work(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Allowlisted work for household readers (and shared catalog surfaces)."""
    if row is None:
        return None
    data = _pick(row, _PUBLIC_WORK_KEYS)
    data["has_cover"] = bool(row.get("cover_path") or row.get("has_cover"))
    story = cover_story(row)
    if story:
        data["cover_story"] = story
    # Defense in depth: never leak path keys even if allowlist drifts.
    for key in _PATH_KEYS:
        data.pop(key, None)
    return data


def public_works(rows: Iterable[Any]) -> list:
    return [public_work(row) for row in rows if row]


def public_work_admin(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Owner/op work shape: public fields plus folder_path / repair counters.

    Still omits ``cover_path`` / ``atmosphere_path`` — covers stay at
    ``/api/works/{id}/cover``.
    """
    if row is None:
        return None
    data = public_work(row)
    if data is None:
        return None
    for key in _ADMIN_WORK_EXTRA_KEYS:
        if key in row:
            data[key] = row[key]
    data.pop("cover_path", None)
    data.pop("atmosphere_path", None)
    return data


def public_works_admin(rows: Iterable[Any]) -> list:
    return [public_work_admin(row) for row in rows if row]
