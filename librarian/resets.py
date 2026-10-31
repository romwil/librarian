"""Owner-issued password reset. HMAC URL token; hash at rest; 24h single-use."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid
from typing import Any, Dict, Tuple
from urllib.parse import urljoin

from librarian.auth import MIN_PASSWORD_LENGTH, hash_password
from librarian.db import Database
from librarian.sessions import invalidate_session_cache, resolve_session_secret

DEFAULT_RESET_TTL_SECONDS = 24 * 3600


def hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(str(raw_token or "").encode("utf-8")).hexdigest()


def _reset_hmac(reset_id: str, raw: str) -> str:
    secret = resolve_session_secret().encode("utf-8")
    return hmac.new(secret, f"reset.{reset_id}.{raw}".encode("utf-8"), hashlib.sha256).hexdigest()


def encode_reset_token(reset_id: str, raw: str) -> str:
    return f"{reset_id}.{raw}.{_reset_hmac(reset_id, raw)}"


def parse_reset_token(token: str) -> Tuple[str, str]:
    cleaned = str(token or "").strip()
    parts = cleaned.split(".")
    if len(parts) != 3 or not all(parts):
        raise ValueError("Reset link not found")
    reset_id, raw, mac = parts
    expected = _reset_hmac(reset_id, raw)
    if not hmac.compare_digest(mac, expected):
        raise ValueError("Reset link not found")
    return reset_id, raw


def public_reset_view(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "expires_at": row["expires_at"],
        "used_at": row.get("used_at"),
    }


def issue_password_reset(
    db: Database,
    *,
    user_id: str,
    created_by: str,
    base_url: str = "",
    expires_in_seconds: int = DEFAULT_RESET_TTL_SECONDS,
) -> Dict[str, Any]:
    user = db.get_user(user_id)
    if user is None:
        raise ValueError("User not found")
    if str(user.get("role") or "") == "owner":
        raise ValueError("Owner password is set from the host environment")
    reset_id = uuid.uuid4().hex
    raw = secrets.token_urlsafe(32)
    expires_at = time.time() + max(60, min(int(expires_in_seconds), DEFAULT_RESET_TTL_SECONDS))
    row = db.create_password_reset(
        reset_id=reset_id,
        token_hash=hash_reset_token(raw),
        user_id=user_id,
        created_by=created_by,
        expires_at=expires_at,
    )
    signed = encode_reset_token(reset_id, raw)
    reset_path = f"/reset?token={signed}"
    origin = str(base_url or "").rstrip("/")
    reset_url = urljoin(origin + "/", reset_path.lstrip("/")) if origin else reset_path
    db.add_security_event(
        kind="password_reset_issued",
        user_id=user_id,
        actor_id=created_by,
        detail={"reset_id": reset_id},
    )
    return {
        "reset": public_reset_view(row),
        "token": signed,
        "reset_path": reset_path,
        "reset_url": reset_url,
        "display_name": user["display_name"],
    }


def lookup_pending_reset(db: Database, raw_token: str) -> Dict[str, Any]:
    reset_id, raw = parse_reset_token(raw_token)
    row = db.get_password_reset_by_token_hash(hash_reset_token(raw))
    if row is None or str(row["id"]) != reset_id:
        raise ValueError("Reset link not found")
    if row.get("used_at"):
        raise ValueError("Reset link has already been used")
    if float(row["expires_at"]) < time.time():
        raise ValueError("Reset link has expired")
    return row


def redeem_password_reset(db: Database, *, raw_token: str, password: str) -> Dict[str, Any]:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError("Password must be at least 8 characters")
    row = lookup_pending_reset(db, raw_token)
    if not db.consume_password_reset(str(row["id"])):
        raise ValueError("Reset link has already been used")
    user_id = str(row["user_id"])
    db.update_user_password(user_id, hash_password(password))
    db.revoke_sessions_for_user(user_id)
    invalidate_session_cache(user_id=user_id)
    db.add_security_event(kind="password_reset_used", user_id=user_id, actor_id=user_id)
    user = db.get_user(user_id)
    assert user is not None
    return {"user": {"id": user["id"], "display_name": user["display_name"], "role": user["role"]}}
