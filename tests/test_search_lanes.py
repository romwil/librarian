"""Search lanes: local first, reader stays on the shelf, owner beyond is a second call."""

from __future__ import annotations

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.rate_limit import clear_rate_limits
from librarian.sabnzbd import SABClient
from librarian.services.search import clear_beyond_cache
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def _client(tmp_path, monkeypatch, **settings_fields):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    monkeypatch.setattr("librarian.config.load_dotenv", lambda path=None: None)
    for name in (
        "LLM_API_KEY",
        "LLM_PROVIDER",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_AI_API_KEY",
        "NZBFINDER_API_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("librarian.indexers.rank.client_from_settings", lambda *a, **k: None)
    fields = {
        "llm_api_key": "",
        "llm_base_url": "",
        "llm_provider": "openai",
        "llm_profiles": {},
        "nzbfinder_api_token": "tok",
        "nzbfinder_url": "https://nzbfinder.test",
        **settings_fields,
    }
    save_settings(tmp_path, Settings(**fields))
    clear_session_secret_cache()
    clear_rate_limits()
    clear_beyond_cache()
    return TestClient(create_app(tmp_path))


def _login(client, username="owner", password="password123"):
    resp = client.post("/api/auth/local/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp


def _reader(client):
    minted = client.post("/api/invites", json={"role": "reader"})
    token = minted.json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    redeemed = client.post(
        "/api/invites/redeem/local",
        json={"token": token, "username": "reader1", "password": "password123"},
    )
    assert redeemed.status_code == 200


def _forbid_beyond(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("local search must not leave the house")

    monkeypatch.setattr("librarian.services.search.search_and_rank", boom)
    monkeypatch.setattr("librarian.services.search.search_public_domain", boom)


def test_local_search_ignores_beyond_flag_and_makes_no_outbound_calls(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    _forbid_beyond(monkeypatch)
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work({"kind": "book", "title": "Dune", "author": "Frank Herbert"})
    folder = tmp_path / "shelf" / str(work["id"])
    folder.mkdir(parents=True)
    path = folder / "dune.epub"
    path.write_bytes(b"epub")
    db.upsert_work({**work, "folder_path": str(folder)})
    db.upsert_file(
        {
            "work_id": work["id"],
            "path": str(path),
            "filename": path.name,
            "kind": "book",
            "size": path.stat().st_size,
        }
    )
    resp = client.get("/api/search", params={"q": "dune", "beyond": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert [row["title"] for row in body["local"]] == ["Dune"]
    assert body["beyond"] == []
    assert body["public_domain"] == []
    assert body["can_beyond"] is True


def test_reader_search_makes_zero_outbound_calls(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    _reader(client)
    _forbid_beyond(monkeypatch)
    resp = client.get("/api/search", params={"q": "coping with divorce", "beyond": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["beyond"] == []
    assert body["public_domain"] == []
    assert body["can_beyond"] is False
    assert client.get("/api/search/beyond", params={"q": "coping with divorce"}).status_code == 403


def test_reader_ask_files_wanted_without_searching_or_sab(tmp_path, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("SABnzbd was called before a person confirmed the slip")

    monkeypatch.setattr(SABClient, "addfile", boom)
    client = _client(tmp_path, monkeypatch)
    _login(client)
    _reader(client)
    _forbid_beyond(monkeypatch)
    resp = client.post(
        "/api/search/ask",
        json={"q": "Kindred", "title": "Kindred", "author": "Octavia Butler", "kind": "audiobook"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["searched"] is False
    assert body["item"]["status"] == "wanted"
    assert body["item"]["title"] == "Kindred"
    assert body["item"]["job_id"] is None
    db = Database(tmp_path / "librarian.db")
    try:
        assert db.list_jobs(limit=10) == []
        row = db.get_wanted(body["item"]["id"])
        assert row["status"] == "wanted"
        assert row["miss_streak"] == 0
    finally:
        db.close()


def test_reader_cannot_open_discover(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    _reader(client)
    _forbid_beyond(monkeypatch)
    assert client.get("/api/discover", params={"kind": "book"}).status_code == 403


def test_reader_cannot_find_beyond_a_wanted_row(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    added = client.post("/api/wanted", json={"title": "Kindred", "kind": "audiobook"})
    wanted_id = added.json()["item"]["id"]
    _reader(client)
    assert client.post(f"/api/wanted/{wanted_id}/beyond").status_code == 403


def test_beyond_cache_is_memory_only_and_skips_a_second_host_call(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    calls = []

    def fake_books_traced(self, *, query="", title="", author="", isbn="", cat=None, limit=25, default_kind="book"):
        calls.append(("books", title or query, isbn))
        hit = {"title": "Dune", "kind": "book", "guid": "g-dune", "isbn": isbn, "author": author}
        return {"raw": [hit], "accepted": [hit], "rejected": [], "default_kind": "book"}

    monkeypatch.setattr("librarian.nzbfinder.NZBFinderClient.books_traced", fake_books_traced)
    monkeypatch.setattr(
        "librarian.nzbfinder.NZBFinderClient.search_traced",
        lambda *a, **k: {"raw": [], "accepted": [], "rejected": [], "default_kind": ""},
    )
    monkeypatch.setattr("librarian.services.search.search_public_domain", lambda *a, **k: [])
    first = client.get("/api/search/beyond", params={"kind": "book", "title": "Dune"})
    second = client.get("/api/search/beyond", params={"kind": "book", "title": "Dune"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert first.json()["beyond"][0]["guid"] == "g-dune"
    assert len(calls) == 1
