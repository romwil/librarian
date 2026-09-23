"""Value-based tests for Clear extra-files progress file updates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from librarian.extra_files_reprocess_progress import (
    begin_extra_files_reprocess_run,
    default_progress,
    finish_extra_files_reprocess_run,
    is_extra_files_reprocess_stale,
    patch_extra_files_reprocess_progress,
    read_extra_files_reprocess_progress,
    write_extra_files_reprocess_progress,
)


def test_default_progress_shape():
    payload = default_progress()
    assert payload["status"] == "idle"
    assert payload["phase"] == ""
    assert payload["current_title"] == ""
    assert payload["done"] == 0
    assert payload["total"] == 0
    assert payload["shelved"] == 0
    assert payload["split"] == 0
    assert payload["applied"] == 0
    assert payload["failed"] == 0
    assert payload["still_review"] == 0
    assert payload["logs"] == []
    assert payload["error"] == ""
    assert payload["heartbeat_at"] == ""
    assert payload["result"] is None


def test_finish_extra_files_reprocess_keeps_counts(tmp_path):
    write_extra_files_reprocess_progress(tmp_path, default_progress())
    patch_extra_files_reprocess_progress(
        tmp_path,
        status="running",
        done=2,
        total=3,
        shelved=1,
        split=1,
        applied=1,
    )
    finished = finish_extra_files_reprocess_run(
        tmp_path,
        result={
            "done": 3,
            "total": 3,
            "considered": 3,
            "shelved": 2,
            "split": 1,
            "applied": 2,
            "failed": 0,
            "still_review": 0,
        },
    )
    assert finished["status"] == "completed"
    assert finished["phase"] == "done"
    assert finished["shelved"] == 2
    assert finished["split"] == 1
    assert finished["applied"] == 2
    assert finished["done"] == 3
    assert finished["result"]["shelved"] == 2
    assert any("shelved 2" in line for line in finished["logs"])


def test_patch_writes_progress_json(tmp_path):
    write_extra_files_reprocess_progress(tmp_path, default_progress())
    patch_extra_files_reprocess_progress(
        tmp_path,
        status="running",
        phase="reprocessing",
        current_title="The Ministry of Time",
        done=4,
        total=79,
        shelved=3,
        applied=4,
    )
    result = read_extra_files_reprocess_progress(tmp_path)
    assert result["status"] == "running"
    assert result["phase"] == "reprocessing"
    assert result["current_title"] == "The Ministry of Time"
    assert result["done"] == 4
    assert result["total"] == 79
    assert result["shelved"] == 3
    assert result["heartbeat_at"]
    assert (tmp_path / "extra_files_reprocess_progress.json").is_file()


def test_begin_sets_heartbeat(tmp_path):
    begun = begin_extra_files_reprocess_run(tmp_path, total=3, phase="reprocessing")
    assert begun["status"] == "running"
    assert begun["started_at"]
    assert begun["heartbeat_at"] == begun["started_at"]


def test_stale_running_progress_without_heartbeat():
    now = datetime(2026, 9, 22, 21, 0, tzinfo=timezone.utc)
    old = (now - timedelta(seconds=200)).isoformat().replace("+00:00", "Z")
    payload = {
        "status": "running",
        "started_at": old,
        "heartbeat_at": old,
    }
    assert is_extra_files_reprocess_stale(payload, stale_after_s=180, now=now) is True
    fresh = {
        "status": "running",
        "started_at": old,
        "heartbeat_at": now.isoformat().replace("+00:00", "Z"),
    }
    assert is_extra_files_reprocess_stale(fresh, stale_after_s=180, now=now) is False
    assert is_extra_files_reprocess_stale({"status": "completed"}, now=now) is False
