"""Value tests for in-process rate limiter helpers."""

from __future__ import annotations

import os

from librarian.rate_limit import auth_local_login_limit


def test_auth_local_login_limit_default_is_ten(monkeypatch):
    monkeypatch.delenv("LIBRARIAN_E2E_RELAX_RATE_LIMITS", raising=False)
    assert auth_local_login_limit() == 10


def test_auth_local_login_limit_relaxes_for_e2e(monkeypatch):
    monkeypatch.setenv("LIBRARIAN_E2E_RELAX_RATE_LIMITS", "1")
    assert auth_local_login_limit() == 500
    monkeypatch.setenv("LIBRARIAN_E2E_RELAX_RATE_LIMITS", "0")
    assert auth_local_login_limit() == 10
