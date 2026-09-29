"""Value tests for in-process rate limiter helpers."""

from __future__ import annotations

import time
from collections import deque
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from librarian import rate_limit
from librarian.rate_limit import auth_local_login_limit, clear_rate_limits, enforce_rate_limit


def _request(host: str = "10.0.0.1") -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host=host), headers={})


def test_auth_local_login_limit_default_is_ten(monkeypatch):
    monkeypatch.delenv("LIBRARIAN_E2E_RELAX_RATE_LIMITS", raising=False)
    assert auth_local_login_limit() == 10


def test_auth_local_login_limit_relaxes_for_e2e(monkeypatch):
    monkeypatch.setenv("LIBRARIAN_E2E_RELAX_RATE_LIMITS", "1")
    assert auth_local_login_limit() == 500
    monkeypatch.setenv("LIBRARIAN_E2E_RELAX_RATE_LIMITS", "0")
    assert auth_local_login_limit() == 10


def test_enforce_evicts_empty_queue_after_prune():
    clear_rate_limits()
    slot = ("login", "10.0.0.9")
    now = time.monotonic()
    with rate_limit._limiter_lock:
        rate_limit._hits[slot] = deque([now - 120.0])  # fully outside 60s window
    enforce_rate_limit(_request("10.0.0.9"), bucket="login", limit=5, window_seconds=60.0)
    with rate_limit._limiter_lock:
        # Old stamp pruned; new hit keeps the key (not an idle empty deque).
        assert slot in rate_limit._hits
        assert len(rate_limit._hits[slot]) == 1


def test_sweep_evicts_idle_expired_keys(monkeypatch):
    clear_rate_limits()
    now = time.monotonic()
    idle = ("auth", "192.0.2.50")
    live = ("auth", "192.0.2.51")
    with rate_limit._limiter_lock:
        rate_limit._hits[idle] = deque([now - 1000.0])
        rate_limit._hits[live] = deque([now - 1.0])
        rate_limit._last_sweep_at = 0.0
    # Force sweep interval elapsed.
    monkeypatch.setattr(rate_limit, "_SWEEP_EVERY_S", 0.0)
    enforce_rate_limit(_request("192.0.2.51"), bucket="auth", limit=10, window_seconds=60.0)
    with rate_limit._limiter_lock:
        assert idle not in rate_limit._hits
        assert live in rate_limit._hits
        assert len(rate_limit._hits[live]) == 2  # prior + this call


def test_enforce_still_429_when_over_limit():
    clear_rate_limits()
    req = _request("10.0.0.8")
    for _ in range(3):
        enforce_rate_limit(req, bucket="burst", limit=3, window_seconds=60.0)
    with pytest.raises(HTTPException) as exc:
        enforce_rate_limit(req, bucket="burst", limit=3, window_seconds=60.0)
    assert exc.value.status_code == 429
