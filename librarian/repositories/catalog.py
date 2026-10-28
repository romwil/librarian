"""Works, files, FTS search, Stacks browse, and catalog lookups."""

from __future__ import annotations

import re
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

from librarian.repositories._base import (
    RepositoryBase,
    _fts_column_query,
    _fts_query,
    _row_dict,
)

# Stacks browse. Omitted or unknown sort is date added, newest first (`updated`).
# When sort_dir is omitted: author and title ascending, updated and year descending.
# Date added is shelf_items.added_at on a named shelf or Favorites, otherwise
# works.created_at. The `updated` key is kept so existing links still resolve.
BROWSE_SORTS = ("author", "title", "updated", "year")
BROWSE_DEFAULT_SORT = "updated"
BROWSE_SORT_DEFAULT_DIR = {
    "author": "asc",
    "title": "asc",
    "updated": "desc",
    "year": "desc",
}
BROWSE_PAGE_MAX_LIMIT = 100
# CSV export reuses these filters and stops here so a full shelf cannot stream unbounded.
BROWSE_EXPORT_ROW_CAP = 5000


def resolve_browse_sort(sort: Optional[str], sort_dir: Optional[str] = None) -> Tuple[str, str]:
    """Whitelist stacks sort and direction. Never pass raw query text into SQL."""
    sort_key = str(sort or "").strip().lower()
    if sort_key not in BROWSE_SORTS:
        sort_key = BROWSE_DEFAULT_SORT
    direction = str(sort_dir or "").strip().lower()
    if direction not in ("asc", "desc"):
        direction = BROWSE_SORT_DEFAULT_DIR[sort_key]
    return sort_key, direction


def browse_order_sql(sort_key: str, direction: str, *, on_shelf: bool) -> str:
    """ORDER BY fragment. ``sort_key`` and ``direction`` must already be whitelisted."""
    sql_dir = "DESC" if direction == "desc" else "ASC"
    if sort_key == "title":
        return f"w.title COLLATE NOCASE {sql_dir}, w.author COLLATE NOCASE ASC"
    if sort_key == "year":
        # Null years stay last in both directions.
        return f"(w.year IS NULL) ASC, w.year {sql_dir}, w.title COLLATE NOCASE ASC"
    if sort_key == "updated" and on_shelf:
        return f"s.added_at {sql_dir}, w.title COLLATE NOCASE ASC"
    if sort_key == "updated":
        return f"w.created_at {sql_dir}, w.title COLLATE NOCASE ASC"
    return f"w.author COLLATE NOCASE {sql_dir}, w.title COLLATE NOCASE ASC"


class CatalogRepository(RepositoryBase):
    def upsert_work(self, work: Dict[str, Any]) -> Dict[str, Any]:
        now = time.time()
        work_id = str(work.get("id") or uuid.uuid4().hex)
        payload = {
            "id": work_id,
            "kind": work["kind"],
            "title": work["title"],
            "author": work.get("author"),
            "series_name": work.get("series_name"),
            "series_index": work.get("series_index"),
            "year": work.get("year"),
            "isbn": work.get("isbn"),
            "mbid": work.get("mbid"),
            "asin": work.get("asin"),
            "narrator": work.get("narrator"),
            "description": work.get("description"),
            "publisher": work.get("publisher"),
            "genre": work.get("genre"),
            "cover_path": work.get("cover_path"),
            "folder_path": work.get("folder_path"),
            "abs_item_id": work.get("abs_item_id"),
            "synopsis_source": work.get("synopsis_source"),
            "llm_blurb": work.get("llm_blurb"),
            "atmosphere_path": work.get("atmosphere_path"),
            "art_attribution": work.get("art_attribution"),
            "review_state": work.get("review_state") or "none",
            "review_reason": work.get("review_reason"),
            "music_state": work.get("music_state"),
            "indexer_guid": work.get("indexer_guid"),
            "part_total": work.get("part_total"),
            "part_style": work.get("part_style"),
            "part_base": work.get("part_base"),
            "part_origin": work.get("part_origin"),
            "repair_fail_count": work.get("repair_fail_count"),
            "created_at": work.get("created_at") or now,
            "updated_at": now,
        }
        preserve = (
            "abs_item_id",
            "synopsis_source",
            "llm_blurb",
            "atmosphere_path",
            "art_attribution",
            "part_total",
            "part_style",
            "part_base",
            "part_origin",
            "repair_fail_count",
        )
        def _write() -> Any:
            with self._connect() as conn:
                existing = conn.execute("SELECT * FROM works WHERE id = ?", (work_id,)).fetchone()
                if existing:
                    for key in preserve:
                        if key not in work:
                            payload[key] = existing[key]
                    # Keep the larger known multipart total when re-organizing another part.
                    if (
                        "part_total" in work
                        and existing["part_total"] is not None
                        and payload["part_total"] is not None
                    ):
                        payload["part_total"] = max(int(existing["part_total"]), int(payload["part_total"]))
                    conn.execute(
                        """
                        UPDATE works SET
                            kind=?, title=?, author=?, series_name=?, series_index=?, year=?,
                            isbn=?, mbid=?, asin=?, narrator=?, description=?, publisher=?, genre=?, cover_path=?,
                            folder_path=?, abs_item_id=?, synopsis_source=?, llm_blurb=?,
                            atmosphere_path=?, art_attribution=?, review_state=?, review_reason=?,
                            music_state=?, indexer_guid=?, part_total=?, part_style=?, part_base=?,
                            part_origin=?, repair_fail_count=?, updated_at=?
                        WHERE id=?
                        """,
                        (
                            payload["kind"],
                            payload["title"],
                            payload["author"],
                            payload["series_name"],
                            payload["series_index"],
                            payload["year"],
                            payload["isbn"],
                            payload["mbid"],
                            payload["asin"],
                            payload["narrator"],
                            payload["description"],
                            payload["publisher"],
                            payload["genre"],
                            payload["cover_path"],
                            payload["folder_path"],
                            payload["abs_item_id"],
                            payload["synopsis_source"],
                            payload["llm_blurb"],
                            payload["atmosphere_path"],
                            payload["art_attribution"],
                            payload["review_state"],
                            payload["review_reason"],
                            payload["music_state"],
                            payload["indexer_guid"],
                            payload["part_total"],
                            payload["part_style"],
                            payload["part_base"],
                            payload["part_origin"],
                            payload["repair_fail_count"],
                            payload["updated_at"],
                            work_id,
                        ),
                    )
                    conn.execute("DELETE FROM works_fts WHERE work_id = ?", (work_id,))
                else:
                    conn.execute(
                        """
                        INSERT INTO works (
                            id, kind, title, author, series_name, series_index, year, isbn, mbid,
                            asin, narrator, description, publisher, genre, cover_path, folder_path, abs_item_id,
                            synopsis_source, llm_blurb, atmosphere_path, art_attribution,
                            review_state, review_reason, music_state, indexer_guid, part_total,
                            part_style, part_base, part_origin, repair_fail_count, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            payload["id"],
                            payload["kind"],
                            payload["title"],
                            payload["author"],
                            payload["series_name"],
                            payload["series_index"],
                            payload["year"],
                            payload["isbn"],
                            payload["mbid"],
                            payload["asin"],
                            payload["narrator"],
                            payload["description"],
                            payload["publisher"],
                            payload["genre"],
                            payload["cover_path"],
                            payload["folder_path"],
                            payload["abs_item_id"],
                            payload["synopsis_source"],
                            payload["llm_blurb"],
                            payload["atmosphere_path"],
                            payload["art_attribution"],
                            payload["review_state"],
                            payload["review_reason"],
                            payload["music_state"],
                            payload["indexer_guid"],
                            payload["part_total"],
                            payload["part_style"],
                            payload["part_base"],
                            payload["part_origin"],
                            payload["repair_fail_count"],
                            payload["created_at"],
                            payload["updated_at"],
                        ),
                    )
                conn.execute(
                    """
                    INSERT INTO works_fts (work_id, title, author, genre, description)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        work_id,
                        payload["title"] or "",
                        payload["author"] or "",
                        payload["genre"] or "",
                        payload["description"] or "",
                    ),
                )
        self.run_write(_write, label='upsert_work')
        row = self.get_work(work_id)
        assert row is not None
        return row

    def works_with_part_total(self, *, limit: int = 500) -> List[Dict[str, Any]]:
        """Shelved works that declare a multipart total (B3 owned holes)."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM works
                WHERE part_total IS NOT NULL AND part_total >= 2
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def get_work(self, work_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM works WHERE id = ?", (work_id,)).fetchone()
        return _row_dict(row)

    def delete_work(self, work_id: str) -> bool:
        """Remove a work and related catalog rows. Does not touch media on disk."""
        wid = str(work_id or "").strip()
        if not wid:
            return False
        if self.get_work(wid) is None:
            return False

        def _write() -> Any:
            with self._connect() as conn:
                conn.execute("DELETE FROM files WHERE work_id = ?", (wid,))
                conn.execute("DELETE FROM shelf_items WHERE work_id = ?", (wid,))
                conn.execute("DELETE FROM progress WHERE work_id = ?", (wid,))
                conn.execute("DELETE FROM whispers WHERE work_id = ?", (wid,))
                conn.execute("DELETE FROM works_fts WHERE work_id = ?", (wid,))
                conn.execute("DELETE FROM jobs WHERE work_id = ?", (wid,))
                conn.execute("DELETE FROM works WHERE id = ?", (wid,))

        self.run_write(_write, label="delete_work")
        return self.get_work(wid) is None

    def record_owned_slip_clearance(
        self,
        *,
        title: str,
        author: str = "",
        shelf_work_id: str = "",
        reason: str,
        now: Optional[float] = None,
        keep_seconds: float = 7 * 24 * 3600,
    ) -> None:
        """Remember a slip the house already had, so Holds can show a short note."""
        moment = time.time() if now is None else float(now)
        cutoff = moment - float(keep_seconds)
        row_id = uuid.uuid4().hex

        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM owned_slip_clearances WHERE created_at < ?",
                    (cutoff,),
                )
                conn.execute(
                    """
                    INSERT INTO owned_slip_clearances (
                        id, title, author, shelf_work_id, reason, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row_id,
                        str(title or ""),
                        str(author or ""),
                        str(shelf_work_id or "") or None,
                        str(reason or ""),
                        moment,
                    ),
                )

        self.run_write(_write, label="record_owned_slip_clearance")

    def list_owned_slip_clearances(
        self,
        *,
        since: float,
        limit: int = 12,
    ) -> List[Dict[str, Any]]:
        capped = max(1, min(int(limit or 12), 40))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM owned_slip_clearances
                WHERE created_at >= ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (float(since), capped),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def count_shell_works(self) -> int:
        """Works that are not Review slips and have no registered media files."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n FROM works w
                WHERE w.review_state != 'needs_review'
                  AND NOT EXISTS (SELECT 1 FROM files f WHERE f.work_id = w.id)
                """
            ).fetchone()
        return int(row["n"] if row else 0)

    def list_shell_works(self, *, limit: int = 5000, offset: int = 0) -> List[Dict[str, Any]]:
        """Non-Review works with zero file rows (candidates for shell purge)."""
        capped = max(1, min(int(limit or 5000), 20000))
        skip = max(0, int(offset or 0))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT w.* FROM works w
                WHERE w.review_state != 'needs_review'
                  AND NOT EXISTS (SELECT 1 FROM files f WHERE f.work_id = w.id)
                ORDER BY w.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (capped, skip),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def get_work_by_folder_path(self, folder_path: str) -> Optional[Dict[str, Any]]:
        text = str(folder_path or "").rstrip("/")
        if not text:
            return None
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM works WHERE folder_path = ?", (text,)).fetchone()
            if row is None and text != str(folder_path or ""):
                row = conn.execute(
                    "SELECT * FROM works WHERE folder_path = ?",
                    (str(folder_path),),
                ).fetchone()
        return _row_dict(row)

    def get_work_by_isbn(self, isbn: str) -> Optional[Dict[str, Any]]:
        digits = re.sub(r"[^0-9Xx]", "", isbn or "").upper()
        if not digits:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM works
                WHERE kind = 'book' AND isbn IS NOT NULL AND isbn != ''
                  AND replace(replace(upper(isbn), '-', ''), ' ', '') = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (digits,),
            ).fetchone()
        return _row_dict(row)

    def get_work_by_series_issue(
        self, *, kind: str, series_name: str, series_index: str
    ) -> Optional[Dict[str, Any]]:
        series = (series_name or "").strip()
        index = str(series_index or "").strip()
        if not series or not index:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM works
                WHERE kind = ? AND lower(series_name) = lower(?) AND lower(series_index) = lower(?)
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (kind, series, index),
            ).fetchone()
        return _row_dict(row)

    def get_work_by_kind_title(
        self,
        *,
        kind: str,
        title: str,
        author: str = "",
        music_state: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        name = (title or "").strip()
        if not name:
            return None
        clauses = ["kind = ?", "lower(title) = lower(?)", "lower(coalesce(author, '')) = lower(?)"]
        args: List[Any] = [kind, name, (author or "").strip()]
        if music_state:
            clauses.append("music_state = ?")
            args.append(music_state)
        sql = f"SELECT * FROM works WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(sql, args).fetchone()
        return _row_dict(row)

    def find_work_conflict(
        self,
        *,
        kind: str,
        folder_path: str,
        isbn: str = "",
        series_name: str = "",
        series_index: str = "",
        title: str = "",
        author: str = "",
        music_state: Optional[str] = None,
        exclude_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Another work with the same identity living at a different folder."""
        folder = str(folder_path or "").rstrip("/")
        clauses = ["kind = ?", "folder_path IS NOT NULL", "folder_path != ''", "rtrim(folder_path, '/') != ?"]
        args: List[Any] = [kind, folder]
        identity_clauses: List[str] = []
        identity_args: List[Any] = []
        digits = re.sub(r"[^0-9Xx]", "", isbn or "").upper()
        if kind == "book" and digits:
            identity_clauses.append("isbn IS NOT NULL AND isbn != '' AND replace(replace(upper(isbn), '-', ''), ' ', '') = ?")
            identity_args.append(digits)
        if series_name and series_index:
            identity_clauses.append("(lower(series_name) = lower(?) AND lower(series_index) = lower(?))")
            identity_args.extend([series_name, str(series_index)])
        if title:
            title_sql = "lower(title) = lower(?) AND lower(coalesce(author, '')) = lower(?)"
            title_args: List[Any] = [title, (author or "").strip()]
            if music_state:
                title_sql += " AND music_state = ?"
                title_args.append(music_state)
            identity_clauses.append(f"({title_sql})")
            identity_args.extend(title_args)
        if not identity_clauses:
            return None
        clauses.append("(" + " OR ".join(identity_clauses) + ")")
        args.extend(identity_args)
        if exclude_id:
            clauses.append("id != ?")
            args.append(exclude_id)
        # Prefer a shelved catalog row over another Review slip when both match.
        sql = (
            f"SELECT * FROM works WHERE {' AND '.join(clauses)} "
            "ORDER BY CASE WHEN review_state = 'needs_review' THEN 1 ELSE 0 END, "
            "updated_at DESC LIMIT 1"
        )
        with self._connect() as conn:
            row = conn.execute(sql, args).fetchone()
        return _row_dict(row)

    def list_shelved_by_isbn(self, isbn: str) -> List[Dict[str, Any]]:
        digits = re.sub(r"[^0-9Xx]", "", isbn or "").upper()
        if not digits:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM works
                WHERE review_state = 'none'
                  AND isbn IS NOT NULL AND isbn != ''
                  AND replace(replace(upper(isbn), '-', ''), ' ', '') = ?
                """,
                (digits,),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def list_shelved_by_title_author(
        self, *, kind: str, title: str, author: str
    ) -> List[Dict[str, Any]]:
        title_text = str(title or "").strip()
        author_text = str(author or "").strip()
        if not title_text or not author_text:
            return []
        clauses = [
            "review_state = 'none'",
            "lower(title) = lower(?)",
            "lower(author) = lower(?)",
            "trim(author) != ''",
        ]
        args: List[Any] = [title_text, author_text]
        if kind:
            clauses.append("kind = ?")
            args.append(kind)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM works WHERE {' AND '.join(clauses)}",
                args,
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def list_shelved_by_subtitle(self, subtitle: str) -> List[Dict[str, Any]]:
        text = str(subtitle or "").strip()
        if not text:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM works
                WHERE review_state = 'none'
                  AND subtitle IS NOT NULL AND trim(subtitle) != ''
                  AND lower(subtitle) = lower(?)
                """,
                (text,),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def list_shelved_by_series(
        self, *, kind: str, series_name: str, series_index: str
    ) -> List[Dict[str, Any]]:
        series = str(series_name or "").strip()
        index = str(series_index or "").strip()
        if not series or not index:
            return []
        clauses = [
            "review_state = 'none'",
            "lower(series_name) = lower(?)",
            "lower(series_index) = lower(?)",
        ]
        args: List[Any] = [series, index]
        if kind:
            clauses.append("kind = ?")
            args.append(kind)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM works WHERE {' AND '.join(clauses)}",
                args,
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def set_work_subtitle(self, work_id: str, subtitle: str) -> None:
        text = str(subtitle or "").strip()

        def _write() -> None:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE works SET subtitle = ? WHERE id = ?",
                    (text, work_id),
                )

        self.run_write(_write, label="set_work_subtitle")

    def list_works(
        self,
        *,
        kind: Optional[str] = None,
        review_state: Optional[str] = None,
        review_reason: Optional[str] = None,
        music_state: Optional[str] = None,
        require_files: bool = False,
        limit: int = 48,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        clauses = ["1=1"]
        args: List[Any] = []
        if kind:
            clauses.append("kind = ?")
            args.append(kind)
        if review_state:
            clauses.append("review_state = ?")
            args.append(review_state)
        if review_reason:
            clauses.append("review_reason = ?")
            args.append(review_reason)
        if music_state:
            clauses.append("music_state = ?")
            args.append(music_state)
        if require_files:
            clauses.append(self._HAS_FILES_SQL.format(alias="works"))
        args.append(int(limit))
        args.append(max(0, int(offset)))
        sql = (
            f"SELECT * FROM works WHERE {' AND '.join(clauses)} "
            "ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def load_owned_slip_sweep(
        self,
        *,
        kinds: Sequence[str],
        limit: int,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Shelved media and fileless Review slips, one connection for the whole read."""
        kind_list = [str(kind) for kind in kinds if str(kind)]
        if not kind_list:
            return [], []
        placeholders = ", ".join("?" for _ in kind_list)
        order_case = " ".join(f"WHEN ? THEN {index}" for index in range(len(kind_list)))
        owned_sql = f"""
            SELECT * FROM works
            WHERE kind IN ({placeholders})
              AND review_state != 'needs_review'
              AND {self._HAS_FILES_SQL.format(alias="works")}
            ORDER BY CASE kind {order_case} ELSE {len(kind_list)} END,
                     title COLLATE NOCASE
        """
        slip_sql = f"""
            SELECT * FROM works
            WHERE review_state = 'needs_review'
              AND NOT {self._HAS_FILES_SQL.format(alias="works")}
            ORDER BY updated_at DESC
            LIMIT ?
        """
        with self._connect() as conn:
            owned_rows = conn.execute(owned_sql, [*kind_list, *kind_list]).fetchall()
            slip_rows = conn.execute(slip_sql, (max(1, int(limit)),)).fetchall()
        return (
            [_row_dict(row) or {} for row in owned_rows],
            [_row_dict(row) or {} for row in slip_rows],
        )

    def list_works_added_since(
        self,
        since_ts: float,
        *,
        limit: int = 12,
        require_files: bool = True,
    ) -> List[Dict[str, Any]]:
        """Works whose created_at is at or after since_ts (newest first)."""
        clauses = ["created_at >= ?"]
        args: List[Any] = [float(since_ts)]
        if require_files:
            clauses.append(self._HAS_FILES_SQL.format(alias="works"))
        args.append(max(1, int(limit)))
        sql = (
            f"SELECT * FROM works WHERE {' AND '.join(clauses)} "
            "ORDER BY created_at DESC LIMIT ?"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def count_works(
        self,
        *,
        review_state: Optional[str] = None,
        review_reason: Optional[str] = None,
    ) -> int:
        """Count works matching review filters (no page limit)."""
        clauses = ["1=1"]
        args: List[Any] = []
        if review_state:
            clauses.append("review_state = ?")
            args.append(review_state)
        if review_reason:
            clauses.append("review_reason = ?")
            args.append(review_reason)
        sql = f"SELECT COUNT(*) AS cnt FROM works WHERE {' AND '.join(clauses)}"
        with self._connect() as conn:
            row = conn.execute(sql, args).fetchone()
        return int(row["cnt"] if row else 0)

    _NEEDS_ENRICHMENT_WHERE = """
        kind IN ('book', 'audiobook')
        AND review_state != 'needs_review'
        AND (
            author IS NULL OR trim(author) = ''
            OR lower(trim(author)) IN (
                'unknown author', 'unknown authors', 'author unknown',
                'anonymous', 'n/a', 'none', 'null'
            )
            OR description IS NULL OR description = ''
            OR genre IS NULL OR genre = ''
            OR year IS NULL
            OR cover_path IS NULL OR cover_path = ''
        )
    """

    # Same holes as Enrich `is_thin` (SQL cannot check that cover_path is on disk).
    _ENRICHMENT_MISSING_SQL = """
        (
            CASE WHEN author IS NULL OR trim(author) = ''
              OR lower(trim(author)) IN (
                'unknown author', 'unknown authors', 'author unknown',
                'anonymous', 'n/a', 'none', 'null'
              ) THEN 1 ELSE 0 END
            + CASE WHEN description IS NULL OR description = '' THEN 1 ELSE 0 END
            + CASE WHEN genre IS NULL OR genre = '' THEN 1 ELSE 0 END
            + CASE WHEN year IS NULL THEN 1 ELSE 0 END
            + CASE WHEN cover_path IS NULL OR cover_path = '' THEN 1 ELSE 0 END
        )
    """

    def works_needing_enrichment(self, *, limit: int = 10) -> List[Dict[str, Any]]:
        """Thinnest books/audiobooks for the enrich trickle (most holes first).

        SQL cannot see the filesystem; a second pass includes otherwise-full
        rows whose ``cover_path`` file is gone (same as Enrich ``is_thin``).
        """
        from librarian.covers import cover_file_ok

        limit_n = max(1, int(limit))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM works
                WHERE {self._NEEDS_ENRICHMENT_WHERE}
                ORDER BY {self._ENRICHMENT_MISSING_SQL} DESC, updated_at ASC
                LIMIT ?
                """,
                (limit_n,),
            ).fetchall()
            extras = conn.execute(
                f"""
                SELECT * FROM works
                WHERE kind IN ('book', 'audiobook')
                  AND review_state != 'needs_review'
                  AND cover_path IS NOT NULL AND trim(cover_path) != ''
                  AND NOT ({self._NEEDS_ENRICHMENT_WHERE})
                ORDER BY updated_at ASC
                LIMIT ?
                """,
                (limit_n * 8,),
            ).fetchall()
        needed = [_row_dict(row) or {} for row in rows]
        seen = {row.get("id") for row in needed}
        for row in extras:
            data = _row_dict(row) or {}
            work_id = data.get("id")
            if work_id in seen or cover_file_ok(data):
                continue
            needed.append(data)
            seen.add(work_id)
            if len(needed) >= limit_n:
                break
        return needed[:limit_n]

    def count_works_needing_enrichment(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM works WHERE {self._NEEDS_ENRICHMENT_WHERE}"
            ).fetchone()
        return int(row["cnt"] if row else 0)

    @staticmethod
    def _author_letter_sql(column: str = "author") -> str:
        return (
            f"CASE "
            f"WHEN {column} IS NULL OR trim({column}) = '' THEN '#' "
            f"WHEN upper(substr(trim({column}), 1, 1)) GLOB '[A-Z]' "
            f"THEN upper(substr(trim({column}), 1, 1)) "
            f"ELSE '#' END"
        )

    def _browse_base(
        self,
        *,
        kind: Optional[str] = None,
        author: Optional[str] = None,
        letter: Optional[str] = None,
        series: Optional[str] = None,
        genre: Optional[str] = None,
        shelf: Optional[str] = None,
        user_id: Optional[str] = None,
        include_review: bool = False,
    ) -> Tuple[str, str, List[Any]]:
        """Return (from_sql, where_sql, args) for Stacks browse."""
        clauses = ["1=1"]
        args: List[Any] = []
        from_sql = "works w"
        shelf_key = str(shelf or "").strip()
        if shelf_key == "favorites":
            if not user_id:
                raise ValueError("user_id required for favorites shelf")
            shelf_row = self.favorites_shelf(user_id)
            from_sql = "shelf_items s JOIN works w ON w.id = s.work_id"
            clauses.append("s.shelf_id = ?")
            args.append(shelf_row["id"])
        elif shelf_key and shelf_key != "favorites":
            # Named household shelf id (hex). Caller enforces visibility.
            if not user_id:
                raise ValueError("user_id required for named shelf")
            shelf_row = self.get_shelf(shelf_key)
            if not shelf_row or not self.user_can_view_shelf(shelf_row, user_id):
                raise ValueError("Shelf not found")
            from_sql = "shelf_items s JOIN works w ON w.id = s.work_id"
            clauses.append("s.shelf_id = ?")
            args.append(shelf_row["id"])
        if not include_review:
            clauses.append("w.review_state != 'needs_review'")
        # Shelf surfaces only show volumes with registered media files.
        clauses.append(self._HAS_FILES_SQL.format(alias="w"))
        if kind:
            clauses.append("w.kind = ?")
            args.append(kind)
        if author:
            clauses.append("lower(trim(w.author)) = lower(?)")
            args.append(author.strip())
        if series:
            clauses.append("lower(trim(w.series_name)) = lower(?)")
            args.append(series.strip())
        if genre:
            clauses.append("lower(trim(w.genre)) = lower(?)")
            args.append(genre.strip())
        letter_key = str(letter or "").strip().upper()
        if letter_key:
            if letter_key != "#" and (len(letter_key) != 1 or not ("A" <= letter_key <= "Z")):
                letter_key = ""
            if letter_key:
                clauses.append(f"{self._author_letter_sql('w.author')} = ?")
                args.append(letter_key)
        where_sql = " AND ".join(clauses)
        return from_sql, where_sql, args

    def browse_works(
        self,
        *,
        kind: Optional[str] = None,
        author: Optional[str] = None,
        letter: Optional[str] = None,
        series: Optional[str] = None,
        genre: Optional[str] = None,
        shelf: Optional[str] = None,
        user_id: Optional[str] = None,
        sort: Optional[str] = None,
        sort_dir: Optional[str] = None,
        offset: int = 0,
        limit: int = 48,
        max_limit: int = BROWSE_PAGE_MAX_LIMIT,
    ) -> Dict[str, Any]:
        ceiling = max(1, min(int(max_limit or BROWSE_PAGE_MAX_LIMIT), BROWSE_EXPORT_ROW_CAP))
        capped = max(1, min(int(limit or 48), ceiling))
        skip = max(0, int(offset or 0))
        sort_key, direction = resolve_browse_sort(sort, sort_dir)
        shelf_key = str(shelf or "").strip()
        order_sql = browse_order_sql(sort_key, direction, on_shelf=bool(shelf_key))

        from_sql, where_sql, args = self._browse_base(
            kind=kind,
            author=author,
            letter=letter,
            series=series,
            genre=genre,
            shelf=shelf,
            user_id=user_id,
        )
        with self._connect() as conn:
            total = int(
                conn.execute(f"SELECT COUNT(*) AS n FROM {from_sql} WHERE {where_sql}", args).fetchone()["n"]
            )
            rows = conn.execute(
                f"""
                SELECT w.* FROM {from_sql}
                WHERE {where_sql}
                ORDER BY {order_sql}
                LIMIT ? OFFSET ?
                """,
                [*args, capped, skip],
            ).fetchall()
        items = [_row_dict(row) or {} for row in rows]
        from librarian.covers import cover_file_ok

        for item in items:
            item["has_cover"] = cover_file_ok(item)
        return {
            "items": items,
            "total": total,
            "offset": skip,
            "limit": capped,
            "sort": sort_key,
            "sort_dir": direction,
        }

    def browse_facets(
        self,
        *,
        kind: Optional[str] = None,
        shelf: Optional[str] = None,
        user_id: Optional[str] = None,
        author_limit: int = 40,
        series_limit: int = 40,
    ) -> Dict[str, Any]:
        from_sql, where_sql, args = self._browse_base(
            kind=kind,
            shelf=shelf,
            user_id=user_id,
        )
        letter_expr = self._author_letter_sql("w.author")
        with self._connect() as conn:
            letter_rows = conn.execute(
                f"""
                SELECT {letter_expr} AS letter, COUNT(*) AS n
                FROM {from_sql}
                WHERE {where_sql}
                GROUP BY letter
                ORDER BY letter
                """,
                args,
            ).fetchall()
            kind_rows = conn.execute(
                f"""
                SELECT w.kind AS kind, COUNT(*) AS n
                FROM {from_sql}
                WHERE {where_sql}
                GROUP BY w.kind
                ORDER BY w.kind
                """,
                args,
            ).fetchall()
            author_rows = conn.execute(
                f"""
                SELECT w.author AS name, COUNT(*) AS n
                FROM {from_sql}
                WHERE {where_sql}
                  AND w.author IS NOT NULL AND trim(w.author) != ''
                GROUP BY lower(trim(w.author))
                ORDER BY n DESC, w.author COLLATE NOCASE ASC
                LIMIT ?
                """,
                [*args, max(1, min(int(author_limit or 40), 100))],
            ).fetchall()
            series_rows = conn.execute(
                f"""
                SELECT w.series_name AS name, COUNT(*) AS n
                FROM {from_sql}
                WHERE {where_sql}
                  AND w.series_name IS NOT NULL AND trim(w.series_name) != ''
                GROUP BY lower(trim(w.series_name))
                ORDER BY n DESC, w.series_name COLLATE NOCASE ASC
                LIMIT ?
                """,
                [*args, max(1, min(int(series_limit or 40), 100))],
            ).fetchall()
            genre_filled = int(
                conn.execute(
                    f"""
                    SELECT COUNT(*) AS n FROM {from_sql}
                    WHERE {where_sql}
                      AND w.genre IS NOT NULL AND trim(w.genre) != ''
                    """,
                    args,
                ).fetchone()["n"]
            )
            genre_total = int(
                conn.execute(f"SELECT COUNT(*) AS n FROM {from_sql} WHERE {where_sql}", args).fetchone()["n"]
            )

        letters = [{"letter": str(row["letter"]), "count": int(row["n"])} for row in letter_rows]
        # Phase B: subject/genre facets stay empty until enrich fills genre at usable rate.
        genre_ready = genre_total > 0 and (genre_filled / genre_total) >= 0.25
        genres: List[Dict[str, Any]] = []
        if genre_ready:
            with self._connect() as conn:
                genre_rows = conn.execute(
                    f"""
                    SELECT w.genre AS name, COUNT(*) AS n
                    FROM {from_sql}
                    WHERE {where_sql}
                      AND w.genre IS NOT NULL AND trim(w.genre) != ''
                    GROUP BY lower(trim(w.genre))
                    ORDER BY n DESC, w.genre COLLATE NOCASE ASC
                    LIMIT 40
                    """,
                    args,
                ).fetchall()
            genres = [{"name": str(row["name"]), "count": int(row["n"])} for row in genre_rows if row["name"]]

        return {
            "letters": letters,
            "kinds": [{"kind": str(row["kind"]), "count": int(row["n"])} for row in kind_rows],
            "authors": [{"name": str(row["name"]), "count": int(row["n"])} for row in author_rows if row["name"]],
            "series": [{"name": str(row["name"]), "count": int(row["n"])} for row in series_rows if row["name"]],
            "genres": genres,
            "genre_ready": genre_ready,
            "genre_fill": {"filled": genre_filled, "total": genre_total},
        }

    def search_works(self, query: str, *, limit: int = 24, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        match = _fts_query(query)
        if not match:
            return []
        return self.search_works_raw(match, limit=limit, kind=kind)

    def search_works_raw(self, match: str, *, limit: int = 24, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        """Run a prepared FTS MATCH string (exact or prefix-forgiving)."""
        needle = str(match or "").strip()
        if not needle:
            return []
        kind_sql = ""
        args: List[Any] = [needle]
        if kind:
            kind_sql = " AND w.kind = ?"
            args.append(kind)
        args.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT w.* FROM works_fts f
                JOIN works w ON w.id = f.work_id
                WHERE works_fts MATCH ?{kind_sql}
                  AND {self._HAS_FILES_SQL.format(alias="w")}
                  AND w.review_state != 'needs_review'
                ORDER BY rank
                LIMIT ?
                """,
                args,
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def search_works_mode(
        self,
        query: str,
        mode: str,
        *,
        limit: int = 24,
        kind: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Shelf search locked to one field. Unknown modes return nothing."""
        key = str(mode or "").strip().lower()
        text = str(query or "").strip()
        if key in {"title", "author"}:
            match = _fts_column_query(key, text)
            if not match:
                return []
            return self.search_works_raw(match, limit=limit, kind=kind)
        if key == "isbn":
            return self._search_works_isbn(text, limit=limit, kind=kind)
        if key == "series":
            return self._search_works_text_column(
                "series_name", text, limit=limit, kind=kind, how="prefix"
            )
        if key == "narrator":
            return self._search_works_text_column(
                "narrator", text, limit=limit, kind=kind, how="contains"
            )
        return []

    def _search_works_isbn(
        self, query: str, *, limit: int, kind: Optional[str]
    ) -> List[Dict[str, Any]]:
        from librarian.identify import isbn_match_keys

        want = set(isbn_match_keys(query))
        if not want:
            return []
        kind_sql = ""
        args: List[Any] = []
        if kind:
            kind_sql = " AND w.kind = ?"
            args.append(kind)
        has_files = self._HAS_FILES_SQL.format(alias="w")
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT w.* FROM works w
                WHERE w.isbn IS NOT NULL AND trim(w.isbn) != ''
                  AND {has_files}
                  AND w.review_state != 'needs_review'
                  {kind_sql}
                """,
                args,
            ).fetchall()
        hits: List[Dict[str, Any]] = []
        for row in rows:
            item = _row_dict(row) or {}
            if want.intersection(isbn_match_keys(str(item.get("isbn") or ""))):
                hits.append(item)
            if len(hits) >= int(limit):
                break
        return hits

    def _search_works_text_column(
        self,
        column: str,
        query: str,
        *,
        limit: int,
        kind: Optional[str],
        how: str,
    ) -> List[Dict[str, Any]]:
        if column not in {"series_name", "narrator"}:
            return []
        needle = str(query or "").strip()
        if not needle:
            return []
        escaped = needle.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%" if how == "contains" else f"{escaped}%"
        kind_sql = ""
        args: List[Any] = [needle.casefold(), like]
        if kind:
            kind_sql = " AND w.kind = ?"
            args.append(kind)
        args.append(int(limit))
        has_files = self._HAS_FILES_SQL.format(alias="w")
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT w.* FROM works w
                WHERE {has_files}
                  AND w.review_state != 'needs_review'
                  AND w.{column} IS NOT NULL AND trim(w.{column}) != ''
                  AND (
                    lower(trim(w.{column})) = ?
                    OR lower(w.{column}) LIKE ? ESCAPE '\\'
                  )
                  {kind_sql}
                ORDER BY w.title COLLATE NOCASE
                LIMIT ?
                """,
                args,
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def works_for_series(self, *, kind: str, series_name: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM works
                WHERE kind = ? AND lower(series_name) = lower(?) AND review_state != 'needs_review'
                  AND {self._HAS_FILES_SQL.format(alias="works")}
                ORDER BY series_index
                """,
                (kind, series_name),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def series_names(self, kind: str) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT series_name FROM works
                WHERE kind = ? AND series_name IS NOT NULL AND series_name != ''
                  AND {self._HAS_FILES_SQL.format(alias="works")}
                ORDER BY series_name
                """,
                (kind,),
            ).fetchall()
        return [str(row["series_name"]) for row in rows if row["series_name"]]

    def suggest_values(
        self,
        *,
        field: str,
        kind: str = "",
        q: str = "",
        limit: int = 24,
    ) -> List[str]:
        """Distinct catalog values for typeahead. Artist→author (music); album→title∪series."""
        key = str(field or "").strip().lower()
        kind_key = str(kind or "").strip().lower()
        needle = re.sub(r"\s+", " ", str(q or "")).strip()
        capped = max(1, min(int(limit or 24), 200))
        like = f"%{needle.casefold()}%" if needle else None

        bookish = ("book", "magazine", "audiobook")
        if key == "author":
            column = "author"
            kinds: Optional[Tuple[str, ...]] = (kind_key,) if kind_key in bookish else bookish
            if kind_key == "music":
                kinds = ("music",)
        elif key == "artist":
            column = "author"
            kinds = ("music",)
        elif key == "title":
            column = "title"
            kinds = (kind_key,) if kind_key else None
        elif key == "series":
            column = "series_name"
            kinds = (kind_key,) if kind_key else None
        elif key == "album":
            return self._suggest_albums(like=like, limit=capped)
        elif key == "year":
            return self._suggest_years(kind=kind_key, needle=needle, limit=capped)
        else:
            return []

        clauses = [
            f"{column} IS NOT NULL",
            f"trim({column}) != ''",
            "review_state != 'needs_review'",
            self._HAS_FILES_SQL.format(alias="works"),
        ]
        args: List[Any] = []
        if kinds is not None:
            placeholders = ", ".join("?" for _ in kinds)
            clauses.append(f"kind IN ({placeholders})")
            args.extend(kinds)
        if like is not None:
            clauses.append(f"lower({column}) LIKE ?")
            args.append(like)
        args.append(capped)
        sql = (
            f"SELECT DISTINCT {column} AS value FROM works "
            f"WHERE {' AND '.join(clauses)} "
            f"ORDER BY {column} COLLATE NOCASE LIMIT ?"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [str(row["value"]).strip() for row in rows if row["value"] and str(row["value"]).strip()]

    def _suggest_albums(self, *, like: Optional[str], limit: int) -> List[str]:
        clauses = [
            "kind = 'music'",
            "review_state != 'needs_review'",
            self._HAS_FILES_SQL.format(alias="works"),
        ]
        args: List[Any] = []
        title_clause = "title IS NOT NULL AND trim(title) != ''"
        series_clause = "series_name IS NOT NULL AND trim(series_name) != ''"
        if like is not None:
            title_clause += " AND lower(title) LIKE ?"
            series_clause += " AND lower(series_name) LIKE ?"
            args.extend([like, like])
        args.append(limit)
        sql = f"""
            SELECT value FROM (
                SELECT DISTINCT title AS value FROM works
                WHERE {' AND '.join(clauses)} AND ({title_clause})
                UNION
                SELECT DISTINCT series_name AS value FROM works
                WHERE {' AND '.join(clauses)} AND ({series_clause})
            )
            ORDER BY value COLLATE NOCASE
            LIMIT ?
        """
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [str(row["value"]).strip() for row in rows if row["value"] and str(row["value"]).strip()]

    def _suggest_years(self, *, kind: str, needle: str, limit: int) -> List[str]:
        clauses = [
            "year IS NOT NULL",
            "review_state != 'needs_review'",
            self._HAS_FILES_SQL.format(alias="works"),
        ]
        args: List[Any] = []
        if kind:
            clauses.append("kind = ?")
            args.append(kind)
        if needle:
            clauses.append("CAST(year AS TEXT) LIKE ?")
            args.append(f"%{needle}%")
        args.append(limit)
        sql = (
            f"SELECT DISTINCT year FROM works WHERE {' AND '.join(clauses)} "
            f"ORDER BY year DESC LIMIT ?"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        out: List[str] = []
        for row in rows:
            year = row["year"]
            if year is None:
                continue
            out.append(str(int(year)))
        return out

    def files_named_for_kind(self, kind: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT f.*, w.series_name, w.title AS work_title, w.author, w.id AS work_pk
                FROM files f
                JOIN works w ON w.id = f.work_id
                WHERE w.kind = ? AND w.review_state != 'needs_review'
                ORDER BY w.title, f.filename
                """,
                (kind,),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def add_file(self, record: Dict[str, Any]) -> Dict[str, Any]:
        file_id = str(record.get("id") or uuid.uuid4().hex)
        now = time.time()
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO files (id, work_id, path, filename, kind, size, part, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        file_id,
                        record.get("work_id"),
                        record["path"],
                        record["filename"],
                        record.get("kind"),
                        record.get("size"),
                        record.get("part"),
                        now,
                    ),
                )
        self.run_write(_write, label='add_file')
        return self.get_file(file_id) or {}

    def get_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        return _row_dict(row)

    def get_file_by_path(self, path: str) -> Optional[Dict[str, Any]]:
        text = str(path or "")
        if not text:
            return None
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM files WHERE path = ?", (text,)).fetchone()
        return _row_dict(row)

    def upsert_file(self, record: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.get_file_by_path(record["path"])
        if existing is None:
            return self.add_file(record)
        def _write() -> Any:
            with self._connect() as conn:
                part = record["part"] if "part" in record else existing.get("part")
                conn.execute(
                    """
                    UPDATE files SET work_id = ?, filename = ?, kind = ?, size = ?, part = ?
                    WHERE id = ?
                    """,
                    (
                        record.get("work_id") or existing.get("work_id"),
                        record.get("filename") or existing.get("filename"),
                        record.get("kind") or existing.get("kind"),
                        record["size"] if record.get("size") is not None else existing.get("size"),
                        part,
                        existing["id"],
                    ),
                )
        self.run_write(_write, label='upsert_file')
        return self.get_file(str(existing["id"])) or {}

    def files_for_work(self, work_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM files WHERE work_id = ? ORDER BY filename",
                (work_id,),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def delete_file(self, file_id: str) -> bool:
        """Remove one file row. Does not touch media on disk."""
        fid = str(file_id or "").strip()
        if not fid or self.get_file(fid) is None:
            return False

        def _write() -> Any:
            with self._connect() as conn:
                conn.execute("DELETE FROM files WHERE id = ?", (fid,))

        self.run_write(_write, label="delete_file")
        return self.get_file(fid) is None

    def relocate_work_files(self, work_id: str, src_folder: str, dest_folder: str) -> int:
        """Rewrite stored file paths after a folder move (music promote)."""
        src = str(src_folder).rstrip("/")
        dest = str(dest_folder).rstrip("/")
        if not src or src == dest:
            return 0
        prefix = src + "/"

        def _write() -> int:
            updated = 0
            with self._connect() as conn:
                rows = conn.execute("SELECT id, path FROM files WHERE work_id = ?", (work_id,)).fetchall()
                for row in rows:
                    old = str(row["path"] or "")
                    if old == src or old.startswith(prefix):
                        conn.execute(
                            "UPDATE files SET path = ? WHERE id = ?",
                            (dest + old[len(src) :], row["id"]),
                        )
                        updated += 1
            return updated

        return int(self.run_write(_write, label="relocate_work_files") or 0)

    def list_shelved_works(self, kind: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM works
                WHERE kind = ? AND {self._HAS_FILES_SQL.format(alias="works")}
                ORDER BY title COLLATE NOCASE
                """,
                (kind,),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def kind_counts(self) -> Dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT kind, COUNT(*) AS n FROM works
                WHERE (review_state IS NULL OR review_state IN ('none', 'resolved', ''))
                  AND {self._HAS_FILES_SQL.format(alias="works")}
                GROUP BY kind
                """
            ).fetchall()
        return {str(row["kind"]): int(row["n"]) for row in rows}

    def author_year_counts(self, *, year: int, min_count: int = 3, limit: int = 5) -> List[Dict[str, Any]]:
        start = time.mktime(time.strptime(f"{int(year)}-01-01", "%Y-%m-%d"))
        end = time.mktime(time.strptime(f"{int(year) + 1}-01-01", "%Y-%m-%d"))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT author, COUNT(*) AS n
                FROM works
                WHERE author IS NOT NULL AND TRIM(author) != ''
                  AND created_at >= ? AND created_at < ?
                GROUP BY author
                HAVING n >= ?
                ORDER BY n DESC
                LIMIT ?
                """,
                (start, end, int(min_count), int(limit)),
            ).fetchall()
        return [{"author": row["author"], "count": int(row["n"]), "year": int(year)} for row in rows]

    def list_shelved_by_author_token(self, *, kind: str, token: str, limit: int = 40) -> List[Dict[str, Any]]:
        """Shelved works of one kind whose author contains ``token`` (duplicate gate)."""
        needle = str(token or "").strip().lower()
        if len(needle) < 2:
            return []
        clauses = [
            "review_state != 'needs_review'",
            "author IS NOT NULL",
            "instr(lower(author), ?) > 0",
            self._HAS_FILES_SQL.format(alias="works"),
        ]
        args: List[Any] = [needle]
        if kind:
            clauses.append("kind = ?")
            args.append(kind)
        args.append(max(1, int(limit)))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM works WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT ?",
                args,
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]
