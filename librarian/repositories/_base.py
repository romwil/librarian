"""Helpers shared by every repository mixin that composes ``librarian.db.Database``."""

from __future__ import annotations

import json
import re
import sqlite3
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, TypeVar

FAVORITES_SHELF = "Favorites"

T = TypeVar("T")


def _row_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def _loads(raw: Any, default: Any = None) -> Any:
    if not raw:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def _fts_query(q: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", q or "")
    if not tokens:
        return ""
    return " AND ".join(f'"{token}"' for token in tokens)


def _fts_column_query(column: str, q: str) -> str:
    """FTS5 query locked to one column so a title search cannot hit the author."""
    if column not in {"title", "author"}:
        return ""
    tokens = re.findall(r"[A-Za-z0-9]+", q or "")
    if not tokens:
        return ""
    return " AND ".join(f'{column} : "{token}"' for token in tokens)


class RepositoryBase:
    """Repositories are mixins: ``Database`` supplies the connection and writer thread."""

    # Catalog rows with at least one registered media file — true "on the shelf".
    # Review slips / Skip ghosts / Goodreads stubs lack file rows and must not
    # appear in Hall, Stacks, kind counts, or local search.
    _HAS_FILES_SQL = "EXISTS (SELECT 1 FROM files f WHERE f.work_id = {alias}.id)"

    if TYPE_CHECKING:

        def _connect(self) -> Any: ...

        def run_write(self, operation: Callable[[], T], *, label: str = "write") -> T: ...

        def try_run_write(self, operation: Callable[[], T], *, label: str = "write") -> bool: ...
