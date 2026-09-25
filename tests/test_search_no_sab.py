"""Search / Discover / suggest must never touch SABnzbd — only explicit Request may."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from librarian.web.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    monkeypatch.setenv("LIBRARIAN_SESSION_SECRET", "test-session-secret-not-dev-default-xx")
    monkeypatch.setenv("LIBRARIAN_SKIP_APP_BOOT", "1")
    root = tmp_path / "data"
    root.mkdir()
    app = create_app(root)
    with TestClient(app) as test_client:
        yield test_client


def _login(client, username="owner", password="password123"):
    response = client.post("/api/auth/local/login", json={"username": username, "password": password})
    assert response.status_code == 200


def test_search_and_discover_never_call_sab(client, monkeypatch):
    calls = []

    def forbid_addurl(self, *args, **kwargs):
        calls.append("addurl")
        raise AssertionError("Search must not call SAB addurl")

    def forbid_addfile(self, *args, **kwargs):
        calls.append("addfile")
        raise AssertionError("Search must not call SAB addfile")

    monkeypatch.setattr("librarian.sabnzbd.SABClient.addurl", forbid_addurl)
    monkeypatch.setattr("librarian.sabnzbd.SABClient.addfile", forbid_addfile)
    monkeypatch.setattr(
        "librarian.web.routers.catalog.search_and_rank",
        lambda *args, **kwargs: {"results": [], "error": None},
    )
    monkeypatch.setattr("librarian.web.routers.catalog.discover_beyond", lambda *args, **kwargs: ([], [], None))

    _login(client)
    search = client.get("/api/search", params={"q": "NFL", "beyond": 1, "kind": "book"})
    assert search.status_code == 200
    suggest = client.get("/api/suggest", params={"field": "title", "q": "a"})
    assert suggest.status_code == 200
    discover = client.get("/api/discover", params={"kind": "book"})
    assert discover.status_code == 200
    assert calls == []
