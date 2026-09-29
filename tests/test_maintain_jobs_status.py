"""Multiplexed Maintain jobs status — one round-trip for the dock."""

from __future__ import annotations

from fastapi.testclient import TestClient

from librarian.web.app import create_app


def test_maintain_jobs_status_owner_only(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/maintain/jobs/status").status_code == 401

    login = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
    )
    assert login.status_code == 200
    response = client.get("/api/maintain/jobs/status")
    assert response.status_code == 200
    body = response.json()
    for key in ("scan", "enrich", "ingest", "extra_files"):
        assert key in body
        assert isinstance(body[key], dict)
        assert "status" in body[key]
    assert "extra_files_remaining" in body["extra_files"]
