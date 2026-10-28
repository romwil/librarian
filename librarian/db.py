"""SQLite WAL catalog facade.

``Database`` composes the repository mixins in ``librarian.repositories`` (catalog,
jobs, wanted, people, shelves, review) and keeps connection handling, the writer
thread, and the smaller tables (indexers, RSS, notifications, whispers) here.
Schema lives in numbered steps under ``librarian.migrations``.
"""

from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, TypeVar

from librarian.db_write_serializer import WriteSerializer
from librarian.migrations import LATEST_VERSION as SCHEMA_VERSION
from librarian.migrations import apply_migrations
from librarian.migrations.m0001_baseline import SCHEMA
from librarian.repositories._base import (
    FAVORITES_SHELF,
    _dumps,
    _fts_column_query,
    _fts_query,
    _loads,
    _row_dict,
)
from librarian.repositories.catalog import (
    BROWSE_DEFAULT_SORT,
    BROWSE_EXPORT_ROW_CAP,
    BROWSE_PAGE_MAX_LIMIT,
    BROWSE_SORT_DEFAULT_DIR,
    BROWSE_SORTS,
    CatalogRepository,
    browse_order_sql,
    resolve_browse_sort,
)
from librarian.repositories.jobs import JobsRepository
from librarian.repositories.people import InviteConflict, PeopleRepository
from librarian.repositories.review import ReviewRepository, safe_release_guid
from librarian.repositories.shelves import ShelvesRepository
from librarian.repositories.wanted import WantedRepository, _wanted_source

SQLITE_BUSY_TIMEOUT_MS = 30000
SQLITE_LOCK_RETRIES = 6
SQLITE_LOCK_RETRY_BASE_DELAY_S = 0.05

logger = logging.getLogger("librarian.db")
T = TypeVar("T")

__all__ = [
    "BROWSE_DEFAULT_SORT",
    "BROWSE_EXPORT_ROW_CAP",
    "BROWSE_PAGE_MAX_LIMIT",
    "BROWSE_SORTS",
    "BROWSE_SORT_DEFAULT_DIR",
    "FAVORITES_SHELF",
    "SCHEMA",
    "SCHEMA_VERSION",
    "Database",
    "InviteConflict",
    "browse_order_sql",
    "resolve_browse_sort",
    "run_with_db_lock_retry",
    "safe_release_guid",
    "_dumps",
    "_fts_column_query",
    "_fts_query",
    "_loads",
    "_row_dict",
    "_wanted_source",
]


def _is_db_locked(exc: BaseException) -> bool:
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    message = str(exc).lower()
    return "locked" in message or "busy" in message


def run_with_db_lock_retry(operation: Callable[[], T], *, label: str = "db") -> T:
    """Retry transient SQLite lock/busy errors with exponential backoff."""
    delay = SQLITE_LOCK_RETRY_BASE_DELAY_S
    last_exc: Optional[BaseException] = None
    for attempt in range(SQLITE_LOCK_RETRIES):
        try:
            return operation()
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if not _is_db_locked(exc) or attempt >= SQLITE_LOCK_RETRIES - 1:
                raise
            logger.warning(
                "SQLite %s locked (attempt %s/%s); retrying in %.2fs: %s",
                label,
                attempt + 1,
                SQLITE_LOCK_RETRIES,
                delay,
                exc,
            )
            time.sleep(delay)
            delay = min(delay * 2, 1.5)
    assert last_exc is not None
    raise last_exc


class Database(
    PeopleRepository,
    CatalogRepository,
    JobsRepository,
    WantedRepository,
    ShelvesRepository,
    ReviewRepository,
):
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_serializer = WriteSerializer()
        try:
            with self._connect() as conn:
                self.schema_version = apply_migrations(conn)
        except Exception:
            self._write_serializer.shutdown(timeout=5.0)
            raise

    def run_write(self, operation: Callable[[], T], *, label: str = "write") -> T:
        """Run a mutating callable on the dedicated writer thread."""
        return self._write_serializer.run(
            lambda: run_with_db_lock_retry(operation, label=label),
            label=label,
        )

    def try_run_write(self, operation: Callable[[], T], *, label: str = "write") -> bool:
        """Like ``run_write`` but drop the job when the serializer queue is full."""
        return self._write_serializer.try_run(
            lambda: run_with_db_lock_retry(operation, label=label),
            label=label,
        )

    def write_queue_stats(self) -> dict:
        return self._write_serializer.stats()

    def close(self) -> None:
        serializer = getattr(self, "_write_serializer", None)
        if serializer is not None:
            serializer.shutdown()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def pragmas(self) -> Dict[str, Any]:
        with self._connect() as conn:
            journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
            busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            sync = conn.execute("PRAGMA synchronous").fetchone()[0]
        return {"journal_mode": str(journal).lower(), "busy_timeout": int(busy), "synchronous": int(sync)}

    def upsert_indexer(self, indexer: Dict[str, Any]) -> Dict[str, Any]:
        now = time.time()
        indexer_id = str(indexer.get("id") or "nzbfinder")
        payload = {
            "id": indexer_id,
            "name": indexer.get("name") or "NZBFinder",
            "kind": indexer.get("kind") or "nzbfinder",
            "base_url": indexer.get("base_url") or "",
            "token_set": 1 if indexer.get("token_set") else 0,
            "last_caps_at": indexer.get("last_caps_at"),
            "last_caps_ok": indexer.get("last_caps_ok"),
            "created_at": indexer.get("created_at") or now,
            "updated_at": now,
        }
        def _write() -> Any:
            with self._connect() as conn:
                existing = conn.execute("SELECT id FROM indexers WHERE id = ?", (indexer_id,)).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE indexers SET
                            name=?, kind=?, base_url=?, token_set=?, last_caps_at=?,
                            last_caps_ok=?, updated_at=?
                        WHERE id=?
                        """,
                        (
                            payload["name"],
                            payload["kind"],
                            payload["base_url"],
                            payload["token_set"],
                            payload["last_caps_at"],
                            payload["last_caps_ok"],
                            payload["updated_at"],
                            indexer_id,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO indexers (
                            id, name, kind, base_url, token_set, last_caps_at,
                            last_caps_ok, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        tuple(payload.values()),
                    )
        self.run_write(_write, label='upsert_indexer')
        row = self.get_indexer(indexer_id)
        assert row is not None
        return row

    def get_indexer(self, indexer_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM indexers WHERE id = ?", (indexer_id,)).fetchone()
        return _row_dict(row)

    def list_indexers(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM indexers ORDER BY name").fetchall()
        return [_row_dict(row) or {} for row in rows]

    def list_rss_feeds(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM rss_feeds ORDER BY created_at").fetchall()
        return [_row_dict(row) or {} for row in rows]

    def get_rss_feed(self, feed_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM rss_feeds WHERE id = ?", (feed_id,)).fetchone()
        return _row_dict(row)

    def upsert_rss_feed(self, feed: Dict[str, Any]) -> Dict[str, Any]:
        now = time.time()
        feed_id = str(feed.get("id") or uuid.uuid4().hex)
        payload = {
            "id": feed_id,
            "name": str(feed.get("name") or "RSS").strip() or "RSS",
            "url": str(feed.get("url") or "").strip(),
            "kind": str(feed.get("kind") or "book").strip() or "book",
            "enabled": 1 if feed.get("enabled", True) else 0,
            "last_guid": feed.get("last_guid"),
            "last_error": feed.get("last_error"),
            "last_poll_at": feed.get("last_poll_at"),
            "created_at": feed.get("created_at") or now,
            "updated_at": now,
        }
        def _write() -> Any:
            with self._connect() as conn:
                existing = conn.execute(
                    "SELECT last_guid, last_error, last_poll_at FROM rss_feeds WHERE id = ?",
                    (feed_id,),
                ).fetchone()
                if existing:
                    if "last_guid" not in feed:
                        payload["last_guid"] = existing["last_guid"]
                    if "last_error" not in feed:
                        payload["last_error"] = existing["last_error"]
                    if "last_poll_at" not in feed:
                        payload["last_poll_at"] = existing["last_poll_at"]
                    conn.execute(
                        """
                        UPDATE rss_feeds SET
                            name=?, url=?, kind=?, enabled=?, last_guid=?, last_error=?,
                            last_poll_at=?, updated_at=?
                        WHERE id=?
                        """,
                        (
                            payload["name"],
                            payload["url"],
                            payload["kind"],
                            payload["enabled"],
                            payload["last_guid"],
                            payload["last_error"],
                            payload["last_poll_at"],
                            payload["updated_at"],
                            feed_id,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO rss_feeds (
                            id, name, url, kind, enabled, last_guid, last_error,
                            last_poll_at, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        tuple(payload.values()),
                    )
        self.run_write(_write, label='upsert_rss_feed')
        row = self.get_rss_feed(feed_id)
        assert row is not None
        return row

    def delete_rss_feed(self, feed_id: str) -> None:
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute("DELETE FROM rss_feeds WHERE id = ?", (feed_id,))
        self.run_write(_write, label='delete_rss_feed')

    def create_notification(
        self,
        *,
        notification_id: str,
        user_id: str,
        kind: str,
        title: str,
        body: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        from_user_id: Optional[str] = None,
        related_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        from librarian.notifications.kinds import NOTIFICATION_KIND_SET

        cleaned_kind = str(kind or "").strip().lower()
        if cleaned_kind not in NOTIFICATION_KIND_SET:
            raise ValueError(f"Unsupported notification kind: {kind}")
        now = time.time()
        payload_json = _dumps(payload or {})

        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO user_notifications (
                        id, user_id, kind, title, body, payload_json,
                        from_user_id, related_id, created_at, seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        notification_id,
                        user_id,
                        cleaned_kind,
                        str(title or "").strip() or "Notification",
                        (str(body).strip() if body else None) or None,
                        payload_json,
                        from_user_id,
                        related_id,
                        now,
                    ),
                )

        self.run_write(_write, label="create_notification")
        rows = self.list_notifications_for_user(user_id, limit=1)
        for row in rows:
            if row.get("id") == notification_id:
                return row
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM user_notifications WHERE id = ?",
                (notification_id,),
            ).fetchone()
        assert row is not None
        return self._row_to_notification(row)

    def list_notifications_for_user(
        self,
        user_id: str,
        *,
        unread_only: bool = False,
        kinds: Optional[Sequence[str]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        from librarian.notifications.kinds import NOTIFICATION_KIND_SET

        query = """
            SELECT n.*,
                   fu.display_name AS from_display_name
            FROM user_notifications n
            LEFT JOIN users fu ON fu.id = n.from_user_id
            WHERE n.user_id = ?
        """
        params: List[Any] = [user_id]
        if unread_only:
            query += " AND n.seen_at IS NULL"
        cleaned_kinds = [
            str(k).strip().lower()
            for k in (kinds or [])
            if str(k).strip().lower() in NOTIFICATION_KIND_SET
        ]
        if cleaned_kinds:
            placeholders = ",".join("?" for _ in cleaned_kinds)
            query += f" AND n.kind IN ({placeholders})"
            params.extend(cleaned_kinds)
        query += " ORDER BY n.created_at DESC LIMIT ?"
        params.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_notification(row) for row in rows]

    def count_unread_notifications(self, user_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM user_notifications
                WHERE user_id = ? AND seen_at IS NULL
                """,
                (user_id,),
            ).fetchone()
        return int(row["cnt"] if row else 0)

    def mark_notifications_seen(
        self,
        user_id: str,
        *,
        notification_ids: Optional[Sequence[str]] = None,
        all_unread: bool = False,
    ) -> int:
        now = time.time()

        def _write() -> int:
            with self._connect() as conn:
                if all_unread:
                    cursor = conn.execute(
                        """
                        UPDATE user_notifications
                        SET seen_at = ?
                        WHERE user_id = ? AND seen_at IS NULL
                        """,
                        (now, user_id),
                    )
                    return int(cursor.rowcount or 0)
                ids = [str(i).strip() for i in (notification_ids or []) if str(i).strip()]
                if not ids:
                    return 0
                placeholders = ",".join("?" for _ in ids)
                cursor = conn.execute(
                    f"""
                    UPDATE user_notifications
                    SET seen_at = ?
                    WHERE user_id = ? AND seen_at IS NULL AND id IN ({placeholders})
                    """,
                    (now, user_id, *ids),
                )
                return int(cursor.rowcount or 0)

        return int(self.run_write(_write, label="mark_notifications_seen") or 0)

    def enqueue_notification_digest(
        self,
        *,
        digest_id: str,
        user_id: str,
        kind: str,
        title: str,
        body: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        related_id: Optional[str] = None,
        period: str = "daily",
    ) -> Dict[str, Any]:
        now = time.time()
        payload_json = _dumps(payload or {})

        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO notification_digest_queue (
                        id, user_id, kind, title, body, payload_json,
                        related_id, period, created_at, sent_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        digest_id,
                        user_id,
                        str(kind or "").strip().lower(),
                        str(title or "").strip() or "Notification",
                        (str(body).strip() if body else None) or None,
                        payload_json,
                        related_id,
                        str(period or "daily").strip().lower(),
                        now,
                    ),
                )

        self.run_write(_write, label="enqueue_notification_digest")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM notification_digest_queue WHERE id = ?",
                (digest_id,),
            ).fetchone()
        assert row is not None
        return self._row_to_digest(row)

    def list_pending_notification_digests(self, *, period: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM notification_digest_queue
                WHERE period = ? AND sent_at IS NULL
                ORDER BY created_at ASC
                """,
                (str(period or "").strip().lower(),),
            ).fetchall()
        return [self._row_to_digest(row) for row in rows]

    def mark_notification_digests_sent(self, digest_ids: Sequence[str]) -> int:
        ids = [str(i).strip() for i in digest_ids if str(i).strip()]
        if not ids:
            return 0
        now = time.time()

        def _write() -> int:
            with self._connect() as conn:
                placeholders = ",".join("?" for _ in ids)
                cursor = conn.execute(
                    f"""
                    UPDATE notification_digest_queue
                    SET sent_at = ?
                    WHERE sent_at IS NULL AND id IN ({placeholders})
                    """,
                    (now, *ids),
                )
                return int(cursor.rowcount or 0)

        return int(self.run_write(_write, label="mark_notification_digests_sent") or 0)

    @staticmethod
    def _row_to_notification(row: sqlite3.Row) -> Dict[str, Any]:
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        payload: Dict[str, Any] = {}
        raw_payload = row["payload_json"] if "payload_json" in keys else None
        if raw_payload:
            parsed = _loads(raw_payload, default={})
            if isinstance(parsed, dict):
                payload = parsed
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "kind": str(row["kind"]),
            "title": str(row["title"]),
            "body": str(row["body"]) if row["body"] is not None else None,
            "payload": payload,
            "from_user_id": str(row["from_user_id"]) if row["from_user_id"] is not None else None,
            "related_id": str(row["related_id"]) if row["related_id"] is not None else None,
            "created_at": float(row["created_at"]),
            "seen_at": float(row["seen_at"]) if row["seen_at"] is not None else None,
            "from_display_name": (
                str(row["from_display_name"])
                if "from_display_name" in keys and row["from_display_name"] is not None
                else None
            ),
            "message": str(row["body"]) if row["body"] is not None else None,
        }

    @staticmethod
    def _row_to_digest(row: sqlite3.Row) -> Dict[str, Any]:
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        payload: Dict[str, Any] = {}
        raw_payload = row["payload_json"] if "payload_json" in keys else None
        if raw_payload:
            parsed = _loads(raw_payload, default={})
            if isinstance(parsed, dict):
                payload = parsed
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "kind": str(row["kind"]),
            "title": str(row["title"]),
            "body": str(row["body"]) if row["body"] is not None else None,
            "payload": payload,
            "related_id": str(row["related_id"]) if row["related_id"] is not None else None,
            "period": str(row["period"]),
            "created_at": float(row["created_at"]),
            "sent_at": float(row["sent_at"]) if row["sent_at"] is not None else None,
        }

    def list_whispers(self, work_id: str, *, limit: int = 40) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT w.*, u.display_name AS author_name
                FROM whispers w
                LEFT JOIN users u ON u.id = w.user_id
                WHERE w.work_id = ?
                ORDER BY w.created_at DESC
                LIMIT ?
                """,
                (work_id, int(limit)),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def add_whisper(self, *, work_id: str, user_id: str, body: str) -> Dict[str, Any]:
        whisper_id = uuid.uuid4().hex
        now = time.time()
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO whispers (id, work_id, user_id, body, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (whisper_id, work_id, user_id, body, now),
                )
        self.run_write(_write, label='add_whisper')
        rows = self.list_whispers(work_id, limit=1)
        return rows[0] if rows else {"id": whisper_id, "work_id": work_id, "user_id": user_id, "body": body, "created_at": now}

    def unseen_celebrations(self, user_id: str, candidates: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
        if not candidates:
            return []
        keys = [str(row.get("key") or "") for row in candidates if row.get("key")]
        with self._connect() as conn:
            seen = {
                row[0]
                for row in conn.execute(
                    f"SELECT celebration_key FROM celebrations_seen WHERE user_id = ? AND celebration_key IN ({','.join('?' for _ in keys)})",
                    (user_id, *keys),
                ).fetchall()
            }
        return [row for row in candidates if str(row.get("key") or "") not in seen]

    def mark_celebration_seen(self, user_id: str, celebration_key: str) -> None:
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO celebrations_seen (user_id, celebration_key, seen_at)
                    VALUES (?, ?, ?)
                    """,
                    (user_id, celebration_key, time.time()),
                )
        self.run_write(_write, label='mark_celebration_seen')
