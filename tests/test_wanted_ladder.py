"""Hourly Wanted pass, immediate search on queue, and the one-field-at-a-time ladder.

SQLite stays real. NZBFinder HTTP is mocked with ``httpx.MockTransport``.
"""

from __future__ import annotations

import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.indexers.match import is_clear_title_match, is_confident_match
from librarian.nzbfinder import NZBFinderClient, NZBFinderRateLimited
from librarian.poller import JobPoller
from librarian.rate_limit import clear_rate_limits
from librarian.sabnzbd import SABClient
from librarian.sessions import clear_session_secret_cache
from librarian.wanted import add_wanted, dedupe_key
from librarian.wanted_search import poll_wanted
from librarian.web.app import create_app

NOW = 1_700_000_000.0
HOUR = 60 * 60
DUNE_ISBN = "9780441172719"
INDEXER = "https://nzbfinder.test"


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "librarian.db")
    try:
        yield database
    finally:
        database.close()


@pytest.fixture(autouse=True)
def _no_sab(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("SABnzbd was called before a person confirmed the slip")

    monkeypatch.setattr(SABClient, "addfile", boom)


def _indexer(responses, seen):
    """Mock NZBFinder v2. ``responses`` maps a request to a status and result list."""

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        entry = {
            "host": request.url.host,
            "path": request.url.path,
            "query": params.get("query", ""),
            "title": params.get("title", ""),
            "author": params.get("author", ""),
            "isbn": params.get("isbn", ""),
            "cat": params.get("cat", ""),
        }
        seen.append(entry)
        status, results = responses(entry)
        if status != 200:
            return httpx.Response(status, json={"message": "slow down"})
        return httpx.Response(200, json={"results": results})

    return httpx.MockTransport(handler)


def _patch_client(monkeypatch, target: str, transport: httpx.MockTransport) -> None:
    real = NZBFinderClient

    def factory(url, token, **kwargs):
        kwargs["transport"] = transport
        return real(url, token, **kwargs)

    monkeypatch.setattr(target, factory)


def _settings() -> Settings:
    return Settings(nzbfinder_api_token="tok", nzbfinder_url=INDEXER)


def _want(database: Database, title: str, author: str = "Frank Herbert", **extra):
    kind = extra.pop("kind", "audiobook")
    isbn = extra.pop("isbn", "")
    return database.insert_wanted(
        {
            "dedupe_key": dedupe_key(kind=kind, title=title, author=author, isbn=isbn),
            "title": title,
            "author": author,
            "isbn": isbn,
            "kind": kind,
            "status": "wanted",
            "miss_streak": 0,
            "next_search_at": extra.pop("next_search_at", NOW),
            "source": "manual",
        }
    )


def _owner_client(tmp_path, monkeypatch, settings: Settings) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    monkeypatch.setenv("LIBRARIAN_SKIP_APP_BOOT", "1")
    monkeypatch.delenv("NZBFINDER_API_TOKEN", raising=False)
    monkeypatch.setattr("librarian.config.load_dotenv", lambda path=None: None)
    monkeypatch.setattr("librarian.indexers.rank.client_from_settings", lambda *a, **k: None)
    save_settings(tmp_path, settings)
    clear_session_secret_cache()
    clear_rate_limits()
    client = TestClient(create_app(tmp_path))
    login = client.post(
        "/api/auth/local/login", json={"username": "owner", "password": "password123"}
    )
    assert login.status_code == 200
    return client


# Schedule


def test_new_row_is_searched_at_once_then_waits_six_hours(tmp_path, monkeypatch):
    seen: list = []
    _patch_client(
        monkeypatch,
        "librarian.wanted_search.NZBFinderClient",
        _indexer(lambda _entry: (200, []), seen),
    )
    client = _owner_client(tmp_path, monkeypatch, _settings())
    before = time.time()
    added = client.post(
        "/api/wanted", json={"title": "Kindred", "author": "Octavia Butler", "kind": "audiobook"}
    )
    assert added.status_code == 200, added.text
    assert [(row["query"], row["cat"]) for row in seen] == [
        ("Kindred", "3030"),
        ("Kindred Octavia Butler", "3030"),
    ]
    database = Database(tmp_path / "librarian.db")
    try:
        row = database.get_wanted(added.json()["item"]["id"])
        assert row["status"] == "wanted"
        assert row["miss_streak"] == 1
        assert before + 6 * HOUR <= row["next_search_at"] <= time.time() + 6 * HOUR
        assert poll_wanted(database, _settings(), now=time.time() + 60) == 0
        assert len(seen) == 2
        assert database.list_jobs(limit=10) == []
    finally:
        database.close()


def test_new_row_hit_files_an_asked_slip_and_never_sab(tmp_path, monkeypatch):
    seen: list = []
    hit = {
        "title": "Frank Herbert - Dune (Unabridged)",
        "guid": "guid-dune",
        "category": "3030",
        "isbn": DUNE_ISBN,
    }
    _patch_client(
        monkeypatch,
        "librarian.wanted_search.NZBFinderClient",
        _indexer(lambda entry: (200, [hit] if entry["query"] == DUNE_ISBN else []), seen),
    )
    client = _owner_client(tmp_path, monkeypatch, _settings())
    added = client.post(
        "/api/wanted",
        json={"title": "Dune", "author": "Frank Herbert", "isbn": DUNE_ISBN, "kind": "audiobook"},
    )
    assert added.status_code == 200, added.text
    assert [row["query"] for row in seen] == [DUNE_ISBN]
    database = Database(tmp_path / "librarian.db")
    try:
        row = database.get_wanted(added.json()["item"]["id"])
        assert row["status"] == "asked"
        job = database.get_job(row["job_id"])
        assert job["status"] == "asked"
        assert not job.get("nzo_id")
    finally:
        database.close()


def test_add_without_an_indexer_token_stays_quiet_and_due(tmp_path, monkeypatch):
    client = _owner_client(tmp_path, monkeypatch, Settings(nzbfinder_api_token=""))
    added = client.post("/api/wanted", json={"title": "Kindred", "kind": "audiobook"})
    assert added.status_code == 200
    item = added.json()["item"]
    assert item["miss_streak"] == 0
    assert item["next_search_at"] <= time.time()


def test_sweep_rows_are_searched_right_away(db, monkeypatch):
    seen: list = []
    _patch_client(
        monkeypatch,
        "librarian.wanted_search.NZBFinderClient",
        _indexer(lambda _entry: (200, []), seen),
    )
    work = db.upsert_work(
        {"kind": "book", "title": "Dune", "author": "Frank Herbert", "genre": "Fiction"}
    )
    db.add_file(
        {"work_id": work["id"], "path": "/data/dune.epub", "filename": "dune.epub", "kind": "book", "size": 1}
    )
    poller = JobPoller(db, _settings, interval=3600)
    poller._run_sweep(_settings())
    rows = db.list_wanted()
    assert len(rows) == 1
    assert rows[0]["source"] == "sweep"
    assert rows[0]["miss_streak"] == 1
    assert [row["query"] for row in seen] == ["Dune", "Dune Frank Herbert"]


def test_hourly_pass_walks_every_due_row_with_no_cap(db):
    rows = [_want(db, f"Title {n}") for n in range(8)]
    later = _want(db, "Later", next_search_at=NOW + HOUR)
    searched: list = []

    def search(sought):
        searched.append(sought["title"])
        return []

    assert poll_wanted(db, Settings(), now=NOW, search=search) == 16
    assert sorted(set(searched)) == sorted(row["title"] for row in rows)
    assert all(db.get_wanted(row["id"])["miss_streak"] == 1 for row in rows)
    assert db.get_wanted(later["id"])["miss_streak"] == 0


def test_remeasured_call_rate_vs_head_360():
    """Sprint 3.1 vs 360 HEAD (PERF-018): 5 due rows / 120 s, NZBFinder only, 3,600/day cap.

    This tree: hourly pass, every due row, up to three ladder rungs, NZBFinder only.
    6,483 due rows are 6,483–19,449 calls in the first hour, then 6 h / 12 h backoff
    with no weekly cap. A 429 ends the pass. Extra indexers are still Find-only.
    """
    from librarian import wanted_search
    from librarian.poller import _BACKGROUND_STEPS, DEFAULT_WANTED_POLL_SECONDS
    from librarian.wanted import BASE_BACKOFF_SECONDS, MAX_BACKOFF_SECONDS, backoff_seconds

    assert DEFAULT_WANTED_POLL_SECONDS == 3600.0
    assert "backup" in _BACKGROUND_STEPS
    assert not hasattr(wanted_search, "MAX_SEARCHES_PER_TICK")
    assert backoff_seconds(1) == BASE_BACKOFF_SECONDS == 6 * HOUR
    assert backoff_seconds(2) == MAX_BACKOFF_SECONDS == 12 * HOUR
    assert backoff_seconds(9) == 12 * HOUR


def test_a_429_stops_the_pass_and_is_not_a_strike(db, monkeypatch):
    first = _want(db, "Alpha", next_search_at=NOW - 3)
    second = _want(db, "Beta", next_search_at=NOW - 2)
    third = _want(db, "Gamma", next_search_at=NOW - 1)
    seen: list = []
    finder = NZBFinderClient(
        INDEXER,
        "tok",
        transport=_indexer(lambda entry: (429, []) if entry["query"] == "Beta" else (200, []), seen),
    )
    try:
        assert poll_wanted(db, Settings(), now=NOW, client=finder) == 3
    finally:
        finder.close()
    assert [row["query"] for row in seen] == ["Alpha", "Alpha Frank Herbert", "Beta"]
    assert db.get_wanted(first["id"])["miss_streak"] == 1
    paused = db.get_wanted(second["id"])
    assert paused["miss_streak"] == 0
    assert paused["next_search_at"] == pytest.approx(NOW - 2)
    untouched = db.get_wanted(third["id"])
    assert untouched["miss_streak"] == 0
    assert untouched["next_search_at"] == pytest.approx(NOW - 1)


def test_search_selected_stops_on_a_429_and_reports_the_rest(db):
    from librarian.wanted_search import search_wanted_selection

    first = _want(db, "Alpha")
    second = _want(db, "Beta")

    def search(_sought):
        raise NZBFinderRateLimited("NZBFinder HTTP 429: rate limited")

    results = search_wanted_selection(
        db, _settings(), ids=[first["id"], second["id"]], now=NOW, search=search
    )
    assert [row["outcome"] for row in results] == ["rate_limited", "rate_limited"]
    assert db.get_wanted(first["id"])["miss_streak"] == 0
    assert db.get_wanted(second["id"])["miss_streak"] == 0


def test_a_second_pass_does_not_start_while_one_is_walking(db):
    from librarian import wanted_search

    _want(db, "Alpha")

    def explode(_sought):
        raise AssertionError("a second pass searched")

    assert wanted_search._PASS_LOCK.acquire(blocking=False)
    try:
        assert poll_wanted(db, Settings(), now=NOW, search=explode) == 0
    finally:
        wanted_search._PASS_LOCK.release()


def test_poller_never_starts_a_second_wanted_thread(db):
    poller = JobPoller(db, Settings, interval=3600)
    entered = threading.Event()
    release = threading.Event()
    runs: list = []

    def slow_pass(_settings):
        runs.append(1)
        entered.set()
        release.wait(5)
        return 0

    poller._runners["wanted"] = slow_pass
    poller._start_wanted_pass()
    assert entered.wait(5)
    poller._start_wanted_pass()
    release.set()
    thread = poller._wanted_thread
    assert thread is not None
    thread.join(5)
    assert runs == [1]
    status = {row["id"]: row for row in poller.step_status()["steps"]}
    assert status["wanted"]["interval_seconds"] == 3600.0
    assert status["wanted"]["last_run"]


# Ladder


def test_wanted_ladder_is_isbn_then_title_then_title_and_author(db):
    row = _want(db, "Dune", isbn=DUNE_ISBN)
    asked: list = []

    def search(sought):
        asked.append((sought["rung"], sought["q"]))
        return []

    assert poll_wanted(db, Settings(), now=NOW, search=search) == 3
    assert asked == [
        ("isbn", DUNE_ISBN),
        ("title", "Dune"),
        ("title_author", "Dune Frank Herbert"),
    ]
    assert db.get_wanted(row["id"])["miss_streak"] == 1


def test_title_only_query_accepts_a_clear_match_and_stops(db):
    row = _want(db, "Dune")
    asked: list = []

    def search(sought):
        asked.append(sought["q"])
        return [{"title": "Frank Herbert - Dune (2005) Unabridged m4b", "guid": "g-dune", "category": "3030"}]

    assert poll_wanted(db, Settings(), now=NOW, search=search) == 1
    assert asked == ["Dune"]
    fresh = db.get_wanted(row["id"])
    assert fresh["status"] == "asked"
    assert db.get_job(fresh["job_id"])["indexer_guid"] == "g-dune"


def test_title_rung_glance_falls_through_to_title_and_author(db):
    row = _want(db, "Dune")
    asked: list = []

    def search(sought):
        asked.append(sought["q"])
        if sought["rung"] == "title":
            return [{"title": "Frank Herbert - Dune Messiah m4b", "guid": "g-messiah", "category": "3030"}]
        return [
            {
                "title": "Dune",
                "book_title": "Dune",
                "author": "Frank Herbert",
                "guid": "g-dune",
                "category": "3030",
            }
        ]

    assert poll_wanted(db, Settings(), now=NOW, search=search) == 2
    assert asked == ["Dune", "Dune Frank Herbert"]
    assert db.get_job(db.get_wanted(row["id"])["job_id"])["indexer_guid"] == "g-dune"


@pytest.mark.parametrize(
    "hit, expected",
    [
        ({"title": "Frank Herbert - Dune (2005) epub", "guid": "g"}, True),
        ({"title": "Herbert-Dune-2005-AUDIOBOOK-GROUP", "guid": "g"}, True),
        ({"title": "Dune", "book_title": "Dune", "author": "Herbert, Frank", "guid": "g"}, True),
        ({"title": "Frank Herbert - Dune Messiah epub", "guid": "g"}, False),
        ({"title": "Herbert-Dune-Messiah", "guid": "g"}, False),
        ({"title": "Dune", "book_title": "Dune", "author": "Brian Herbert", "guid": "g"}, False),
        ({"title": "Dune", "guid": "g"}, False),
        ({"title": "Frank Herbert - Children of Dune", "guid": "g"}, False),
    ],
)
def test_clear_title_match_needs_the_title_and_the_author(hit, expected):
    sought = {"kind": "book", "title": "Dune", "author": "Frank Herbert"}
    assert is_clear_title_match(sought, hit) is expected


def test_clear_title_match_without_a_sought_author_is_still_a_glance():
    assert is_clear_title_match({"title": "Dune"}, {"title": "Dune", "guid": "g"}) is False
    assert is_confident_match({"title": "Dune"}, {"title": "Dune", "guid": "g"}) is False


def test_confident_match_fails_closed_without_a_guid():
    sought = {"title": "Dune", "author": "Frank Herbert", "isbn": DUNE_ISBN}
    assert is_confident_match(sought, {"title": "Dune", "isbn": DUNE_ISBN}) is False
    assert is_confident_match(sought, {"title": "Dune", "isbn": DUNE_ISBN, "guid": "g"}) is True


# Click Search on Find


def _find_client(tmp_path, monkeypatch, responses, seen) -> TestClient:
    _patch_client(monkeypatch, "librarian.indexers.hosts.NZBFinderClient", _indexer(responses, seen))
    return _owner_client(tmp_path, monkeypatch, _settings())


def test_click_search_never_sends_every_field_at_once(tmp_path, monkeypatch):
    seen: list = []
    client = _find_client(tmp_path, monkeypatch, lambda _entry: (200, []), seen)
    resp = client.get(
        "/api/search/beyond",
        params={
            "q": "Frank Herbert Dune 9780441172719 1965",
            "kind": "book",
            "title": "Dune",
            "author": "Frank Herbert",
            "isbn": DUNE_ISBN,
            "year": "1965",
        },
    )
    assert resp.status_code == 200, resp.text
    assert [(row["path"], row["isbn"], row["title"], row["author"]) for row in seen] == [
        ("/api/v2/books", DUNE_ISBN, "", ""),
        ("/api/v2/books", "", "Dune", ""),
        ("/api/v2/books", "", "Dune", "Frank Herbert"),
    ]
    assert not any("1965" in row["title"] for row in seen)


def test_click_search_stops_on_a_confident_title_hit(tmp_path, monkeypatch):
    seen: list = []
    hit = {
        "title": "Frank.Herbert.Dune.epub",
        "book_title": "Dune",
        "author": "Frank Herbert",
        "guid": "g-dune",
        "category": "7020",
    }
    client = _find_client(
        tmp_path,
        monkeypatch,
        lambda entry: (200, [hit] if entry["title"] == "Dune" and not entry["author"] else []),
        seen,
    )
    resp = client.get(
        "/api/search/beyond",
        params={"kind": "book", "title": "Dune", "author": "Frank Herbert", "isbn": DUNE_ISBN},
    )
    assert resp.status_code == 200, resp.text
    assert [(row["isbn"], row["title"], row["author"]) for row in seen] == [
        (DUNE_ISBN, "", ""),
        ("", "Dune", ""),
    ]
    body = resp.json()
    assert [row["guid"] for row in body["beyond"]] == ["g-dune"]
    assert body["pick"]["guid"] == "g-dune"


def test_wanted_reopen_is_searched_again_from_a_clean_streak(tmp_path, monkeypatch):
    seen: list = []
    _patch_client(
        monkeypatch,
        "librarian.wanted_search.NZBFinderClient",
        _indexer(lambda _entry: (200, []), seen),
    )
    client = _owner_client(tmp_path, monkeypatch, _settings())
    database = Database(tmp_path / "librarian.db")
    try:
        row = add_wanted(database, {"title": "Kindred", "author": "Octavia Butler", "kind": "audiobook"})
        database.backoff_wanted(row["id"], now=time.time(), from_status="wanted")
        database.backoff_wanted(row["id"], now=time.time(), from_status="wanted")
        assert database.get_wanted(row["id"])["miss_streak"] == 2
        assert client.post(f"/api/wanted/{row['id']}/dismiss").status_code == 200
        again = client.post(
            "/api/wanted", json={"title": "Kindred", "author": "Octavia Butler", "kind": "audiobook"}
        )
        assert again.status_code == 200
        assert again.json()["item"]["id"] == row["id"]
        assert [entry["query"] for entry in seen] == ["Kindred", "Kindred Octavia Butler"]
        assert database.get_wanted(row["id"])["miss_streak"] == 1
    finally:
        database.close()


def test_hourly_pass_searches_extra_indexers(db, monkeypatch):
    seen: list = []
    extra = "https://extra.test"
    _patch_client(
        monkeypatch,
        "librarian.wanted_search.NZBFinderClient",
        _indexer(lambda _entry: (200, []), seen),
    )
    row = _want(db, "Kindred", "Octavia Butler")
    settings = Settings(
        nzbfinder_api_token="tok",
        nzbfinder_url=INDEXER,
        extra_indexers=[
            {
                "id": "extra1",
                "name": "Books.nzb",
                "url": extra,
                "api_token": "extra-tok",
                "enabled": True,
                "dialect": "v2",
            }
        ],
    )
    calls = poll_wanted(db, settings, now=NOW)
    assert calls >= 2
    hosts = {entry["host"] for entry in seen}
    assert "nzbfinder.test" in hosts
    assert "extra.test" in hosts
    assert db.get_wanted(row["id"])["status"] == "wanted"
