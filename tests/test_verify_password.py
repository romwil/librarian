"""P3-MED-01 — malformed salt must pay the same PBKDF2 cost as a missing-$ hash."""

from __future__ import annotations

import time

from librarian.auth import hash_password, verify_password


def test_verify_password_accepts_round_trip():
    stored = hash_password("correct-horse")
    assert verify_password("correct-horse", stored) is True
    assert verify_password("wrong-battery", stored) is False


def test_verify_password_rejects_missing_dollar():
    assert verify_password("anything", "not-a-hash") is False
    assert verify_password("anything", "") is False


def test_verify_password_rejects_malformed_salt_hex():
    assert verify_password("anything", "zz$deadbeef") is False
    assert verify_password("anything", "not-hex$00") is False


def test_malformed_salt_pays_dummy_pbkdf2_cost(monkeypatch):
    """Invalid salt hex must not short-circuit cheaper than a missing-$ reject."""
    monkeypatch.setenv("LIBRARIAN_PBKDF2_ITERATIONS", "20000")

    def _median_ms(stored: str, rounds: int = 7) -> float:
        samples = []
        for _ in range(rounds):
            start = time.perf_counter()
            assert verify_password("probe", stored) is False
            samples.append((time.perf_counter() - start) * 1000.0)
        samples.sort()
        return samples[len(samples) // 2]

    missing_dollar = _median_ms("not-a-hash")
    bad_salt = _median_ms("not-hex$00aabb")
    # Pre-fix bad-salt returned in microseconds; both paths must share PBKDF2 cost.
    ratio = bad_salt / max(missing_dollar, 0.01)
    assert 0.4 <= ratio <= 2.5
