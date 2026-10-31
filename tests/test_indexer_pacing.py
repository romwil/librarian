"""Phase 3.3: 500 calls/day/host, Wanted ≤ half, enabled(settings), 429 still ends the pass.

SQLite is real. NZBFinder / SAB HTTP is mocked. Wanted never calls SABnzbd.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from librarian.config import Settings
from librarian.db import Database
from librarian.indexer_budget import (
    INDEXER_DAILY_CALL_BUDGET,
    PURPOSE_INTERACTIVE,
    PURPOSE_WANTED,
    WantedBudgetExhausted,
    allow_call,
    current_wanted_cap,
    daily_wanted_budget,
    halt_wanted_on_429,
    household_totals,
    record_call,
    remaining_host,
    remaining_wanted,
    wanted_calls,
)
from librarian.nzbfinder import NZBFinderRateLimited
from librarian.poller import DEFAULT_OWNED_POLL_SECONDS, JobPoller
from librarian.sabnzbd import SABClient
from librarian.wanted import dedupe_key
from librarian.wanted_search import poll_wanted, search_wanted_hosts

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc).timestamp()
DAY_START = datetime(2026, 10, 31, tzinfo=timezone.utc).timestamp()


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


def _want(database: Database, title: str, *, source: str = "manual", now: float = NOW, **extra):
    author = extra.pop("author", "Frank Herbert")
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
            "next_search_at": extra.pop("next_search_at", now),
            "source": source,
            "created_at": extra.pop("created_at", now),
        }
    )


def test_wanted_budget_is_half_of_host_budget():
    assert INDEXER_DAILY_CALL_BUDGET == 500
    assert daily_wanted_budget() == 250
    assert daily_wanted_budget(Settings(indexer_daily_call_budget=100)) == 50


def test_simulated_day_of_due_rows_stays_within_wanted_half(db):
    """3.1 uncapped: every due row in the hourly pass (6k–19k calls). 3.3 caps Wanted at 250."""
    for n in range(180):
        _want(db, f"Bulk {n}", now=DAY_START, next_search_at=DAY_START, created_at=DAY_START + n)

    def search(_sought):
        return []

    total = 0
    for hour in range(24):
        total += poll_wanted(db, Settings(), now=DAY_START + hour * 3600, search=search)
    assert total <= daily_wanted_budget()
    assert wanted_calls(db, "nzbfinder", now=DAY_START) <= 250
    assert wanted_calls(db, "nzbfinder", now=DAY_START) <= INDEXER_DAILY_CALL_BUDGET // 2
    still_due = db.list_due_wanted(now=DAY_START + 23 * 3600)
    assert len(still_due) > 0


def test_user_added_wants_are_searched_before_sweep(db):
    _want(db, "Sweep Book", source="sweep", now=NOW, created_at=NOW + 10)
    _want(db, "Owner Book", source="manual", now=NOW, created_at=NOW)
    searched: list[str] = []

    def search(sought):
        searched.append(sought["title"])
        return []

    poll_wanted(db, Settings(), now=NOW, search=search)
    assert searched[0] == "Owner Book"
    assert "Sweep Book" in searched


def test_a_429_halves_remaining_wanted_allowance_and_ends_the_pass(db):
    _want(db, "First")
    _want(db, "Second")
    _want(db, "Third")

    def search(_sought):
        raise NZBFinderRateLimited("NZBFinder HTTP 429: rate limited")

    calls = poll_wanted(db, Settings(), now=NOW, search=search)
    assert calls == 1
    assert wanted_calls(db, "nzbfinder", now=NOW) == 1
    cap = current_wanted_cap(db, "nzbfinder", now=NOW)
    assert cap == 1 + (250 - 1) // 2
    assert remaining_wanted(db, "nzbfinder", now=NOW) == cap - 1
    assert all(row["miss_streak"] == 0 for row in db.list_wanted())
    assert all(row["status"] == "wanted" for row in db.list_wanted())


def test_wanted_stops_at_half_while_interactive_can_use_the_rest(db):
    record_call(db, "nzbfinder", PURPOSE_WANTED, now=NOW, calls=250)
    assert remaining_wanted(db, "nzbfinder", now=NOW) == 0
    assert remaining_host(db, "nzbfinder", now=NOW) == 250
    assert allow_call(db, "nzbfinder", PURPOSE_WANTED, now=NOW) is False
    assert allow_call(db, "nzbfinder", PURPOSE_INTERACTIVE, now=NOW) is True
    record_call(db, "nzbfinder", PURPOSE_INTERACTIVE, now=NOW, calls=250)
    assert remaining_host(db, "nzbfinder", now=NOW) == 0
    assert allow_call(db, "nzbfinder", PURPOSE_INTERACTIVE, now=NOW) is False


def test_search_wanted_hosts_skips_a_spent_wanted_budget(db, monkeypatch):
    record_call(db, "nzbfinder", PURPOSE_WANTED, now=NOW, calls=250)
    settings = Settings(nzbfinder_api_token="tok", nzbfinder_url="https://nzbfinder.test")
    seen = []

    def boom(*_a, **_k):
        seen.append("called")
        return []

    monkeypatch.setattr("librarian.wanted_search.nzbfinder_search", boom)
    with pytest.raises(WantedBudgetExhausted):
        search_wanted_hosts(
            settings,
            {"q": "Dune", "cat": "3030", "kind": "audiobook"},
            db=db,
            now=NOW,
            purpose=PURPOSE_WANTED,
        )
    assert seen == []


def test_household_totals_have_no_user_ids(db):
    record_call(db, "nzbfinder", PURPOSE_WANTED, now=NOW, calls=8, errors=1)
    record_call(db, "nzbfinder", PURPOSE_INTERACTIVE, now=NOW, calls=4)
    payload = household_totals(
        db,
        [{"id": "nzbfinder", "name": "NZBFinder"}],
        now=NOW,
    )
    blob = str(payload)
    assert "user_id" not in blob
    assert "username" not in blob
    assert payload["hosts"][0]["calls"] == 12
    assert payload["hosts"][0]["wanted_calls"] == 8
    assert payload["hosts"][0]["budget"] == 500
    assert payload["hosts"][0]["wanted_budget"] == 250


def test_unconfigured_poller_steps_stay_off(tmp_path, monkeypatch):
    db = Database(tmp_path / "librarian.db")
    monkeypatch.setattr(
        "librarian.audiobookshelf.match_audiobooks",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("abs ran")),
    )
    monkeypatch.setattr(
        "librarian.owned_slip.sweep_owned_slips",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("owned ran")),
    )
    monkeypatch.setattr(
        "librarian.wanted_search.poll_wanted",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("wanted ran")),
    )
    poller = JobPoller(db, lambda: Settings(), interval=30)
    assert poller._run_step("abs") == 0
    assert poller._run_step("owned") == 0
    assert poller._run_step("wanted") == 0
    assert poller._run_step("watch") == 0
    assert poller._run_step("sab") == 0
    status = {step["id"]: step for step in poller.step_status()["steps"]}
    assert status["abs"]["state"] == "off"
    assert status["abs"]["last_run"] is None
    assert status["owned"]["off_reason"] == "Off: nothing to do"
    assert status["wanted"]["off_reason"] == "Off: not configured"
    assert DEFAULT_OWNED_POLL_SECONDS == 300.0


def test_owned_sweep_one_select_when_there_are_no_slips(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work({"kind": "book", "title": "Kindred", "author": "Butler"})
    db.add_file(
        {
            "work_id": work["id"],
            "path": "/data/kindred.epub",
            "filename": "kindred.epub",
            "kind": "book",
            "size": 1,
        }
    )
    statements: list[str] = []
    orig = db._connect

    def traced():
        conn = orig()
        conn.set_trace_callback(lambda sql: statements.append(sql))
        return conn

    db._connect = traced  # type: ignore[method-assign]
    from librarian.owned_slip import OWNED_KINDS

    owned, slips = db.load_owned_slip_sweep(kinds=OWNED_KINDS, limit=8000)
    assert owned == []
    assert slips == []
    selects = [sql for sql in statements if sql.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 1
    assert "needs_review" in selects[0]


def test_halt_on_429_halves_the_stored_cap(db):
    record_call(db, "nzbfinder", PURPOSE_WANTED, now=NOW, calls=10, rate_limited=1)
    cap = halt_wanted_on_429(db, "nzbfinder", now=NOW)
    assert cap == 10 + (250 - 10) // 2
    assert current_wanted_cap(db, "nzbfinder", now=NOW) == cap


def test_poll_wanted_never_calls_sab(db, monkeypatch):
    _want(db, "Dune", isbn="9780441172719")

    def search(_sought):
        return [
            {
                "title": "Frank Herbert - Dune (Unabridged)",
                "guid": "guid-dune",
                "category": "3030",
                "isbn": "9780441172719",
            }
        ]

    assert poll_wanted(db, Settings(), now=NOW, search=search) == 1
    jobs = db.list_jobs(limit=10)
    assert jobs and jobs[0]["status"] == "asked"
    assert not jobs[0].get("nzo_id")
