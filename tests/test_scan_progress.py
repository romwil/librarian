"""Value-based tests for scan progress file updates and payload shape."""

from __future__ import annotations

import threading

from librarian.scan_progress import (
    append_scan_log,
    begin_scan_run,
    default_progress,
    finish_scan_run,
    patch_scan_progress,
    read_scan_progress,
    write_scan_progress,
)


def test_begin_and_finish_scan_progress(tmp_path):
    started = begin_scan_run(tmp_path, source="manual", total=3, phase="scanning")
    assert started["status"] == "running"
    assert started["total"] == 3
    assert started["phase"] == "scanning"
    assert "Started scan" in started["logs"][0]

    patch_scan_progress(tmp_path, done=2, created=1, updated=1, current_title="Dune")
    finished = finish_scan_run(
        tmp_path,
        result={"scanned": 3, "created": 1, "updated": 2, "review": 0, "errors": 0},
    )
    assert finished["status"] == "completed"
    assert finished["phase"] == "done"
    assert finished["done"] == 3
    assert finished["created"] == 1
    assert finished["updated"] == 2
    assert finished["result"]["scanned"] == 3
    assert any("Finished" in line for line in finished["logs"])


def test_concurrent_patch_and_append_keep_both_updates(tmp_path, monkeypatch):
    write_scan_progress(tmp_path, default_progress())

    import librarian.scan_progress as scan_progress

    original_read = scan_progress.read_scan_progress
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def synced_read(data_dir):
        snapshot = original_read(data_dir)
        barrier.wait(timeout=2)
        return snapshot

    monkeypatch.setattr(scan_progress, "read_scan_progress", synced_read)

    def do_patch() -> None:
        try:
            patch_scan_progress(tmp_path, done=4, phase="scanning")
        except BaseException as error:
            errors.append(error)

    def do_log() -> None:
        try:
            append_scan_log(tmp_path, "scanned Left Hand")
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

    result = read_scan_progress(tmp_path)
    assert result["done"] == 4
    assert result["phase"] == "scanning"
    assert result["logs"] == ["scanned Left Hand"]
