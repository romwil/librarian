"""NYT Books client — fixtures only, never a real token."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from librarian.nyt_books import (
    NytBooksClient,
    NytBooksError,
    clear_nyt_memory_cache,
    default_list_names,
    match_local_work,
    normalize_list_date,
    normalize_list_name,
    public_book,
)

FIXTURES = Path(__file__).parent / "fixtures" / "nyt"


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_nyt_memory_cache()
    yield
    clear_nyt_memory_cache()


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    assert "api-key=" in url
    assert "secret-nyt-key" in url or "test-key" in url
    if "/lists/names.json" in url:
        return httpx.Response(200, json=_load("list_names.json"))
    if "/lists/current/hardcover-fiction.json" in url:
        return httpx.Response(200, json=_load("hardcover_fiction_current.json"))
    if "/lists/2024-01-07/hardcover-fiction.json" in url:
        payload = _load("hardcover_fiction_current.json")
        payload["results"]["published_date"] = "2024-01-07"
        return httpx.Response(200, json=payload)
    if "/lists/" in url and ".json" in url:
        return httpx.Response(404, json={"fault": "not found"})
    return httpx.Response(500, json={"error": "unexpected"})


def test_normalize_list_name_and_date():
    assert normalize_list_name("Hardcover Fiction") == "hardcover-fiction"
    assert normalize_list_name("hardcover_fiction") == "hardcover-fiction"
    assert normalize_list_name("../evil") == ""
    assert normalize_list_date("") == "current"
    assert normalize_list_date("current") == "current"
    assert normalize_list_date("2024-01-07") == "2024-01-07"
    assert normalize_list_date("not-a-date") == ""


def test_fail_closed_without_key(tmp_path):
    client = NytBooksClient("", data_dir=tmp_path, transport=httpx.MockTransport(_handler))
    assert client.configured() is False
    assert client.list_names() == []
    payload = client.bestseller_list("hardcover-fiction")
    assert payload["configured"] is False
    assert payload["books"] == []
    assert payload["empty_reason"] == "missing_key"
    client.close()


def test_list_names_and_current_list(tmp_path):
    client = NytBooksClient(
        "test-key",
        data_dir=tmp_path,
        transport=httpx.MockTransport(_handler),
        cache_ttl_current=3600,
    )
    names = client.list_names()
    assert [row["list_name_encoded"] for row in names] == [
        "hardcover-fiction",
        "hardcover-nonfiction",
        "combined-print-and-e-book-fiction",
        "young-adult-hardcover",
    ]
    payload = client.bestseller_list("hardcover-fiction", date="current")
    assert payload["configured"] is True
    assert payload["published_date"] == "2026-09-13"
    assert len(payload["books"]) == 2
    first = payload["books"][0]
    assert first["title"] == "Dune"
    assert first["author"] == "Frank Herbert"
    assert first["isbn"] == "9781250883834"
    assert first["rank"] == 1
    assert first["kind"] == "book"
    # Second call hits disk/memory cache — handler would 500 if re-fetched wrongly.
    again = client.bestseller_list("hardcover-fiction", date="current")
    assert again["books"][0]["title"] == "Dune"
    dated = client.bestseller_list("hardcover-fiction", date="2024-01-07")
    assert dated["published_date"] == "2024-01-07"
    client.close()


def test_refused_key_raises(tmp_path):
    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"fault": "denied"})

    client = NytBooksClient("bad", data_dir=tmp_path, transport=httpx.MockTransport(refuse))
    with pytest.raises(NytBooksError, match="refused"):
        client.bestseller_list("hardcover-fiction")
    client.close()


def test_error_messages_never_include_key(tmp_path):
    secret = "nyt-super-secret-token"

    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"fault": secret})

    client = NytBooksClient(secret, data_dir=tmp_path, transport=httpx.MockTransport(refuse))
    with pytest.raises(NytBooksError) as caught:
        client.list_names()
    assert secret not in str(caught.value)
    client.close()


def test_match_local_work_isbn_then_title_author():
    book = public_book(
        {
            "title": "DUNE",
            "author": "Frank Herbert",
            "primary_isbn13": "9781250883834",
            "isbns": [{"isbn13": "9781250883834"}],
        }
    )
    by_isbn = match_local_work(
        book,
        [{"id": "w1", "title": "Other", "author": "X", "isbn": "9781250883834"}],
    )
    assert by_isbn and by_isbn["id"] == "w1"
    no_isbn = public_book({"title": "DUNE", "author": "Frank Herbert", "primary_isbn13": ""})
    by_title = match_local_work(
        no_isbn,
        [
            {"id": "w2", "title": "Dune", "author": "Frank Herbert", "isbn": ""},
            {"id": "w3", "title": "Dune", "author": "Someone Else", "isbn": ""},
        ],
    )
    assert by_title and by_title["id"] == "w2"
    assert match_local_work(no_isbn, [{"id": "w4", "title": "Dune", "author": "", "isbn": ""}]) is None


def test_default_list_names_cover_fiction_and_nonfiction():
    ids = {row["list_name_encoded"] for row in default_list_names()}
    assert "hardcover-fiction" in ids
    assert "hardcover-nonfiction" in ids


def _api_client(tmp_path, monkeypatch, **settings_fields):
    from fastapi.testclient import TestClient

    from librarian.config import Settings, save_settings
    from librarian.rate_limit import clear_rate_limits
    from librarian.sessions import clear_session_secret_cache
    from librarian.web.app import create_app

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    if settings_fields:
        save_settings(tmp_path, Settings(**settings_fields))
    clear_session_secret_cache()
    clear_rate_limits()
    return TestClient(create_app(tmp_path))


def test_api_nyt_fail_closed_without_key(tmp_path, monkeypatch):
    client = _api_client(tmp_path, monkeypatch, nyt_books_api_key="")
    login = client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    assert login.status_code == 200
    names = client.get("/api/lists/nyt/names")
    assert names.status_code == 200
    body = names.json()
    assert body["configured"] is False
    assert body["empty_reason"] == "missing_key"
    assert "New York Times" in body["empty_copy"] or "LLM" in body["empty_copy"] or "bestseller" in body["empty_copy"].lower()
    assert any(row["list_name_encoded"] == "hardcover-fiction" for row in body["names"])
    listing = client.get("/api/lists/nyt", params={"list": "hardcover-fiction"})
    assert listing.status_code == 200
    payload = listing.json()
    assert payload["configured"] is False
    assert payload["books"] == []
    assert "LLM" in payload["empty_copy"] or "API" in payload["empty_copy"] or "fallback" in payload["empty_copy"].lower()
