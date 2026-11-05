"""Shelf health permission report — Maintain Surface."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from librarian.config import Settings
from librarian.shelf_health import CHOWN_COMMAND, shelf_permission_report
from librarian.shelf_health_cache import clear_shelf_health_cache, wait_shelf_health_idle
from librarian.web.app import create_app


def _wait_shelf_health(client, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    body = {}
    while time.monotonic() < deadline:
        body = client.get("/api/maintain/shelf-health").json()
        if not body.get("refreshing"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"shelf-health stayed refreshing: {body}")


def test_shelf_permission_report_marks_writable_roots(tmp_path):
    books = tmp_path / "books"
    books.mkdir()
    settings = Settings(
        books_root=str(books),
        magazines_root="",
        comics_root="",
        audiobooks_root="",
        music_root="",
    )
    report = shelf_permission_report(settings)
    assert report["ok"] is True
    assert report["locked_count"] == 0
    assert report["chown_command"] == CHOWN_COMMAND
    assert len(report["roots"]) == 1
    assert report["roots"][0]["writable"] is True
    assert report["roots"][0]["label"] == "Books"


def test_shelf_permission_report_counts_locked_roots(tmp_path, monkeypatch):
    locked = tmp_path / "locked"
    locked.mkdir()
    settings = Settings(
        books_root=str(locked),
        magazines_root="",
        comics_root="",
        audiobooks_root="",
        music_root="",
    )
    real_write = Path.write_text

    def _deny(self, *args, **kwargs):
        if self.name == ".librarian-write-probe":
            raise PermissionError(13, "Permission denied", str(self))
        return real_write(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _deny)
    report = shelf_permission_report(settings)
    assert report["ok"] is False
    assert report["locked_count"] == 1
    assert report["roots"][0]["writable"] is False
    assert "permission" in report["roots"][0]["detail"]


def test_maintain_shelf_health_owner_only(tmp_path):
    clear_shelf_health_cache()
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/maintain/shelf-health")
    assert response.status_code == 401
    login = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
    )
    assert login.status_code == 200
    response = client.get("/api/maintain/shelf-health")
    assert response.status_code == 200
    # Cold miss may warm asynchronously; wait for the snapshot.
    assert wait_shelf_health_idle(timeout=5.0)
    body = _wait_shelf_health(client)
    assert "roots" in body
    assert body["chown_command"] == CHOWN_COMMAND
    assert "chown" in body["chown_tip"]
    assert body["cached"] is True
    assert body["refreshing"] is False
    assert body["generated_at"]
