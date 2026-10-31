"""Keep the m0003 canonical tables aligned with a ``works`` row.

``works.author`` / ``works.isbn`` stay as denormalized display cache. Reader
paths should prefer ``work_authors``, ``editions``, and ``work_identifiers``.
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from typing import Any, Mapping

from librarian.identity.authors import display_name, sort_name, split_authors
from librarian.identity.isbn import canonical_isbn13

_ASIN = re.compile(r"^[A-Z0-9]{10}$", re.IGNORECASE)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _ensure_author(conn: sqlite3.Connection, raw_name: str) -> str | None:
    shown = display_name(raw_name)
    if not shown:
        return None
    row = conn.execute(
        """
        SELECT a.id FROM authors a
        LEFT JOIN author_aliases aa ON aa.author_id = a.id
        WHERE a.display_name = ? OR aa.alias = ?
        ORDER BY CASE WHEN a.display_name = ? THEN 0 ELSE 1 END
        LIMIT 1
        """,
        (shown, shown, shown),
    ).fetchone()
    if row is None:
        raw = _text(raw_name)
        if raw and raw != shown:
            row = conn.execute(
                """
                SELECT a.id FROM authors a
                LEFT JOIN author_aliases aa ON aa.author_id = a.id
                WHERE a.display_name = ? OR aa.alias = ?
                LIMIT 1
                """,
                (raw, raw),
            ).fetchone()
    if row is not None:
        author_id = str(row[0])
    else:
        author_id = uuid.uuid4().hex
        conn.execute(
            """
            INSERT INTO authors (id, display_name, sort_name)
            VALUES (?, ?, ?)
            ON CONFLICT(display_name) DO UPDATE SET sort_name=excluded.sort_name
            """,
            (author_id, shown, sort_name(shown)),
        )
        stored = conn.execute(
            "SELECT id FROM authors WHERE display_name = ?", (shown,)
        ).fetchone()
        if stored is not None:
            author_id = str(stored[0])
    for alias in dict.fromkeys(item for item in (_text(raw_name), shown) if item):
        conn.execute(
            """
            INSERT INTO author_aliases (alias, author_id) VALUES (?, ?)
            ON CONFLICT(alias) DO UPDATE SET author_id=excluded.author_id
            """,
            (alias, author_id),
        )
    return author_id


def _ensure_identifier(conn: sqlite3.Connection, *, scheme: str, value: str, work_id: str) -> None:
    if not scheme or not value or not work_id:
        return
    conn.execute(
        """
        INSERT INTO work_identifiers (scheme, value, work_id)
        VALUES (?, ?, ?)
        ON CONFLICT(scheme, value) DO NOTHING
        """,
        (scheme, value, work_id),
    )


def _looks_like_asin(value: str) -> bool:
    return bool(_ASIN.fullmatch(value))


def _ensure_edition(conn: sqlite3.Connection, work: Mapping[str, Any]) -> None:
    work_id = _text(work.get("id"))
    kind = _text(work.get("kind")) or "book"
    isbn13 = canonical_isbn13(work.get("isbn")) or None
    asin_raw = _text(work.get("asin"))
    asin = asin_raw if _looks_like_asin(asin_raw) else None
    publisher = _text(work.get("publisher")) or None
    folder = _text(work.get("folder_path")) or None
    cover = _text(work.get("cover_path")) or None
    year = work.get("year")
    if not work_id or not (isbn13 or asin):
        return
    existing = conn.execute(
        "SELECT id FROM editions WHERE work_id = ? LIMIT 1",
        (work_id,),
    ).fetchone()
    if existing is not None:
        return
    conn.execute(
        """
        INSERT INTO editions (
            id, work_id, kind, isbn13, asin, publisher, year, format, folder_path, cover_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uuid.uuid4().hex,
            work_id,
            kind,
            isbn13,
            asin,
            publisher or None,
            year,
            kind,
            folder,
            cover,
        ),
    )


def sync_work_canonical(conn: sqlite3.Connection, work: Mapping[str, Any]) -> None:
    """Write ``work_authors`` / identifiers / a primary edition for one work."""
    work_id = _text(work.get("id"))
    if not work_id:
        return
    author_ids = []
    for part in split_authors(work.get("author")):
        author_id = _ensure_author(conn, part)
        if author_id:
            author_ids.append(author_id)
    conn.execute("DELETE FROM work_authors WHERE work_id = ?", (work_id,))
    for author_id in dict.fromkeys(author_ids):
        conn.execute(
            "INSERT OR IGNORE INTO work_authors (work_id, author_id) VALUES (?, ?)",
            (work_id, author_id),
        )
    isbn13 = canonical_isbn13(work.get("isbn"))
    if isbn13:
        _ensure_identifier(conn, scheme="isbn13", value=isbn13, work_id=work_id)
    asin = _text(work.get("asin"))
    if _looks_like_asin(asin):
        _ensure_identifier(conn, scheme="asin", value=asin.upper(), work_id=work_id)
    _ensure_edition(conn, work)


def backfill_canonical(conn: sqlite3.Connection) -> dict[str, int]:
    """Populate canonical tables for every existing work (m0008)."""
    works = list(conn.execute("SELECT * FROM works ORDER BY created_at, id"))
    for row in works:
        payload = {key: row[key] for key in row.keys()}
        sync_work_canonical(conn, payload)
    authors = int(conn.execute("SELECT COUNT(*) FROM authors").fetchone()[0])
    editions = int(conn.execute("SELECT COUNT(*) FROM editions").fetchone()[0])
    links = int(conn.execute("SELECT COUNT(*) FROM work_authors").fetchone()[0])
    return {
        "works": len(works),
        "authors": authors,
        "editions": editions,
        "work_authors": links,
    }
