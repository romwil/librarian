"""Value-based tests for Clear extra-files progress file updates."""

from __future__ import annotations

from librarian.extra_files_reprocess_progress import (
    default_progress,
    finish_extra_files_reprocess_run,
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
    assert (tmp_path / "extra_files_reprocess_progress.json").is_file()
