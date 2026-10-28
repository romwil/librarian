"""Edition records belonging to canonical works."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from librarian.repositories._base import RepositoryBase, _row_dict


class EditionsRepository(RepositoryBase):
    def upsert_edition(self, edition: Dict[str, Any]) -> Dict[str, Any]:
        edition_id = str(edition.get("id") or uuid.uuid4().hex)
        payload = {
            "id": edition_id,
            "work_id": str(edition["work_id"]),
            "kind": str(edition["kind"]),
            "isbn13": edition.get("isbn13"),
            "asin": edition.get("asin"),
            "publisher": edition.get("publisher"),
            "year": edition.get("year"),
            "format": edition.get("format"),
            "folder_path": edition.get("folder_path"),
            "cover_path": edition.get("cover_path"),
        }

        def _write() -> None:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO editions (
                        id, work_id, kind, isbn13, asin, publisher, year, format, folder_path, cover_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        work_id=excluded.work_id, kind=excluded.kind, isbn13=excluded.isbn13,
                        asin=excluded.asin, publisher=excluded.publisher, year=excluded.year,
                        format=excluded.format, folder_path=excluded.folder_path,
                        cover_path=excluded.cover_path
                    """,
                    tuple(payload.values()),
                )

        self.run_write(_write, label="upsert_edition")
        row = self.get_edition(edition_id)
        assert row is not None
        return row

    def get_edition(self, edition_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM editions WHERE id = ?", (edition_id,)).fetchone()
        return _row_dict(row)

    def list_editions_for_work(self, work_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM editions WHERE work_id = ? ORDER BY kind, format, id",
                (work_id,),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]
