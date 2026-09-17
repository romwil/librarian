"""Serve /release-notes.json from frontend/dist (not only Vite /assets)."""

from __future__ import annotations

from unittest import mock

from fastapi.testclient import TestClient

from librarian.web.app import FRONTEND_DIST, create_app


def test_release_notes_json_served(tmp_path):
    dist_notes = FRONTEND_DIST / "release-notes.json"
    public_notes = FRONTEND_DIST.parent / "public" / "release-notes.json"
    if not dist_notes.is_file() and not public_notes.is_file():
        import pytest

        pytest.skip("release-notes.json not present in frontend/dist or public")

    client = TestClient(create_app(tmp_path))
    response = client.get("/release-notes.json")
    assert response.status_code == 200
    assert "application/json" in response.headers.get("content-type", "")
    body = response.json()
    assert "releases" in body
    assert isinstance(body["releases"], list)
    assert len(body["releases"]) >= 1
    assert body["releases"][0].get("version")


def test_release_notes_json_404_when_missing(tmp_path):
    empty_dist = tmp_path / "empty-frontend" / "dist"
    empty_dist.mkdir(parents=True)
    with mock.patch("librarian.web.app.FRONTEND_DIST", empty_dist):
        client = TestClient(create_app(tmp_path / "data"))
        response = client.get("/release-notes.json")
        assert response.status_code == 404


def test_release_notes_prefers_newer_of_dist_and_public(tmp_path):
    import os
    import time

    dist = tmp_path / "frontend" / "dist"
    public = tmp_path / "frontend" / "public"
    dist.mkdir(parents=True)
    public.mkdir(parents=True)
    dist_file = dist / "release-notes.json"
    public_file = public / "release-notes.json"
    dist_file.write_text(
        '{"generated_at":"2026-01-01T00:00:00Z","releases":[{"version":"0.1.0","date":"2026-01-01","summary":"","sections":[]}]}',
        encoding="utf-8",
    )
    public_file.write_text(
        '{"generated_at":"2026-09-17T00:00:00Z","releases":[{"version":"9.9.9","date":"2026-09-17","summary":"","sections":[]}]}',
        encoding="utf-8",
    )
    now = time.time()
    os.utime(dist_file, (now - 100, now - 100))
    os.utime(public_file, (now, now))

    with mock.patch("librarian.web.app.FRONTEND_DIST", dist):
        client = TestClient(create_app(tmp_path / "data"))
        response = client.get("/release-notes.json")
        assert response.status_code == 200
        assert response.json()["releases"][0]["version"] == "9.9.9"
