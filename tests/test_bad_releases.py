"""Bad downloads go back to Wanted, not the Holds desk. SQLite stays real."""

from __future__ import annotations

import time

import pytest

from librarian.bad_releases import (
    MIGRATION_NAME,
    UNRETURNABLE_NOTE,
    migrate_bad_release_slips,
    read_migration_progress,
    release_bad_wanted,
)
from librarian.config import Settings
from librarian.db import Database, safe_release_guid
from librarian.jobs import BAD_RELEASE_ERROR, BAD_RELEASE_UNRETURNABLE_ERROR, poll_job
from librarian.wanted import backoff_seconds, dedupe_key
from librarian.wanted_search import poll_wanted

NOW = 1_700_000_000.0
HIT = {
    "guid": "guid-bad",
    "title": "Dune",
    "book_title": "Dune",
    "author": "Frank Herbert",
    "isbn": "9780441172719",
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


def _want(db: Database, title: str = "Dune") -> dict:
    return db.insert_wanted(
        {
            "dedupe_key": dedupe_key(kind="audiobook", title=title, author="Frank Herbert"),
            "title": title,
            "author": "Frank Herbert",
            "kind": "audiobook",
            "status": "wanted",
            "next_search_at": NOW,
            "source": "manual",
        }
    )


def _asked(db: Database, wanted: dict, *, guid: str = "guid-bad", host_id: str = "nzbfinder") -> dict:
    job = db.claim_and_create_wanted_job(
        wanted["id"],
        {
            "indexer_guid": guid,
            "title": wanted["title"],
            "kind": "audiobook",
            "payload": {
                "source": "wanted",
                "wanted_id": wanted["id"],
                "guid": guid,
                "selected": {"guid": guid, "host_id": host_id, "title": wanted["title"]},
            },
        },
        now=NOW,
    )
    assert job is not None
    return job


def _slip(db: Database, folder, *, reason: str, guid: str = "guid-bad", title: str = "Dune") -> dict:
    return db.upsert_work(
        {
            "kind": "audiobook",
            "title": title,
            "author": "Frank Herbert",
            "review_state": "needs_review",
            "review_reason": reason,
            "folder_path": str(folder),
            "indexer_guid": guid,
        }
    )


def test_release_bad_wanted_returns_row_to_retry_clock_and_records_guid(db, tmp_path):
    wanted = _want(db)
    job = _asked(db, wanted)
    folder = tmp_path / "complete" / "Dune"
    folder.mkdir(parents=True)
    (folder / "Dune.nfo").write_text("nfo")

    result = release_bad_wanted(db, reason="no_payload", job_id=job["id"], now=NOW + 10)

    assert result["released"] is True
    fresh = db.get_wanted(wanted["id"])
    assert fresh["status"] == "wanted"
    assert fresh["job_id"] is None
    assert fresh["miss_streak"] == 1
    assert fresh["next_search_at"] == pytest.approx(NOW + 10 + backoff_seconds(1))
    bad = db.list_bad_indexer_releases()
    assert [(row["host_id"], row["guid"], row["reason"], row["wanted_id"]) for row in bad] == [
        ("nzbfinder", "guid-bad", "no_payload", wanted["id"])
    ]
    assert bad[0]["seen_count"] == 1
    audit = db.list_review_audit(action="release_bad_wanted")
    assert len(audit) == 1 and audit[0]["wanted_id"] == wanted["id"]
    assert (folder / "Dune.nfo").is_file()


def test_bad_guid_is_never_picked_again_by_wanted_or_regrab(db):
    wanted = _want(db)
    job = _asked(db, wanted)
    release_bad_wanted(db, reason="convert_failed", job_id=job["id"], now=NOW)
    row = db.get_wanted(wanted["id"])

    seen = []

    def search(sought):
        seen.append(sought["q"])
        return [dict(HIT)]

    assert poll_wanted(db, Settings(), now=row["next_search_at"] + 1, search=search) == 1
    after = db.get_wanted(wanted["id"])
    assert after["status"] == "wanted"
    assert after["miss_streak"] == 2
    assert [item["id"] for item in db.list_jobs(limit=10)] == [job["id"]]
    assert "guid-bad" in db.tried_indexer_guids_for_work({"id": "other", "title": "Other"})


def test_second_bad_sighting_counts_and_keeps_first_seen(db):
    db.record_bad_indexer_release(host_id="h", guid="g1", reason="no_payload", now=NOW)
    db.record_bad_indexer_release(host_id="h", guid="g1", reason="convert_failed", now=NOW + 5)
    rows = db.list_bad_indexer_releases()
    assert len(rows) == 1
    assert rows[0]["seen_count"] == 2
    assert rows[0]["first_seen_at"] == NOW
    assert rows[0]["last_seen_at"] == NOW + 5
    assert rows[0]["reason"] == "convert_failed"


def test_credential_bearing_url_is_never_stored(db):
    url = "https://indexer.example/getnzb/abc123.nzb?i=9&r=SECRETKEY&apikey=SECRETKEY"
    assert safe_release_guid(url) == "abc123"
    assert safe_release_guid("https://indexer.example/api?t=get&id=xyz&apikey=SECRET") == "xyz"
    db.record_bad_indexer_release(host_id="h", guid=url, reason="no_payload", now=NOW)
    stored = db.list_bad_indexer_releases()
    assert stored[0]["guid"] == "abc123"
    assert "SECRET" not in repr(stored)


def test_no_wanted_row_dismisses_slip_and_keeps_the_folder(db, tmp_path):
    folder = tmp_path / "complete" / "Orphan"
    folder.mkdir(parents=True)
    (folder / "Orphan.nfo").write_text("nfo only")
    url = "https://indexer.example/getnzb/abc123.nzb?i=9&r=SECRETKEY&apikey=SECRETKEY"
    slip = _slip(db, folder, reason="no_payload", guid=url)

    result = release_bad_wanted(db, reason="no_payload", work_id=slip["id"], remove_slip=True, now=NOW)

    assert result["released"] is False
    assert result["dismissed"] is True
    assert result["missing"] == "wanted"
    assert result["note"] == UNRETURNABLE_NOTE
    assert db.get_work(slip["id"]) is None
    assert db.count_works(review_state="needs_review") == 0
    assert db.count_wanted(include_dismissed=True) == 0
    assert (folder / "Orphan.nfo").is_file()
    stored = db.list_bad_indexer_releases()
    assert stored[0]["guid"] == "abc123"
    assert "SECRET" not in repr(stored)
    assert slip["id"] in db.review_audit_work_ids("dismiss_bad_slip")


def test_no_guid_dismisses_slip_and_leaves_the_wanted_row(db, tmp_path):
    wanted = _want(db)
    folder = tmp_path / "complete" / "NoGuid"
    folder.mkdir(parents=True)
    (folder / "NoGuid.nfo").write_text("nfo only")
    slip = db.upsert_work(
        {
            "kind": "audiobook",
            "title": "Dune",
            "review_state": "needs_review",
            "review_reason": "convert_failed",
            "folder_path": str(folder),
        }
    )
    db.reopen_wanted(wanted["id"], now=NOW, fields={"title": "Dune"})
    before = db.count_wanted(include_dismissed=True)
    result = release_bad_wanted(db, reason="convert_failed", work_id=slip["id"], remove_slip=True)
    assert result["released"] is False
    assert result["dismissed"] is True
    assert result["missing"] == "guid"
    assert db.get_work(slip["id"]) is None
    assert (folder / "NoGuid.nfo").is_file()
    fresh = db.get_wanted(wanted["id"])
    assert fresh["status"] == "wanted"
    assert db.count_wanted(include_dismissed=True) == before
    assert db.list_bad_indexer_releases() == []


def test_completed_no_payload_download_goes_back_to_wanted(db, tmp_path):
    wanted = _want(db)
    job = _asked(db, wanted)
    folder = tmp_path / "complete" / "Dune.Audiobook"
    folder.mkdir(parents=True)
    (folder / "Dune.nfo").write_text("nfo only")
    (folder / "Dune.par2").write_bytes(b"par2")
    db.update_job(job["id"], nzo_id="nzo-1", status="downloading")

    class Sab:
        def job_status(self, _nzo):
            return {
                "status": "completed",
                "sab_status": "Completed",
                "name": "Dune",
                "percentage": "100",
                "bytes": 10,
                "storage": str(folder),
            }

    settings = Settings(complete_root=str(tmp_path / "complete"), audiobooks_root=str(tmp_path / "ab"))
    polled = poll_job(db, settings, job["id"], sab=Sab())

    assert polled["status"] == "failed"
    assert polled["error"] == BAD_RELEASE_ERROR
    assert polled["work_id"] is None
    fresh = db.get_wanted(wanted["id"])
    assert fresh["status"] == "wanted"
    assert fresh["job_id"] is None
    assert "guid-bad" in db.bad_indexer_guids()
    assert db.count_works(review_state="needs_review") == 0
    assert (folder / "Dune.nfo").is_file()


def test_second_failed_comic_convert_is_a_sorting_slip(db, tmp_path, monkeypatch):
    from librarian.organize import organize_identified

    wanted = _want(db, title="Saga 1")
    job = _asked(db, wanted, guid="guid-cbr")
    folder = tmp_path / "complete" / "Saga 001"
    folder.mkdir(parents=True)
    (folder / "Saga 001 (2012).cbr").write_bytes(b"Rar!\x1a\x07\x00broken")
    calls = []

    def no_convert(_folder, _kind, **_kwargs):
        calls.append(1)
        return {"converted": False}

    monkeypatch.setattr("librarian.organize.maybe_convert_payload", no_convert)
    monkeypatch.setattr("librarian.organize.unpack_release", lambda *_a, **_k: {"unpacked": False})
    settings = Settings(complete_root=str(tmp_path / "complete"), comics_root=str(tmp_path / "comics"))
    result = organize_identified(
        db,
        settings,
        folder=folder,
        indexer_item={
            "kind": "comic",
            "title": "Saga 001",
            "series": "Saga",
            "issue": "1",
            "guid": "guid-cbr",
            "job_id": job["id"],
        },
        move_source=True,
    )
    assert len(calls) == 2
    assert result.get("released_bad") is not True
    work = result["work"]
    assert work is not None
    assert work["review_reason"] == "convert_failed"
    assert work["review_state"] == "needs_review"
    assert db.count_works(review_state="needs_review") == 1
    assert db.get_wanted(wanted["id"])["status"] == "asked"
    assert db.list_bad_indexer_releases() == []
    assert (folder / "Saga 001 (2012).cbr").is_file()


def test_second_failed_convert_without_wanted_is_a_sorting_slip(db, tmp_path, monkeypatch):
    from librarian.organize import organize_identified

    folder = tmp_path / "complete" / "Saga 001"
    folder.mkdir(parents=True)
    (folder / "Saga 001 (2012).cbr").write_bytes(b"Rar!\x1a\x07\x00broken")

    def no_convert(_folder, _kind, **_kwargs):
        return {"converted": False}

    monkeypatch.setattr("librarian.organize.maybe_convert_payload", no_convert)
    monkeypatch.setattr("librarian.organize.unpack_release", lambda *_a, **_k: {"unpacked": False})
    settings = Settings(complete_root=str(tmp_path / "complete"), comics_root=str(tmp_path / "comics"))
    result = organize_identified(
        db,
        settings,
        folder=folder,
        indexer_item={
            "kind": "comic",
            "title": "Saga 001",
            "series": "Saga",
            "issue": "1",
            "guid": "guid-cbr",
        },
        move_source=True,
    )
    assert result.get("dismissed_bad") is not True
    work = result["work"]
    assert work is not None
    assert work["review_reason"] == "convert_failed"
    assert work["review_state"] == "needs_review"
    assert db.count_works(review_state="needs_review") == 1
    assert db.count_wanted(include_dismissed=True) == 0
    assert db.list_bad_indexer_releases() == []
    assert (folder / "Saga 001 (2012).cbr").is_file()


def test_completed_no_payload_without_wanted_keeps_folder_and_skips_the_desk(db, tmp_path):
    folder = tmp_path / "complete" / "Wolves of the Calla"
    folder.mkdir(parents=True)
    (folder / "Wolves.nfo").write_text("nfo only")
    job = db.create_job(
        {
            "status": "downloading",
            "nzo_id": "nzo-empty",
            "indexer_guid": "guid-wolves",
            "title": "Wolves of the Calla",
            "kind": "audiobook",
            "payload": {"guid": "guid-wolves", "selected": {"guid": "guid-wolves", "host_id": "nzbfinder"}},
        }
    )

    class Sab:
        def job_status(self, _nzo):
            return {
                "status": "completed",
                "sab_status": "Completed",
                "name": "Wolves of the Calla",
                "percentage": "100",
                "bytes": 10,
                "storage": str(folder),
            }

    settings = Settings(complete_root=str(tmp_path / "complete"), audiobooks_root=str(tmp_path / "ab"))
    polled = poll_job(db, settings, job["id"], sab=Sab())

    assert polled["status"] == "failed"
    assert polled["error"] == BAD_RELEASE_UNRETURNABLE_ERROR
    assert polled["work_id"] is None
    assert db.count_works(review_state="needs_review") == 0
    assert db.count_wanted(include_dismissed=True) == 0
    assert db.list_bad_indexer_releases()[0]["guid"] == "guid-wolves"
    assert (folder / "Wolves.nfo").is_file()


def test_migration_returns_bad_slips_once_and_counts_leftovers(db, tmp_path):
    wanted = _want(db)
    job = _asked(db, wanted)
    folder = tmp_path / "complete" / "Dune"
    folder.mkdir(parents=True)
    (folder / "x.nfo").write_text("x")
    slip = _slip(db, folder, reason="no_payload")
    db.update_job(job["id"], work_id=slip["id"], status="review")
    orphan_folder = tmp_path / "complete" / "Orphan"
    orphan_folder.mkdir(parents=True)
    (orphan_folder / "Orphan.nfo").write_text("keep")
    orphan = _slip(db, orphan_folder, reason="convert_failed", guid="", title="Orphan")
    keeper = _slip(db, orphan_folder, reason="low_confidence", guid="g-low", title="Keep Me")

    report = migrate_bad_release_slips(db, data_dir=tmp_path, now=NOW)

    assert report == {
        "total": 2,
        "returned": 1,
        "dismissed": 1,
        "left_on_desk": 0,
        "failed": 0,
    }
    assert db.get_work(slip["id"]) is None
    assert db.get_job(job["id"]) is None
    assert db.get_wanted(wanted["id"])["status"] == "wanted"
    assert db.get_wanted(wanted["id"])["job_id"] is None
    assert db.get_work(orphan["id"]) is None
    assert db.get_work(keeper["id"])["review_reason"] == "low_confidence"
    assert (folder / "x.nfo").is_file()
    assert (orphan_folder / "Orphan.nfo").is_file()
    progress = read_migration_progress(tmp_path)
    assert progress["status"] == "completed"
    assert progress["returned"] == 1 and progress["dismissed"] == 1 and progress["left_on_desk"] == 0
    assert db.get_migration(MIGRATION_NAME)["report"]["returned"] == 1
    assert db.get_migration(MIGRATION_NAME)["report"]["dismissed"] == 1

    again = migrate_bad_release_slips(db, data_dir=tmp_path, now=NOW + 60)
    assert again["already_done"] is True
    assert again["returned"] == 1
    assert again["dismissed"] == 1
    assert db.get_work(orphan["id"]) is None
    assert db.get_wanted(wanted["id"])["miss_streak"] == 1


def test_review_list_explains_leftover_and_reports_migration(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from librarian.sessions import clear_session_secret_cache
    from librarian.web.app import create_app

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    app = create_app(tmp_path)
    client = TestClient(app)
    assert client.post(
        "/api/auth/local/login", json={"username": "owner", "password": "password123"}
    ).status_code == 200
    db = app.state.db
    folder = tmp_path / "complete" / "Orphan"
    folder.mkdir(parents=True)
    (folder / "Orphan.nfo").write_text("still here")
    orphan = _slip(db, folder, reason="convert_failed", guid="", title="Orphan")
    migrate_bad_release_slips(db, data_dir=tmp_path, now=time.time())

    body = client.get("/api/review").json()
    assert all(w["id"] != orphan["id"] for w in body["works"])
    assert db.get_work(orphan["id"]) is None
    assert (folder / "Orphan.nfo").is_file()
    assert body["bad_release_migration"]["status"] == "completed"
    assert body["bad_release_migration"]["dismissed"] == 1
    assert body["bad_release_migration"]["left_on_desk"] == 0
    status = client.get("/api/review/bad-release-migration/status").json()
    assert status["dismissed"] == 1
    assert status["left_on_desk"] == 0
