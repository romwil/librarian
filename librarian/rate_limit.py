"""In-process per-IP sliding-window rate limiter."""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

from fastapi import HTTPException, Request

from librarian.proxy import trust_proxy_headers

_limiter_lock = threading.Lock()
_hits: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)


def client_ip(request: Request) -> str:
    """Visible client IP. Ignore ``X-Forwarded-For`` unless proxy trust is on."""
    if trust_proxy_headers():
        forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        if forwarded:
            return forwarded
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def auth_local_login_limit() -> int:
    """Login attempts per window. E2E suite may relax via env (throwaway DATA_DIR only)."""
    if os.environ.get("LIBRARIAN_E2E_RELAX_RATE_LIMITS") == "1":
        return 500
    return 10


def enforce_rate_limit(
    request: Request,
    *,
    bucket: str,
    limit: int,
    window_seconds: float = 60.0,
) -> None:
    now = time.monotonic()
    cutoff = now - window_seconds
    key = client_ip(request)
    with _limiter_lock:
        queue = _hits[(bucket, key)]
        while queue and queue[0] < cutoff:
            queue.popleft()
        if len(queue) >= limit:
            retry_after = max(1, int(window_seconds - (now - queue[0])) + 1)
            raise HTTPException(
                status_code=429,
                detail="Too many requests",
                headers={"Retry-After": str(retry_after)},
            )
        queue.append(now)


def clear_rate_limits() -> None:
    """Test helper."""
    with _limiter_lock:
        _hits.clear()
