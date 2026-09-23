"""Write serializer concurrency smoke + stats."""

from __future__ import annotations

import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from librarian.db import Database
from librarian.db_write_serializer import WriteSerializer


def test_concurrent_writers_do_not_raise_database_locked():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "librarian.db")
        try:
            errors: list[BaseException] = []

            def _insert(i: int) -> None:
                try:
                    db.upsert_work(
                        {
                            "kind": "book",
                            "title": f"Title {i}",
                            "author": "Author",
                            "folder_path": f"/tmp/{i}",
                        }
                    )
                except BaseException as exc:  # noqa: BLE001
                    errors.append(exc)

            with ThreadPoolExecutor(max_workers=12) as pool:
                futures = [pool.submit(_insert, i) for i in range(40)]
                for fut in as_completed(futures):
                    fut.result()

            assert errors == []
            assert len(db.list_works(limit=100)) >= 40
            stats = db.write_queue_stats()
            assert int(stats["jobs_done"]) >= 40
        finally:
            db.close()


def test_run_write_propagates_errors():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "librarian.db")
        try:

            def _boom() -> None:
                raise ValueError("write failed")

            try:
                db.run_write(_boom, label="boom")
                raise AssertionError("expected ValueError")
            except ValueError as exc:
                assert "write failed" in str(exc)
        finally:
            db.close()


def test_try_run_drops_when_queue_is_full():
    import threading
    import time

    ser = WriteSerializer(maxsize=1)
    release = threading.Event()
    started = threading.Event()

    def hold() -> None:
        started.set()
        release.wait(timeout=3)

    holder = threading.Thread(target=lambda: ser.run(hold, label="hold"), daemon=True)
    holder.start()
    assert started.wait(timeout=2)

    queued = threading.Event()

    def park() -> None:
        queued.set()
        ser.run(lambda: None, label="park")

    parker = threading.Thread(target=park, daemon=True)
    parker.start()
    assert queued.wait(timeout=2)
    time.sleep(0.05)
    dropped = ser.try_run(lambda: None, label="drop-me")
    assert dropped is False
    release.set()
    holder.join(timeout=2)
    parker.join(timeout=2)
    ser.shutdown(timeout=2)
