"""Wanted requests: the search/retry ledger for things not yet on a shelf."""

from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Any, Dict, List, Mapping, Optional

from librarian.repositories._base import (
    RepositoryBase,
    _dumps,
    _row_dict,
)


def _wanted_source(value: Any) -> Optional[str]:
    """Persist only sweep or manual. Older rows stay unset until cleanup."""
    source = str(value or "").strip().lower()
    if source in ("sweep", "manual"):
        return source
    return None


class WantedRepository(RepositoryBase):
    def _wanted_from_row(self, row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
        return _row_dict(row)

    def get_wanted(self, wanted_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM wanted WHERE id = ?", (wanted_id,)).fetchone()
        return self._wanted_from_row(row)

    def get_wanted_by_dedupe(self, dedupe_key: str) -> Optional[Dict[str, Any]]:
        key = str(dedupe_key or "").strip()
        if not key:
            return None
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM wanted WHERE dedupe_key = ?", (key,)).fetchone()
        return self._wanted_from_row(row)

    def get_wanted_by_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        text = str(job_id or "").strip()
        if not text:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM wanted WHERE job_id = ? LIMIT 1",
                (text,),
            ).fetchone()
        return self._wanted_from_row(row)

    def _wanted_where(
        self,
        *,
        status: Optional[str] = None,
        kind: Optional[str] = None,
        source: Optional[str] = None,
        include_dismissed: bool = False,
    ) -> tuple[str, List[Any]]:
        clauses: List[str] = []
        args: List[Any] = []
        if status:
            clauses.append("status = ?")
            args.append(status)
        elif not include_dismissed:
            clauses.append("status != 'dismissed'")
        if kind:
            clauses.append("kind = ?")
            args.append(kind)
        source_key = str(source or "").strip().lower()
        if source_key == "manual":
            clauses.append("source = ?")
            args.append("manual")
        elif source_key == "sweep":
            clauses.append("(source = 'sweep' OR source IS NULL OR source = '')")
        return " AND ".join(clauses) or "1 = 1", args

    def list_wanted(
        self,
        *,
        status: Optional[str] = None,
        kind: Optional[str] = None,
        source: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        include_dismissed: bool = False,
    ) -> List[Dict[str, Any]]:
        where, args = self._wanted_where(
            status=status, kind=kind, source=source, include_dismissed=include_dismissed
        )
        sql = f"SELECT * FROM wanted WHERE {where} ORDER BY updated_at DESC, id ASC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            args.extend([max(0, int(limit)), max(0, int(offset))])
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [self._wanted_from_row(row) or {} for row in rows]

    def count_wanted(
        self,
        *,
        status: Optional[str] = None,
        kind: Optional[str] = None,
        source: Optional[str] = None,
        include_dismissed: bool = False,
    ) -> int:
        where, args = self._wanted_where(
            status=status, kind=kind, source=source, include_dismissed=include_dismissed
        )
        with self._connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM wanted WHERE {where}", args).fetchone()
        return int(row["n"] if row is not None else 0)

    def distinct_wanted_kinds(
        self,
        *,
        status: Optional[str] = None,
        include_dismissed: bool = False,
    ) -> List[str]:
        where, args = self._wanted_where(
            status=status, include_dismissed=include_dismissed
        )
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT DISTINCT kind FROM wanted WHERE {where} ORDER BY kind ASC",
                args,
            ).fetchall()
        return [str(row["kind"]) for row in rows if row["kind"]]

    def list_due_wanted(self, *, now: float, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Due rows: owner-added before sweep, then newest. No cap unless asked."""
        sql = """
            SELECT * FROM wanted
            WHERE status = 'wanted' AND next_search_at <= ?
            ORDER BY CASE WHEN IFNULL(source, '') = 'sweep' THEN 1 ELSE 0 END ASC,
                     created_at DESC,
                     id DESC
        """
        args: List[Any] = [float(now)]
        if limit is not None:
            sql += " LIMIT ?"
            args.append(max(0, int(limit)))
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [self._wanted_from_row(row) or {} for row in rows]

    def insert_wanted(self, row: Dict[str, Any]) -> Dict[str, Any]:
        now = time.time()
        wanted_id = str(row.get("id") or uuid.uuid4().hex)
        dedupe_key = str(row["dedupe_key"])

        def _write() -> Any:
            with self._connect() as conn:
                try:
                    conn.execute(
                        """
                        INSERT INTO wanted (
                            id, dedupe_key, work_id, title, author, isbn, kind, status,
                            miss_streak, next_search_at, job_id, created_at, updated_at,
                            source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            wanted_id,
                            dedupe_key,
                            row.get("work_id") or None,
                            row.get("title") or "",
                            row.get("author") or "",
                            row.get("isbn") or "",
                            row["kind"],
                            row.get("status") or "wanted",
                            int(row.get("miss_streak") or 0),
                            float(row.get("next_search_at") if row.get("next_search_at") is not None else now),
                            row.get("job_id") or None,
                            float(row.get("created_at") or now),
                            float(row.get("updated_at") or now),
                            _wanted_source(row.get("source")),
                        ),
                    )
                except sqlite3.IntegrityError:
                    return None
            return wanted_id

        self.run_write(_write, label="insert_wanted")
        stored = self.get_wanted_by_dedupe(dedupe_key)
        assert stored is not None
        return stored

    def delete_wanted(self, wanted_id: str) -> None:
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute("DELETE FROM wanted WHERE id = ?", (wanted_id,))

        self.run_write(_write, label="delete_wanted")

    def dismiss_wanted(self, wanted_id: str, *, now: float) -> Optional[Dict[str, Any]]:
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE wanted
                    SET status = 'dismissed', updated_at = ?
                    WHERE id = ? AND status != 'dismissed'
                    """,
                    (float(now), wanted_id),
                )

        self.run_write(_write, label="dismiss_wanted")
        return self.get_wanted(wanted_id)

    def dismiss_open_sweep_wanted(self, *, now: float) -> int:
        """Dismiss untouched sweep-seeded rows. Owner-added and asked slips stay."""

        def _write() -> Any:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    UPDATE wanted
                    SET status = 'dismissed', updated_at = ?
                    WHERE status = 'wanted'
                      AND IFNULL(job_id, '') = ''
                      AND (source = 'sweep' OR source IS NULL OR source = '')
                    """,
                    (float(now),),
                )
                return int(cur.rowcount or 0)

        return int(self.run_write(_write, label="dismiss_open_sweep_wanted") or 0)

    def restore_recent_sweep_wanted(self, *, now: float, since: float) -> int:
        """Reopen sweep rows dismissed on or after ``since``. Older rows stay dismissed."""

        def _write() -> Any:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    UPDATE wanted
                    SET status = 'wanted',
                        miss_streak = 0,
                        next_search_at = ?,
                        job_id = NULL,
                        updated_at = ?
                    WHERE status = 'dismissed'
                      AND updated_at >= ?
                      AND (source = 'sweep' OR source IS NULL OR source = '')
                    """,
                    (float(now), float(now), float(since)),
                )
                return int(cur.rowcount or 0)

        return int(self.run_write(_write, label="restore_recent_sweep_wanted") or 0)

    def count_restorable_sweep_wanted(self, *, since: float) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n FROM wanted
                WHERE status = 'dismissed'
                  AND updated_at >= ?
                  AND (source = 'sweep' OR source IS NULL OR source = '')
                """,
                (float(since),),
            ).fetchone()
        return int(row["n"] if row is not None else 0)

    def reopen_wanted(self, wanted_id: str, *, now: float, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE wanted
                    SET title = ?, author = ?, isbn = ?, status = 'wanted',
                        miss_streak = 0, next_search_at = ?, job_id = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        fields.get("title") or "",
                        fields.get("author") or "",
                        fields.get("isbn") or "",
                        float(now),
                        float(now),
                        wanted_id,
                    ),
                )

        self.run_write(_write, label="reopen_wanted")
        return self.get_wanted(wanted_id)

    def postpone_wanted(self, wanted_id: str, *, now: float, delay: float) -> None:
        """Push next_search_at without counting a miss. Only while still wanted."""

        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE wanted
                    SET next_search_at = ?, updated_at = ?
                    WHERE id = ? AND status = 'wanted'
                    """,
                    (float(now) + float(delay), float(now), wanted_id),
                )

        self.run_write(_write, label="postpone_wanted")

    def backoff_wanted(self, wanted_id: str, *, now: float, from_status: str) -> Optional[Dict[str, Any]]:
        """Compare-and-set a miss or a failed slip back onto the backoff clock."""
        from librarian.wanted import backoff_seconds

        def _write() -> Any:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM wanted WHERE id = ?", (wanted_id,)).fetchone()
                if row is None or row["status"] != from_status:
                    return None
                streak = int(row["miss_streak"] or 0) + 1
                nxt = float(now) + backoff_seconds(streak)
                cur = conn.execute(
                    """
                    UPDATE wanted
                    SET status = 'wanted',
                        job_id = NULL,
                        miss_streak = ?,
                        next_search_at = ?,
                        updated_at = ?
                    WHERE id = ? AND status = ?
                    """,
                    (streak, nxt, float(now), wanted_id, from_status),
                )
                if cur.rowcount != 1:
                    return None
                return wanted_id

        updated = self.run_write(_write, label="backoff_wanted")
        if not updated:
            return None
        return self.get_wanted(wanted_id)

    def claim_and_create_wanted_job(
        self,
        wanted_id: str,
        job: Dict[str, Any],
        *,
        now: float,
    ) -> Optional[Dict[str, Any]]:
        """Flip wanted → asked and insert one Asked job in a single write.

        A second caller loses the compare-and-set and inserts nothing.
        """
        job_id = str(job.get("id") or uuid.uuid4().hex)

        def _write() -> Any:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    UPDATE wanted
                    SET status = 'asked', updated_at = ?
                    WHERE id = ? AND status = 'wanted'
                    """,
                    (float(now), wanted_id),
                )
                if cur.rowcount != 1:
                    return None
                conn.execute(
                    """
                    INSERT INTO jobs (
                        id, work_id, nzo_id, status, indexer_guid, title, kind,
                        requested_by, storage_path, error, sab_status, nzo_name,
                        percent, bytes, payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        job.get("work_id"),
                        None,
                        "asked",
                        job.get("indexer_guid"),
                        job.get("title"),
                        job.get("kind"),
                        job.get("requested_by") or "wanted",
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        _dumps(job.get("payload") or {}),
                        float(now),
                        float(now),
                    ),
                )
                conn.execute(
                    "UPDATE wanted SET job_id = ? WHERE id = ?",
                    (job_id, wanted_id),
                )
                return job_id

        created = self.run_write(_write, label="claim_and_create_wanted_job")
        if not created:
            return None
        return self.get_job(job_id)

    def tried_indexer_guids_for_work(self, work: Mapping[str, Any], *, limit: int = 80) -> List[str]:
        """Failed + previously queued guids for a Review re-grab (exclude from ranking)."""
        guids: List[str] = []
        seen = set()

        def _add(value: object) -> None:
            text = str(value or "").strip()
            if text and text not in seen:
                seen.add(text)
                guids.append(text)

        _add(work.get("indexer_guid"))
        work_id = str(work.get("id") or "").strip()
        title = str(work.get("title") or "").strip()
        for job in self.list_jobs(limit=int(limit)):
            jg = job.get("indexer_guid")
            if not jg:
                continue
            if work_id and str(job.get("work_id") or "") == work_id:
                _add(jg)
                continue
            if title and str(job.get("title") or "").strip() == title:
                _add(jg)
        for bad in sorted(self.bad_indexer_guids()):
            _add(bad)
        return guids

    def get_open_wanted_by_work(self, work_id: str) -> Optional[Dict[str, Any]]:
        wid = str(work_id or "").strip()
        if not wid:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM wanted
                WHERE work_id = ? AND status != 'dismissed'
                ORDER BY updated_at DESC LIMIT 1
                """,
                (wid,),
            ).fetchone()
        return self._wanted_from_row(row)
