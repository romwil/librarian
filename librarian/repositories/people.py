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
