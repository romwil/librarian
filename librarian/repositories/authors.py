"""Canonical authors and their aliases.

Narrators are intentionally not represented here; they remain metadata on works.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Iterable, List, Optional

from librarian.repositories._base import RepositoryBase, _row_dict


class AuthorsRepository(RepositoryBase):
    def upsert_author(self, author: Dict[str, Any]) -> Dict[str, Any]:
        author_id = str(author.get("id") or uuid.uuid4().hex)
        display_name = str(author.get("display_name") or "").strip()
        if not display_name:
            raise ValueError("Author display_name is required")
        sort_name = str(author.get("sort_name") or display_name).strip()

        def _write() -> None:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO authors (id, display_name, sort_name)
                    VALUES (?, ?, ?)
                    ON CONFLICT(display_name) DO UPDATE SET sort_name=excluded.sort_name
                    """,
                    (author_id, display_name, sort_name),
                )

        self.run_write(_write, label="upsert_author")
        row = self.get_author_by_name(display_name)
        assert row is not None
        return row

    def get_author(self, author_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM authors WHERE id = ?", (author_id,)).fetchone()
        return _row_dict(row)

    def get_author_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        text = str(name or "").strip()
        if not text:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT a.* FROM authors a
                LEFT JOIN author_aliases aa ON aa.author_id = a.id
                WHERE a.display_name = ? OR aa.alias = ?
                ORDER BY CASE WHEN a.display_name = ? THEN 0 ELSE 1 END
                LIMIT 1
                """,
                (text, text, text),
            ).fetchone()
        return _row_dict(row)

    def upsert_author_alias(self, *, author_id: str, alias: str) -> Dict[str, Any]:
        text = str(alias or "").strip()
        if not text:
            raise ValueError("Author alias is required")
        if self.get_author(author_id) is None:
            raise ValueError("Unknown author")

        def _write() -> None:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO author_aliases (alias, author_id) VALUES (?, ?)
                    ON CONFLICT(alias) DO UPDATE SET author_id=excluded.author_id
                    """,
                    (text, author_id),
                )

        self.run_write(_write, label="upsert_author_alias")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM author_aliases WHERE alias = ?",
                (text,),
            ).fetchone()
        assert row is not None
        return _row_dict(row) or {}

    def add_work_author(self, *, work_id: str, author_id: str) -> None:
        def _write() -> None:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO work_authors (work_id, author_id) VALUES (?, ?)",
                    (work_id, author_id),
                )

        self.run_write(_write, label="add_work_author")

    def set_work_authors(self, *, work_id: str, author_ids: Iterable[str]) -> None:
        ids = list(dict.fromkeys(str(author_id) for author_id in author_ids if str(author_id)))

        def _write() -> None:
            with self._connect() as conn:
                conn.execute("DELETE FROM work_authors WHERE work_id = ?", (work_id,))
                conn.executemany(
                    "INSERT INTO work_authors (work_id, author_id) VALUES (?, ?)",
                    [(work_id, author_id) for author_id in ids],
                )

        self.run_write(_write, label="set_work_authors")

    def list_work_authors(self, work_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT a.* FROM work_authors wa
                JOIN authors a ON a.id = wa.author_id
                WHERE wa.work_id = ?
                ORDER BY a.sort_name COLLATE NOCASE, a.display_name COLLATE NOCASE
                """,
                (work_id,),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]
