"""SEC-009 / SEC-010 / PERF-010: CSP, nosniff, gzip, immutable hashed assets."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from librarian.web.app import create_app
from librarian.web.security import APP_CSP, FILE_CSP, FileSkipGZipMiddleware, should_gzip_path


def _assert_baseline(response):
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "no-referrer"
    assert "camera=()" in (response.headers.get("permissions-policy") or "")
    assert response.headers.get("cross-origin-opener-policy") == "same-origin"
    csp = response.headers.get("content-security-policy") or ""
    assert csp
    assert "fonts.googleapis.com" not in csp
    assert "fonts.gstatic.com" not in csp
    assert "frame-ancestors 'none'" in csp
    assert response.headers.get("x-robots-tag") == "noindex, nofollow"


def test_health_carries_security_headers(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/health")
    assert response.status_code == 200
    _assert_baseline(response)
    assert response.headers.get("content-security-policy") == APP_CSP
    assert "script-src 'self' blob:" in APP_CSP
    assert "worker-src 'self' blob:" in APP_CSP
    assert "'unsafe-inline'" not in APP_CSP.split("script-src")[1].split(";")[0]
    assert "fonts.googleapis.com" not in APP_CSP


@contextmanager
def _spa_client(tmp_path: Path):
    dist = tmp_path / "frontend" / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Librarian</title>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('ok');\n" + ("x" * 2048), encoding="utf-8")
    data = tmp_path / "data"
    data.mkdir()
    with mock.patch("librarian.web.app.FRONTEND_DIST", dist):
        yield TestClient(create_app(data)), dist


def test_spa_document_csp_and_no_cache_index(tmp_path):
    with _spa_client(tmp_path) as (client, _dist):
        response = client.get("/")
        assert response.status_code == 200
        _assert_baseline(response)
        assert response.headers.get("content-security-policy") == APP_CSP
        assert "no-cache" in (response.headers.get("cache-control") or "")
        assert "immutable" not in (response.headers.get("cache-control") or "")


def test_hashed_assets_are_immutable(tmp_path):
    with _spa_client(tmp_path) as (client, _dist):
        response = client.get("/assets/app.js")
        assert response.status_code == 200
        _assert_baseline(response)
        assert response.headers.get("cache-control") == "public, max-age=31536000, immutable"
        assert response.content.startswith(b"console.log")


def test_volume_paths_are_not_gzip_candidates():
    assert should_gzip_path("/api/health") is True
    assert should_gzip_path("/api/works/abc/download") is False
    assert should_gzip_path("/api/works/abc/stream") is False
    assert should_gzip_path("/assets/app.js") is True


def test_gzip_middleware_is_installed(tmp_path):
    app = create_app(tmp_path)
    assert any(item.cls is FileSkipGZipMiddleware for item in app.user_middleware)


def test_download_uses_sandbox_csp(tmp_path, monkeypatch):
    from librarian.db import Database
    from librarian.rate_limit import clear_rate_limits
    from librarian.sessions import clear_session_secret_cache

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    clear_rate_limits()
    client = TestClient(create_app(tmp_path))
    assert (
        client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"}).status_code
        == 200
    )
    db = Database(tmp_path / "librarian.db")
    folder = tmp_path / "incoming" / "Mix"
    folder.mkdir(parents=True)
    flac = folder / "track.flac"
    flac.write_bytes(b"fLaCfake")
    work = db.upsert_work(
        {
            "kind": "music",
            "title": "Mix",
            "author": "Various",
            "music_state": "incoming",
            "folder_path": str(folder),
        }
    )
    db.add_file({"work_id": work["id"], "path": str(flac), "filename": flac.name, "kind": "music", "size": 8})
    response = client.get(f"/api/works/{work['id']}/download")
    assert response.status_code == 200
    assert response.headers.get("content-security-policy") == FILE_CSP
    assert response.headers.get("x-content-type-options") == "nosniff"


def test_volume_download_is_not_gzipped_and_accepts_ranges(tmp_path, monkeypatch):
    from librarian.db import Database
    from librarian.rate_limit import clear_rate_limits
    from librarian.sessions import clear_session_secret_cache

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    clear_rate_limits()
    client = TestClient(create_app(tmp_path))
    assert (
        client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"}).status_code
        == 200
    )
    db = Database(tmp_path / "librarian.db")
    folder = tmp_path / "books" / "Tia Levings" / "A Well Trained Wife"
    folder.mkdir(parents=True)
    body = b"%PDF-1.4\n" + (b"x" * 8000) + b"\n%%EOF\n"
    pdf = folder / "A Well Trained Wife.pdf"
    pdf.write_bytes(body)
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "A Well Trained Wife",
            "author": "Tia Levings",
            "folder_path": str(folder),
        }
    )
    db.add_file({"work_id": work["id"], "path": str(pdf), "filename": pdf.name, "kind": "book", "size": len(body)})
    url = f"/api/works/{work['id']}/download"
    full = client.get(url, params={"inline": 1}, headers={"Accept-Encoding": "gzip"})
    assert full.status_code == 200
    assert "gzip" not in (full.headers.get("content-encoding") or "").lower()
    assert full.headers.get("accept-ranges") == "bytes"
    assert full.content == body
    start = client.get(url, params={"inline": 1}, headers={"Range": "bytes=0-7"})
    assert start.status_code == 206
    assert start.content == b"%PDF-1.4"
    tail = client.get(url, params={"inline": 1}, headers={"Range": "bytes=-6"})
    assert tail.status_code == 206
    assert tail.content == b"%%EOF\n"
