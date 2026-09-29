"""In-process per-IP sliding-window rate limiter."""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Deque, Dict, Tuple

from fastapi import HTTPException, Request

from librarian.proxy import trust_proxy_headers

_limiter_lock = threading.Lock()
_hits: Dict[Tuple[str, str], Deque[float]] = {}
_last_sweep_at = 0.0
# Opportunistic sweep cadence + idle window for keys that never return.
_SWEEP_EVERY_S = 60.0
_SWEEP_MAX_WINDOW_S = 300.0


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


def _prune_deque(queue: Deque[float], cutoff: float) -> None:
    while queue and queue[0] < cutoff:
        queue.popleft()


def _sweep_expired_unlocked(now: float) -> None:
    """Drop idle/expired keys. Caller must hold ``_limiter_lock``."""
    global _last_sweep_at
    if now - _last_sweep_at < _SWEEP_EVERY_S:
        return
    _last_sweep_at = now
    cutoff = now - _SWEEP_MAX_WINDOW_S
    stale: list[Tuple[str, str]] = []
    for key, queue in _hits.items():
        _prune_deque(queue, cutoff)
        if not queue:
            stale.append(key)
    for key in stale:
        _hits.pop(key, None)


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
    slot = (bucket, key)
    with _limiter_lock:
        _sweep_expired_unlocked(now)
        queue = _hits.get(slot)
        if queue is None:
            queue = deque()
        else:
            _prune_deque(queue, cutoff)
            if not queue:
                _hits.pop(slot, None)
                queue = deque()
        if len(queue) >= limit:
            _hits[slot] = queue
            retry_after = max(1, int(window_seconds - (now - queue[0])) + 1)
            raise HTTPException(
                status_code=429,
                detail="Too many requests",
                headers={"Retry-After": str(retry_after)},
            )
        queue.append(now)
        _hits[slot] = queue


def clear_rate_limits() -> None:
    """Test helper."""
    global _last_sweep_at
    with _limiter_lock:
        _hits.clear()
        _last_sweep_at = 0.0
