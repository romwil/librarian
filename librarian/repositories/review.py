"""Holds desk: bad releases, review audit, suggestions, cooldowns, one-time migrations."""

from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Any, Dict, List, Mapping, Optional, Sequence

from librarian.repositories._base import (
    RepositoryBase,
    _dumps,
    _loads,
    _row_dict,
)


def safe_release_guid(value: Any) -> str:
    """Newznab release id only. Strip URL query/fragment so no credential is ever stored."""
    text = str(value or "").strip()
    if not text:
        return ""
    if "://" not in text and "?" not in text and "&" not in text:
        return text[:200]
    from urllib.parse import urlsplit

    parts = urlsplit(text if "://" in text else f"x://h/{text}")
    path = parts.path.rstrip("/")
    tail = path.rsplit("/", 1)[-1] if path else ""
    if tail.endswith(".nzb"):
        tail = tail[: -len(".nzb")]
    if tail and tail.lower() not in {"getnzb", "api", "details", "nzb"}:
        return tail[:200]
    from urllib.parse import parse_qs

    query = parse_qs(parts.query)
    for key in ("guid", "id"):
        values = query.get(key) or []
        if values and values[0].strip():
            return values[0].strip()[:200]
    return ""


class ReviewRepository(RepositoryBase):
    def bad_indexer_guids(self, *, limit: int = 2000) -> set:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT guid FROM bad_indexer_releases ORDER BY last_seen_at DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return {str(row["guid"]) for row in rows if row["guid"]}

    def list_bad_indexer_releases(self, *, limit: int = 200) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM bad_indexer_releases ORDER BY last_seen_at DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    @staticmethod
    def _upsert_bad_release(
        conn: sqlite3.Connection,
        *,
        host_id: str,
        guid: str,
        wanted_id: Optional[str],
        reason: str,
        now: float,
    ) -> None:
        conn.execute(
            """
            INSERT INTO bad_indexer_releases (
                host_id, guid, wanted_id, reason, first_seen_at, last_seen_at, seen_count
            ) VALUES (?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(host_id, guid) DO UPDATE SET
                wanted_id = coalesce(excluded.wanted_id, bad_indexer_releases.wanted_id),
                reason = excluded.reason,
                last_seen_at = excluded.last_seen_at,
                seen_count = bad_indexer_releases.seen_count + 1
            """,
            (host_id, guid, wanted_id, reason, now, now),
        )

    @staticmethod
    def _insert_audit(
        conn: sqlite3.Connection,
        *,
        action: str,
        now: float,
        work_id: Optional[str] = None,
        wanted_id: Optional[str] = None,
        job_id: Optional[str] = None,
        guid: Optional[str] = None,
        reason: Optional[str] = None,
        detail: Optional[Mapping[str, Any]] = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO review_audit (
                id, action, work_id, wanted_id, job_id, guid, reason, detail_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                action,
                work_id,
                wanted_id,
                job_id,
                guid,
                reason,
                _dumps(dict(detail or {})),
                now,
            ),
        )

    @staticmethod
    def _delete_slip_rows(conn: sqlite3.Connection, work_id: str) -> None:
        conn.execute("DELETE FROM files WHERE work_id = ?", (work_id,))
        conn.execute("DELETE FROM shelf_items WHERE work_id = ?", (work_id,))
        conn.execute("DELETE FROM progress WHERE work_id = ?", (work_id,))
        conn.execute("DELETE FROM whispers WHERE work_id = ?", (work_id,))
        conn.execute("DELETE FROM jobs WHERE work_id = ?", (work_id,))
        conn.execute("DELETE FROM review_suggestions WHERE work_id = ?", (work_id,))
        conn.execute("DELETE FROM review_diagnosis WHERE work_id = ?", (work_id,))
        conn.execute("DELETE FROM works WHERE id = ?", (work_id,))

    def record_bad_indexer_release(
        self,
        *,
        host_id: str,
        guid: str,
        reason: str,
        wanted_id: Optional[str] = None,
        now: Optional[float] = None,
    ) -> None:
        clean = safe_release_guid(guid)
        if not clean:
            return
        moment = time.time() if now is None else float(now)

        def _write() -> Any:
            with self._connect() as conn:
                self._upsert_bad_release(
                    conn,
                    host_id=str(host_id or ""),
                    guid=clean,
                    wanted_id=wanted_id,
                    reason=reason,
                    now=moment,
                )

        self.run_write(_write, label="record_bad_indexer_release")

    def apply_bad_release(
        self,
        *,
        host_id: str,
        guid: str,
        wanted_id: str,
        reason: str,
        job_id: Optional[str] = None,
        work_id: Optional[str] = None,
        remove_slip: bool = False,
        now: Optional[float] = None,
        detail: Optional[Mapping[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Mark a release bad and put its Wanted row back on the normal retry clock.

        One write: bad release row, Wanted backoff (``job_id`` cleared), optional slip
        removal, and an audit event. Returns the updated Wanted row, or None when the
        Wanted row is gone or dismissed.
        """
        from librarian.wanted import backoff_seconds

        clean = safe_release_guid(guid)
        moment = time.time() if now is None else float(now)

        def _write() -> Any:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM wanted WHERE id = ?", (wanted_id,)).fetchone()
                if row is None or row["status"] == "dismissed" or not clean:
                    return None
                self._upsert_bad_release(
                    conn,
                    host_id=str(host_id or ""),
                    guid=clean,
                    wanted_id=wanted_id,
                    reason=reason,
                    now=moment,
                )
                streak = int(row["miss_streak"] or 0) + 1
                conn.execute(
                    """
                    UPDATE wanted
                    SET status = 'wanted', job_id = NULL, miss_streak = ?,
                        next_search_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (streak, moment + backoff_seconds(streak), moment, wanted_id),
                )
                if remove_slip and work_id:
                    self._delete_slip_rows(conn, str(work_id))
                if remove_slip and job_id:
                    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
                self._insert_audit(
                    conn,
                    action="release_bad_wanted",
                    now=moment,
                    work_id=work_id,
                    wanted_id=wanted_id,
                    job_id=job_id,
                    guid=clean,
                    reason=reason,
                    detail=detail,
                )
                return wanted_id

        released = self.run_write(_write, label="apply_bad_release")
        if not released:
            return None
        return self.get_wanted(wanted_id)

    def record_review_audit(
        self,
        action: str,
        *,
        work_id: Optional[str] = None,
        wanted_id: Optional[str] = None,
        job_id: Optional[str] = None,
        guid: Optional[str] = None,
        reason: Optional[str] = None,
        detail: Optional[Mapping[str, Any]] = None,
        now: Optional[float] = None,
    ) -> None:
        moment = time.time() if now is None else float(now)

        def _write() -> Any:
            with self._connect() as conn:
                self._insert_audit(
                    conn,
                    action=action,
                    now=moment,
                    work_id=work_id,
                    wanted_id=wanted_id,
                    job_id=job_id,
                    guid=safe_release_guid(guid or "") or None,
                    reason=reason,
                    detail=detail,
                )

        self.run_write(_write, label="record_review_audit")

    def list_review_audit(self, *, action: str = "", limit: int = 200) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM review_audit"
        args: List[Any] = []
        if action:
            sql += " WHERE action = ?"
            args.append(action)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(max(1, int(limit)))
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        out = []
        for row in rows:
            data = _row_dict(row) or {}
            data["detail"] = _loads(data.pop("detail_json", None), {})
            out.append(data)
        return out

    def review_audit_work_ids(self, action: str) -> set:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT work_id FROM review_audit WHERE action = ? AND work_id IS NOT NULL",
                (action,),
            ).fetchall()
        return {str(row["work_id"]) for row in rows}

    def discard_review_slip(
        self,
        work_id: str,
        *,
        dismiss_wanted_ids: Sequence[str] = (),
        job_ids: Sequence[str] = (),
        now: Optional[float] = None,
        detail: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        """Owner discard: slip, catalog rows, its jobs, and its Wanted requests. No disk deletes."""
        wid = str(work_id or "").strip()
        if not wid:
            return False
        moment = time.time() if now is None else float(now)

        def _write() -> Any:
            with self._connect() as conn:
                row = conn.execute("SELECT id FROM works WHERE id = ?", (wid,)).fetchone()
                if row is None:
                    return False
                for wanted_id in dismiss_wanted_ids:
                    conn.execute(
                        """
                        UPDATE wanted SET status = 'dismissed', job_id = NULL, updated_at = ?
                        WHERE id = ? AND status != 'dismissed'
                        """,
                        (moment, wanted_id),
                    )
                for job_id in job_ids:
                    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
                self._delete_slip_rows(conn, wid)
                self._insert_audit(
                    conn,
                    action="delete_slip",
                    now=moment,
                    work_id=wid,
                    detail={
                        **dict(detail or {}),
                        "wanted_dismissed": list(dismiss_wanted_ids),
                        "jobs_removed": list(job_ids),
                    },
                )
                return True

        return bool(self.run_write(_write, label="discard_review_slip"))

    def set_review_reason(self, work_id: str, reason: Optional[str]) -> None:
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE works SET review_reason = ?, updated_at = ? WHERE id = ?",
                    (reason, time.time(), work_id),
                )

        self.run_write(_write, label="set_review_reason")

    def set_review_suggestion(
        self,
        work_id: str,
        *,
        outcome: str,
        suggestion: Optional[Mapping[str, Any]] = None,
        explanation: str = "",
        now: Optional[float] = None,
    ) -> None:
        moment = time.time() if now is None else float(now)

        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO review_suggestions (work_id, outcome, suggestion_json, explanation, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(work_id) DO UPDATE SET
                        outcome = excluded.outcome,
                        suggestion_json = excluded.suggestion_json,
                        explanation = excluded.explanation,
                        updated_at = excluded.updated_at
                    """,
                    (
                        work_id,
                        outcome,
                        _dumps(dict(suggestion)) if suggestion else None,
                        explanation or "",
                        moment,
                    ),
                )

        self.run_write(_write, label="set_review_suggestion")

    def get_review_suggestions(self, work_ids: Optional[Sequence[str]] = None) -> Dict[str, Dict[str, Any]]:
        with self._connect() as conn:
            if work_ids is None:
                rows = conn.execute("SELECT * FROM review_suggestions").fetchall()
            else:
                ids = [str(w) for w in work_ids if str(w or "").strip()]
                if not ids:
                    return {}
                placeholders = ",".join("?" for _ in ids)
                rows = conn.execute(
                    f"SELECT * FROM review_suggestions WHERE work_id IN ({placeholders})",
                    ids,
                ).fetchall()
        out: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            data = _row_dict(row) or {}
            data["suggestion"] = _loads(data.pop("suggestion_json", None), None)
            out[str(data["work_id"])] = data
        return out

    def delete_review_suggestion(self, work_id: str) -> None:
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute("DELETE FROM review_suggestions WHERE work_id = ?", (work_id,))

        self.run_write(_write, label="delete_review_suggestion")

    def set_slip_cooldown(
        self,
        folder_key: str,
        *,
        signature: str,
        reason: str,
        until: float,
        now: Optional[float] = None,
    ) -> None:
        moment = time.time() if now is None else float(now)

        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO review_slip_cooldowns (folder_key, signature, reason, until_at, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(folder_key) DO UPDATE SET
                        signature = excluded.signature,
                        reason = excluded.reason,
                        until_at = excluded.until_at,
                        created_at = excluded.created_at
                    """,
                    (folder_key, signature, reason, float(until), moment),
                )

        self.run_write(_write, label="set_slip_cooldown")

    def get_slip_cooldown(self, folder_key: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM review_slip_cooldowns WHERE folder_key = ?",
                (folder_key,),
            ).fetchone()
        return _row_dict(row)

    def get_migration(self, name: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM app_migrations WHERE name = ?", (name,)).fetchone()
        data = _row_dict(row)
        if data is not None:
            data["report"] = _loads(data.pop("report_json", None), {})
        return data

    def mark_migration(self, name: str, report: Mapping[str, Any], *, now: Optional[float] = None) -> None:
        moment = time.time() if now is None else float(now)

        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO app_migrations (name, finished_at, report_json) VALUES (?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        finished_at = excluded.finished_at,
                        report_json = excluded.report_json
                    """,
                    (name, moment, _dumps(dict(report))),
                )

        self.run_write(_write, label="mark_migration")

    def upsert_review_diagnosis(
        self,
        work_id: str,
        *,
        folder_path: str = "",
        diagnosis: Mapping[str, Any],
        now: Optional[float] = None,
    ) -> None:
        moment = time.time() if now is None else float(now)
        shaped = dict(diagnosis or {})

        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO review_diagnosis (
                        work_id, problem, path_clear, collection_dump, payload_count,
                        archive_count, junk_count, par2_count, distinct_title_count,
                        folder_path, diagnosis_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(work_id) DO UPDATE SET
                        problem = excluded.problem,
                        path_clear = excluded.path_clear,
                        collection_dump = excluded.collection_dump,
                        payload_count = excluded.payload_count,
                        archive_count = excluded.archive_count,
                        junk_count = excluded.junk_count,
                        par2_count = excluded.par2_count,
                        distinct_title_count = excluded.distinct_title_count,
                        folder_path = excluded.folder_path,
                        diagnosis_json = excluded.diagnosis_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        work_id,
                        str(shaped.get("problem") or ""),
                        1 if shaped.get("path_clear") else 0,
                        1 if shaped.get("collection_dump") else 0,
                        int(shaped.get("payload_count") or 0),
                        int(shaped.get("archive_count") or 0),
                        int(shaped.get("junk_count") or 0),
                        int(shaped.get("par2_count") or 0),
                        int(shaped.get("distinct_title_count") or 0),
                        str(folder_path or ""),
                        _dumps(shaped),
                        moment,
                    ),
                )

        self.run_write(_write, label="upsert_review_diagnosis")

    def get_review_diagnoses(self, work_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        ids = [str(w) for w in work_ids if str(w or "").strip()]
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM review_diagnosis WHERE work_id IN ({placeholders})",
                ids,
            ).fetchall()
        out: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            data = _row_dict(row) or {}
            data["diagnosis"] = _loads(data.get("diagnosis_json"), {})
            out[str(data["work_id"])] = data
        return out

    def delete_review_diagnosis(self, work_id: str) -> None:
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute("DELETE FROM review_diagnosis WHERE work_id = ?", (work_id,))

        self.run_write(_write, label="delete_review_diagnosis")
