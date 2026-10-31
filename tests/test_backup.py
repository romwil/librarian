"""Nightly backup: real SQLite files, real integrity_check, real permissions."""

import os
import sqlite3
import stat
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from librarian.backup import (
    BackupError,
    backup_dir_for,
    backup_due,
    backup_status,
    daily_name,
    run_backup,
    weekly_name,
)
from librarian.config import Settings
from librarian.db import Database
from librarian.poller import JobPoller
from librarian.web.app import create_app

SECRET = "super-secret-session-token-do-not-copy"


def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def _seed(tmp_path):
    db = Database(tmp_path / "librarian.db")
    (tmp_path / "session_secret").write_text(SECRET, encoding="utf-8")
    (tmp_path / "settings.json").write_text('{"nzbfinder_api_token": "tok-123"}', encoding="utf-8")
    with sqlite3.connect(db.path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS backup_probe (id INTEGER PRIMARY KEY, note TEXT)")
        conn.execute("INSERT INTO backup_probe (note) VALUES ('on the shelf')")
    return db


def _day(offset: int) -> datetime:
    return datetime(2026, 10, 5, 3, 0, tzinfo=timezone.utc) + timedelta(days=offset)  # a Monday


def test_snapshot_is_a_real_restorable_database(tmp_path):
    db = _seed(tmp_path)
    folder = backup_dir_for(tmp_path)
    result = run_backup(db.path, folder, now=_day(0))

    assert result.daily == folder / daily_name(_day(0).date())
    assert result.weekly == folder / weekly_name(_day(0).date())
    with sqlite3.connect(result.daily) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT note FROM backup_probe").fetchall() == [("on the shelf",)]
    with sqlite3.connect(result.weekly) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    # One self-contained file per snapshot: no WAL/SHM litter, no temp leftovers.
    names = sorted(p.name for p in folder.iterdir())
    assert not any(n.endswith(suffix) for n in names for suffix in ("-wal", "-shm", "-journal"))
    assert not [n for n in names if n.startswith(".tmp")]
    # Restore copies the snapshot out of backups/ before the catalog opens it.
    restored_path = tmp_path / "restored.db"
    restored_path.write_bytes(result.daily.read_bytes())
    restored = Database(restored_path)
    assert restored.schema_version == db.schema_version
    with sqlite3.connect(restored_path) as conn:
        assert conn.execute("SELECT note FROM backup_probe").fetchone()[0] == "on the shelf"


def test_snapshot_includes_rows_still_in_the_wal(tmp_path):
    db = _seed(tmp_path)
    live = sqlite3.connect(db.path)
    live.execute("INSERT INTO backup_probe (note) VALUES ('only in the wal')")
    live.commit()
    assert (tmp_path / "librarian.db-wal").exists()
    result = run_backup(db.path, backup_dir_for(tmp_path), now=_day(0))
    live.close()
    with sqlite3.connect(result.daily) as conn:
        notes = [row[0] for row in conn.execute("SELECT note FROM backup_probe ORDER BY id")]
    assert notes == ["on the shelf", "only in the wal"]


def test_files_are_private_and_the_session_secret_stays_out(tmp_path):
    db = _seed(tmp_path)
    os.chmod(db.path, 0o644)
    folder = backup_dir_for(tmp_path)
    run_backup(db.path, folder, now=_day(0))

    assert _mode(folder) == 0o700
    assert _mode(db.path) == 0o600
    files = list(folder.iterdir())
    assert len(files) == 2
    for path in files:
        assert _mode(path) == 0o600
        blob = path.read_bytes()
        assert SECRET.encode() not in blob
        assert b"tok-123" not in blob
    assert not any("session_secret" in p.name or p.name == "settings.json" for p in files)


def test_database_file_is_0600_from_first_boot(tmp_path):
    db = Database(tmp_path / "librarian.db")
    assert _mode(db.path) == 0o600
    for sidecar in (tmp_path / "librarian.db-wal", tmp_path / "librarian.db-shm"):
        if sidecar.exists():
            assert _mode(sidecar) == 0o600


def test_keeps_seven_dailies_and_four_weeklies(tmp_path):
    db = _seed(tmp_path)
    folder = backup_dir_for(tmp_path)
    for offset in range(0, 63):  # nine weeks, one run per day
        run_backup(db.path, folder, now=_day(offset))

    names = sorted(p.name for p in folder.iterdir())
    dailies = [n for n in names if n.startswith("librarian-2")]
    weeklies = [n for n in names if n.startswith("librarian-weekly-")]
    last = _day(62).date()
    assert dailies == [daily_name(last - timedelta(days=d)) for d in range(6, -1, -1)]
    assert len(weeklies) == 4
    assert weeklies[-1] == weekly_name(last)
    assert weeklies[0] == weekly_name(last - timedelta(weeks=3))
    assert len(names) == 11


def test_second_run_the_same_day_keeps_the_first_snapshot(tmp_path):
    db = _seed(tmp_path)
    folder = backup_dir_for(tmp_path)
    first = run_backup(db.path, folder, now=_day(0))
    assert backup_due(folder, now=_day(0)) is False
    assert backup_due(folder, now=_day(1)) is True
    stamp = first.daily.stat().st_mtime_ns
    again = run_backup(db.path, folder, now=_day(0))
    assert again.daily is None and again.weekly is None
    assert first.daily.stat().st_mtime_ns == stamp


def test_same_day_retry_fills_a_missing_weekly(tmp_path):
    db = _seed(tmp_path)
    folder = backup_dir_for(tmp_path)
    first = run_backup(db.path, folder, now=_day(0))
    first.weekly.unlink()
    assert backup_due(folder, now=_day(0)) is True
    stamp = first.daily.stat().st_mtime_ns
    again = run_backup(db.path, folder, now=_day(0))
    assert again.daily is None
    assert again.weekly == folder / weekly_name(_day(0).date())
    assert first.daily.stat().st_mtime_ns == stamp


def test_a_corrupt_catalog_fails_loudly_and_keeps_earlier_backups(tmp_path):
    db = _seed(tmp_path)
    folder = backup_dir_for(tmp_path)
    good = run_backup(db.path, folder, now=_day(0))
    good_bytes = good.daily.read_bytes()

    with sqlite3.connect(db.path) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    raw = bytearray(db.path.read_bytes())
    for page in range(1, len(raw) // 4096):
        raw[page * 4096 : page * 4096 + 64] = b"\xff" * 64  # wreck every non-header page
    db.path.write_bytes(bytes(raw))

    with pytest.raises(BackupError):
        run_backup(db.path, folder, now=_day(1))

    assert good.daily.read_bytes() == good_bytes
    names = sorted(p.name for p in folder.iterdir())
    assert names == sorted([good.daily.name, good.weekly.name])


def test_integrity_check_failure_discards_the_copy(tmp_path):
    """Index no longer matches its table: the page copy succeeds, integrity_check says no."""
    db = _seed(tmp_path)
    folder = backup_dir_for(tmp_path)
    good = run_backup(db.path, folder, now=_day(0))
    with sqlite3.connect(db.path) as conn:
        conn.execute("CREATE TABLE damaged (a, b)")
        conn.execute("CREATE INDEX damaged_idx ON damaged (a)")
        conn.executemany("INSERT INTO damaged VALUES (?, ?)", [(i, f"z{i}") for i in range(50)])
        conn.commit()
        conn.execute("PRAGMA writable_schema=ON")
        conn.execute("UPDATE sqlite_master SET sql='CREATE INDEX damaged_idx ON damaged (b)' WHERE name='damaged_idx'")
        conn.commit()

    with pytest.raises(BackupError, match="integrity_check"):
        run_backup(db.path, folder, now=_day(1))
    assert sorted(p.name for p in folder.iterdir()) == sorted([good.daily.name, good.weekly.name])


def test_status_reports_last_backup_and_counts(tmp_path):
    folder = backup_dir_for(tmp_path)
    assert backup_status(folder) == {
        "last_backup": None,
        "last_backup_file": None,
        "daily_count": 0,
        "weekly_count": 0,
    }
    db = _seed(tmp_path)
    run_backup(db.path, folder, now=_day(0))
    run_backup(db.path, folder, now=_day(1))
    status = backup_status(folder)
    assert status["last_backup_file"] == daily_name(_day(1).date())
    assert status["daily_count"] == 2
    assert status["weekly_count"] == 1
    assert datetime.fromisoformat(status["last_backup"]).tzinfo is not None


def test_poller_backup_step_writes_snapshot_and_records_errors(tmp_path):
    db = _seed(tmp_path)
    poller = JobPoller(db, lambda: Settings(), interval=30, data_dir=tmp_path)
    for name in list(poller._runners):
        if name != "backup":
            poller._runners[name] = lambda _settings: 0
    poller.tick()
    status = {s["id"]: s for s in poller.step_status()["steps"]}
    assert status["backup"]["last_error"] is None
    assert status["backup"]["last_run"]
    assert status["backup"]["label"] == "Nightly backup"
    folder = backup_dir_for(tmp_path)
    assert backup_status(folder)["daily_count"] == 1

    # A backup folder that cannot be created is recorded on the step, not raised.
    blocked = JobPoller(db, lambda: Settings(), interval=30, data_dir=tmp_path / "session_secret")
    for name in list(blocked._runners):
        if name != "backup":
            blocked._runners[name] = lambda _settings: 0
    blocked.tick()
    failed = {s["id"]: s for s in blocked.step_status()["steps"]}["backup"]
    assert failed["last_error"]


def test_maintain_jobs_status_reports_last_backup(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        login = client.post(
            "/api/auth/local/login",
            json={"username": "owner", "password": "password123"},
        )
        assert login.status_code == 200
        before = client.get("/api/maintain/jobs/status").json()["backup"]
        assert before["last_backup"] is None
        assert before["daily_count"] == 0
        assert before["last_error"] is None

        run_backup(tmp_path / "librarian.db", backup_dir_for(tmp_path), now=_day(0))
        after = client.get("/api/maintain/jobs/status").json()["backup"]
    assert after["last_backup_file"] == daily_name(_day(0).date())
    assert after["daily_count"] == 1
    assert after["weekly_count"] == 1
    assert after["last_backup"]
