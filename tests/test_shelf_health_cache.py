"""Shelf-health SWR cache — Maintain paint must never wait on blend walks."""

from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient

from librarian.config import Settings
from librarian.db import Database
from librarian.shelf_health import CHOWN_COMMAND
from librarian.shelf_health_cache import (
    SOFT_TTL_SECONDS,
    clear_shelf_health_cache,
    get_shelf_health_snapshot,
    invalidate_shelf_health_cache,
    refresh_shelf_health_snapshot,
    wait_shelf_health_idle,
)
from librarian.web.app import create_app


def _owner_client(tmp_path):
    clear_shelf_health_cache()
    client = TestClient(create_app(tmp_path))
    login = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
    )
    assert login.status_code == 200
    return client


def _wait_ready(client, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    body = {}
    while time.monotonic() < deadline:
        body = client.get("/api/maintain/shelf-health").json()
        if not body.get("refreshing"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"shelf-health stayed refreshing: {body}")


def test_cold_miss_returns_warming_without_waiting_on_slow_builder(tmp_path):
    clear_shelf_health_cache()
    db = Database(tmp_path / "librarian.db")
    settings = Settings(books_root=str(tmp_path / "books"))
    (tmp_path / "books").mkdir()
    started = threading.Event()
    release = threading.Event()

    def slow_builder():
        started.set()
        assert release.wait(timeout=2.0)
        return {
            "roots": [{"field": "books_root", "label": "Books", "writable": True}],
            "locked_count": 0,
            "ok": True,
            "chown_tip": "tip",
            "chown_command": CHOWN_COMMAND,
            "puid": "",
            "pgid": "",
            "score": {
                "pulse": "calm",
                "presence": "The shelves feel settled.",
                "tend": None,
                "ok": True,
                "signals": {
                    "locked_roots": 0,
                    "extra_files": 0,
                    "unshelved_shells": 0,
                    "comic_book_blends": 0,
                },
            },
        }

    t0 = time.monotonic()
    first = get_shelf_health_snapshot(db, settings, builder=slow_builder, cold_wait=0.0)
    elapsed = time.monotonic() - t0
    assert elapsed < 0.5, f"cold miss blocked for {elapsed:.2f}s"
    assert first["refreshing"] is True
    assert first["cached"] is False
    assert first["generated_at"] is None
    assert started.wait(timeout=1.0)

    release.set()
    assert wait_shelf_health_idle(timeout=2.0)
    second = get_shelf_health_snapshot(db, settings, builder=slow_builder)
    assert second["refreshing"] is False
    assert second["cached"] is True
    assert second["stale"] is False
    assert second["generated_at"]
    assert second["ok"] is True
    assert len(second["roots"]) == 1


def test_soft_ttl_expiry_serves_stale_and_refreshes(tmp_path, monkeypatch):
    clear_shelf_health_cache()
    db = Database(tmp_path / "librarian.db")
    settings = Settings(books_root=str(tmp_path / "books"))
    (tmp_path / "books").mkdir()
    builds = {"n": 0}

    def counting_builder():
        builds["n"] += 1
        return {
            "roots": [],
            "locked_count": 0,
            "ok": True,
            "chown_tip": "tip",
            "chown_command": CHOWN_COMMAND,
            "puid": "",
            "pgid": "",
            "score": {
                "pulse": "calm",
                "presence": "settled",
                "tend": None,
                "ok": True,
                "signals": {
                    "locked_roots": 0,
                    "extra_files": 0,
                    "unshelved_shells": 0,
                    "comic_book_blends": builds["n"],
                },
            },
        }

    fresh = refresh_shelf_health_snapshot(db, settings, builder=counting_builder)
    assert fresh["cached"] is True
    assert fresh["score"]["signals"]["comic_book_blends"] == 1
    assert builds["n"] == 1

    monkeypatch.setattr(
        "librarian.shelf_health_cache.SOFT_TTL_SECONDS",
        0.01,
    )
    time.sleep(0.02)
    stale = get_shelf_health_snapshot(db, settings, builder=counting_builder)
    assert stale["stale"] is True
    assert stale["cached"] is True
    assert stale["refreshing"] is True
    # Stale paint still has the previous snapshot.
    assert stale["score"]["signals"]["comic_book_blends"] == 1
    assert wait_shelf_health_idle(timeout=2.0)
    rebuilt = get_shelf_health_snapshot(db, settings, builder=counting_builder)
    assert rebuilt["stale"] is False
    assert rebuilt["score"]["signals"]["comic_book_blends"] == 2
    assert builds["n"] == 2


def test_invalidate_marks_snapshot_soft_stale(tmp_path):
    clear_shelf_health_cache()
    db = Database(tmp_path / "librarian.db")
    settings = Settings(books_root=str(tmp_path / "books"))
    (tmp_path / "books").mkdir()
    refresh_shelf_health_snapshot(
        db,
        settings,
        builder=lambda: {
            "roots": [],
            "locked_count": 0,
            "ok": True,
            "chown_tip": "tip",
            "chown_command": CHOWN_COMMAND,
            "puid": "",
            "pgid": "",
            "score": {
                "pulse": "calm",
                "presence": "settled",
                "tend": None,
                "ok": True,
                "signals": {
                    "locked_roots": 0,
                    "extra_files": 0,
                    "unshelved_shells": 0,
                    "comic_book_blends": 0,
                },
            },
        },
    )
    invalidate_shelf_health_cache()
    rebuilt = {"done": False}

    def builder():
        rebuilt["done"] = True
        return {
            "roots": [],
            "locked_count": 1,
            "ok": False,
            "chown_tip": "tip",
            "chown_command": CHOWN_COMMAND,
            "puid": "",
            "pgid": "",
            "score": {
                "pulse": "needs_you",
                "presence": "locked",
                "tend": {"kind": "shelf_health"},
                "ok": False,
                "signals": {
                    "locked_roots": 1,
                    "extra_files": 0,
                    "unshelved_shells": 0,
                    "comic_book_blends": 0,
                },
            },
        }

    stale = get_shelf_health_snapshot(db, settings, builder=builder)
    assert stale["stale"] is True
    assert stale["locked_count"] == 0
    assert wait_shelf_health_idle(timeout=2.0)
    assert rebuilt["done"] is True


def test_maintain_shelf_health_route_is_fast_when_builder_is_slow(tmp_path, monkeypatch):
    client = _owner_client(tmp_path)
    release = threading.Event()

    def slow_build(db, settings):
        release.wait(timeout=2.0)
        return {
            "roots": [],
            "locked_count": 0,
            "ok": True,
            "chown_tip": "tip",
            "chown_command": CHOWN_COMMAND,
            "puid": "",
            "pgid": "",
            "score": {
                "pulse": "calm",
                "presence": "settled",
                "tend": None,
                "ok": True,
                "signals": {
                    "locked_roots": 0,
                    "extra_files": 0,
                    "unshelved_shells": 0,
                    "comic_book_blends": 0,
                },
            },
        }

    monkeypatch.setattr(
        "librarian.shelf_health_cache.build_shelf_health_snapshot",
        slow_build,
    )
    clear_shelf_health_cache()
    t0 = time.monotonic()
    response = client.get("/api/maintain/shelf-health")
    elapsed = time.monotonic() - t0
    assert response.status_code == 200
    assert elapsed < 1.0, f"route blocked for {elapsed:.2f}s"
    body = response.json()
    assert body["refreshing"] is True
    release.set()
    assert wait_shelf_health_idle(timeout=2.0)


def test_maintain_shelf_health_warm_hit_under_budget(tmp_path):
    client = _owner_client(tmp_path)
    ready = _wait_ready(client)
    assert ready["cached"] is True
    assert "score" in ready
    assert ready["chown_command"] == CHOWN_COMMAND

    times = []
    for _ in range(5):
        t0 = time.monotonic()
        response = client.get("/api/maintain/shelf-health")
        times.append(time.monotonic() - t0)
        assert response.status_code == 200
        body = response.json()
        assert body["refreshing"] is False
        assert body["cached"] is True
    p95 = sorted(times)[int(len(times) * 0.95) - 1] if len(times) > 1 else times[0]
    # Empty catalog warm hits should be far under the 2s SLO.
    assert p95 < 0.5, f"warm p95 {p95:.3f}s exceeded budget"
    assert SOFT_TTL_SECONDS >= 60


def test_morning_brief_does_not_block_on_slow_shelf_health(tmp_path, monkeypatch):
    client = _owner_client(tmp_path)
    release = threading.Event()

    def slow_build(db, settings):
        release.wait(timeout=2.0)
        return {
            "roots": [],
            "locked_count": 0,
            "ok": True,
            "chown_tip": "tip",
            "chown_command": CHOWN_COMMAND,
            "puid": "",
            "pgid": "",
            "score": {
                "pulse": "calm",
                "presence": "settled",
                "tend": None,
                "ok": True,
                "signals": {
                    "locked_roots": 0,
                    "extra_files": 0,
                    "unshelved_shells": 0,
                    "comic_book_blends": 0,
                },
            },
        }

    monkeypatch.setattr(
        "librarian.shelf_health_cache.build_shelf_health_snapshot",
        slow_build,
    )
    clear_shelf_health_cache()
    t0 = time.monotonic()
    response = client.get("/api/maintain/morning-brief")
    elapsed = time.monotonic() - t0
    assert response.status_code == 200
    assert elapsed < 1.0, f"morning-brief blocked for {elapsed:.2f}s"
    body = response.json()
    assert "items" in body
    assert body.get("shelf_health_refreshing") is True
    release.set()
    assert wait_shelf_health_idle(timeout=2.0)
