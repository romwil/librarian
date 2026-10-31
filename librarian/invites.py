"""Invite-only household join. HMAC URL token; hash at rest; one-tx redeem."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid
from typing import Any, Dict, Tuple
from urllib.parse import urljoin

from librarian.auth import INVITE_ROLES, MIN_PASSWORD_LENGTH, hash_password
from librarian.db import Database, InviteConflict
from librarian.sessions import resolve_session_secret

DEFAULT_INVITE_TTL_SECONDS = 7 * 24 * 3600
MIN_INVITE_TTL_SECONDS = 3600
MAX_INVITE_TTL_SECONDS = DEFAULT_INVITE_TTL_SECONDS


def hash_invite_token(raw_token: str) -> str:
    return hashlib.sha256(str(raw_token or "").encode("utf-8")).hexdigest()


def generate_invite_token() -> str:
    return secrets.token_urlsafe(32)


def _invite_hmac(invite_id: str, raw: str) -> str:
    secret = resolve_session_secret().encode("utf-8")
    return hmac.new(secret, f"{invite_id}.{raw}".encode("utf-8"), hashlib.sha256).hexdigest()


def encode_invite_token(invite_id: str, raw: str) -> str:
    return f"{invite_id}.{raw}.{_invite_hmac(invite_id, raw)}"


def parse_invite_token(token: str) -> Tuple[str, str]:
    """Verify HMAC and return (invite_id, raw). Fail closed without a DB lookup."""
    cleaned = str(token or "").strip()
    parts = cleaned.split(".")
    if len(parts) != 3 or not all(parts):
        raise ValueError("Invite not found")
    invite_id, raw, mac = parts
    expected = _invite_hmac(invite_id, raw)
    if not hmac.compare_digest(mac, expected):
        raise ValueError("Invite not found")
    return invite_id, raw


def cap_invite_ttl(expires_in_seconds: int) -> int:
    try:
        ttl = int(expires_in_seconds)
    except (TypeError, ValueError):
        ttl = DEFAULT_INVITE_TTL_SECONDS
    return min(max(MIN_INVITE_TTL_SECONDS, ttl), MAX_INVITE_TTL_SECONDS)


def resolve_invite_base_url(settings: Any = None, request: Any = None) -> str:
    configured = ""
    if settings is not None:
        configured = str(getattr(settings, "public_base_url", "") or "").strip()
    if configured:
        return configured.rstrip("/")
    if request is not None:
        return str(getattr(request, "base_url", "") or "").rstrip("/")
    return ""


def public_invite_view(invite: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": invite["id"],
        "status": invite["status"],
        "expires_at": invite["expires_at"],
        "role": invite["role"],
        "created_at": invite.get("created_at"),
        "created_by": invite.get("created_by"),
        "redeemed_at": invite.get("redeemed_at"),
    }


def assert_can_invite(actor_role: str, invite_role: str) -> None:
    cleaned = str(invite_role or "").strip().lower()
    if cleaned == "owner":
        raise ValueError("Cannot invite a second owner")
    if cleaned not in INVITE_ROLES:
        raise ValueError("role must be op or reader")
    if actor_role == "owner":
        return
    if actor_role == "op" and cleaned == "reader":
        return
    raise ValueError("Not allowed to mint this invite")


def create_household_invite(
    db: Database,
    *,
    created_by: str,
    actor_role: str,
    role: str,
    expires_in_seconds: int = DEFAULT_INVITE_TTL_SECONDS,
    base_url: str = "",
) -> Dict[str, Any]:
    assert_can_invite(actor_role, role)
    invite_id = uuid.uuid4().hex
    raw = generate_invite_token()
    token_hash = hash_invite_token(raw)
    expires_at = time.time() + cap_invite_ttl(expires_in_seconds)
    invite = db.create_invite(
        invite_id=invite_id,
        token_hash=token_hash,
        created_by=created_by,
        role=str(role).strip().lower(),
        expires_at=expires_at,
    )
    signed = encode_invite_token(str(invite["id"]), raw)
    join_path = f"/join?token={signed}"
    origin = str(base_url or "").rstrip("/")
    join_url = urljoin(origin + "/", join_path.lstrip("/")) if origin else join_path
    return {
        "invite": public_invite_view(invite),
        "token": signed,
        "join_path": join_path,
        "join_url": join_url,
        "expires_at": invite["expires_at"],
    }


def list_pending_invites(db: Database) -> list[Dict[str, Any]]:
    now = time.time()
    pending = []
    for invite in db.list_invites(status="pending"):
        if float(invite.get("expires_at") or 0) < now:
            continue
        pending.append(public_invite_view(invite))
    return pending


def revoke_household_invite(db: Database, *, invite_id: str, actor_role: str) -> Dict[str, Any]:
    invite = db.get_invite(invite_id)
    if invite is None:
        raise ValueError("Invite not found")
    if invite["status"] != "pending":
        raise ValueError("Invite is not pending")
    if actor_role == "op" and str(invite.get("role") or "") != "reader":
        raise ValueError("Not allowed to revoke this invite")
    db.revoke_invite(invite_id)
    updated = db.get_invite(invite_id)
    assert updated is not None
    return public_invite_view(updated)


def lookup_pending_invite(db: Database, raw_token: str) -> Dict[str, Any]:
    invite_id, raw = parse_invite_token(raw_token)
    invite = db.get_invite_by_token_hash(hash_invite_token(raw))
    if invite is None or str(invite["id"]) != invite_id:
        raise ValueError("Invite not found")
    if invite["status"] == "revoked":
        raise ValueError("Invite has been revoked")
    if invite["status"] == "redeemed":
        raise ValueError("Invite has already been used")
    if invite["status"] != "pending":
        raise ValueError("Invite is not available")
    if float(invite["expires_at"]) < time.time():
        raise ValueError("Invite has expired")
    return invite


def redeem_local_invite(
    db: Database,
    *,
    raw_token: str,
    username: str,
    password: str,
) -> Dict[str, Any]:
    invite = lookup_pending_invite(db, raw_token)
    role = str(invite["role"]).strip().lower()
    if role == "owner" or role not in ("op", "reader"):
        raise ValueError("Invite is not available")

    name = str(username or "").strip()
    if len(name) < 2:
        raise ValueError("Username must be at least 2 characters")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError("Password must be at least 8 characters")
    if db.get_user_by_display_name(name) is not None:
        raise ValueError("Username already taken")

    user_id = f"local-{secrets.token_hex(12)}"
    try:
        result = db.create_local_user_and_redeem_invite(
            invite_id=str(invite["id"]),
            user_id=user_id,
            display_name=name,
            password_hash=hash_password(password),
            role=role,
        )
    except InviteConflict as error:
        raise ValueError(str(error)) from error
    return {
        "invite": public_invite_view(result["invite"]),
        "user": {
            "id": result["user"]["id"],
            "display_name": result["user"]["display_name"],
            "role": result["user"]["role"],
        },
    }
