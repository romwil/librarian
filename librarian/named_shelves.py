"""Named household shelves — living collections beyond Favorites."""

from __future__ import annotations

import re
import time
import uuid
from typing import Any, Dict, List, Optional

# Favorites stays the reserved personal rail — named shelves never collide.
RESERVED_SHELF_NAMES = frozenset({"favorites"})
MAX_SHELF_NAME_LEN = 48
MAX_NAMED_SHELVES_PER_USER = 24
MAX_SHELF_WORKS_RAIL = 18

_NAME_CLEAN = re.compile(r"\s+")


def normalize_shelf_name(value: object) -> str:
    text = _NAME_CLEAN.sub(" ", str(value or "").strip())
    if len(text) > MAX_SHELF_NAME_LEN:
        text = text[:MAX_SHELF_NAME_LEN].rstrip()
    return text


def shelf_name_ok(name: str) -> bool:
    cleaned = normalize_shelf_name(name)
    if not cleaned:
        return False
    return cleaned.casefold() not in RESERVED_SHELF_NAMES


def public_shelf(row: Optional[Dict[str, Any]], *, work_count: int = 0) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    shelf_id = str(row.get("id") or "").strip()
    name = normalize_shelf_name(row.get("name"))
    if not shelf_id or not name:
        return None
    return {
        "id": shelf_id,
        "name": name,
        "owner_user_id": str(row.get("owner_user_id") or "").strip(),
        "shared": bool(int(row.get("shared") or 0)),
        "created_at": row.get("created_at"),
        "work_count": max(0, int(work_count or 0)),
    }


def shelf_presence(shelves: List[Dict[str, Any]]) -> str:
    count = len(shelves or [])
    if count < 1:
        return "Name a shelf for the house — Beach, Kids comics, whatever fits."
    if count == 1:
        return "One named shelf keeps a quiet corner of the house."
    return f"{count} named shelves keep corners of the house."
