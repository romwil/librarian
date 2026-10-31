"""Phase 3.4: sweep source, bulk dismiss, 30-day restore, cap, new-install default.

SQLite is real. NZBFinder / SAB HTTP is mocked. Wanted never calls SABnzbd.
Existing settings.json without the key keeps the sweep on (Automat is not frozen off).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from librarian.config import (
    AUTO_AUDIOBOOK_WANTS_ALL,
    AUTO_AUDIOBOOK_WANTS_OFF,
    Settings,
    auto_audiobook_wants_enabled,
    load_merged_settings,
    save_settings,
    settings_path,
)
from librarian.db import Database
from librarian.indexer_budget import INDEXER_DAILY_CALL_BUDGET, daily_wanted_budget
from librarian.poller import JobPoller
from librarian.rate_limit import clear_rate_limits
from librarian.sabnzbd import SABClient
from librarian.sessions import clear_session_secret_cache
from librarian.wanted import (
    SOURCE_MANUAL,
    SOURCE_SWEEP,
    SWEEP_RESTORE_SECONDS,
    WantedError,
    add_wanted,
    dismiss_sweep_wanted,
    dismiss_wanted,
    public_wanted,
    restore_sweep_wanted,
    restore_wanted,
)
from librarian.wanted_sweep import OPEN_SWEEP_CAP, sweep_wanted_audiobooks
from librarian.web.app import create_app

NOW = 1_700_000_000.0


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


def _owner_client(tmp_path, monkeypatch, **settings_fields):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    monkeypatch.setenv("LIBRARIAN_SKIP_APP_BOOT", "1")
    monkeypatch.setattr("librarian.config.load_dotenv", lambda path=None: None)
    save_settings(tmp_path, Settings(llm_api_key="", **settings_fields))
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


def test_pacing_budget_is_unchanged():
    assert INDEXER_DAILY_CALL_BUDGET == 500
    assert daily_wanted_budget() == 250
    assert OPEN_SWEEP_CAP == 200
    assert SWEEP_RESTORE_SECONDS == 30 * 24 * 60 * 60


def test_new_install_defaults_sweep_off(tmp_path, monkeypatch):
    monkeypatch.delenv("AUTO_AUDIOBOOK_WANTS", raising=False)
    monkeypatch.setattr("librarian.config.load_dotenv", lambda path=None: None)
    assert Settings().auto_audiobook_wants == AUTO_AUDIOBOOK_WANTS_OFF
    assert auto_audiobook_wants_enabled(Settings()) is False
    assert not settings_path(tmp_path).exists()
    loaded = load_merged_settings(tmp_path)
    assert loaded.auto_audiobook_wants == AUTO_AUDIOBOOK_WANTS_OFF
    assert auto_audiobook_wants_enabled(loaded) is False


def test_existing_settings_without_the_key_keep_sweep_on(tmp_path, monkeypatch):
    monkeypatch.delenv("AUTO_AUDIOBOOK_WANTS", raising=False)
    monkeypatch.setattr("librarian.config.load_dotenv", lambda path=None: None)
    settings_path(tmp_path).write_text(
        json.dumps({"household_name": "The Hall"}),
        encoding="utf-8",
    )
    loaded = load_merged_settings(tmp_path)
    assert loaded.auto_audiobook_wants == AUTO_AUDIOBOOK_WANTS_ALL
    assert auto_audiobook_wants_enabled(loaded) is True


def test_existing_settings_can_stay_explicitly_on_after_save(tmp_path, monkeypatch):
    monkeypatch.delenv("AUTO_AUDIOBOOK_WANTS", raising=False)
    monkeypatch.setattr("librarian.config.load_dotenv", lambda path=None: None)
    settings_path(tmp_path).write_text(
        json.dumps({"household_name": "The Hall"}),
        encoding="utf-8",
    )
    loaded = load_merged_settings(tmp_path)
    save_settings(tmp_path, loaded)
    again = load_merged_settings(tmp_path)
    assert again.auto_audiobook_wants == AUTO_AUDIOBOOK_WANTS_ALL


def test_public_wanted_row_shows_source(db):
    sweep_row = db.insert_wanted(
        {
            "dedupe_key": "work:book-1:audiobook",
            "work_id": "book-1",
            "title": "Circe",
            "author": "Madeline Miller",
            "isbn": "",
            "kind": "audiobook",
            "status": "wanted",
            "miss_streak": 0,
            "next_search_at": NOW,
            "source": SOURCE_SWEEP,
        }
    )
    owner = add_wanted(db, {"title": "Kindred", "author": "Octavia Butler", "kind": "audiobook"}, now=NOW)
    public_sweep = public_wanted(sweep_row)
    public_owner = public_wanted(owner)
    assert public_sweep["source"] == SOURCE_SWEEP
    assert public_owner["source"] == SOURCE_MANUAL
    assert public_sweep["restorable"] is False
    assert public_owner["restorable"] is False


def test_sweep_caps_open_rows_and_ranks_by_reading(db):
    older = _shelve(db, kind="book", title="Older", author="A", genre="Fiction", isbn="1")
    _shelve(db, kind="book", title="Newer", author="B", genre="Fiction", isbn="2")
    db.upsert_progress(user_id="owner", work_id=older["id"], fraction=0.4)
    created = sweep_wanted_audiobooks(db, now=NOW, cap=1)
    assert created == 1
    rows = db.list_wanted()
    assert len(rows) == 1
    assert rows[0]["work_id"] == older["id"]
    assert rows[0]["source"] == SOURCE_SWEEP
    assert sweep_wanted_audiobooks(db, now=NOW, cap=1) == 0
    assert len(db.list_wanted()) == 1


def test_sweep_does_not_drop_owner_wants_to_make_room(db):
    owner_book = _shelve(db, kind="book", title="Kindred", author="Butler", genre="Fiction", isbn="3")
    add_wanted(db, {"work_id": owner_book["id"], "kind": "audiobook"}, now=NOW)
    extra = _shelve(db, kind="book", title="Circe", author="Miller", genre="Fiction", isbn="4")
    assert sweep_wanted_audiobooks(db, now=NOW, cap=1) == 1
    rows = {row["work_id"]: row for row in db.list_wanted()}
    assert rows[owner_book["id"]]["source"] == SOURCE_MANUAL
    assert rows[extra["id"]]["source"] == SOURCE_SWEEP


def test_bulk_dismiss_sweep_leaves_owner_and_asked_and_restores_for_30_days(db):
    sweep_book = _shelve(db, kind="book", title="Circe", author="Miller", genre="Fiction", isbn="5")
    owner_book = _shelve(db, kind="book", title="Kindred", author="Butler", genre="Fiction", isbn="6")
    assert sweep_wanted_audiobooks(db, now=NOW) == 2
    owner = next(row for row in db.list_wanted() if row["work_id"] == owner_book["id"])
    # Re-tag one as owner-added so bulk dismiss must leave it.
    db.delete_wanted(owner["id"])
    add_wanted(db, {"work_id": owner_book["id"], "kind": "audiobook"}, now=NOW)
    asked_book = _shelve(db, kind="book", title="Piranesi", author="Clarke", genre="Fiction", isbn="7")
    asked = db.insert_wanted(
        {
            "dedupe_key": f"work:{asked_book['id']}:audiobook",
            "work_id": asked_book["id"],
            "title": "Piranesi",
            "author": "Clarke",
            "isbn": "7",
            "kind": "audiobook",
            "status": "asked",
            "miss_streak": 0,
            "next_search_at": NOW,
            "job_id": "job-asked",
            "source": SOURCE_SWEEP,
        }
    )
    dismissed = dismiss_sweep_wanted(db, now=NOW)
    assert dismissed == 1
    open_rows = db.list_wanted()
    assert {row["work_id"] for row in open_rows} == {owner_book["id"], asked_book["id"]}
    gone = db.get_wanted_by_dedupe(f"work:{sweep_book['id']}:audiobook")
    assert gone["status"] == "dismissed"
    assert public_wanted(gone, now=NOW)["restorable"] is True
    assert public_wanted(gone, now=NOW + SWEEP_RESTORE_SECONDS + 1)["restorable"] is False

    restored = restore_wanted(db, gone["id"], now=NOW + 10)
    assert restored["status"] == "wanted"
    assert restored["source"] == SOURCE_SWEEP

    dismiss_sweep_wanted(db, now=NOW + 20)
    bulk = restore_sweep_wanted(db, now=NOW + 30)
    assert bulk == 1
    assert db.get_wanted_by_dedupe(f"work:{sweep_book['id']}:audiobook")["status"] == "wanted"

    dismiss_sweep_wanted(db, now=NOW + 40)
    late = db.get_wanted_by_dedupe(f"work:{sweep_book['id']}:audiobook")
    with pytest.raises(WantedError, match="no longer be restored"):
        restore_wanted(db, late["id"], now=NOW + 40 + SWEEP_RESTORE_SECONDS + 5)
    assert restore_sweep_wanted(db, now=NOW + 40 + SWEEP_RESTORE_SECONDS + 5) == 0
    assert db.get_wanted(asked["id"])["status"] == "asked"


def test_wanted_api_exposes_source_and_bulk_dismiss_restore(tmp_path, monkeypatch):
    client = _owner_client(tmp_path, monkeypatch, auto_audiobook_wants=AUTO_AUDIOBOOK_WANTS_ALL)
    database = Database(tmp_path / "librarian.db")
    try:
        sweep_book = _shelve(
            database, kind="book", title="Circe", author="Miller", genre="Fiction", isbn="9780316556347"
        )
        assert sweep_wanted_audiobooks(database, now=NOW) == 1
        owner = add_wanted(
            database, {"title": "Kindred", "author": "Octavia Butler", "kind": "audiobook"}, now=NOW
        )
    finally:
        database.close()

    listed = client.get("/api/wanted")
    assert listed.status_code == 200
    body = listed.json()
    by_title = {row["title"]: row for row in body["items"]}
    assert by_title["Circe"]["source"] == SOURCE_SWEEP
    assert by_title["Kindred"]["source"] == SOURCE_MANUAL
    assert body["sweep"]["enabled"] is True
    assert body["sweep"]["cap"] == OPEN_SWEEP_CAP
    assert body["sweep"]["open"] >= 1

    dismissed = client.post("/api/wanted/dismiss-sweep")
    assert dismissed.status_code == 200
    assert dismissed.json()["dismissed"] == 1
    open_titles = {row["title"] for row in client.get("/api/wanted").json()["items"]}
    assert "Circe" not in open_titles
    assert "Kindred" in open_titles

    hidden = client.get("/api/wanted", params={"status": "dismissed"})
    circe = next(row for row in hidden.json()["items"] if row["title"] == "Circe")
    assert circe["restorable"] is True
    restored = client.post(f"/api/wanted/{circe['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["item"]["status"] == "wanted"
    assert restored.json()["item"]["source"] == SOURCE_SWEEP

    client.post("/api/wanted/dismiss-sweep")
    bulk = client.post("/api/wanted/restore-sweep")
    assert bulk.status_code == 200
    assert bulk.json()["restored"] == 1
    assert owner["title"] == "Kindred"


def test_new_install_poller_skips_sweep(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(
        "librarian.wanted_sweep.sweep_wanted_audiobooks",
        lambda *_a, **_k: seen.append("sweep") or 0,
    )
    monkeypatch.setattr("librarian.wanted_search.poll_wanted", lambda *_a, **_k: 0)
    poller = JobPoller(Database(tmp_path / "librarian.db"), lambda: Settings(), interval=3600)
    poller.tick()
    assert seen == []
    status = {step["id"]: step for step in poller.step_status()["steps"]}
    assert status["sweep"]["state"] == "off"
    assert "automatic audiobook wants" in status["sweep"]["off_reason"]


def test_owner_can_opt_in_sweep_without_freezing_existing(tmp_path, monkeypatch):
    client = _owner_client(tmp_path, monkeypatch)
    listed = client.get("/api/wanted")
    assert listed.json()["sweep"]["enabled"] is False
    toggled = client.post("/api/wanted/sweep", json={"enabled": True})
    assert toggled.status_code == 200
    assert toggled.json()["sweep"]["enabled"] is True
    assert load_merged_settings(tmp_path).auto_audiobook_wants == AUTO_AUDIOBOOK_WANTS_ALL


def test_sweep_and_wanted_paths_still_never_call_sab(db, monkeypatch):
    _shelve(db, kind="book", title="Dune", author="Frank Herbert", genre="Fiction", isbn="9780441172719")
    assert sweep_wanted_audiobooks(db, now=NOW) == 1
    row = db.list_wanted()[0]
    dismiss_wanted(db, row["id"], now=NOW)
    restore_wanted(db, row["id"], now=NOW + 1)
    dismiss_sweep_wanted(db, now=NOW + 2)
    restore_sweep_wanted(db, now=NOW + 3)
    from librarian.wanted_search import poll_wanted

    assert poll_wanted(db, Settings(), now=NOW + 4) == 0
