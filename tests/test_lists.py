"""Curated LLM lists — mock LLM only, never a real token."""

from __future__ import annotations

import json

import httpx
import pytest

from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.identify import validated_isbn
from librarian.lists import (
    chase_missing_item,
    clear_lists_memory_cache,
    curated_list_payload,
    fetch_llm_list,
    match_books_to_catalog,
    normalize_list_book,
    normalize_list_books,
    parse_json_list_payload,
)
from librarian.llm import LLMClient
from librarian.nyt_books import match_local_work
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache


@pytest.fixture(autouse=True)
def _clear_lists_cache():
    clear_lists_memory_cache()
    yield
    clear_lists_memory_cache()


def test_validated_isbn_keeps_good_drops_bad():
    assert validated_isbn("9780441172719") == "9780441172719"
    assert validated_isbn("9780441172710") == ""  # bad check digit
    assert validated_isbn("not-an-isbn") == ""


def test_normalize_list_book_drops_invented_isbn():
    book = normalize_list_book(
        {"title": "Dune", "author": "Frank Herbert", "isbn": "9780441172710", "rank": 1}
    )
    assert book is not None
    assert book["title"] == "Dune"
    assert book["author"] == "Frank Herbert"
    assert book["isbn"] == ""
    assert book["isbns"] == []


def test_normalize_list_book_keeps_valid_isbn():
    book = normalize_list_book(
        {"title": "Dune", "author": "Frank Herbert", "isbn": "9780441172719", "rank": 2}
    )
    assert book is not None
    assert book["isbn"] == "9780441172719"
    assert "9780441172719" in book["isbns"]


def test_parse_json_list_payload_object_and_array():
    as_obj = parse_json_list_payload(
        json.dumps({"books": [{"title": "A", "author": "B"}], "display_name": "Fiction"})
    )
    assert len(as_obj["books"]) == 1
    assert as_obj["display_name"] == "Fiction"
    as_arr = parse_json_list_payload(json.dumps([{"title": "A", "author": "B"}]))
    assert len(as_arr["books"]) == 1


def test_match_books_to_catalog_book_and_audiobook(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert_work(
        {
            "id": "w-book",
            "kind": "book",
            "title": "Dune",
            "author": "Frank Herbert",
            "isbn": "9780441172719",
        }
    )
    db.upsert_work(
        {
            "id": "w-audio",
            "kind": "audiobook",
            "title": "Leftover",
            "author": "Someone",
            "isbn": "",
        }
    )
    db.upsert_work(
        {
            "id": "w-audio-dune",
            "kind": "audiobook",
            "title": "Dune",
            "author": "Frank Herbert",
            "isbn": "9780441172719",
        }
    )
    books = normalize_list_books(
        [
            {"title": "Dune", "author": "Frank Herbert", "isbn": "9780441172719"},
            {"title": "Missing", "author": "Nobody", "isbn": None},
        ]
    )
    matched = match_books_to_catalog(db, books)
    dune = next(row for row in matched["books"] if row["title"] == "Dune")
    miss = next(row for row in matched["books"] if row["title"] == "Missing")
    assert dune["shelved"]["id"] == "w-book"
    assert dune["shelved_audiobook"]["id"] == "w-audio-dune"
    assert miss["shelved"] is None
    assert miss in matched["missing"]
    assert dune in matched["shelved"]


def test_fetch_llm_list_mocked(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        body = json.loads(request.content.decode())
        assert "bestseller" in body["messages"][1]["content"].lower() or "fiction" in body["messages"][1][
            "content"
        ].lower()
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "display_name": "Hardcover Fiction",
                                    "books": [
                                        {
                                            "title": "Dune",
                                            "author": "Frank Herbert",
                                            "isbn": "9780441172710",
                                            "rank": 1,
                                        },
                                        {
                                            "title": "Left Hand",
                                            "author": "Ursula K. Le Guin",
                                            "isbn": None,
                                            "rank": 2,
                                        },
                                    ],
                                }
                            )
                        }
                    }
                ]
            },
        )

    client = LLMClient(
        "http://llm.example/v1",
        "test-key",
        "gpt-test",
        transport=httpx.MockTransport(handler),
    )
    payload = fetch_llm_list(client, preset="hardcover-fiction", date="current", data_dir=tmp_path)
    client.close()
    assert payload["configured"] is True
    assert payload["source"] == "llm"
    assert len(payload["books"]) == 2
    assert payload["books"][0]["isbn"] == ""  # invented/bad check digit dropped
    assert payload["books"][0]["title"] == "Dune"


def test_curated_list_fail_closed_without_llm(tmp_path):
    db = Database(tmp_path / "t.db")
    settings = Settings()
    payload = curated_list_payload(settings, db, data_dir=tmp_path)
    assert payload["configured"] is False
    assert payload["books"] == []
    assert payload["empty_reason"] == "missing_llm"
    assert "LLM" in payload["empty_copy"]


def test_chase_missing_searches_book_and_audiobook(monkeypatch):
    calls = []

    def fake_search(settings, *, transport=None, **fields):
        calls.append(dict(fields))
        kind = fields.get("kind")
        if kind == "book":
            return (
                [
                    {
                        "guid": "book-1",
                        "title": "Dune ebook",
                        "author": "Frank Herbert",
                        "kind": "book",
                        "isbn": "9780441172719",
                        "host_id": "nzb",
                        "host_name": "NZBFinder",
                    }
                ],
                None,
            )
        return (
            [
                {
                    "guid": "audio-1",
                    "title": "Dune audiobook",
                    "author": "Frank Herbert",
                    "kind": "audiobook",
                    "isbn": "",
                    "host_id": "nzb",
                    "host_name": "NZBFinder",
                }
            ],
            None,
        )

    monkeypatch.setattr("librarian.indexers.hosts.search_beyond", fake_search)
    result = chase_missing_item(
        Settings(),
        {"title": "Dune", "author": "Frank Herbert", "isbn": "9780441172719"},
    )
    kinds = {row["kind"] for row in calls}
    assert kinds == {"book", "audiobook"}
    assert result["book_hit"]["guid"] == "book-1"
    assert result["audiobook_hit"]["guid"] == "audio-1"
    assert result["audiobook_available"] is True
    assert result["book_hit"]["isbn"] == "9780441172719"


def _api_client(tmp_path, monkeypatch, **settings_fields):
    from fastapi.testclient import TestClient

    from librarian.web.app import create_app

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    if settings_fields:
        save_settings(tmp_path, Settings(**settings_fields))
    clear_session_secret_cache()
    clear_rate_limits()
    return TestClient(create_app(tmp_path))


def test_api_lists_llm_fail_closed(tmp_path, monkeypatch):
    client = _api_client(tmp_path, monkeypatch, llm_base_url="", llm_api_key="")
    login = client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    assert login.status_code == 200
    presets = client.get("/api/lists/presets")
    assert presets.status_code == 200
    assert presets.json()["configured"] is False
    listing = client.post("/api/lists/llm", json={"preset": "hardcover-fiction", "date": "current"})
    assert listing.status_code == 200
    body = listing.json()
    assert body["configured"] is False
    assert body["books"] == []
    assert "LLM" in body["empty_copy"]


def test_api_lists_llm_and_chase_mocked(tmp_path, monkeypatch):
    def llm_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "display_name": "Hardcover Fiction",
                                    "books": [
                                        {"title": "Dune", "author": "Frank Herbert", "isbn": None},
                                    ],
                                }
                            )
                        }
                    }
                ]
            },
        )

    mock_transport = httpx.MockTransport(llm_handler)
    monkeypatch.setattr(
        "librarian.lists.client_from_settings",
        lambda settings, transport=None: LLMClient(
            "http://llm.example/v1", "k", "m", transport=mock_transport
        ),
    )

    def fake_search(settings, *, transport=None, **fields):
        kind = fields.get("kind")
        return (
            [
                {
                    "guid": f"{kind}-guid",
                    "title": f"Dune {kind}",
                    "author": "Frank Herbert",
                    "kind": kind,
                    "host_id": "nzb",
                    "host_name": "NZBFinder",
                }
            ],
            None,
        )

    monkeypatch.setattr("librarian.indexers.hosts.search_beyond", fake_search)

    client = _api_client(
        tmp_path,
        monkeypatch,
        llm_base_url="http://llm.example/v1",
        llm_api_key="secret",
        llm_model="m",
    )
    login = client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    assert login.status_code == 200
    listing = client.post("/api/lists/llm", json={"preset": "hardcover-fiction"})
    assert listing.status_code == 200
    body = listing.json()
    assert body["configured"] is True
    assert body["source"] == "llm"
    assert len(body["missing"]) == 1
    assert body["missing"][0]["title"] == "Dune"

    chase = client.post(
        "/api/lists/llm/chase",
        json={"items": [{"title": "Dune", "author": "Frank Herbert"}]},
    )
    assert chase.status_code == 200
    results = chase.json()["results"]
    assert len(results) == 1
    assert results[0]["book_hit"]["guid"] == "book-guid"
    assert results[0]["audiobook_hit"]["guid"] == "audiobook-guid"
    # Chase must not create jobs.
    queue = client.get("/api/queue")
    assert queue.status_code == 200
    assert queue.json()["jobs"] == []


def test_match_local_work_still_isbn_first():
    hit = match_local_work(
        {"title": "Dune", "author": "Frank Herbert", "isbn": "9780441172719", "isbns": ["9780441172719"]},
        [{"id": "w1", "title": "Other", "author": "X", "isbn": "9780441172719"}],
    )
    assert hit and hit["id"] == "w1"
