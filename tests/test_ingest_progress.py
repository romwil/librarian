"""Value-based tests for ingest progress file updates and payload shape."""

from __future__ import annotations

import threading

from librarian.ingest_progress import (
    append_ingest_log,
    default_progress,
    finish_ingest_run,
    patch_ingest_progress,
    read_ingest_progress,
    write_ingest_progress,
)


def test_default_progress_shape():
    payload = default_progress()
    assert payload["status"] == "idle"
    assert payload["phase"] == ""
    assert payload["current_path"] == ""
    assert payload["current_title"] == ""
    assert payload["done"] == 0
    assert payload["total"] == 0
    assert payload["shelved"] == 0
    assert payload["review"] == 0
    assert payload["skipped"] == 0
    assert payload["errors"] == 0
    assert payload["logs"] == []
    assert payload["error"] == ""
    assert payload["source_path"] == ""
    assert payload["result"] is None


def test_finish_ingest_run_keeps_counts(tmp_path):
    write_ingest_progress(tmp_path, default_progress())
    patch_ingest_progress(tmp_path, status="running", done=2, total=3, shelved=1, review=1)
    finished = finish_ingest_run(
        tmp_path,
        result={"done": 3, "total": 3, "shelved": 2, "review": 1, "skipped": 0, "errors": 0},
    )
    assert finished["status"] == "completed"
    assert finished["phase"] == "done"
    assert finished["shelved"] == 2
    assert finished["review"] == 1
    assert finished["done"] == 3
    assert finished["result"]["shelved"] == 2
    assert any("shelved 2" in line for line in finished["logs"])


def test_concurrent_patch_and_append_keep_both_updates(tmp_path, monkeypatch):
    write_ingest_progress(tmp_path, default_progress())

    import librarian.ingest_progress as ingest_progress

    original_read = ingest_progress.read_ingest_progress
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def synced_read(data_dir):
        snapshot = original_read(data_dir)
        barrier.wait(timeout=2)
        return snapshot

    monkeypatch.setattr(ingest_progress, "read_ingest_progress", synced_read)

    def do_patch() -> None:
        try:
            patch_ingest_progress(tmp_path, done=4, phase="organizing", shelved=2)
        except BaseException as error:
            errors.append(error)

    def do_log() -> None:
        try:
            append_ingest_log(tmp_path, "Shelved — Christine")
        except BaseException as error:
            errors.append(error)

    threads = [
        threading.Thread(target=do_patch),
        threading.Thread(target=do_log),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert errors == []

    result = read_ingest_progress(tmp_path)
    assert result["done"] == 4
    assert result["phase"] == "organizing"
    assert result["shelved"] == 2
    assert result["logs"] == ["Shelved — Christine"]
