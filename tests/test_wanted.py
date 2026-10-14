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
    return database.insert_wanted(
        {
            "dedupe_key": key,
            "work_id": fields.get("work_id") or None,
            "title": fields["title"],
            "author": fields["author"],
            "isbn": fields["isbn"],
            "kind": fields["kind"],
            "status": "wanted",
            "miss_streak": 0,
            "next_search_at": NOW,
        }
    )


def test_sweep_marks_unmatched_book_and_isbn_match_clears(db):
    book = _shelve(
        db,
        kind="book",
        title="Dune",
        author="Frank Herbert",
        isbn=DUNE_ISBN,
    )
    _shelve(db, kind="magazine", title="Wired", author="")
    unshelved = db.upsert_work({"kind": "book", "title": "Shell", "author": "Nobody"})
    assert sweep_wanted_audiobooks(db, now=NOW) == 1
    rows = db.list_wanted()
    assert len(rows) == 1
    assert rows[0]["work_id"] == book["id"]
    assert rows[0]["kind"] == "audiobook"
    assert rows[0]["status"] == "wanted"
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


def test_sweep_does_not_call_the_indexer(db, monkeypatch):
    _shelve(db, kind="book", title="Dune", author="Frank Herbert", isbn=DUNE_ISBN)

    def explode(self, *args, **kwargs):
        raise AssertionError("sweep called the indexer")

    monkeypatch.setattr(NZBFinderClient, "search", explode)
    monkeypatch.setattr(SABClient, "addfile", explode)
    assert sweep_wanted_audiobooks(db, now=NOW) == 1


def test_dismissed_row_is_never_searched(db):
    book = _shelve(db, kind="book", title="Dune", author="Frank Herbert", isbn=DUNE_ISBN)
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


def test_three_misses_then_silence(db, caplog):
    row = _audiobook_want(db)
    calls = []

    def search(_sought):
        calls.append(1)
        return []

    moment = NOW
    caplog.set_level(logging.INFO, logger="librarian.wanted_search")
    for streak in (1, 2, 3):
        assert poll_wanted(db, Settings(), now=moment, search=search) == 1
        fresh = db.get_wanted(row["id"])
        assert fresh["status"] == "wanted"
        assert fresh["miss_streak"] == streak
        assert fresh["next_search_at"] == pytest.approx(moment + backoff_seconds(streak))
        assert poll_wanted(db, Settings(), now=moment + 1, search=search) == 0
        assert db.get_wanted(row["id"])["miss_streak"] == streak
        moment = fresh["next_search_at"]
    assert caplog.text.count("dropped to slow search") == 1
    assert poll_wanted(db, Settings(), now=moment, search=search) == 1
    assert db.get_wanted(row["id"])["miss_streak"] == 4
    assert caplog.text.count("dropped to slow search") == 1
    assert len(calls) == 4


def test_junk_multidisc_pushes_next_search_at(db):
    row = _audiobook_want(db)

    def search(sought):
        assert sought["cat"] == "3030"
        return [JUNK]

    assert poll_wanted(db, Settings(), now=NOW, search=search) == 1
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
    assert sought["q"] == "Frank Herbert Dune"


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
    JobPoller(db, lambda: Settings(), interval=3600).tick()
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
