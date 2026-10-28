"""Download jobs (SAB queue rows) and their timing history."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Iterable, List, Optional

from librarian.repositories._base import (
    RepositoryBase,
    _dumps,
    _loads,
    _row_dict,
)


class JobsRepository(RepositoryBase):
    def list_completed_jobs_for_user(
        self,
        user_id: str,
        *,
        limit: int = 12,
    ) -> List[Dict[str, Any]]:
        """Recent completed download jobs requested by this member (taste signal)."""
        uid = str(user_id or "").strip()
        if not uid:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM jobs
                WHERE requested_by = ? AND status = 'completed'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (uid, max(1, int(limit))),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def create_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        now = time.time()
        job_id = str(job.get("id") or uuid.uuid4().hex)
        def _write() -> Any:
            with self._connect() as conn:
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
                        job.get("nzo_id"),
                        job["status"],
                        job.get("indexer_guid"),
                        job.get("title"),
                        job.get("kind"),
                        job.get("requested_by"),
                        job.get("storage_path"),
                        job.get("error"),
                        job.get("sab_status"),
                        job.get("nzo_name"),
                        job.get("percent"),
                        job.get("bytes"),
                        _dumps(job.get("payload") or {}),
                        now,
                        now,
                    ),
                )
        self.run_write(_write, label='create_job')
        row = self.get_job(job_id)
        assert row is not None
        return row

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        data = _row_dict(row)
        if data is not None:
            data["payload"] = _loads(data.pop("payload_json", None), {})
        return data

    def get_job_by_nzo(self, nzo_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE nzo_id = ?", (nzo_id,)).fetchone()
        data = _row_dict(row)
        if data is not None:
            data["payload"] = _loads(data.pop("payload_json", None), {})
        return data

    def get_job_by_indexer_guid(self, guid: str) -> Optional[Dict[str, Any]]:
        text = str(guid or "").strip()
        if not text:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM jobs
                WHERE indexer_guid = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (text,),
            ).fetchone()
        data = _row_dict(row)
        if data is not None:
            data["payload"] = _loads(data.pop("payload_json", None), {})
        return data

    def update_job(self, job_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        allowed = {
            "work_id",
            "nzo_id",
            "status",
            "storage_path",
            "error",
            "title",
            "kind",
            "sab_status",
            "nzo_name",
            "percent",
            "bytes",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if "payload" in fields:
            updates["payload_json"] = _dumps(fields["payload"])
        if not updates:
            return self.get_job(job_id)
        updates["updated_at"] = time.time()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    f"UPDATE jobs SET {assignments} WHERE id = ?",
                    (*updates.values(), job_id),
                )
        self.run_write(_write, label='update_job')
        return self.get_job(job_id)

    def get_job_by_storage_path(self, path: str) -> Optional[Dict[str, Any]]:
        text = str(path or "").rstrip("/")
        if not text:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM jobs
                WHERE storage_path = ? OR storage_path = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (text, text + "/"),
            ).fetchone()
        data = _row_dict(row)
        if data is not None:
            data["payload"] = _loads(data.pop("payload_json", None), {})
        return data

    def list_jobs(self, *, statuses: Optional[Iterable[str]] = None, limit: int = 80) -> List[Dict[str, Any]]:
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            sql = f"SELECT * FROM jobs WHERE status IN ({placeholders}) ORDER BY updated_at DESC LIMIT ?"
            args: List[Any] = [*statuses, int(limit)]
        else:
            sql = "SELECT * FROM jobs ORDER BY updated_at DESC LIMIT ?"
            args = [int(limit)]
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        out = []
        for row in rows:
            data = _row_dict(row) or {}
            data["payload"] = _loads(data.pop("payload_json", None), {})
            out.append(data)
        return out

    def recent_job_durations(
        self,
        *,
        limit: int = 12,
        kind: Optional[str] = None,
        multipart: Optional[bool] = None,
    ) -> List[float]:
        """Seconds between created_at and updated_at for finished downloads.

        Prefers real terminal statuses (``organized`` / ``review``). When ``kind``
        is set, only that kind is sampled. When ``multipart`` is True, keep jobs
        whose title (or selected payload title) carries a part marker.
        """
        from librarian.parts import parse_part_marker

        kind_key = str(kind or "").strip() or None
        fetch_limit = int(limit)
        if kind_key or multipart is not None:
            fetch_limit = max(fetch_limit * 4, 48)
        with self._connect() as conn:
            if kind_key:
                rows = conn.execute(
                    """
                    SELECT created_at, updated_at, title, payload_json FROM jobs
                    WHERE status IN ('organized', 'review')
                      AND updated_at > created_at
                      AND kind = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (kind_key, fetch_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT created_at, updated_at, title, payload_json FROM jobs
                    WHERE status IN ('organized', 'review')
                      AND updated_at > created_at
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (fetch_limit,),
                ).fetchall()
        out: List[float] = []
        for row in rows:
            if multipart is not None:
                title = str(row["title"] or "")
                payload = _loads(row["payload_json"], {})
                selected = payload.get("selected") if isinstance(payload, dict) else {}
                sel_title = ""
                if isinstance(selected, dict):
                    sel_title = str(selected.get("title") or selected.get("name") or "")
                has_part = bool(parse_part_marker(title) or parse_part_marker(sel_title))
                if multipart and not has_part:
                    continue
                if multipart is False and has_part:
                    continue
            try:
                delta = float(row["updated_at"]) - float(row["created_at"])
            except (TypeError, ValueError):
                continue
            if delta > 0:
                out.append(delta)
            if len(out) >= int(limit):
                break
        return out

    def jobs_for_work(self, work_id: str) -> List[Dict[str, Any]]:
        wid = str(work_id or "").strip()
        if not wid:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE work_id = ? ORDER BY updated_at DESC",
                (wid,),
            ).fetchall()
        out = []
        for row in rows:
            data = _row_dict(row) or {}
            data["payload"] = _loads(data.pop("payload_json", None), {})
            out.append(data)
        return out
