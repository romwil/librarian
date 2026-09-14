"""Household roles, password hashes, env owner seed, public handshake."""

from __future__ import annotations

import hashlib
import hmac as _hmac
import logging
import os
import secrets
from typing import Any, Dict, FrozenSet, Optional, Tuple

from librarian.db import Database
from librarian.sessions import (
    DEFAULT_TTL_SECONDS,
    SESSION_COOKIE_NAME,
    create_session_token,
    parse_session_token,
)

logger = logging.getLogger(__name__)

ROLES = ("owner", "op", "reader")
INVITE_ROLES = ("op", "reader")
DEFAULT_OWNER_USERNAME = "owner"
MIN_PASSWORD_LENGTH = 8

PUBLIC_HANDSHAKE_EXACT: FrozenSet[Tuple[str, str]] = frozenset(
    {
        ("GET", "/api/health"),
        ("GET", "/api/features"),
        ("GET", "/api/invites/validate"),
        ("POST", "/api/invites/redeem/local"),
        ("POST", "/api/auth/local/login"),
        ("POST", "/api/auth/logout"),
    }
)

_PASSWORD_SALT_BYTES = 32


def _pbkdf2_iterations() -> int:
    raw = (os.environ.get("LIBRARIAN_PBKDF2_ITERATIONS") or "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return 600_000


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    if salt is None:
        salt = secrets.token_bytes(_PASSWORD_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _pbkdf2_iterations())
    return f"{salt.hex()}${derived.hex()}"


_DUMMY_PASSWORD_HASH = hash_password("!", salt=b"\x00" * _PASSWORD_SALT_BYTES)


def verify_password(password: str, stored_hash: str) -> bool:
    if "$" not in (stored_hash or ""):
        verify_password("!", _DUMMY_PASSWORD_HASH)
        return False
    salt_hex, expected_hex = stored_hash.split("$", 1)
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _pbkdf2_iterations())
    return _hmac.compare_digest(derived.hex(), expected_hex)


def is_public_handshake(method: str, path: str) -> bool:
    cleaned = (path or "").split("?", 1)[0]
    if len(cleaned) > 1:
        cleaned = cleaned.rstrip("/")
    return (str(method or "GET").upper(), cleaned) in PUBLIC_HANDSHAKE_EXACT


def resolve_owner_credentials() -> tuple[str, str]:
    username = (os.environ.get("LIBRARIAN_OWNER_USERNAME") or "").strip() or DEFAULT_OWNER_USERNAME
    password = os.environ.get("LIBRARIAN_OWNER_PASSWORD") or ""
    return username, password


def has_real_owner(db: Database) -> bool:
    return db.owner_count() > 0


def public_user(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "display_name": row["display_name"],
        "role": row["role"],
    }


def seed_env_owner(db: Database) -> Optional[str]:
    """Ensure the env-injected owner exists. Never clobber a different owner."""
    username, password = resolve_owner_credentials()
    if not password:
        return None
    if len(password) < MIN_PASSWORD_LENGTH:
        logger.warning(
            "LIBRARIAN_OWNER_PASSWORD is set but shorter than %d characters; "
            "refusing to seed a weak owner.",
            MIN_PASSWORD_LENGTH,
        )
        return None

    existing = db.get_user_by_display_name(username)
    if existing is not None:
        user_id = str(existing["id"])
        is_owner = str(existing["role"]) == "owner"
        if not is_owner and has_real_owner(db):
            logger.warning(
                "LIBRARIAN_OWNER_PASSWORD is set but a different owner already exists; "
                "skipping promote of '%s'.",
                username,
            )
            return None
        changed = False
        if not is_owner:
            db.update_user_role(user_id, "owner")
            changed = True
        stored_hash = existing.get("password_hash") or ""
        if not verify_password(password, str(stored_hash)):
            db.update_user_password(user_id, hash_password(password))
            changed = True
        if changed:
            logger.info("Owner account '%s' updated from LIBRARIAN_OWNER_PASSWORD.", username)
        return user_id

    if has_real_owner(db):
        logger.warning(
            "LIBRARIAN_OWNER_PASSWORD is set but a different owner already exists; "
            "skipping seed of '%s'.",
            username,
        )
        return None

    user_id = f"local-{secrets.token_hex(12)}"
    db.create_local_user(
        user_id=user_id,
        display_name=username,
        password_hash=hash_password(password),
        role="owner",
    )
    logger.info("Seeded owner account '%s' from LIBRARIAN_OWNER_PASSWORD.", username)
    return user_id


def cookie_should_be_secure(request: Any = None) -> bool:
    from librarian.proxy import request_is_trusted_https

    return request_is_trusted_https(request)


def set_session_cookie(
    response: Any,
    user_id: str,
    *,
    request: Any = None,
    secure: Optional[bool] = None,
    session_epoch: int = 0,
) -> None:
    token = create_session_token(user_id, session_epoch=session_epoch)
    use_secure = cookie_should_be_secure(request) if secure is None else bool(secure)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=DEFAULT_TTL_SECONDS,
        path="/",
        secure=use_secure,
    )


def clear_session_cookie(response: Any, request: Any = None) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=cookie_should_be_secure(request),
    )


def user_from_request(request: Any, db: Database) -> Optional[Dict[str, Any]]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    payload = parse_session_token(token or "")
    if payload is None:
        return None
    user = db.get_user(str(payload["uid"]))
    if user is None:
        return None
    expected_epoch = int(user.get("session_epoch") or 0)
    if int(payload.get("sv") or 0) != expected_epoch:
        return None
    return user


def require_role(user: Optional[Dict[str, Any]], *allowed: str) -> None:
    from fastapi import HTTPException

    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user["role"] not in allowed:
        raise HTTPException(status_code=403, detail="Not allowed")
