"""Canonical identifier lookups for works."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from librarian.repositories._base import RepositoryBase, _row_dict

IDENTIFIER_SCHEMES = frozenset(
    {"isbn13", "asin", "ol_work", "hardcover", "comicvine", "calibre"}
)


class IdentifiersRepository(RepositoryBase):
    def upsert_work_identifier(self, *, scheme: str, value: str, work_id: str) -> Dict[str, Any]:
        normalized_scheme = str(scheme or "").strip().lower()
        normalized_value = str(value or "").strip()
        if normalized_scheme not in IDENTIFIER_SCHEMES:
            raise ValueError(f"Unsupported identifier scheme: {scheme}")
        if not normalized_value:
            raise ValueError("Identifier value is required")
        if not str(work_id or "").strip():
            raise ValueError("work_id is required")

        def _write() -> None:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO work_identifiers (scheme, value, work_id)
                    VALUES (?, ?, ?)
                    ON CONFLICT(scheme, value) DO UPDATE SET work_id=excluded.work_id
                    """,
                    (normalized_scheme, normalized_value, work_id),
                )

        self.run_write(_write, label="upsert_work_identifier")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM work_identifiers WHERE scheme = ? AND value = ?",
                (normalized_scheme, normalized_value),
            ).fetchone()
        assert row is not None
        return _row_dict(row) or {}

    def get_work_by_identifier(self, *, scheme: str, value: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT w.* FROM work_identifiers i
                JOIN works w ON w.id = i.work_id
                WHERE i.scheme = ? AND i.value = ?
                """,
                (str(scheme or "").strip().lower(), str(value or "").strip()),
            ).fetchone()
        return _row_dict(row)

    def list_work_identifiers(self, work_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM work_identifiers WHERE work_id = ? ORDER BY scheme, value",
                (work_id,),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]
