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
    chase_missing_items,
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

    def shelve(payload: dict, *, filename: str = "book.epub") -> None:
        work = db.upsert_work(payload)
        folder = tmp_path / "shelf" / str(work["id"])
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / filename
        path.write_bytes(b"payload")
        db.upsert_work({**work, "folder_path": str(folder)})
        db.upsert_file(
            {
                "work_id": work["id"],
                "path": str(path),
                "filename": path.name,
                "kind": work.get("kind") or "book",
                "size": path.stat().st_size,
            }
        )

    shelve(
        {
            "id": "w-book",
            "kind": "book",
            "title": "Dune",
            "author": "Frank Herbert",
            "isbn": "9780441172719",
        }
    )
    shelve(
        {
            "id": "w-audio",
            "kind": "audiobook",
            "title": "Leftover",
            "author": "Someone",
            "isbn": "",
        },
        filename="leftover.m4b",
    )
    shelve(
        {
            "id": "w-audio-dune",
            "kind": "audiobook",
            "title": "Dune",
            "author": "Frank Herbert",
            "isbn": "9780441172719",
        },
        filename="dune.m4b",
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

    def fake_search_traced(settings, *, transport=None, **fields):
        calls.append(dict(fields))
        kind = fields.get("kind")
        if kind == "book":
            hit = {
                "guid": "book-1",
                "title": "Dune ebook",
                "author": "Frank Herbert",
                "kind": "book",
                "isbn": "9780441172719",
                "host_id": "nzb",
                "host_name": "NZBFinder",
            }
            return {
                "hits": [hit],
                "error": None,
                "plan": {"endpoint": "books", "params": {"title": "Dune"}, "sought": fields},
                "steps": [{"step": "plan", "detail": "books title='Dune'"}],
                "results": [{**hit, "decision": "accepted", "reason": "", "notes": []}],
                "raw_count": 1,
                "rejected_count": 0,
            }
        hit = {
            "guid": "audio-1",
            "title": "Dune audiobook",
            "author": "Frank Herbert",
            "kind": "audiobook",
            "isbn": "",
            "host_id": "nzb",
            "host_name": "NZBFinder",
        }
        return {
            "hits": [hit],
            "error": None,
            "plan": {"endpoint": "search", "params": {"query": "Frank Herbert Dune"}, "sought": fields},
            "steps": [{"step": "plan", "detail": "search cat=3030"}],
            "results": [{**hit, "decision": "accepted", "reason": "", "notes": []}],
            "raw_count": 1,
            "rejected_count": 0,
        }

    monkeypatch.setattr("librarian.indexers.hosts.search_beyond_traced", fake_search_traced)
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
    assert result["trace"]["book"]["raw_count"] == 1
    assert result["trace"]["conversation"]


def test_art_of_war_chase_query_construction(monkeypatch):
    from librarian.indexers.query import plan_beyond_search

    plan = plan_beyond_search(kind="book", title="The Art of War", author="Sun Tzu", q="Sun Tzu The Art of War")
    assert plan is not None
    assert plan["endpoint"] == "books"
    assert plan["params"]["title"] == "The Art of War"
    assert plan["params"]["author"] == "Sun Tzu"
    assert plan["params"]["cat"] == "7000"

    captured = []

    def fake_search_traced(settings, *, transport=None, **fields):
        captured.append(dict(fields))
        return {
            "hits": [],
            "error": None,
            "plan": plan_beyond_search(**fields),
            "steps": [{"step": "plan", "detail": "empty"}],
            "results": [],
            "raw_count": 0,
            "rejected_count": 0,
        }

    monkeypatch.setattr("librarian.indexers.hosts.search_beyond_traced", fake_search_traced)
    chase_missing_item(Settings(), {"title": "The Art of War", "author": "Sun Tzu"})
    book_call = next(row for row in captured if row.get("kind") == "book")
    assert book_call["title"] == "The Art of War"
    assert book_call["author"] == "Sun Tzu"
    assert "Sun Tzu" in book_call["q"] and "Art of War" in book_call["q"]


def test_chase_exposes_raw_when_kind_filter_empties_hits(monkeypatch):
    """Indexer returned a real ebook row; kind filter rejected it — still in trace."""

    def fake_search_traced(settings, *, transport=None, **fields):
        kind = fields.get("kind")
        if kind != "book":
            return {
                "hits": [],
                "error": None,
                "plan": {"endpoint": "search", "params": {}, "sought": fields},
                "steps": [],
                "results": [],
                "raw_count": 0,
                "rejected_count": 0,
            }
        rejected = {
            "guid": "art-guid",
            "title": "Sun Tzu - The Art of War EPUB",
            "author": "Sun Tzu",
            "kind": "",
            "host_id": "nzb",
            "host_name": "NZBFinder",
            "decision": "rejected",
            "reason": "kind None not shelfable",
            "notes": [],
        }
        return {
            "hits": [],
            "error": None,
            "plan": {
                "endpoint": "books",
                "params": {"title": "The Art of War", "author": "Sun Tzu", "cat": "7000"},
                "sought": fields,
            },
            "steps": [
                {"step": "plan", "detail": "books title='The Art of War'"},
                {"step": "host", "detail": "NZBFinder: raw=1 accepted=0 rejected=1"},
            ],
            "results": [rejected],
            "raw_count": 1,
            "rejected_count": 1,
        }

    monkeypatch.setattr("librarian.indexers.hosts.search_beyond_traced", fake_search_traced)
    result = chase_missing_item(Settings(), {"title": "The Art of War", "author": "Sun Tzu"})
    assert result["book_hit"] is None
    assert result["trace"]["book"]["raw_count"] == 1
    assert result["trace"]["book"]["rejected_count"] == 1
    assert result["trace"]["book"]["results"][0]["guid"] == "art-guid"
    assert "not shelfable" in result["trace"]["book"]["results"][0]["reason"]


def test_pick_chase_hit_skips_blank_guid():
    from librarian.lists import pick_chase_hit

    picked = pick_chase_hit(
        [
            {"guid": "", "title": "blank"},
            {"guid": "real-1", "title": "The Art of War"},
        ]
    )
    assert picked["guid"] == "real-1"


def test_filter_shelf_items_assumes_book_kind_and_keeps_rejected():
    from librarian.nzbfinder import filter_shelf_items

    traced = filter_shelf_items(
        [
            {"title": "The Art of War", "guid": "g1", "kind": None, "author": "Sun Tzu"},
            {"title": "Some Movie", "guid": "g2", "kind": "movie"},
        ],
        default_kind="book",
    )
    assert len(traced["accepted"]) == 1
    assert traced["accepted"][0]["kind"] == "book"
    assert traced["accepted"][0]["guid"] == "g1"
    assert len(traced["rejected"]) == 1
    assert traced["rejected"][0]["decision"] == "rejected"
    assert "movie" in traced["rejected"][0]["reason"]
    assert len(traced["raw"]) == 2


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
    monkeypatch.setattr("librarian.config.load_dotenv", lambda path=None: None)
    for name in (
        "LLM_API_KEY",
        "LLM_PROVIDER",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    client = _api_client(tmp_path, monkeypatch, llm_base_url="", llm_api_key="", llm_provider="openai")
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
        hit = {
            "guid": f"{kind}-guid",
            "title": f"Dune {kind}",
            "author": "Frank Herbert",
            "kind": kind,
            "host_id": "nzb",
            "host_name": "NZBFinder",
        }
        return {
            "hits": [hit],
            "error": None,
            "plan": {"endpoint": "books" if kind == "book" else "search", "params": {}, "sought": fields},
            "steps": [],
            "results": [{**hit, "decision": "accepted", "reason": "", "notes": []}],
            "raw_count": 1,
            "rejected_count": 0,
        }

    monkeypatch.setattr("librarian.indexers.hosts.search_beyond_traced", fake_search)

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


def test_curated_list_429_uses_friendly_copy(tmp_path, monkeypatch):
    from librarian.llm import LLM_RATE_LIMIT_COPY, LLMError

    class Boom:
        def configured(self):
            return True

        def close(self):
            return None

    def boom_client(settings, *, transport=None):
        return Boom()

    def boom_fetch(client, **kwargs):
        raise LLMError("LLM HTTP 429", status_code=429)

    monkeypatch.setattr("librarian.lists.client_from_settings", boom_client)
    monkeypatch.setattr("librarian.lists.fetch_llm_list", boom_fetch)
    db = Database(tmp_path / "t.db")
    payload = curated_list_payload(Settings(llm_base_url="http://x", llm_api_key="k"), db, data_dir=tmp_path)
    assert payload["empty_reason"] == "rate_limited"
    assert payload["empty_copy"] == LLM_RATE_LIMIT_COPY
    assert "429" not in payload["empty_copy"]


def test_curated_list_retired_gemini_model_uses_friendly_copy(tmp_path, monkeypatch):
    from librarian.llm import LLM_BAD_MODEL_COPY, LLMError

    class Boom:
        def configured(self):
            return True

        def close(self):
            return None

    def boom_client(settings, *, transport=None):
        return Boom()

    def boom_fetch(client, **kwargs):
        raise LLMError(
            "LLM request failed (404): This model models/gemini-2.5-flash is no longer available "
            "to new users. Please update your code to use models/gemini-3.6-flash for the latest…",
            status_code=404,
        )

    monkeypatch.setattr("librarian.lists.client_from_settings", boom_client)
    monkeypatch.setattr("librarian.lists.fetch_llm_list", boom_fetch)
    db = Database(tmp_path / "t.db")
    payload = curated_list_payload(Settings(llm_base_url="http://x", llm_api_key="k"), db, data_dir=tmp_path)
    assert payload["empty_reason"] == "error"
    assert payload["empty_copy"] == LLM_BAD_MODEL_COPY
    assert len(payload["empty_copy"]) <= 180
    assert "traceback" not in payload["empty_copy"].lower()


def test_chase_disables_llm_after_rate_limit(monkeypatch):
    from librarian.lists import chase_missing_items

    calls = []

    def fake_search_and_rank(settings, *, transport=None, llm=None, **fields):
        calls.append({"kind": fields.get("kind"), "title": fields.get("title"), "llm": llm is not None})
        hit = {
            "guid": f"{fields.get('kind')}-{fields.get('title')}",
            "title": fields.get("title"),
            "author": fields.get("author"),
            "kind": fields.get("kind"),
        }
        rate = llm is not None and fields.get("title") == "First" and fields.get("kind") == "book"
        return {
            "hits": [hit],
            "pick": hit,
            "candidates": [{"guid": hit["guid"], "title": hit["title"], "rank": 1}],
            "rank_method": "heuristic" if rate else ("llm" if llm else "heuristic"),
            "rank_reason": "rate-limited — using heuristic" if rate else "ok",
            "error": "rate-limited" if rate else None,
            "conversation": [
                {
                    "role": "assistant",
                    "content": "LLM unavailable (rate-limited); using heuristic" if rate else "ranked",
                }
            ],
            "steps": [],
            "plan": None,
            "raw_count": 1,
            "rejected_count": 0,
            "results": [],
        }

    monkeypatch.setattr("librarian.indexers.rank.search_and_rank", fake_search_and_rank)
    # chase_missing_item imports search_and_rank locally — patch on lists module path via rank
    monkeypatch.setattr(
        "librarian.lists.client_from_settings",
        lambda settings, *, transport=None: object(),
    )

    # Patch where chase_missing_item looks it up
    import librarian.indexers.rank as rank_mod

    monkeypatch.setattr(rank_mod, "search_and_rank", fake_search_and_rank)

    class FakeLLM:
        def configured(self):
            return True

        def close(self):
            return None

    results = chase_missing_items(
        Settings(),
        [
            {"title": "First", "author": "A"},
            {"title": "Second", "author": "B"},
        ],
        llm=FakeLLM(),
        limit=5,
    )
    assert len(results) == 2
    # First title: book with LLM (rate-limited), audiobook without LLM
    assert calls[0] == {"kind": "book", "title": "First", "llm": True}
    assert calls[1] == {"kind": "audiobook", "title": "First", "llm": False}
    # Second title: both heuristic (LLM disabled for remaining)
    assert calls[2]["title"] == "Second" and calls[2]["llm"] is False
    assert calls[3]["title"] == "Second" and calls[3]["llm"] is False
