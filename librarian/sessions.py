"""Signed session cookies. Refuse the public development default (S2)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any, Optional

SESSION_COOKIE_NAME = "librarian_session"
DEFAULT_TTL_SECONDS = 30 * 86400
DEV_SESSION_SECRET = "librarian-dev-session-secret"
SESSION_SECRET_FILENAME = "session_secret"
_ENV_SESSION_SECRET = "LIBRARIAN_SESSION_SECRET"

logger = logging.getLogger(__name__)

_cached_secret: Optional[str] = None


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/config"))


def session_secret_path(data_dir: Optional[Path] = None) -> Path:
    return (data_dir or _data_dir()) / SESSION_SECRET_FILENAME


def _env_secret() -> str:
    return (os.environ.get(_ENV_SESSION_SECRET) or "").strip()


def is_dev_session_secret(value: str) -> bool:
    return (value or "").strip() == DEV_SESSION_SECRET


def has_usable_session_secret(data_dir: Optional[Path] = None) -> bool:
    env = _env_secret()
    if env:
        return not is_dev_session_secret(env)
    path = session_secret_path(data_dir)
    if not path.is_file():
        return False
    try:
        stored = path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return bool(stored) and not is_dev_session_secret(stored)


def resolve_session_secret(data_dir: Optional[Path] = None, *, persist: bool = True) -> str:
    """Return a cryptographically strong session secret. Never the public default."""
    global _cached_secret
    if _cached_secret and not is_dev_session_secret(_cached_secret):
        env = _env_secret()
        if not env or env == _cached_secret:
            return _cached_secret

    root = data_dir or _data_dir()
    env = _env_secret()
    if env and is_dev_session_secret(env):
        raise RuntimeError(
            "LIBRARIAN_SESSION_SECRET is the public development default; refuse to start. "
            "Set a long random value."
        )
    if env:
        _cached_secret = env
        return env

    path = session_secret_path(root)
    if path.is_file():
        try:
            stored = path.read_text(encoding="utf-8").strip()
        except OSError:
            stored = ""
        if stored and not is_dev_session_secret(stored):
            _cached_secret = stored
            return stored

    if not persist:
        raise RuntimeError("No usable Librarian session secret configured")

    secret = secrets.token_urlsafe(48)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(secret + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    logger.info("Generated session secret at %s", path)
    _cached_secret = secret
    return secret


def ensure_session_secret(data_dir: Optional[Path] = None) -> str:
    return resolve_session_secret(data_dir, persist=True)


def clear_session_secret_cache() -> None:
    global _cached_secret
    _cached_secret = None


def _secret_bytes(data_dir: Optional[Path] = None) -> bytes:
    return resolve_session_secret(data_dir).encode("utf-8")


def create_session_token(
    user_id: str,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    session_epoch: int = 0,
    jti: Optional[str] = None,
    data_dir: Optional[Path] = None,
) -> str:
    payload = {
        "uid": user_id,
        "exp": time.time() + ttl_seconds,
        "jti": jti or secrets.token_urlsafe(16),
        "sv": int(session_epoch),
    }
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    sig = hmac.new(_secret_bytes(data_dir), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def parse_session_token(token: str, *, data_dir: Optional[Path] = None) -> Optional[dict[str, Any]]:
    cleaned = str(token or "").strip()
    parts = cleaned.split(".")
    if len(parts) != 2 or not all(parts):
        return None
    body, sig = parts
    expected = hmac.new(_secret_bytes(data_dir), body.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        exp = float(payload.get("exp") or 0)
    except (TypeError, ValueError):
        return None
    if exp < time.time():
        return None
    uid = str(payload.get("uid") or "").strip()
    if not uid:
        return None
    return payload
