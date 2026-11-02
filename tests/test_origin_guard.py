"""SEC-013: same-origin signal on every state-changing /api request."""

from fastapi.testclient import TestClient

from librarian.web.app import create_app
from librarian.web.security import CROSS_ORIGIN_REFUSED, MISSING_HOUSEHOLD_HEADER

SKIP = {"X-Librarian-Test": "skip-origin"}


def test_login_without_origin_is_refused(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
        headers=SKIP,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == CROSS_ORIGIN_REFUSED
    assert response.headers.get("x-content-type-options") == "nosniff"


def test_login_foreign_origin_is_refused(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
        headers={**SKIP, "Origin": "http://10.10.1.202:8788", "X-Librarian": "1"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == CROSS_ORIGIN_REFUSED


def test_login_missing_household_header_is_refused(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
        headers={**SKIP, "Origin": "http://testserver"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == MISSING_HOUSEHOLD_HEADER


def test_login_same_origin_with_header_succeeds(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
        headers={**SKIP, "Origin": "http://testserver", "X-Librarian": "1"},
    )
    assert response.status_code == 200


def test_referer_fallback_matches_origin(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
        headers={
            **SKIP,
            "Referer": "http://testserver/login",
            "X-Librarian": "1",
        },
    )
    assert response.status_code == 200


def test_get_does_not_require_origin(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/health", headers=SKIP)
    assert response.status_code == 200


def test_trusted_proxy_matches_forwarded_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_TRUST_PROXY_HEADERS", "1")
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
        headers={
            **SKIP,
            "Origin": "https://librarian.home.arpa",
            "X-Librarian": "1",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "librarian.home.arpa",
        },
    )
    assert response.status_code == 200


def test_untrusted_forwarded_origin_is_ignored(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
        headers={
            **SKIP,
            "Origin": "https://librarian.home.arpa",
            "X-Librarian": "1",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "librarian.home.arpa",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == CROSS_ORIGIN_REFUSED


def test_trusted_proxy_uses_host_when_forwarded_host_missing(tmp_path, monkeypatch):
    """Cloudflare Tunnel often sets Proto + Host, not X-Forwarded-Host."""
    monkeypatch.setenv("LIBRARIAN_TRUST_PROXY_HEADERS", "1")
    # Socket URL is HTTP; browser Origin is HTTPS. Trust + Proto must lift scheme.
    client = TestClient(create_app(tmp_path), base_url="http://librarian.automat.vip")
    response = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
        headers={
            **SKIP,
            "Origin": "https://librarian.automat.vip",
            "X-Librarian": "1",
            "X-Forwarded-Proto": "https",
        },
    )
    assert response.status_code == 200


def test_public_base_url_origin_is_allowed(tmp_path):
    from librarian.config import Settings, save_settings

    save_settings(tmp_path, Settings(public_base_url="https://librarian.automat.vip"))
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
        headers={
            **SKIP,
            "Origin": "https://librarian.automat.vip",
            "X-Librarian": "1",
        },
    )
    assert response.status_code == 200


def test_public_origins_env_allows_listed_host(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_PUBLIC_ORIGINS", "https://librarian.automat.vip")
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
        headers={
            **SKIP,
            "Origin": "https://librarian.automat.vip",
            "X-Librarian": "1",
        },
    )
    assert response.status_code == 200


def test_foreign_origin_still_refused_with_public_base_url(tmp_path):
    from librarian.config import Settings, save_settings

    save_settings(tmp_path, Settings(public_base_url="https://librarian.automat.vip"))
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
        headers={
            **SKIP,
            "Origin": "https://evil.example",
            "X-Librarian": "1",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == CROSS_ORIGIN_REFUSED
