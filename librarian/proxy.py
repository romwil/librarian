"""Reverse-proxy trust. Fail closed unless LIBRARIAN_TRUST_PROXY_HEADERS is on.

Untrusted ``X-Forwarded-*`` must never set Secure cookies, never change the
rate-limit key, and never be treated as a trusted HTTPS hop.
"""

from __future__ import annotations

import os
from typing import Any, Optional

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_ENV_TRUST_PROXY = "LIBRARIAN_TRUST_PROXY_HEADERS"


def trust_proxy_headers() -> bool:
    """True only when the operator opted in behind a trusted reverse proxy.

    Default off. A laptop tunnel, a spoofed header on a LAN bind, or a
    mis-copied Compose file must not unlock forwarded proto/IP.
    """
    raw = (os.environ.get(_ENV_TRUST_PROXY) or "").strip().lower()
    return raw in _TRUTHY


def request_is_trusted_https(request: Optional[Any] = None) -> bool:
    """True when this request is HTTPS on the socket, or via a trusted proxy."""
    if request is None:
        return False
    scheme = ""
    try:
        scheme = str(request.url.scheme or "").lower()
    except Exception:
        scheme = ""
    if scheme == "https":
        return True
    if not trust_proxy_headers():
        return False
    forwarded = ""
    try:
        forwarded = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    except Exception:
        forwarded = ""
    return forwarded == "https"
