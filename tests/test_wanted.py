"""Wanted sweep, backoff search, and the desk API. SQLite stays real."""

from __future__ import annotations

import logging
import threading
import time

import pytest
from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.jobs import confirm_asked_job, poll_active_jobs, poll_job
from librarian.nzbfinder import NZBFinderClient, NZBFinderError
from librarian.poller import JobPoller
from librarian.rate_limit import clear_rate_limits
from librarian.sabnzbd import SABClient
from librarian.sessions import clear_session_secret_cache
from librarian.wanted import BASE_BACKOFF_SECONDS, backoff_seconds
from librarian.wanted_search import poll_wanted, sought_for_row
from librarian.wanted_sweep import sweep_wanted_audiobooks
from librarian.web.app import create_app

DUNE_ISBN = "9780441172719"
DUNE_ISBN10 = "0441172717"
NOW = 1_700_000_000.0

HIT = {
    "guid": "guid-dune",
    "title": "Dune",
    "book_title": "Dune",
    "author": "Frank Herbert",
    "isbn": DUNE_ISBN,
    "kind": "audiobook",
    "category": "3030",
}

JUNK = {
    "guid": "guid-junk",
    "title": "Dune CD1",
    "book_title": "Dune.Disc.1.of.12.part01.rar",
    "author": "Frank Herbert",
    "isbn": DUNE_ISBN,
    "kind": "audiobook",
    "category": "3030",
}


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "librarian.db")
    try:
        yield database
    finally:
        database.close()


def _shelve(database: Database, **fields):
    work = database.upsert_work(fields)
    database.add_file(
        {
            "work_id": work["id"],
            "path": f"/data/{work['id']}.bin",
            "filename": f"{work['id']}.bin",
            "kind": work["kind"],
            "size": 12,
        }
    )
    return work


def _audiobook_want(database: Database, **overrides):
    from librarian.wanted import dedupe_key

    fields = {
        "title": "Dune",
        "author": "Frank Herbert",
        "isbn": DUNE_ISBN,
        "kind": "audiobook",
    }
    fields.update(overrides)
    key = dedupe_key(
        kind=fields["kind"],
        work_id=str(fields.get("work_id") or ""),
        title=fields["title"],
        author=fields["author"],
        isbn=fields["isbn"],
    )
    row = {
        "dedupe_key": key,
        "work_id": fields.get("work_id") or None,
        "title": fields["title"],
        "author": fields["author"],
        "isbn": fields["isbn"],
        "kind": fields["kind"],
        "status": fields.get("status") or "wanted",
        "miss_streak": 0,
        "next_search_at": NOW,
    }
    if "source" in overrides:
        row["source"] = overrides["source"]
    if overrides.get("job_id"):
        row["job_id"] = overrides["job_id"]
    return database.insert_wanted(row)


def test_sweep_marks_unmatched_book_and_isbn_match_clears(db):
    book = _shelve(
        db,
        kind="book",
        title="Dune",
        author="Frank Herbert",
        isbn=DUNE_ISBN,
        genre="Fiction",
    )
    _shelve(db, kind="magazine", title="Wired", author="")
    unshelved = db.upsert_work({"kind": "book", "title": "Shell", "author": "Nobody"})
    assert sweep_wanted_audiobooks(db, now=NOW) == 1
    rows = db.list_wanted()
    assert len(rows) == 1
    assert rows[0]["work_id"] == book["id"]
    assert rows[0]["kind"] == "audiobook"
    assert rows[0]["status"] == "wanted"
    assert rows[0]["source"] == "sweep"
    assert all(row["work_id"] != unshelved["id"] for row in rows)
    assert sweep_wanted_audiobooks(db, now=NOW) == 0
    assert len(db.list_wanted()) == 1

    _shelve(
        db,
        kind="audiobook",
        title="Dune (narrated)",
        author="Someone Else",
        isbn=DUNE_ISBN10,
    )
    assert sweep_wanted_audiobooks(db, now=NOW) == 0
    assert db.get_wanted(rows[0]["id"]) is None
    assert db.list_wanted() == []


def test_idle_sweep_does_not_reconnect_per_book(db, monkeypatch):
    for index in range(30):
        _shelve(
            db,
            kind="book",
            title=f"Title {index}",
            author=f"Author {index}",
            isbn="",
            genre="Fiction",
        )
    assert sweep_wanted_audiobooks(db, now=NOW) == 30
    calls = {"n": 0}
    original = Database._connect

    def counting(self):
        calls["n"] += 1
        return original(self)

    monkeypatch.setattr(Database, "_connect", counting)
    assert sweep_wanted_audiobooks(db, now=NOW) == 0
    assert calls["n"] <= 5


def test_sweep_does_not_call_the_indexer(db, monkeypatch):
    _shelve(db, kind="book", title="Dune", author="Frank Herbert", isbn=DUNE_ISBN, genre="Fiction")

    def explode(self, *args, **kwargs):
        raise AssertionError("sweep called the indexer")

    monkeypatch.setattr(NZBFinderClient, "search", explode)
    monkeypatch.setattr(SABClient, "addfile", explode)
    assert sweep_wanted_audiobooks(db, now=NOW) == 1


def test_dismissed_row_is_never_searched(db):
    book = _shelve(db, kind="book", title="Dune", author="Frank Herbert", isbn=DUNE_ISBN, genre="Fiction")
    assert sweep_wanted_audiobooks(db, now=NOW) == 1
    row = db.list_wanted()[0]
    assert row["work_id"] == book["id"]
    dismissed = db.dismiss_wanted(row["id"], now=NOW)
    assert dismissed is not None and dismissed["status"] == "dismissed"
    calls = []

    def search(sought):
        calls.append(sought)
        return [HIT]

    assert poll_wanted(db, Settings(), now=NOW + 10**9, search=search) == 0
    assert calls == []
    assert sweep_wanted_audiobooks(db, now=NOW + 5) == 0
    assert db.get_wanted(row["id"])["status"] == "dismissed"


def test_sweep_skips_nonfiction_book(db):
    history = _shelve(
        db,
        kind="book",
        title="The Power Broker",
        author="Robert Caro",
        genre="Biography, History",
    )
    fiction = _shelve(
        db,
        kind="book",
        title="Dune",
        author="Frank Herbert",
        isbn=DUNE_ISBN,
        genre="Science Fiction, Fantasy",
    )
    assert sweep_wanted_audiobooks(db, now=NOW) == 1
    rows = db.list_wanted()
    assert [row["work_id"] for row in rows] == [fiction["id"]]
    assert rows[0]["source"] == "sweep"
    assert all(row["work_id"] != history["id"] for row in rows)


def test_sweep_skips_unknown_genre(db):
    _shelve(db, kind="book", title="Untitled Poems", author="Ada Lovelace", genre="")
    _shelve(db, kind="book", title="Field Notes", author="Ada Lovelace", genre="Poetry")
    assert sweep_wanted_audiobooks(db, now=NOW) == 0
    assert db.list_wanted() == []


def test_sweep_clears_untouched_nonfiction_row(db):
    book = _shelve(
        db,
        kind="book",
        title="Circe",
        author="Madeline Miller",
        genre="Fiction",
    )
    assert sweep_wanted_audiobooks(db, now=NOW) == 1
    row = db.list_wanted()[0]
    assert row["source"] == "sweep"
    assert row["job_id"] is None
    stored = db.get_work(book["id"])
    assert stored is not None
    stored["genre"] = "Biography"
    db.upsert_work(stored)
    assert sweep_wanted_audiobooks(db, now=NOW) == 0
    assert db.get_wanted(row["id"]) is None

    kept = _shelve(
        db,
        kind="book",
        title="The Left Hand of Darkness",
        author="Ursula K. Le Guin",
        genre="Fiction",
    )
    assert sweep_wanted_audiobooks(db, now=NOW) == 1
    dismissed_row = next(item for item in db.list_wanted() if item["work_id"] == kept["id"])
    assert db.dismiss_wanted(dismissed_row["id"], now=NOW)["status"] == "dismissed"
    kept_stored = db.get_work(kept["id"])
    assert kept_stored is not None
    kept_stored["genre"] = "History"
    db.upsert_work(kept_stored)
    assert sweep_wanted_audiobooks(db, now=NOW) == 0
    assert db.get_wanted(dismissed_row["id"])["status"] == "dismissed"
    kept_stored["genre"] = "Science Fiction"
    db.upsert_work(kept_stored)
    assert sweep_wanted_audiobooks(db, now=NOW) == 0
    assert db.get_wanted(dismissed_row["id"])["status"] == "dismissed"

    legacy_book = _shelve(
        db,
        kind="book",
        title="Salt Fat Acid Heat",
        author="Samin Nosrat",
        genre="Cooking",
    )
    legacy = _audiobook_want(db, title="Salt Fat Acid Heat", author="Samin Nosrat", work_id=legacy_book["id"], isbn="")
    assert legacy.get("source") in (None, "")
    unknown_book = _shelve(db, kind="book", title="Field Guide", author="Ada Lovelace", genre="Essays")
    unknown = _audiobook_want(db, title="Field Guide", author="Ada Lovelace", work_id=unknown_book["id"], isbn="")
    assert sweep_wanted_audiobooks(db, now=NOW) == 0
    assert db.get_wanted(legacy["id"]) is None
    assert db.get_wanted(unknown["id"]) is None


def test_sweep_keeps_row_with_job_and_manual_row(db):
    job_book = _shelve(
        db,
        kind="book",
        title="Team of Rivals",
        author="Doris Kearns Goodwin",
        genre="History",
    )
    job_row = _audiobook_want(
        db,
        title="Team of Rivals",
        author="Doris Kearns Goodwin",
        work_id=job_book["id"],
        isbn="",
        source="sweep",
        job_id="job-rivals",
    )
    manual_book = _shelve(
        db,
        kind="book",
        title="Good to Great",
        author="Jim Collins",
        genre="Business",
    )
    manual = _audiobook_want(
        db,
        title="Good to Great",
        author="Jim Collins",
        work_id=manual_book["id"],
        isbn="",
        source="manual",
    )
    legacy_book = _shelve(
        db,
        kind="book",
        title="A Brief History of Time",
        author="Stephen Hawking",
        genre="Science",
    )
    legacy_job = _audiobook_want(
        db,
        title="A Brief History of Time",
        author="Stephen Hawking",
        work_id=legacy_book["id"],
        isbn="",
        job_id="job-hawking",
    )
    fiction = _shelve(
        db,
        kind="book",
        title="The Hobbit",
        author="J.R.R. Tolkien",
        genre="Fantasy",
    )
    assert sweep_wanted_audiobooks(db, now=NOW) == 1
    assert db.get_wanted(job_row["id"])["job_id"] == "job-rivals"
    assert db.get_wanted(job_row["id"])["status"] == "wanted"
    kept_manual = db.get_wanted(manual["id"])
    assert kept_manual["source"] == "manual"
    assert kept_manual["job_id"] is None
    assert kept_manual["status"] == "wanted"
    assert db.get_wanted(legacy_job["id"])["job_id"] == "job-hawking"
    created = [row for row in db.list_wanted() if row["work_id"] == fiction["id"]]
    assert len(created) == 1
    assert created[0]["source"] == "sweep"


def test_due_row_enqueues_one_asked_job_and_second_poll_is_quiet(db, monkeypatch):
    row = _audiobook_want(db)
    calls = []

    def search(sought):
        calls.append(dict(sought))
        return [HIT]

    def boom(*_args, **_kwargs):
        raise AssertionError("SABnzbd was called")

    monkeypatch.setattr(SABClient, "addfile", boom)
    monkeypatch.setattr("librarian.jobs.SABClient", lambda *a, **k: (_ for _ in ()).throw(AssertionError("SAB")))

    assert poll_wanted(db, Settings(), now=NOW, search=search) == 1
    assert calls[0]["kind"] == "audiobook"
    assert calls[0]["cat"] == "3030"
    stored = db.get_wanted(row["id"])
    assert stored["status"] == "asked"
    jobs = db.list_jobs(limit=10)
    assert len(jobs) == 1
    assert jobs[0]["status"] == "asked"
    assert jobs[0]["id"] == stored["job_id"]
    assert not jobs[0].get("nzo_id")
    assert jobs[0]["payload"]["source"] == "wanted"
    assert poll_active_jobs(db, Settings()) == 0

    assert poll_wanted(db, Settings(), now=NOW + 30, search=search) == 0
    assert len(calls) == 1
    assert len(db.list_jobs(limit=10)) == 1
    assert db.get_wanted(row["id"])["status"] == "asked"


def test_overlapping_claims_enqueue_one_job(db):
    row = _audiobook_want(db)
    job = {
        "status": "asked",
        "indexer_guid": "guid-dune",
        "title": "Dune",
        "kind": "audiobook",
        "requested_by": "wanted",
        "payload": {"source": "wanted", "guid": "guid-dune"},
    }
    barrier = threading.Barrier(2)
    found = []
    errors = []

    def claim():
        try:
            barrier.wait()
            found.append(db.claim_and_create_wanted_job(row["id"], dict(job), now=NOW))
        except Exception as exc:  # noqa: BLE001 — surface thread failures in the assertion
            errors.append(exc)

    threads = [threading.Thread(target=claim) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    winners = [item for item in found if item]
    assert len(winners) == 1
    assert len(db.list_jobs(limit=10)) == 1
    assert db.get_wanted(row["id"])["status"] == "asked"


def test_backoff_walks_off_six_then_twelve_and_stays_at_twelve():
    hour = 60 * 60
    assert backoff_seconds(1) == 6 * hour
    assert backoff_seconds(2) == 12 * hour
    assert backoff_seconds(3) == 12 * hour
    assert backoff_seconds(9) == 12 * hour


def test_misses_wait_six_then_twelve_hours_and_never_a_week(db):
    row = _audiobook_want(db)
    rungs = []

    def search(sought):
        rungs.append(sought["rung"])
        return []

    hour = 60 * 60
    moment = NOW
    for streak, wait in ((1, 6 * hour), (2, 12 * hour), (3, 12 * hour), (4, 12 * hour)):
        assert poll_wanted(db, Settings(), now=moment, search=search) == 3
        fresh = db.get_wanted(row["id"])
        assert fresh["status"] == "wanted"
        assert fresh["miss_streak"] == streak
        assert fresh["next_search_at"] == pytest.approx(moment + wait)
        assert poll_wanted(db, Settings(), now=fresh["next_search_at"] - 1, search=search) == 0
        moment = fresh["next_search_at"]
    assert rungs == ["isbn", "title", "title_author"] * 4


def test_reopen_resets_the_miss_streak(db):
    from librarian.wanted import add_wanted, dismiss_wanted

    row = add_wanted(db, {"title": "Kindred", "author": "Octavia Butler", "kind": "audiobook"}, now=NOW)
    poll_wanted(db, Settings(), now=NOW, search=lambda _s: [])
    poll_wanted(db, Settings(), now=NOW + 7 * 60 * 60, search=lambda _s: [])
    assert db.get_wanted(row["id"])["miss_streak"] == 2
    dismiss_wanted(db, row["id"], now=NOW + 8 * 60 * 60)
    again = add_wanted(
        db, {"title": "Kindred", "author": "Octavia Butler", "kind": "audiobook"}, now=NOW + 9 * 60 * 60
    )
    assert again["id"] == row["id"]
    assert again["miss_streak"] == 0
    assert again["next_search_at"] == pytest.approx(NOW + 9 * 60 * 60)


def test_junk_multidisc_pushes_next_search_at(db):
    row = _audiobook_want(db)

    def search(sought):
        assert sought["cat"] == "3030"
        return [JUNK]

    assert poll_wanted(db, Settings(), now=NOW, search=search) == 3
    fresh = db.get_wanted(row["id"])
    assert fresh["status"] == "wanted"
    assert fresh["miss_streak"] == 1
    assert fresh["next_search_at"] == pytest.approx(NOW + backoff_seconds(1))
    assert fresh["job_id"] is None
    assert db.list_jobs(limit=10) == []
    assert poll_wanted(db, Settings(), now=NOW + 1, search=search) == 0


def test_failed_job_returns_to_wanted_on_backoff_clock(db):
    row = _audiobook_want(db)

    def search(_sought):
        return [HIT]

    poll_wanted(db, Settings(), now=NOW, search=search)
    stored = db.get_wanted(row["id"])
    job_id = stored["job_id"]
    db.update_job(job_id, nzo_id="nzo-1", status="downloading")

    class Sab:
        def job_status(self, _nzo):
            return {
                "status": "failed",
                "fail_message": "unpack failed",
                "sab_status": "Failed",
                "name": "Dune",
                "percentage": "0",
                "bytes": 10,
                "storage": "",
            }

    before = time.time()
    failed = poll_job(db, Settings(), job_id, sab=Sab())
    after = time.time()
    assert failed["status"] == "failed"
    fresh = db.get_wanted(row["id"])
    assert fresh["status"] == "wanted"
    assert fresh["job_id"] is None
    assert fresh["miss_streak"] == 1
    assert before + backoff_seconds(1) <= fresh["next_search_at"] <= after + backoff_seconds(1) + 1

    def explode(_sought):
        raise AssertionError("searched before the backoff clock")

    assert poll_wanted(db, Settings(), now=time.time(), search=explode) == 0


def test_confirm_sends_once_and_does_not_enqueue_again(db):
    row = _audiobook_want(db)

    def search(_sought):
        return [HIT]

    poll_wanted(db, Settings(), now=NOW, search=search)
    job_id = db.get_wanted(row["id"])["job_id"]
    sab_calls = []

    class Finder:
        def fetch_nzb(self, guid):
            assert guid == "guid-dune"
            return b"<nzb></nzb>"

    class Sab:
        def addfile(self, data, **kwargs):
            sab_calls.append(kwargs.get("nzbname"))
            assert data.startswith(b"<nzb")
            return "nzo-confirm"

    confirmed = confirm_asked_job(db, Settings(), job_id, sab=Sab(), nzb=Finder())
    assert confirmed["status"] == "queued"
    assert confirmed["nzo_id"] == "nzo-confirm"
    assert sab_calls == ["Dune"]
    assert db.get_wanted(row["id"])["status"] == "asked"

    def explode(_sought):
        raise AssertionError("second poll searched an asked row")

    assert poll_wanted(db, Settings(), now=NOW + 10**6, search=explode) == 0
    assert len(db.list_jobs(limit=10)) == 1
    with pytest.raises(ValueError):
        confirm_asked_job(db, Settings(), job_id, sab=Sab(), nzb=Finder())
    assert sab_calls == ["Dune"]


def test_nzbfinder_client_searches_audiobook_category(db):
    row = _audiobook_want(db)
    seen = []

    class Finder:
        def search(self, query, *, cat=None, kind=None, limit=25, offset=0, keep_untyped=False):
            seen.append({"query": query, "cat": cat, "kind": kind, "limit": limit})
            return [HIT]

        def close(self):
            seen.append("close")

    assert poll_wanted(db, Settings(), now=NOW, client=Finder()) == 1
    assert seen == [
        {"query": DUNE_ISBN, "cat": "3030", "kind": "audiobook", "limit": 25}
    ]
    assert db.get_wanted(row["id"])["status"] == "asked"


def test_indexer_error_waits_without_a_miss(db):
    row = _audiobook_want(db)

    def search(_sought):
        raise NZBFinderError("indexer down")

    assert poll_wanted(db, Settings(), now=NOW, search=search) == 1
    fresh = db.get_wanted(row["id"])
    assert fresh["status"] == "wanted"
    assert fresh["miss_streak"] == 0
    assert fresh["next_search_at"] == pytest.approx(NOW + BASE_BACKOFF_SECONDS)
    assert db.list_jobs(limit=10) == []


def test_unconfigured_indexer_does_not_search(db):
    row = _audiobook_want(db)
    assert poll_wanted(db, Settings(), now=NOW) == 0
    assert poll_wanted(db, Settings(nzbfinder_api_token="token", nzbfinder_muted=True), now=NOW) == 0
    fresh = db.get_wanted(row["id"])
    assert fresh["status"] == "wanted"
    assert fresh["miss_streak"] == 0
    assert fresh["next_search_at"] == pytest.approx(NOW)


def test_sought_audiobook_uses_nzbfinder_category():
    sought = sought_for_row({"kind": "audiobook", "title": "Dune", "author": "Frank Herbert"})
    assert sought["cat"] == "3030"
    assert sought["q"] == "Dune"


def test_poller_tick_calls_sweep_and_search(db, monkeypatch):
    seen = []
    monkeypatch.setattr(
        "librarian.wanted_sweep.sweep_wanted_audiobooks",
        lambda *_a, **_k: seen.append("sweep") or 0,
    )
    monkeypatch.setattr(
        "librarian.wanted_search.poll_wanted",
        lambda *_a, **_k: seen.append("search") or 0,
    )
    JobPoller(
        db,
        lambda: Settings(
            nzbfinder_api_token="tok",
            nzbfinder_url="https://nzbfinder.test",
            auto_audiobook_wants="all_fiction",
        ),
        interval=3600,
    ).tick()
    assert seen == ["sweep", "search"]


def _owner_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    monkeypatch.setenv("LIBRARIAN_SKIP_APP_BOOT", "1")
    monkeypatch.setattr("librarian.config.load_dotenv", lambda path=None: None)
    save_settings(tmp_path, Settings(llm_api_key=""))
    clear_session_secret_cache()
    clear_rate_limits()
    client = TestClient(create_app(tmp_path))
    assert (
        client.post(
            "/api/auth/local/login",
            json={"username": "owner", "password": "password123"},
        ).status_code
        == 200
    )
    return client


def test_wanted_api_readers_list_owner_adds_and_dismisses(tmp_path, monkeypatch):
    client = _owner_client(tmp_path, monkeypatch)
    added = client.post(
        "/api/wanted",
        json={"title": "Kindred", "author": "Octavia Butler", "kind": "audiobook"},
    )
    assert added.status_code == 200
    item = added.json()["item"]
    assert item["status"] == "wanted"
    assert item["title"] == "Kindred"
    assert item["kind"] == "audiobook"
    assert item["job_id"] is None
    database = Database(tmp_path / "librarian.db")
    try:
        assert database.list_jobs(limit=10) == []
    finally:
        database.close()

    listed = client.get("/api/wanted")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()["items"]] == [item["id"]]

    minted = client.post("/api/invites", json={"role": "reader"})
    token = minted.json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    redeemed = client.post(
        "/api/invites/redeem/local",
        json={"token": token, "username": "reader1", "password": "password123"},
    )
    assert redeemed.status_code == 200
    assert client.get("/api/wanted").status_code == 200
    assert client.post("/api/wanted", json={"title": "Nope", "kind": "book"}).status_code == 403
    assert client.post(f"/api/wanted/{item['id']}/dismiss").status_code == 403

    client.post("/api/auth/logout")
    client.cookies.clear()
    assert (
        client.post(
            "/api/auth/local/login",
            json={"username": "owner", "password": "password123"},
        ).status_code
        == 200
    )
    dismissed = client.post(f"/api/wanted/{item['id']}/dismiss")
    assert dismissed.status_code == 200
    assert dismissed.json()["item"]["status"] == "dismissed"
    assert client.get("/api/wanted").json()["items"] == []
    assert client.get("/api/wanted", params={"status": "dismissed"}).json()["items"][0]["id"] == item["id"]


def test_add_wanted_with_work_id_copies_catalog_fields(tmp_path, monkeypatch):
    client = _owner_client(tmp_path, monkeypatch)
    database = Database(tmp_path / "librarian.db")
    try:
        work = database.upsert_work(
            {"kind": "book", "title": "Parable of the Sower", "author": "Octavia Butler", "isbn": "0446675504"}
        )
    finally:
        database.close()
    added = client.post("/api/wanted", json={"work_id": work["id"], "kind": "audiobook"})
    assert added.status_code == 200
    item = added.json()["item"]
    assert item["work_id"] == work["id"]
    assert item["title"] == "Parable of the Sower"
    assert item["author"] == "Octavia Butler"
    assert item["kind"] == "audiobook"
    database = Database(tmp_path / "librarian.db")
    try:
        stored = database.get_wanted(item["id"])
        assert stored is not None
        assert stored["source"] == "manual"
    finally:
        database.close()
    missing = client.post("/api/wanted", json={"work_id": "missing-work", "kind": "book"})
    assert missing.status_code == 404


def test_owned_book_is_not_inserted_and_missing_audiobook_still_is(tmp_path, monkeypatch):
    client = _owner_client(tmp_path, monkeypatch)
    database = Database(tmp_path / "librarian.db")
    try:
        book = _shelve(
            database,
            kind="book",
            title="Atomic Habits",
            author="James Clear",
            isbn="9780735211292",
        )
        _shelve(
            database,
            kind="audiobook",
            title="Messiah Unabridged",
            author="Someone Else",
            series_name="Dune",
            series_index="2",
        )
        series_book = database.upsert_work(
            {
                "kind": "book",
                "title": "Dune Messiah",
                "author": "",
                "series_name": "Dune",
                "series_index": "2",
            }
        )
    finally:
        database.close()

    refused = client.post(
        "/api/wanted",
        json={"title": "Atomic Habits", "author": "James Clear", "isbn": "9780735211292", "kind": "book"},
    )
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["detail"] == "Already on the shelf"
    assert detail["work_id"] == book["id"]
    assert detail["kind"] == "book"

    database = Database(tmp_path / "librarian.db")
    try:
        assert database.list_wanted() == []
    finally:
        database.close()

    title_only = client.post("/api/wanted", json={"title": "Atomic Habits", "kind": "book"})
    assert title_only.status_code == 200

    audio = client.post(
        "/api/wanted",
        json={"title": "Atomic Habits", "author": "James Clear", "isbn": "9780735211292", "kind": "audiobook"},
    )
    assert audio.status_code == 200
    assert audio.json()["item"]["kind"] == "audiobook"
    assert audio.json()["item"]["shelved_book"]["id"] == book["id"]
    assert audio.json()["item"]["shelved_audiobook"] is None
    assert audio.json()["item"]["shelved"] is None

    listed = client.get("/api/wanted")
    assert listed.status_code == 200
    habits = next(row for row in listed.json()["items"] if row["kind"] == "audiobook")
    assert habits["title"] == "Atomic Habits"
    assert "shelved_book" not in habits
    assert "shelved_audiobook" not in habits

    series_refused = client.post("/api/wanted", json={"work_id": series_book["id"], "kind": "audiobook"})
    assert series_refused.status_code == 409
    assert series_refused.json()["detail"]["kind"] == "audiobook"

    database = Database(tmp_path / "librarian.db")
    try:
        rows = database.list_wanted()
        assert all(not (row["kind"] == "book" and row["author"] == "James Clear") for row in rows)
        assert any(row["kind"] == "audiobook" and row["title"] == "Atomic Habits" for row in rows)
        assert all(row["work_id"] != series_book["id"] for row in rows)
    finally:
        database.close()


def test_wanted_list_does_not_scan_shelved_works(tmp_path, monkeypatch):
    client = _owner_client(tmp_path, monkeypatch)
    added = client.post(
        "/api/wanted",
        json={"title": "Kindred", "author": "Octavia Butler", "kind": "audiobook"},
    )
    assert added.status_code == 200

    def _refuse_catalog_scan(self, kind):
        raise AssertionError(f"wanted list scanned shelved {kind}")

    monkeypatch.setattr(Database, "list_shelved_works", _refuse_catalog_scan)
    listed = client.get("/api/wanted")
    assert listed.status_code == 200
    item = listed.json()["items"][0]
    assert item["id"] == added.json()["item"]["id"]
    assert item["title"] == "Kindred"
    assert "shelved_book" not in item


def test_subtitle_shelf_title_blocks_wanted_for_that_kind_only(tmp_path, monkeypatch):
    client = _owner_client(tmp_path, monkeypatch)
    database = Database(tmp_path / "librarian.db")
    try:
        book = _shelve(
            database,
            kind="book",
            title="Atomic Habits: An Easy & Proven Way to Build Good Habits & Break Bad Ones",
            author="James Clear",
            isbn="",
        )
    finally:
        database.close()

    refused = client.post(
        "/api/wanted",
        json={"title": "Atomic Habits", "author": "James Clear", "kind": "book"},
    )
    assert refused.status_code == 409
    assert refused.json()["detail"]["work_id"] == book["id"]
    assert refused.json()["detail"]["kind"] == "book"

    shared_word = client.post(
        "/api/wanted",
        json={"title": "Atomic", "author": "James Clear", "kind": "book"},
    )
    assert shared_word.status_code == 200

    audio = client.post(
        "/api/wanted",
        json={"title": "Atomic Habits", "author": "James Clear", "kind": "audiobook"},
    )
    assert audio.status_code == 200
    assert audio.json()["item"]["shelved_book"]["id"] == book["id"]
    assert audio.json()["item"]["shelved_audiobook"] is None


def _open_row(database: Database, *, title: str, kind: str, updated_at: float, status: str = "wanted"):
    from librarian.wanted import dedupe_key

    key = dedupe_key(kind=kind, title=title, author="Ada")
    return database.insert_wanted(
        {
            "dedupe_key": key,
            "title": title,
            "author": "Ada",
            "isbn": "",
            "kind": kind,
            "status": status,
            "miss_streak": 0,
            "next_search_at": NOW,
            "created_at": updated_at,
            "updated_at": updated_at,
        }
    )


def test_wanted_list_pages_after_kind_and_stays_a_cheap_read(tmp_path, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("ShelfIndex does not belong on the Wanted list")

    monkeypatch.setattr("librarian.web.routers.wanted.ShelfIndex", boom)
    client = _owner_client(tmp_path, monkeypatch)
    database = Database(tmp_path / "librarian.db")
    try:
        first = _open_row(database, title="One", kind="book", updated_at=300)
        second = _open_row(database, title="Two", kind="book", updated_at=200)
        third = _open_row(database, title="Three", kind="book", updated_at=100)
        _open_row(database, title="Heard", kind="audiobook", updated_at=400)
    finally:
        database.close()

    books = client.get("/api/wanted", params={"kind": "book", "page": 1, "page_size": 2})
    assert books.status_code == 200
    body = books.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert [row["id"] for row in body["items"]] == [first["id"], second["id"]]
    assert all(row["kind"] == "book" for row in body["items"])
    assert "audiobook" in body["kinds"]
    assert "book" in body["kinds"]

    page_two = client.get("/api/wanted", params={"kind": "book", "page": 2, "page_size": 2})
    assert [row["id"] for row in page_two.json()["items"]] == [third["id"]]
    assert first["id"] not in [row["id"] for row in page_two.json()["items"]]
    assert second["id"] not in [row["id"] for row in page_two.json()["items"]]


def test_wanted_search_respects_kind_ids_and_asked_lock(tmp_path, monkeypatch):
    from librarian.config import Settings, save_settings
    from librarian.sabnzbd import SABClient
    from librarian.wanted_search import search_wanted_selection

    client = _owner_client(tmp_path, monkeypatch)
    save_settings(tmp_path, Settings(nzbfinder_api_token="token", nzbfinder_url="https://indexer.test"))
    database = Database(tmp_path / "librarian.db")
    calls = []

    def search(sought):
        calls.append(dict(sought))
        return []

    def boom(*_args, **_kwargs):
        raise AssertionError("SABnzbd was called")

    monkeypatch.setattr(SABClient, "addfile", boom)
    try:
        book = _open_row(database, title="Paper", kind="book", updated_at=30)
        other = _open_row(database, title="Voice", kind="audiobook", updated_at=20)
        asked = _open_row(database, title="Slip", kind="book", updated_at=10, status="asked")
        settings = Settings(nzbfinder_api_token="token")
        by_kind = search_wanted_selection(
            database, settings, all_rows=True, kind="book", now=NOW, search=search
        )
        assert [item["q"] for item in calls] == ["Paper", "Paper Ada"]
        outcomes = {row["id"]: row["outcome"] for row in by_kind}
        assert outcomes[asked["id"]] == "already_asked"
        assert outcomes[book["id"]] == "miss"
        assert other["id"] not in outcomes
        calls.clear()
        by_ids = search_wanted_selection(
            database, settings, ids=[other["id"]], now=NOW, search=search
        )
        assert [item["q"] for item in calls] == ["Voice", "Voice Ada"]
        assert [row["id"] for row in by_ids] == [other["id"]]
        calls.clear()
        again = search_wanted_selection(
            database,
            settings,
            ids=[asked["id"], book["id"]],
            now=NOW + 10**9,
            search=search,
        )
        assert [item["q"] for item in calls] == ["Paper", "Paper Ada"]
        assert any(row["id"] == asked["id"] and row["outcome"] == "already_asked" for row in again)

        http_calls = []

        class Finder:
            def __init__(self, *_args, **_kwargs):
                pass

            def search(self, _query, cat="", kind=None, limit=25):
                http_calls.append(kind)
                return []

            def close(self):
                return None

        monkeypatch.setattr("librarian.wanted_search.NZBFinderClient", Finder)
        found = client.post("/api/wanted/search", json={"all": True, "kind": "audiobook"})
        assert found.status_code == 200, found.text
        assert http_calls == ["audiobook", "audiobook"]
        assert all(row["id"] != book["id"] for row in found.json()["results"])
    finally:
        database.close()

    minted = client.post("/api/invites", json={"role": "reader"})
    client.post("/api/auth/logout")
    client.cookies.clear()
    redeemed = client.post(
        "/api/invites/redeem/local",
        json={"token": minted.json()["token"], "username": "reader1", "password": "password123"},
    )
    assert redeemed.status_code == 200
    assert client.post("/api/wanted/search", json={"all": True}).status_code == 403


def test_ask_wanted_hit_does_not_enqueue_twice(db, monkeypatch):
    from librarian.sabnzbd import SABClient
    from librarian.wanted_search import ask_wanted_hit

    row = _audiobook_want(db)
    monkeypatch.setattr(SABClient, "addfile", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("SAB")))
    first = ask_wanted_hit(db, row["id"], {"guid": "guid-1", "title": "Dune"}, now=NOW)
    assert first["outcome"] == "hit"
    assert db.get_wanted(row["id"])["status"] == "asked"
    second = ask_wanted_hit(db, row["id"], {"guid": "guid-2", "title": "Dune again"}, now=NOW + 1)
    assert second["outcome"] == "already_asked"
    assert second["note"] == "Already on a slip"
    assert len(db.list_jobs(limit=10)) == 1


DORIAN = "Titan.Comics.Dorian.Gray.2026.HYBRID.COMIC.eBook-21A1"
DORIAN_GUID = "575ab9e4-6d92-4b5e-8c2a-d544d27f963e"


def _indexer_transport(results, seen):
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        seen.append(
            {
                "path": request.url.path,
                "query": params.get("query", ""),
                "cat": params.get("cat", ""),
            }
        )
        return httpx.Response(200, json={"results": results})

    return httpx.MockTransport(handler)


def test_comic_release_name_want_grabs_the_posting_the_indexer_returns(db):
    """Discover/RSS saved the posting name. The indexer returns that posting. Grab it."""
    from librarian.wanted import add_wanted

    row = add_wanted(db, {"title": DORIAN, "kind": "comic"}, now=NOW)
    seen: list = []
    finder = NZBFinderClient(
        "https://nzbfinder.ws",
        "test-token",
        transport=_indexer_transport(
            [{"title": DORIAN, "guid": DORIAN_GUID, "category": "7030", "size": 61_000_000}],
            seen,
        ),
    )
    try:
        assert poll_wanted(db, Settings(), now=NOW, client=finder) == 1
    finally:
        finder.close()
    assert seen == [{"path": "/api/v2/search", "query": DORIAN, "cat": "7030"}]
    fresh = db.get_wanted(row["id"])
    assert fresh["status"] == "asked"
    assert fresh["miss_streak"] == 0
    job = db.get_job(fresh["job_id"])
    assert job["status"] == "asked"
    assert job["indexer_guid"] == DORIAN_GUID
    assert job["kind"] == "comic"


def test_title_only_glance_still_misses_and_backs_off(db):
    """A short title with no author is not the release. Nothing found stays honest."""
    from librarian.wanted import add_wanted

    row = add_wanted(db, {"title": "Dune", "kind": "comic"}, now=NOW)
    seen: list = []
    finder = NZBFinderClient(
        "https://nzbfinder.ws",
        "test-token",
        transport=_indexer_transport(
            [{"title": "Dune", "guid": "guid-other-dune", "category": "7030"}], seen
        ),
    )
    try:
        assert poll_wanted(db, Settings(), now=NOW, client=finder) == 1
    finally:
        finder.close()
    fresh = db.get_wanted(row["id"])
    assert fresh["status"] == "wanted"
    assert fresh["miss_streak"] == 1
    assert fresh["next_search_at"] == pytest.approx(NOW + backoff_seconds(1))
    assert db.list_jobs(limit=10) == []


def test_wanted_add_with_clicked_hit_files_that_guid(tmp_path, monkeypatch):
    """Get on a Discover/RSS card: one call saves the row and asks for that posting."""
    client = _owner_client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        NZBFinderClient,
        "search_traced",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("add must not search")),
    )
    hit = {
        "guid": DORIAN_GUID,
        "title": DORIAN,
        "kind": "comic",
        "category": "7030",
        "host_id": "nzbfinder",
        "download_url": "https://nzbfinder.ws/api/v2/download?id=x&api_token=secret-token",
    }
    added = client.post("/api/wanted", json={"title": DORIAN, "kind": "comic", "hit": hit})
    assert added.status_code == 200
    body = added.json()
    assert body["item"]["status"] == "asked"
    assert body["outcome"] == "hit"
    database = Database(tmp_path / "librarian.db")
    try:
        jobs = database.list_jobs(limit=10)
        assert len(jobs) == 1
        assert jobs[0]["indexer_guid"] == DORIAN_GUID
        assert jobs[0]["status"] == "asked"
        assert jobs[0]["id"] == body["job_id"]
        assert "secret-token" not in str(database.get_job(jobs[0]["id"])["payload"])
    finally:
        database.close()

    again = client.post("/api/wanted", json={"title": DORIAN, "kind": "comic", "hit": hit})
    assert again.status_code == 200
    assert again.json()["item"]["status"] == "asked"
    database = Database(tmp_path / "librarian.db")
    try:
        assert len(database.list_jobs(limit=10)) == 1
    finally:
        database.close()
