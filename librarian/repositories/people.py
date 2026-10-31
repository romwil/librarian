"""Household people: users, invites, session epochs, and per-user prefs."""

from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

from librarian.repositories._base import (
    FAVORITES_SHELF,
    RepositoryBase,
    _dumps,
    _loads,
    _row_dict,
)


class InviteConflict(RuntimeError):
    """Redeem lost the race or the invite is no longer pending."""


class PeopleRepository(RepositoryBase):
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
            # Shallow merge; None values are explicit clears (update alone cannot delete keys).
            next_prefs.update(prefs)
            for key, value in prefs.items():
                if value is None:
                    next_prefs.pop(key, None)
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

    def list_invites(self, *, status: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM invites"
        params: List[Any] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_dict(row) or {} for row in rows]

    def set_user_disabled(self, user_id: str, disabled: bool) -> None:
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE users SET disabled = ? WHERE id = ?",
                    (1 if disabled else 0, user_id),
                )
        self.run_write(_write, label="set_user_disabled")

    def bump_session_epoch(self, user_id: str) -> int:
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE users SET session_epoch = session_epoch + 1 WHERE id = ?",
                    (user_id,),
                )
                row = conn.execute(
                    "SELECT session_epoch FROM users WHERE id = ?", (user_id,)
                ).fetchone()
            return int(row["session_epoch"] if row else 0)

        return int(self.run_write(_write, label="bump_session_epoch") or 0)

    def create_session(
        self,
        *,
        jti: str,
        user_id: str,
        expires_at: float,
        user_agent: str = "",
        ip: str = "",
    ) -> None:
        now = time.time()

        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO sessions (
                        id, user_id, created_at, last_seen_at, expires_at, user_agent, ip
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (jti, user_id, now, now, expires_at, user_agent[:240], ip[:64]),
                )

        self.run_write(_write, label="create_session")

    def get_session(self, jti: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (jti,)).fetchone()
        return _row_dict(row)

    def touch_session(self, jti: str) -> None:
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE sessions SET last_seen_at = ? WHERE id = ? AND revoked_at IS NULL",
                    (time.time(), jti),
                )

        self.try_run_write(_write, label="touch_session")

    def revoke_session(self, jti: str) -> None:
        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                    (time.time(), jti),
                )

        self.run_write(_write, label="revoke_session")

    def revoke_sessions_for_user(self, user_id: str) -> int:
        now = time.time()

        def _write() -> Any:
            with self._connect() as conn:
                cursor = conn.execute(
                    "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                    (now, user_id),
                )
                return int(cursor.rowcount or 0)

        return int(self.run_write(_write, label="revoke_sessions_for_user") or 0)

    def create_password_reset(
        self,
        *,
        reset_id: str,
        token_hash: str,
        user_id: str,
        created_by: str,
        expires_at: float,
    ) -> Dict[str, Any]:
        now = time.time()

        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO password_resets (
                        id, token_hash, user_id, created_by, expires_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (reset_id, token_hash, user_id, created_by, expires_at, now),
                )

        self.run_write(_write, label="create_password_reset")
        row = self.get_password_reset(reset_id)
        assert row is not None
        return row

    def get_password_reset(self, reset_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM password_resets WHERE id = ?", (reset_id,)).fetchone()
        return _row_dict(row)

    def get_password_reset_by_token_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM password_resets WHERE token_hash = ?", (token_hash,)
            ).fetchone()
        return _row_dict(row)

    def consume_password_reset(self, reset_id: str) -> bool:
        now = time.time()

        def _write() -> Any:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    UPDATE password_resets
                    SET used_at = ?
                    WHERE id = ? AND used_at IS NULL AND expires_at >= ?
                    """,
                    (now, reset_id, now),
                )
                return int(cursor.rowcount or 0) == 1

        return bool(self.run_write(_write, label="consume_password_reset"))

    def add_security_event(
        self,
        *,
        kind: str,
        user_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        event_id = uuid.uuid4().hex
        now = time.time()
        payload = _dumps(detail or {})

        def _write() -> Any:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO security_events (id, at, user_id, actor_id, kind, detail_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (event_id, now, user_id, actor_id, kind, payload),
                )

        self.try_run_write(_write, label="add_security_event")

    def export_member_bundle(self, user_id: str) -> Dict[str, Any]:
        """Everything this member owns, minus secrets. Used by /api/auth/export."""
        user = self.get_user(user_id)
        if user is None:
            return {}
        prefs = self.get_user_prefs(user_id)
        with self._connect() as conn:
            progress = [
                _row_dict(row) or {}
                for row in conn.execute(
                    "SELECT work_id, position, fraction, updated_at FROM progress WHERE user_id = ?",
                    (user_id,),
                ).fetchall()
            ]
            shelves = [
                _row_dict(row) or {}
                for row in conn.execute(
                    "SELECT id, name, created_at, shared FROM shelves WHERE owner_user_id = ?",
                    (user_id,),
                ).fetchall()
            ]
            shelf_ids = [str(row["id"]) for row in shelves]
            items: List[Dict[str, Any]] = []
            if shelf_ids:
                placeholders = ",".join("?" * len(shelf_ids))
                items = [
                    _row_dict(row) or {}
                    for row in conn.execute(
                        f"SELECT shelf_id, work_id, added_at FROM shelf_items WHERE shelf_id IN ({placeholders})",
                        shelf_ids,
                    ).fetchall()
                ]
            whispers = [
                _row_dict(row) or {}
                for row in conn.execute(
                    "SELECT id, work_id, body, created_at FROM whispers WHERE user_id = ?",
                    (user_id,),
                ).fetchall()
            ]
            notifications = [
                _row_dict(row) or {}
                for row in conn.execute(
                    """
                    SELECT id, kind, title, body, related_id, created_at, seen_at
                    FROM user_notifications WHERE user_id = ?
                    """,
                    (user_id,),
                ).fetchall()
            ]
        return {
            "user": {
                "id": user["id"],
                "display_name": user["display_name"],
                "role": user["role"],
                "created_at": user.get("created_at"),
                "last_login_at": user.get("last_login_at"),
                "disabled": bool(int(user.get("disabled") or 0)),
            },
            "prefs": {"ambient": prefs.get("ambient"), "prefs": prefs.get("prefs") or {}},
            "progress": progress,
            "shelves": shelves,
            "shelf_items": items,
            "whispers": whispers,
            "notifications": notifications,
        }

    def delete_user_cascade(self, user_id: str) -> None:
        """Erase a member. Walks every user-id column; FKs cover the new tables."""

        def _write() -> Any:
            with self._connect() as conn:
                shelf_ids = [
                    str(row["id"])
                    for row in conn.execute(
                        "SELECT id FROM shelves WHERE owner_user_id = ?", (user_id,)
                    ).fetchall()
                ]
                if shelf_ids:
                    placeholders = ",".join("?" * len(shelf_ids))
                    conn.execute(
                        f"DELETE FROM shelf_items WHERE shelf_id IN ({placeholders})",
                        shelf_ids,
                    )
                conn.execute("DELETE FROM shelves WHERE owner_user_id = ?", (user_id,))
                conn.execute("DELETE FROM progress WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM user_prefs WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM whispers WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM celebrations_seen WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM user_notifications WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM notification_digest_queue WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM password_resets WHERE user_id = ?", (user_id,))
                conn.execute(
                    "UPDATE invites SET status = 'revoked' WHERE created_by = ? AND status = 'pending'",
                    (user_id,),
                )
                conn.execute(
                    "UPDATE invites SET redeemed_user_id = NULL WHERE redeemed_user_id = ?",
                    (user_id,),
                )
                conn.execute(
                    "UPDATE jobs SET requested_by = '' WHERE requested_by = ?",
                    (user_id,),
                )
                conn.execute(
                    "UPDATE user_notifications SET from_user_id = NULL WHERE from_user_id = ?",
                    (user_id,),
                )
                conn.execute(
                    "UPDATE security_events SET user_id = NULL WHERE user_id = ?",
                    (user_id,),
                )
                conn.execute(
                    "UPDATE security_events SET actor_id = NULL WHERE actor_id = ?",
                    (user_id,),
                )
                cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
                if int(cursor.rowcount or 0) != 1:
                    raise ValueError("User not found")

        self.run_write(_write, label="delete_user_cascade")

