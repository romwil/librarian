"""Favorites, named shelves, and per-user reading progress."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Mapping, Optional

from librarian.repositories._base import (
    FAVORITES_SHELF,
    RepositoryBase,
    _row_dict,
)


class ShelvesRepository(RepositoryBase):
    def favorites_shelf(self, user_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM shelves WHERE owner_user_id = ? AND name = ?",
                (user_id, FAVORITES_SHELF),
            ).fetchone()
        data = _row_dict(row)
        if data is not None:
            return data
        now = time.time()
        shelf_id = uuid.uuid4().hex
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO shelves (id, name, owner_user_id, created_at) VALUES (?, ?, ?, ?)",
                    (shelf_id, FAVORITES_SHELF, user_id, now),
                )
        self.run_write(_write, label='favorites_shelf')
        return {"id": shelf_id, "name": FAVORITES_SHELF, "owner_user_id": user_id, "created_at": now}

    def add_favorite(self, user_id: str, work_id: str) -> bool:
        """Put a work on Favorites. Idempotent — does not un-favorite."""
        if self.is_favorite(user_id, work_id):
            return False
        shelf = self.favorites_shelf(user_id)
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO shelf_items (shelf_id, work_id, added_at) VALUES (?, ?, ?)",
                    (shelf["id"], work_id, time.time()),
                )
        self.run_write(_write, label='add_favorite')
        return True

    def toggle_favorite(self, user_id: str, work_id: str) -> bool:
        shelf = self.favorites_shelf(user_id)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT 1 FROM shelf_items WHERE shelf_id = ? AND work_id = ?",
                (shelf["id"], work_id),
            ).fetchone()
        def _write() -> Any:
            with self._connect() as conn:
                if existing:
                    conn.execute(
                        "DELETE FROM shelf_items WHERE shelf_id = ? AND work_id = ?",
                        (shelf["id"], work_id),
                    )
                    return False
                conn.execute(
                    "INSERT INTO shelf_items (shelf_id, work_id, added_at) VALUES (?, ?, ?)",
                    (shelf["id"], work_id, time.time()),
                )
                return True
        return self.run_write(_write, label='toggle_favorite')

    def is_favorite(self, user_id: str, work_id: str) -> bool:
        shelf = self.favorites_shelf(user_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM shelf_items WHERE shelf_id = ? AND work_id = ?",
                (shelf["id"], work_id),
            ).fetchone()
        return row is not None

    def favorite_works(self, user_id: str, *, limit: int = 24) -> List[Dict[str, Any]]:
        shelf = self.favorites_shelf(user_id)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT w.* FROM shelf_items s
                JOIN works w ON w.id = s.work_id
                WHERE s.shelf_id = ?
                  AND {self._HAS_FILES_SQL.format(alias="w")}
                ORDER BY s.added_at DESC
                LIMIT ?
                """,
                (shelf["id"], int(limit)),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def get_shelf(self, shelf_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM shelves WHERE id = ?", (shelf_id,)).fetchone()
        return _row_dict(row)

    def list_named_shelves(self, user_id: str, *, include_shared: bool = True) -> List[Dict[str, Any]]:
        """Personal named shelves (+ household-shared ones when requested). Favorites excluded."""
        uid = str(user_id or "").strip()
        if not uid:
            return []
        with self._connect() as conn:
            if include_shared:
                rows = conn.execute(
                    """
                    SELECT * FROM shelves
                    WHERE name != ?
                      AND (owner_user_id = ? OR shared = 1)
                    ORDER BY shared DESC, lower(name) ASC, created_at ASC
                    """,
                    (FAVORITES_SHELF, uid),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM shelves
                    WHERE name != ? AND owner_user_id = ?
                    ORDER BY lower(name) ASC, created_at ASC
                    """,
                    (FAVORITES_SHELF, uid),
                ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def list_named_shelves_with_counts(
        self, user_id: str, *, include_shared: bool = True
    ) -> List[Dict[str, Any]]:
        """Named shelves plus file-backed work counts in one grouped query."""
        uid = str(user_id or "").strip()
        if not uid:
            return []
        has_files = self._HAS_FILES_SQL.format(alias="w")
        if include_shared:
            where = "s.name != ? AND (s.owner_user_id = ? OR s.shared = 1)"
            args: List[Any] = [FAVORITES_SHELF, uid]
        else:
            where = "s.name != ? AND s.owner_user_id = ?"
            args = [FAVORITES_SHELF, uid]
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT s.*, COUNT(w.id) AS work_count
                FROM shelves s
                LEFT JOIN shelf_items si ON si.shelf_id = s.id
                LEFT JOIN works w ON w.id = si.work_id AND {has_files}
                WHERE {where}
                GROUP BY s.id
                ORDER BY s.shared DESC, lower(s.name) ASC, s.created_at ASC
                """,
                args,
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def create_named_shelf(
        self,
        user_id: str,
        name: str,
        *,
        shared: bool = False,
    ) -> Dict[str, Any]:
        from librarian.named_shelves import (
            MAX_NAMED_SHELVES_PER_USER,
            normalize_shelf_name,
            shelf_name_ok,
        )

        uid = str(user_id or "").strip()
        cleaned = normalize_shelf_name(name)
        if not uid or not shelf_name_ok(cleaned):
            raise ValueError("Shelf needs a warm name that isn’t Favorites.")
        owned = self.list_named_shelves(uid, include_shared=False)
        if len(owned) >= MAX_NAMED_SHELVES_PER_USER:
            raise ValueError("The house already keeps enough named shelves.")
        for row in owned:
            if str(row.get("name") or "").casefold() == cleaned.casefold():
                raise ValueError("That shelf name is already on the wall.")
        now = time.time()
        shelf_id = uuid.uuid4().hex

        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO shelves (id, name, owner_user_id, created_at, shared) VALUES (?, ?, ?, ?, ?)",
                    (shelf_id, cleaned, uid, now, 1 if shared else 0),
                )

        self.run_write(_write, label="create_named_shelf")
        return {
            "id": shelf_id,
            "name": cleaned,
            "owner_user_id": uid,
            "created_at": now,
            "shared": bool(shared),
        }

    def set_shelf_shared(self, shelf_id: str, user_id: str, *, shared: bool) -> Dict[str, Any]:
        shelf = self.get_shelf(shelf_id)
        if not shelf or str(shelf.get("owner_user_id") or "") != str(user_id or ""):
            raise ValueError("Shelf not found")
        if str(shelf.get("name") or "") == FAVORITES_SHELF:
            raise ValueError("Favorites stays personal.")

        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE shelves SET shared = ? WHERE id = ?",
                    (1 if shared else 0, shelf_id),
                )

        self.run_write(_write, label="set_shelf_shared")
        shelf["shared"] = bool(shared)
        return shelf

    def delete_named_shelf(self, shelf_id: str, user_id: str) -> bool:
        shelf = self.get_shelf(shelf_id)
        if not shelf or str(shelf.get("owner_user_id") or "") != str(user_id or ""):
            return False
        if str(shelf.get("name") or "") == FAVORITES_SHELF:
            raise ValueError("Favorites cannot be removed.")

        def _write() -> Any:
            with self._connect() as conn:
                conn.execute("DELETE FROM shelf_items WHERE shelf_id = ?", (shelf_id,))
                conn.execute("DELETE FROM shelves WHERE id = ?", (shelf_id,))

        self.run_write(_write, label="delete_named_shelf")
        return True

    def shelf_work_count(self, shelf_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS n FROM shelf_items s
                JOIN works w ON w.id = s.work_id
                WHERE s.shelf_id = ?
                  AND {self._HAS_FILES_SQL.format(alias="w")}
                """,
                (shelf_id,),
            ).fetchone()
        return int(row["n"] if row else 0)

    def shelf_works(self, shelf_id: str, *, limit: int = 24) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT w.* FROM shelf_items s
                JOIN works w ON w.id = s.work_id
                WHERE s.shelf_id = ?
                  AND {self._HAS_FILES_SQL.format(alias="w")}
                ORDER BY s.added_at DESC
                LIMIT ?
                """,
                (shelf_id, int(limit)),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def add_to_named_shelf(self, shelf_id: str, user_id: str, work_id: str) -> bool:
        shelf = self._shelf_writable(shelf_id, user_id)
        if self.is_on_shelf(shelf_id, work_id):
            return False

        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO shelf_items (shelf_id, work_id, added_at) VALUES (?, ?, ?)",
                    (shelf["id"], work_id, time.time()),
                )

        self.run_write(_write, label="add_to_named_shelf")
        return True

    def remove_from_named_shelf(self, shelf_id: str, user_id: str, work_id: str) -> bool:
        shelf = self._shelf_writable(shelf_id, user_id)
        if not self.is_on_shelf(shelf["id"], work_id):
            return False

        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM shelf_items WHERE shelf_id = ? AND work_id = ?",
                    (shelf["id"], work_id),
                )

        self.run_write(_write, label="remove_from_named_shelf")
        return True

    def is_on_shelf(self, shelf_id: str, work_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM shelf_items WHERE shelf_id = ? AND work_id = ?",
                (shelf_id, work_id),
            ).fetchone()
        return row is not None

    def _shelf_writable(self, shelf_id: str, user_id: str) -> Dict[str, Any]:
        shelf = self.get_shelf(shelf_id)
        if not shelf:
            raise ValueError("Shelf not found")
        if str(shelf.get("name") or "") == FAVORITES_SHELF:
            raise ValueError("Use Favorites for that shelf.")
        owner = str(shelf.get("owner_user_id") or "")
        uid = str(user_id or "")
        shared = bool(int(shelf.get("shared") or 0))
        if owner != uid and not shared:
            raise ValueError("Shelf not found")
        # Shared shelves: any household member may tend items; rename/delete stay owner-only.
        return shelf

    def user_can_view_shelf(self, shelf: Mapping[str, Any], user_id: str) -> bool:
        if not shelf:
            return False
        if str(shelf.get("owner_user_id") or "") == str(user_id or ""):
            return True
        return bool(int(shelf.get("shared") or 0))

    def upsert_progress(
        self,
        *,
        user_id: str,
        work_id: str,
        position: str = "",
        fraction: float = 0.0,
    ) -> Dict[str, Any]:
        now = time.time()
        frac = max(0.0, min(1.0, float(fraction)))
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO progress (user_id, work_id, position, fraction, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, work_id) DO UPDATE SET
                        position = excluded.position,
                        fraction = excluded.fraction,
                        updated_at = excluded.updated_at
                    """,
                    (user_id, work_id, position, frac, now),
                )
        self.run_write(_write, label='upsert_progress')
        row = self.get_progress(user_id, work_id)
        assert row is not None
        return row

    def latest_progress_by_work(self) -> Dict[str, float]:
        """Most recent progress touch per work, for ranking sweep candidates."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT work_id, MAX(updated_at) AS last_read FROM progress GROUP BY work_id"
            ).fetchall()
        out: Dict[str, float] = {}
        for row in rows:
            work_id = str(row["work_id"] or "").strip()
            if work_id:
                out[work_id] = float(row["last_read"] or 0)
        return out

    def get_progress(self, user_id: str, work_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM progress WHERE user_id = ? AND work_id = ?",
                (user_id, work_id),
            ).fetchone()
        return _row_dict(row)

    def continue_works(self, user_id: str, *, limit: int = 18) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT w.*, p.fraction, p.position, p.updated_at AS progress_at
                FROM progress p
                JOIN works w ON w.id = p.work_id
                WHERE p.user_id = ? AND p.fraction < 1 AND p.fraction >= 0.01
                  AND {self._HAS_FILES_SQL.format(alias="w")}
                ORDER BY p.updated_at DESC
                LIMIT ?
                """,
                (user_id, int(limit)),
            ).fetchall()
        out = []
        for row in rows:
            data = _row_dict(row) or {}
            from librarian.covers import cover_file_ok

            data["has_cover"] = cover_file_ok(data)
            data["progress"] = int(round(float(data.get("fraction") or 0) * 100))
            out.append(data)
        return out

    def finished_works(self, user_id: str, *, limit: int = 18) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT w.*, p.fraction, p.position, p.updated_at AS progress_at
                FROM progress p
                JOIN works w ON w.id = p.work_id
                WHERE p.user_id = ? AND p.fraction >= 1
                  AND {self._HAS_FILES_SQL.format(alias="w")}
                ORDER BY p.updated_at DESC
                LIMIT ?
                """,
                (user_id, int(limit)),
            ).fetchall()
        out = []
        for row in rows:
            data = _row_dict(row) or {}
            from librarian.covers import cover_file_ok

            data["has_cover"] = cover_file_ok(data)
            data["progress"] = 100
            out.append(data)
        return out
