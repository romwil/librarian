"""Value-based tests for enrich progress file updates."""

from __future__ import annotations

import threading

from librarian.enrich_progress import (
    append_enrich_log,
    default_progress,
    patch_enrich_progress,
    read_enrich_progress,
    write_enrich_progress,
)


def test_concurrent_patch_and_append_keep_both_updates(tmp_path, monkeypatch):
    """Read-modify-write must hold the lock across both steps or one update is lost."""
    write_enrich_progress(tmp_path, default_progress())

    import librarian.enrich_progress as enrich_progress

    original_read = enrich_progress.read_enrich_progress
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def synced_read(data_dir):
        snapshot = original_read(data_dir)
        barrier.wait(timeout=2)
        return snapshot

    monkeypatch.setattr(enrich_progress, "read_enrich_progress", synced_read)

    def do_patch() -> None:
        try:
            patch_enrich_progress(tmp_path, done=7, phase="scanning")
        except BaseException as error:
            errors.append(error)

    def do_log() -> None:
        try:
            append_enrich_log(tmp_path, "enriched Left Hand")
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

    result = read_enrich_progress(tmp_path)
    assert result["done"] == 7
    assert result["phase"] == "scanning"
    assert result["logs"] == ["enriched Left Hand"]


def test_repeated_concurrent_patch_and_append_keep_final_values(tmp_path):
    write_enrich_progress(tmp_path, default_progress())
    n = 40
    errors: list[BaseException] = []

    def patcher() -> None:
        try:
            for i in range(n):
                patch_enrich_progress(tmp_path, done=i + 1, phase="scanning")
        except BaseException as error:
            errors.append(error)

    def logger() -> None:
        try:
            for i in range(n):
                append_enrich_log(tmp_path, f"line-{i}")
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=patcher), threading.Thread(target=logger)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert errors == []

    result = read_enrich_progress(tmp_path)
    assert result["done"] == n
    assert result["phase"] == "scanning"
    assert result["logs"] == [f"line-{i}" for i in range(n)]
