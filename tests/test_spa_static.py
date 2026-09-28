"""SPA catch-all must not escape FRONTEND_DIST (P3-CRIT-01)."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from librarian.web.app import create_app


@contextmanager
def _spa_app(tmp_path: Path):
    """Minimal FRONTEND_DIST + secret outside it; patch stays live for requests."""
    dist = tmp_path / "frontend" / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Librarian</title>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('ok')", encoding="utf-8")

    secret = tmp_path / "config" / "settings.json"
    secret.parent.mkdir(parents=True)
    secret.write_text('{"api_token":"leaked-secret-token"}', encoding="utf-8")

    data = tmp_path / "data"
    data.mkdir()
    with mock.patch("librarian.web.app.FRONTEND_DIST", dist):
        client = TestClient(create_app(data))
        yield client, dist, secret


def test_spa_serves_in_dist_file(tmp_path):
    with _spa_app(tmp_path) as (client, dist, _secret):
        # Prefer a path the catch-all owns (not the /assets StaticFiles mount).
        (dist / "favicon.ico").write_bytes(b"ico-bytes")
        response = client.get("/favicon.ico")
        assert response.status_code == 200
        assert response.content == b"ico-bytes"


def test_spa_falls_through_to_index_for_client_routes(tmp_path):
    with _spa_app(tmp_path) as (client, _dist, _secret):
        response = client.get("/hall")
        assert response.status_code == 200
        assert "Librarian" in response.text


def test_spa_rejects_dotdot_traversal_to_secret(tmp_path):
    """Unauthenticated catch-all must not follow .. out of FRONTEND_DIST."""
    with _spa_app(tmp_path) as (client, _dist, secret):
        # Relative climb from a plausible static path — the pre-jail bug served any is_file().
        response = client.get("/assets/../../config/settings.json")
        body = response.text
        assert "leaked-secret-token" not in body
        assert secret.read_text(encoding="utf-8") == '{"api_token":"leaked-secret-token"}'
        # Jail falls through to SPA shell (or 404 if index missing) — never the secret.
        assert response.status_code in (200, 404)
        if response.status_code == 200:
            assert "Librarian" in body or "<!doctype html>" in body.lower()


def test_spa_rejects_absolute_style_escape_via_nested_dotdot(tmp_path):
    with _spa_app(tmp_path) as (client, _dist, secret):
        # Extra depth so resolve() lands on the secret if the jail were absent.
        response = client.get("/x/y/z/../../../../config/settings.json")
        assert "leaked-secret-token" not in response.text
        assert secret.is_file()


def test_spa_symlink_escape_is_jailed(tmp_path):
    """resolve() follows symlinks; relative_to must still refuse outside root."""
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Librarian</title>", encoding="utf-8")

    secret = tmp_path / "outside" / "secret.txt"
    secret.parent.mkdir(parents=True)
    secret.write_text("symlink-escape-payload", encoding="utf-8")
    link = dist / "escape.txt"
    try:
        link.symlink_to(secret)
    except OSError:
        import pytest

        pytest.skip("symlink creation not permitted in this environment")

    data = tmp_path / "data"
    data.mkdir()
    with mock.patch("librarian.web.app.FRONTEND_DIST", dist):
        client = TestClient(create_app(data))
        response = client.get("/escape.txt")
        assert "symlink-escape-payload" not in response.text
        assert response.status_code in (200, 404)
