"""Value-based tests for the shared progress_job kit."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from librarian.progress_job import BackgroundJobSlot, ProgressJob, is_stale_running, utc_now


def _job(**kwargs) -> ProgressJob:
    return ProgressJob(
        filename="demo_progress.json",
        defaults=lambda: {
            "status": "idle",
            "phase": "",
            "done": 0,
            "total": 0,
            "logs": [],
            "error": "",
            "started_at": "",
            "heartbeat_at": "",
            "finished_at": "",
            "result": None,
            "current_title": "",
        },
        **kwargs,
    )


def test_patch_and_append_keep_both_updates(tmp_path):
    job = _job()
    job.write(tmp_path, job.default_progress())
    n = 30
    errors: list[BaseException] = []

    def patcher() -> None:
        try:
            for i in range(n):
                job.patch(tmp_path, done=i + 1, phase="working")
        except BaseException as error:
            errors.append(error)

    def logger() -> None:
        try:
            for i in range(n):
                job.append_log(tmp_path, f"line-{i}")
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=patcher), threading.Thread(target=logger)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert errors == []
    result = job.read(tmp_path)
    assert result["done"] == n
    assert result["phase"] == "working"
    assert len(result["logs"]) == n


def test_begin_finish_and_heartbeat(tmp_path):
    job = _job(heartbeat=True, heartbeat_stale_s=60.0)
    begun = job.begin(tmp_path, start_log="Started demo.", total=2, phase="working")
    assert begun["status"] == "running"
    assert begun["heartbeat_at"] == begun["started_at"]
    assert begun["logs"] == ["Started demo."]

    finished = job.finish(
        tmp_path,
        result={"done": 2, "total": 2, "considered": 2},
        result_keys=("done", "total"),
        considered_as_total=True,
        finish_log=lambda current, summary: f"Finished — done {summary.get('done')}.",
    )
    assert finished["status"] == "completed"
    assert finished["done"] == 2
    assert any("Finished — done 2" in line for line in finished["logs"])
    assert finished["current_title"] == ""


def test_stale_running_uses_heartbeat(tmp_path):
    job = _job(heartbeat=True, heartbeat_stale_s=30.0)
    payload = {
        "status": "running",
        "started_at": "2020-01-01T00:00:00Z",
        "heartbeat_at": "2020-01-01T00:00:00Z",
    }
    now = datetime(2020, 1, 1, 0, 1, tzinfo=timezone.utc)
    assert job.is_stale(payload, now=now) is True
    assert is_stale_running(payload, stale_after_s=120.0, now=now) is False


def test_background_job_slot_start_if_idle():
    slot = BackgroundJobSlot()
    ran = {"count": 0}

    def target() -> None:
        ran["count"] += 1

    first = slot.start_if_idle(
        already_running=False,
        begin=lambda: None,
        target=target,
        name="librarian-demo",
    )
    assert first is True
    slot.thread["thread"].join(timeout=2)
    assert ran["count"] == 1

    # Simulate a live worker holding the slot.
    hold = threading.Event()

    def blocker() -> None:
        hold.wait(timeout=2)

    second_begin = {"called": False}
    live = slot.start_if_idle(
        already_running=False,
        begin=lambda: None,
        target=blocker,
        name="librarian-demo-live",
    )
    assert live is True
    blocked = slot.start_if_idle(
        already_running=True,
        begin=lambda: second_begin.__setitem__("called", True),
        target=target,
        name="librarian-demo-blocked",
    )
    assert blocked is False
    assert second_begin["called"] is False
    hold.set()
    slot.thread["thread"].join(timeout=2)


def test_utc_now_is_zulu():
    stamp = utc_now()
    assert stamp.endswith("Z")
    assert "+" not in stamp
    # Smoke: parseable as recent.
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert abs((datetime.now(timezone.utc) - parsed).total_seconds()) < 5
    assert parsed + timedelta(seconds=0) == parsed
