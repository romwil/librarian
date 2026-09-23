"""SQLite WAL catalog: users, invites, works, files, jobs, shelves."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, TypeVar

from librarian.db_write_serializer import WriteSerializer

SQLITE_BUSY_TIMEOUT_MS = 30000
SQLITE_LOCK_RETRIES = 6
SQLITE_LOCK_RETRY_BASE_DELAY_S = 0.05
FAVORITES_SHELF = "Favorites"

logger = logging.getLogger("librarian.db")
T = TypeVar("T")


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

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at REAL NOT NULL,
    last_login_at REAL,
    session_epoch INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS invites (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    created_by TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    expires_at REAL NOT NULL,
    redeemed_at REAL,
    redeemed_user_id TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS works (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    author TEXT,
    series_name TEXT,
    series_index TEXT,
    year INTEGER,
    isbn TEXT,
    mbid TEXT,
    description TEXT,
    publisher TEXT,
    genre TEXT,
    cover_path TEXT,
    folder_path TEXT,
    abs_item_id TEXT,
    synopsis_source TEXT,
    llm_blurb TEXT,
    atmosphere_path TEXT,
    art_attribution TEXT,
    review_state TEXT NOT NULL DEFAULT 'none',
    review_reason TEXT,
    music_state TEXT,
    indexer_guid TEXT,
    part_total INTEGER,
    part_style TEXT,
    part_base TEXT,
    part_origin INTEGER,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    work_id TEXT,
    path TEXT NOT NULL,
    filename TEXT NOT NULL,
    kind TEXT,
    size INTEGER,
    part INTEGER,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    work_id TEXT,
    nzo_id TEXT,
    status TEXT NOT NULL,
    indexer_guid TEXT,
    title TEXT,
    kind TEXT,
    requested_by TEXT,
    storage_path TEXT,
    error TEXT,
    sab_status TEXT,
    nzo_name TEXT,
    percent TEXT,
    bytes INTEGER,
    payload_json TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS shelves (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(name, owner_user_id)
);
CREATE TABLE IF NOT EXISTS shelf_items (
    shelf_id TEXT NOT NULL,
    work_id TEXT NOT NULL,
    added_at REAL NOT NULL,
    PRIMARY KEY (shelf_id, work_id)
);
CREATE TABLE IF NOT EXISTS progress (
    user_id TEXT NOT NULL,
    work_id TEXT NOT NULL,
    position TEXT,
    fraction REAL NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL,
    PRIMARY KEY (user_id, work_id)
);
CREATE TABLE IF NOT EXISTS indexers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    base_url TEXT NOT NULL,
    token_set INTEGER NOT NULL DEFAULT 0,
    last_caps_at REAL,
    last_caps_ok INTEGER,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS works_fts USING fts5(
    work_id UNINDEXED,
    title,
    author,
    genre,
    description
);
CREATE INDEX IF NOT EXISTS idx_works_kind ON works(kind);
CREATE INDEX IF NOT EXISTS idx_works_review ON works(review_state);
CREATE INDEX IF NOT EXISTS idx_works_author ON works(author COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_works_kind_author ON works(kind, author COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_works_series ON works(series_name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_jobs_nzo ON jobs(nzo_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE TABLE IF NOT EXISTS rss_feeds (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    kind TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_guid TEXT,
    last_error TEXT,
    last_poll_at REAL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS user_prefs (
    user_id TEXT PRIMARY KEY,
    ambient TEXT NOT NULL DEFAULT 'off',
    prefs_json TEXT,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS whispers (
    id TEXT PRIMARY KEY,
    work_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_whispers_work ON whispers(work_id, created_at DESC);
CREATE TABLE IF NOT EXISTS celebrations_seen (
    user_id TEXT NOT NULL,
    celebration_key TEXT NOT NULL,
    seen_at REAL NOT NULL,
    PRIMARY KEY (user_id, celebration_key)
);
"""


class InviteConflict(RuntimeError):
    """Redeem lost the race or the invite is no longer pending."""


def _row_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def _loads(raw: Any, default: Any = None) -> Any:
    if not raw:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def _fts_query(q: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", q or "")
    if not tokens:
        return ""
    return " AND ".join(f'"{token}"' for token in tokens)


JOB_EXTRA_COLUMNS = {
    "sab_status": "TEXT",
    "nzo_name": "TEXT",
    "percent": "TEXT",
    "bytes": "INTEGER",
}


WORK_EXTRA_COLUMNS = {
    "abs_item_id": "TEXT",
    "synopsis_source": "TEXT",
    "llm_blurb": "TEXT",
    "atmosphere_path": "TEXT",
    "art_attribution": "TEXT",
    "part_total": "INTEGER",
    "part_style": "TEXT",
    "part_base": "TEXT",
    "part_origin": "INTEGER",
    "repair_fail_count": "INTEGER",
    "asin": "TEXT",
    "narrator": "TEXT",
}

FILE_EXTRA_COLUMNS = {
    "part": "INTEGER",
}


def _ensure_job_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    for name, decl in JOB_EXTRA_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {decl}")


def _ensure_work_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(works)").fetchall()}
    for name, decl in WORK_EXTRA_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE works ADD COLUMN {name} {decl}")


def _ensure_file_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(files)").fetchall()}
    for name, decl in FILE_EXTRA_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE files ADD COLUMN {name} {decl}")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_serializer = WriteSerializer()
        try:
            with self._connect() as conn:
                conn.executescript(SCHEMA)
                _ensure_job_columns(conn)
                _ensure_work_columns(conn)
                _ensure_file_columns(conn)
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

    # --- users ----------------------------------------------------------------

    def create_local_user(
        self,
        *,
        user_id: str,
        display_name: str,
        password_hash: str,
        role: str,
    ) -> Dict[str, Any]:
        now = time.time()
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO users (id, display_name, role, password_hash, created_at, last_login_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, display_name, role, password_hash, now, now),
                )
                conn.execute(
                    "INSERT INTO shelves (id, name, owner_user_id, created_at) VALUES (?, ?, ?, ?)",
                    (uuid.uuid4().hex, FAVORITES_SHELF, user_id, now),
                )
        self.run_write(_write, label='create_local_user')
        row = self.get_user(user_id)
        assert row is not None
        return row

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_dict(row)

    def get_user_by_display_name(self, name: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE lower(display_name) = lower(?)",
                (name,),
            ).fetchone()
        return _row_dict(row)

    def list_users(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
        return [_row_dict(row) or {} for row in rows]

    def owner_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'owner'").fetchone()
        return int(row["n"] if row else 0)

    def update_user_role(self, user_id: str, role: str) -> None:
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        self.run_write(_write, label='update_user_role')

    def update_user_password(self, user_id: str, password_hash: str) -> None:
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE users SET password_hash = ?, session_epoch = session_epoch + 1 WHERE id = ?",
                    (password_hash, user_id),
                )
        self.run_write(_write, label='update_user_password')

    def touch_login(self, user_id: str) -> None:
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (time.time(), user_id))
        self.run_write(_write, label='touch_login')

    # --- invites --------------------------------------------------------------

    def create_invite(
        self,
        *,
        invite_id: str,
        token_hash: str,
        created_by: str,
        role: str,
        expires_at: float,
    ) -> Dict[str, Any]:
        now = time.time()
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO invites (
                        id, token_hash, created_by, role, status, expires_at, created_at
                    ) VALUES (?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (invite_id, token_hash, created_by, role, expires_at, now),
                )
        self.run_write(_write, label='create_invite')
        row = self.get_invite(invite_id)
        assert row is not None
        return row

    def get_invite(self, invite_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM invites WHERE id = ?", (invite_id,)).fetchone()
        return _row_dict(row)

    def get_invite_by_token_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM invites WHERE token_hash = ?", (token_hash,)).fetchone()
        return _row_dict(row)

    def revoke_invite(self, invite_id: str) -> None:
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE invites SET status = 'revoked' WHERE id = ? AND status = 'pending'",
                    (invite_id,),
                )
        self.run_write(_write, label='revoke_invite')

    def create_local_user_and_redeem_invite(
        self,
        *,
        invite_id: str,
        user_id: str,
        display_name: str,
        password_hash: str,
        role: str,
    ) -> Dict[str, Any]:
        """Insert a local user and burn the invite in one SQLite transaction."""
        now = time.time()

        def _write() -> None:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """
                    INSERT INTO users (id, display_name, role, password_hash, created_at, last_login_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, display_name, role, password_hash, now, now),
                )
                conn.execute(
                    "INSERT INTO shelves (id, name, owner_user_id, created_at) VALUES (?, ?, ?, ?)",
                    (uuid.uuid4().hex, FAVORITES_SHELF, user_id, now),
                )
                cursor = conn.execute(
                    """
                    UPDATE invites
                    SET status = 'redeemed', redeemed_at = ?, redeemed_user_id = ?
                    WHERE id = ? AND status = 'pending' AND expires_at >= ?
                    """,
                    (now, user_id, invite_id, now),
                )
                if int(cursor.rowcount or 0) != 1:
                    raise InviteConflict("Invite has already been used")
                conn.commit()
            except sqlite3.OperationalError as error:
                conn.rollback()
                if "locked" in str(error).lower() or "busy" in str(error).lower():
                    raise InviteConflict("Invite has already been used") from error
                raise
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        self.run_write(_write, label="create_local_user_and_redeem_invite")
        user = self.get_user(user_id)
        invite = self.get_invite(invite_id)
        assert user is not None and invite is not None
        return {"user": user, "invite": invite}

    # --- works / FTS ----------------------------------------------------------

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
        sql = f"SELECT * FROM works WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(sql, args).fetchone()
        return _row_dict(row)

    def list_works(
        self,
        *,
        kind: Optional[str] = None,
        review_state: Optional[str] = None,
        music_state: Optional[str] = None,
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
        if music_state:
            clauses.append("music_state = ?")
            args.append(music_state)
        args.append(int(limit))
        args.append(max(0, int(offset)))
        sql = (
            f"SELECT * FROM works WHERE {' AND '.join(clauses)} "
            "ORDER BY updated_at DESC LIMIT ? OFFSET ?"
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
            description IS NULL OR description = ''
            OR genre IS NULL OR genre = ''
            OR year IS NULL
            OR cover_path IS NULL OR cover_path = ''
        )
    """

    def works_needing_enrichment(self, *, limit: int = 10) -> List[Dict[str, Any]]:
        """Oldest thin books/audiobooks for the enrich trickle."""
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM works
                WHERE {self._NEEDS_ENRICHMENT_WHERE}
                ORDER BY updated_at ASC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

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
        if shelf == "favorites":
            if not user_id:
                raise ValueError("user_id required for favorites shelf")
            shelf_row = self.favorites_shelf(user_id)
            from_sql = "shelf_items s JOIN works w ON w.id = s.work_id"
            clauses.append("s.shelf_id = ?")
            args.append(shelf_row["id"])
        if not include_review:
            clauses.append("w.review_state != 'needs_review'")
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
        sort: str = "author",
        offset: int = 0,
        limit: int = 48,
    ) -> Dict[str, Any]:
        capped = max(1, min(int(limit or 48), 100))
        skip = max(0, int(offset or 0))
        sort_key = str(sort or "author").strip().lower()
        if sort_key not in ("author", "title", "updated"):
            sort_key = "author"
        if sort_key == "title":
            order_sql = "w.title COLLATE NOCASE ASC, w.author COLLATE NOCASE ASC"
        elif sort_key == "updated":
            order_sql = "w.updated_at DESC, w.title COLLATE NOCASE ASC"
        else:
            order_sql = "w.author COLLATE NOCASE ASC, w.title COLLATE NOCASE ASC"
        if shelf == "favorites" and sort_key == "updated":
            order_sql = "s.added_at DESC, w.title COLLATE NOCASE ASC"

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
        for item in items:
            item["has_cover"] = bool(item.get("cover_path"))
        return {
            "items": items,
            "total": total,
            "offset": skip,
            "limit": capped,
            "sort": sort_key,
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
        kind_sql = ""
        args: List[Any] = [match]
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
                ORDER BY rank
                LIMIT ?
                """,
                args,
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def works_for_series(self, *, kind: str, series_name: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM works
                WHERE kind = ? AND lower(series_name) = lower(?) AND review_state != 'needs_review'
                ORDER BY series_index
                """,
                (kind, series_name),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def series_names(self, kind: str) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT series_name FROM works
                WHERE kind = ? AND series_name IS NOT NULL AND series_name != ''
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
        clauses = ["kind = 'music'", "review_state != 'needs_review'"]
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
        clauses = ["year IS NOT NULL", "review_state != 'needs_review'"]
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

    # --- files / jobs / shelves -----------------------------------------------

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
                """
                SELECT w.* FROM shelf_items s
                JOIN works w ON w.id = s.work_id
                WHERE s.shelf_id = ?
                ORDER BY s.added_at DESC
                LIMIT ?
                """,
                (shelf["id"], int(limit)),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

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
                """
                SELECT w.*, p.fraction, p.position, p.updated_at AS progress_at
                FROM progress p
                JOIN works w ON w.id = p.work_id
                WHERE p.user_id = ? AND p.fraction < 1
                ORDER BY p.updated_at DESC
                LIMIT ?
                """,
                (user_id, int(limit)),
            ).fetchall()
        out = []
        for row in rows:
            data = _row_dict(row) or {}
            data["has_cover"] = bool(data.get("cover_path"))
            data["progress"] = int(round(float(data.get("fraction") or 0) * 100))
            out.append(data)
        return out

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

    # --- delight prefs / whispers / celebrations ------------------------------

    def get_user_prefs(self, user_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM user_prefs WHERE user_id = ?", (user_id,)).fetchone()
        data = _row_dict(row)
        if data is None:
            return {"user_id": user_id, "ambient": "off", "prefs": {}}
        return {
            "user_id": user_id,
            "ambient": str(data.get("ambient") or "off"),
            "prefs": _loads(data.get("prefs_json"), default={}) or {},
            "updated_at": data.get("updated_at"),
        }

    def set_user_prefs(
        self,
        user_id: str,
        *,
        ambient: Optional[str] = None,
        prefs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        current = self.get_user_prefs(user_id)
        next_ambient = ambient if ambient is not None else current.get("ambient") or "off"
        next_prefs = dict(current.get("prefs") or {})
        if prefs is not None:
            next_prefs.update(prefs)
        now = time.time()
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO user_prefs (user_id, ambient, prefs_json, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        ambient=excluded.ambient,
                        prefs_json=excluded.prefs_json,
                        updated_at=excluded.updated_at
                    """,
                    (user_id, next_ambient, _dumps(next_prefs), now),
                )
        self.run_write(_write, label='set_user_prefs')
        return self.get_user_prefs(user_id)

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

    def kind_counts(self) -> Dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT kind, COUNT(*) AS n FROM works
                WHERE review_state IS NULL OR review_state IN ('none', 'resolved', '')
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
        return guids
