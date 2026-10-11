"""New & noted — fixture feeds only. Never a live indexer, LLM, or Open Library call."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.indexers.discover import clear_discover_cache
from librarian.lists import clear_lists_memory_cache
from librarian.noted import (
    OPEN_LIBRARY_TRENDING,
    fetch_open_library_trending,
    noted_desk,
    parse_open_library_trending,
)
from librarian.nzbfinder import NZBFinderError
from librarian.rate_limit import clear_rate_limits
from librarian.sabnzbd import SABClient
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app

FIXTURES = Path(__file__).parent / "fixtures" / "openlibrary"
CAPS = json.loads((Path(__file__).parent / "fixtures" / "nzbfinder" / "capabilities.json").read_text())
DAILY = json.loads((FIXTURES / "trending_daily.json").read_text())
WEEKLY = json.loads((FIXTURES / "trending_weekly.json").read_text())

BOOK_HIT = {
    "title": "Piranesi",
    "author": "Susanna Clarke",
    "kind": "book",
    "guid": "g-piranesi",
    "category": 7020,
    "category_name": "Ebook",
    "isbn": "9780441172719",
    "download_url": "https://nzbfinder.example/get?id=g-piranesi&api_token=secret",
}
AUDIO_HIT = {
    "title": "Project Hail Mary",
    "author": "Andy Weir",
    "kind": "audiobook",
    "guid": "g-hail",
    "category": 3030,
    "category_name": "Audiobook",
    "download_url": "https://nzbfinder.example/get?id=g-hail&api_token=secret",
}
COMIC_HIT = {
    "title": "Saga 001",
    "kind": "comic",
    "guid": "g-saga",
    "category": 7030,
    "category_name": "Comics",
    "download_url": "https://nzbfinder.example/get?id=g-saga&api_token=secret",
}


def _ol_transport(status: int = 200):
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        if request.url.host != "openlibrary.org":
            return httpx.Response(599, text="refused")
        if status != 200:
            return httpx.Response(status, text="unavailable")
        if request.url.path.endswith("/trending/weekly.json"):
            return httpx.Response(200, json=WEEKLY)
        if request.url.path.endswith("/trending/daily.json"):
            return httpx.Response(200, json=DAILY)
        return httpx.Response(404, json={"works": []})

    return httpx.MockTransport(handler), hosts


def _patch_open_library(monkeypatch, transport):
    real = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    monkeypatch.setattr("librarian.noted.httpx.Client", factory)


def _patch_discover(monkeypatch):
    monkeypatch.setattr("librarian.nzbfinder.NZBFinderClient.capabilities", lambda self: CAPS)

    def latest(self, cat, *, limit=25, path="search"):
        cat_id = str(cat)
        if cat_id == "3030":
            return [AUDIO_HIT]
        if cat_id == "7020":
            return [BOOK_HIT, COMIC_HIT]
        if cat_id == "7030":
            return [COMIC_HIT]
        return [BOOK_HIT]

    monkeypatch.setattr("librarian.nzbfinder.NZBFinderClient.latest", latest)
    monkeypatch.setattr(
        "librarian.nzbfinder.NZBFinderClient.fetch_rss_category",
        lambda self, cat, *, limit=25: (_ for _ in ()).throw(NZBFinderError("rss should not run")),
    )


def _client(tmp_path, monkeypatch, **settings_fields):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    monkeypatch.setenv("LIBRARIAN_SKIP_APP_BOOT", "1")
    monkeypatch.setattr("librarian.config.load_dotenv", lambda path=None: None)
    save_settings(tmp_path, Settings(**settings_fields))
    clear_session_secret_cache()
    clear_rate_limits()
    clear_discover_cache()
    clear_lists_memory_cache()
    client = TestClient(create_app(tmp_path))
    assert (
        client.post(
            "/api/auth/local/login",
            json={"username": "owner", "password": "password123"},
        ).status_code
        == 200
    )
    return client


def _lane(body, lane_id):
    return next(row for row in body["lanes"] if row["id"] == lane_id)


def test_open_library_constant_is_json_not_a_scrape():
    assert OPEN_LIBRARY_TRENDING == "https://openlibrary.org/trending/{period}.json"
    assert "audible" not in OPEN_LIBRARY_TRENDING
    assert "libby" not in OPEN_LIBRARY_TRENDING
    assert "goodreads" not in OPEN_LIBRARY_TRENDING


def test_parse_trending_fixture_keeps_valid_isbn_and_drops_blanks():
    items = parse_open_library_trending(DAILY)
    assert [row["title"] for row in items] == ["The Left Hand of Darkness", "Untitled Draft"]
    first = items[0]
    assert first["author"] == "Ursula K. Le Guin"
    assert first["isbn"] == "9780441172719"
    assert first["kind"] == "book"
    assert first["wanted"]["kinds"] == ["book", "audiobook"]
    assert first["search"]["q"] == "Ursula K. Le Guin The Left Hand of Darkness"
    assert first["find"]["title"] == "The Left Hand of Darkness"
    assert first["cover"].endswith("/b/id/101-M.jpg")
    assert items[1]["isbn"] == ""
    assert items[1]["author"] == ""


def test_fetch_weekly_uses_fixture_transport():
    transport, hosts = _ol_transport()
    payload = fetch_open_library_trending("weekly", transport=transport)
    assert hosts == ["openlibrary.org"]
    items = parse_open_library_trending(payload)
    assert items[0]["title"] == "Weekly Only"
    assert items[0]["cover"] == ""


def test_missing_llm_leaves_trending_and_discover(tmp_path, monkeypatch):
    transport, hosts = _ol_transport()
    _patch_discover(monkeypatch)
    monkeypatch.setenv("NZBFINDER_API_TOKEN", "tok")
    desk = noted_desk(
        Settings(nzbfinder_api_token="tok"),
        Database(tmp_path / "t.db"),
        period="daily",
        ol_transport=transport,
        data_dir=tmp_path,
    )
    assert hosts == ["openlibrary.org"]
    trending = _lane(desk, "trending")
    bestsellers = _lane(desk, "bestsellers")
    discover = _lane(desk, "discover")
    assert trending["items"][0]["title"] == "The Left Hand of Darkness"
    assert bestsellers["configured"] is False
    assert bestsellers["empty_reason"] == "missing_llm"
    assert bestsellers["items"] == []
    assert bestsellers["empty_copy"]
    titles = {(row["kind"], row["category"], row["title"]) for row in discover["items"]}
    assert ("book", "7020", "Piranesi") in titles
    assert ("audiobook", "3030", "Project Hail Mary") in titles
    assert all(row["kind"] in ("book", "audiobook") for row in discover["items"])
    assert all(row["category"] in ("7020", "3030") for row in discover["items"])
    blob = json.dumps(desk)
    assert "secret" not in blob
    assert "download_url" not in blob
    assert "api_token" not in blob
    assert "Saga 001" not in blob


def test_open_library_outage_keeps_the_other_lanes(tmp_path):
    transport, _hosts = _ol_transport(status=503)
    desk = noted_desk(
        Settings(),
        Database(tmp_path / "t.db"),
        ol_transport=transport,
        data_dir=tmp_path,
    )
    trending = _lane(desk, "trending")
    assert trending["items"] == []
    assert trending["empty_reason"] == "unavailable"
    assert _lane(desk, "bestsellers")["empty_reason"] == "missing_llm"
    assert _lane(desk, "discover")["empty_reason"] == "missing_indexer"


def test_bestseller_lane_includes_companion_note(tmp_path):
    db = Database(tmp_path / "t.db")
    work = db.upsert_work(
        {
            "id": "w-audio-dune",
            "kind": "audiobook",
            "title": "Dune",
            "author": "Frank Herbert",
            "isbn": "9780441172719",
        }
    )
    folder = tmp_path / "shelf" / str(work["id"])
    folder.mkdir(parents=True)
    path = folder / "dune.m4b"
    path.write_bytes(b"m4b")
    db.upsert_work({**work, "folder_path": str(folder)})
    db.upsert_file(
        {
            "work_id": work["id"],
            "path": str(path),
            "filename": path.name,
            "kind": "audiobook",
            "size": path.stat().st_size,
        }
    )

    class FakeLLM:
        def chat_raw(self, *, system: str, user: str, temperature: float = 0.1) -> str:
            return json.dumps(
                {
                    "books": [
                        {"title": "Dune", "author": "Frank Herbert", "isbn": "9780441172719", "rank": 1},
                        {"title": "Kindred", "author": "Octavia E. Butler", "rank": 2},
                    ]
                }
            )

        def close(self) -> None:
            return None

    clear_lists_memory_cache()
    desk = noted_desk(
        Settings(),
        db,
        ol_transport=_ol_transport()[0],
        data_dir=tmp_path,
        llm=FakeLLM(),
    )
    books = _lane(desk, "bestsellers")["items"]
    dune = next(row for row in books if row["title"] == "Dune")
    kindred = next(row for row in books if row["title"] == "Kindred")
    assert dune["companion_note"] == "Companion audiobook is on the shelf."
    assert dune["shelved_audiobook"]["id"] == "w-audio-dune"
    assert kindred["companion_note"] == "No companion audiobook on the shelf."
    assert kindred["shelved_audiobook"] is None
    assert dune["wanted"]["title"] == "Dune"
    assert dune["wanted"]["isbn"] == "9780441172719"


def test_noted_api_cards_can_be_wanted_without_sab(tmp_path, monkeypatch):
    transport, _hosts = _ol_transport()
    _patch_open_library(monkeypatch, transport)
    _patch_discover(monkeypatch)

    def boom(*_args, **_kwargs):
        raise AssertionError("SABnzbd was called")

    monkeypatch.setattr(SABClient, "addfile", boom)
    monkeypatch.setattr("librarian.jobs.SABClient", lambda *a, **k: (_ for _ in ()).throw(AssertionError("SAB")))
    monkeypatch.setenv("NZBFINDER_API_TOKEN", "tok")
    client = _client(tmp_path, monkeypatch, nzbfinder_api_token="tok")

    denied = TestClient(create_app(tmp_path))
    denied.cookies.clear()
    assert denied.get("/api/noted").status_code == 401

    bad = client.get("/api/noted", params={"period": "hourly"})
    assert bad.status_code == 400

    resp = client.get("/api/noted", params={"period": "daily"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["can_add"] is True
    assert [row["id"] for row in body["lanes"]] == ["trending", "bestsellers", "discover"]
    card = _lane(body, "trending")["items"][0]
    assert card["wanted"]["kinds"] == ["book", "audiobook"]
    for kind in ("book", "audiobook"):
        added = client.post(
            "/api/wanted",
            json={
                "title": card["wanted"]["title"],
                "author": card["wanted"]["author"],
                "isbn": card["wanted"]["isbn"],
                "kind": kind,
            },
        )
        assert added.status_code == 200
        assert added.json()["item"]["status"] == "wanted"
        assert added.json()["item"]["kind"] == kind
        assert added.json()["item"]["job_id"] is None

    weekly = client.get("/api/noted", params={"period": "weekly"})
    assert _lane(weekly.json(), "trending")["items"][0]["title"] == "Weekly Only"

    database = Database(tmp_path / "librarian.db")
    try:
        assert database.list_jobs(limit=10) == []
    finally:
        database.close()
    blob = json.dumps(body)
    assert "secret" not in blob
    assert "download_url" not in blob
