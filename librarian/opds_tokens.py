"""Signed OPDS tokens. Catalog navigation and file acquisition never use the session cookie."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any, Optional

from librarian.sessions import resolve_session_secret

# Long enough for a reader app to keep a catalog URL and a downloaded book link.
OPDS_TTL_SECONDS = 10 * 365 * 24 * 60 * 60
_PURPOSE_CATALOG = "catalog"
_PURPOSE_FILE = "file"


def _secret_bytes(data_dir: Optional[Path] = None) -> bytes:
    return resolve_session_secret(data_dir).encode("utf-8")


def _sign(payload: dict[str, Any], *, data_dir: Optional[Path] = None) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    sig = hmac.new(_secret_bytes(data_dir), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def _parse(token: str, *, data_dir: Optional[Path] = None) -> Optional[dict[str, Any]]:
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
    return payload


def create_catalog_token(
    *,
    ttl_seconds: int = OPDS_TTL_SECONDS,
    data_dir: Optional[Path] = None,
) -> str:
    """Token that may open the catalog. It cannot download a file."""
    return _sign(
        {"v": 1, "pur": _PURPOSE_CATALOG, "exp": time.time() + ttl_seconds},
        data_dir=data_dir,
    )


def create_file_token(
    work_id: str,
    file_id: str,
    *,
    ttl_seconds: int = OPDS_TTL_SECONDS,
    data_dir: Optional[Path] = None,
) -> str:
    """Token scoped to one work file. It cannot open the catalog or another file."""
    return _sign(
        {
            "v": 1,
            "pur": _PURPOSE_FILE,
            "wid": str(work_id),
            "fid": str(file_id),
            "exp": time.time() + ttl_seconds,
        },
        data_dir=data_dir,
    )


def parse_catalog_token(token: str, *, data_dir: Optional[Path] = None) -> Optional[dict[str, Any]]:
    payload = _parse(token, data_dir=data_dir)
    if payload is None or payload.get("pur") != _PURPOSE_CATALOG:
        return None
    return payload


def parse_file_token(token: str, *, data_dir: Optional[Path] = None) -> Optional[dict[str, Any]]:
    payload = _parse(token, data_dir=data_dir)
    if payload is None or payload.get("pur") != _PURPOSE_FILE:
        return None
    work_id = str(payload.get("wid") or "").strip()
    file_id = str(payload.get("fid") or "").strip()
    if not work_id or not file_id:
        return None
    return {"work_id": work_id, "file_id": file_id, "exp": payload.get("exp")}


def is_acquisition_download(method: str, path: str, token: str) -> bool:
    """True when a download request is presenting an OPDS acquisition token."""
    if str(method or "").upper() != "GET":
        return False
    if not str(token or "").strip():
        return False
    parts = str(path or "").rstrip("/").split("/")
    return (
        len(parts) == 5
        and parts[0] == ""
        and parts[1] == "api"
        and parts[2] == "works"
        and parts[4] == "download"
    )
