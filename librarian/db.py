"""SQLite WAL catalog: users, invites, works, files, jobs, shelves."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SQLITE_BUSY_TIMEOUT_MS = 30000
FAVORITES_SHELF = "Favorites"

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
    review_state TEXT NOT NULL DEFAULT 'none',
    review_reason TEXT,
    music_state TEXT,
    indexer_guid TEXT,
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
CREATE VIRTUAL TABLE IF NOT EXISTS works_fts USING fts5(
    work_id UNINDEXED,
    title,
    author,
    genre,
    description
);
CREATE INDEX IF NOT EXISTS idx_works_kind ON works(kind);
CREATE INDEX IF NOT EXISTS idx_works_review ON works(review_state);
CREATE INDEX IF NOT EXISTS idx_jobs_nzo ON jobs(nzo_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
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


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(SCHEMA)

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
        with self._lock, self._connect() as conn:
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
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))

    def update_user_password(self, user_id: str, password_hash: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, session_epoch = session_epoch + 1 WHERE id = ?",
                (password_hash, user_id),
            )

    def touch_login(self, user_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (time.time(), user_id))

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
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO invites (
                    id, token_hash, created_by, role, status, expires_at, created_at
                ) VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """,
                (invite_id, token_hash, created_by, role, expires_at, now),
            )
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
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE invites SET status = 'revoked' WHERE id = ? AND status = 'pending'",
                (invite_id,),
            )

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
        conn = self._connect()
        try:
            with self._lock:
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
            "description": work.get("description"),
            "publisher": work.get("publisher"),
            "genre": work.get("genre"),
            "cover_path": work.get("cover_path"),
            "folder_path": work.get("folder_path"),
            "review_state": work.get("review_state") or "none",
            "review_reason": work.get("review_reason"),
            "music_state": work.get("music_state"),
            "indexer_guid": work.get("indexer_guid"),
            "created_at": work.get("created_at") or now,
            "updated_at": now,
        }
        with self._lock, self._connect() as conn:
            existing = conn.execute("SELECT id FROM works WHERE id = ?", (work_id,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE works SET
                        kind=?, title=?, author=?, series_name=?, series_index=?, year=?,
                        isbn=?, mbid=?, description=?, publisher=?, genre=?, cover_path=?,
                        folder_path=?, review_state=?, review_reason=?, music_state=?,
                        indexer_guid=?, updated_at=?
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
                        payload["description"],
                        payload["publisher"],
                        payload["genre"],
                        payload["cover_path"],
                        payload["folder_path"],
                        payload["review_state"],
                        payload["review_reason"],
                        payload["music_state"],
                        payload["indexer_guid"],
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
                        description, publisher, genre, cover_path, folder_path, review_state,
                        review_reason, music_state, indexer_guid, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    tuple(payload.values()),
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
        row = self.get_work(work_id)
        assert row is not None
        return row

    def get_work(self, work_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM works WHERE id = ?", (work_id,)).fetchone()
        return _row_dict(row)

    def list_works(
        self,
        *,
        kind: Optional[str] = None,
        review_state: Optional[str] = None,
        music_state: Optional[str] = None,
        limit: int = 48,
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
        sql = f"SELECT * FROM works WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT ?"
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def search_works(self, query: str, *, limit: int = 24) -> List[Dict[str, Any]]:
        match = _fts_query(query)
        if not match:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT w.* FROM works_fts f
                JOIN works w ON w.id = f.work_id
                WHERE works_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (match, int(limit)),
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

    # --- files / jobs / shelves -----------------------------------------------

    def add_file(self, record: Dict[str, Any]) -> Dict[str, Any]:
        file_id = str(record.get("id") or uuid.uuid4().hex)
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO files (id, work_id, path, filename, kind, size, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_id,
                    record.get("work_id"),
                    record["path"],
                    record["filename"],
                    record.get("kind"),
                    record.get("size"),
                    now,
                ),
            )
        return self.get_file(file_id) or {}

    def get_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        return _row_dict(row)

    def files_for_work(self, work_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM files WHERE work_id = ? ORDER BY filename",
                (work_id,),
            ).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def create_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        now = time.time()
        job_id = str(job.get("id") or uuid.uuid4().hex)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, work_id, nzo_id, status, indexer_guid, title, kind,
                    requested_by, storage_path, error, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    _dumps(job.get("payload") or {}),
                    now,
                    now,
                ),
            )
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

    def update_job(self, job_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        allowed = {
            "work_id",
            "nzo_id",
            "status",
            "storage_path",
            "error",
            "title",
            "kind",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if "payload" in fields:
            updates["payload_json"] = _dumps(fields["payload"])
        if not updates:
            return self.get_job(job_id)
        updates["updated_at"] = time.time()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE jobs SET {assignments} WHERE id = ?",
                (*updates.values(), job_id),
            )
        return self.get_job(job_id)

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
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO shelves (id, name, owner_user_id, created_at) VALUES (?, ?, ?, ?)",
                (shelf_id, FAVORITES_SHELF, user_id, now),
            )
        return {"id": shelf_id, "name": FAVORITES_SHELF, "owner_user_id": user_id, "created_at": now}

    def toggle_favorite(self, user_id: str, work_id: str) -> bool:
        shelf = self.favorites_shelf(user_id)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT 1 FROM shelf_items WHERE shelf_id = ? AND work_id = ?",
                (shelf["id"], work_id),
            ).fetchone()
        with self._lock, self._connect() as conn:
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
