"""Public work shaping for API responses."""

from __future__ import annotations

from typing import Any, Dict, Optional

from librarian.delight import cover_story


def public_work(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    data = dict(row)
    data["has_cover"] = bool(data.get("cover_path"))
    story = cover_story(data)
    if story:
        data["cover_story"] = story
    return data


def public_works(rows: list) -> list:
    return [public_work(row) for row in rows if row]
