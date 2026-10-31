import json
import threading
import time
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from librarian.config import Settings
from librarian.db import Database
from librarian.indexers.sync import ping_nzbfinder, summarize_capabilities, sync_nzbfinder
from librarian.jobs import enqueue_indexer_item
from librarian.noted import run_noted_refresh
from librarian.poller import (
    DEFAULT_BACKUP_POLL_SECONDS,
    DEFAULT_ENRICH_POLL_SECONDS,
    DEFAULT_NOTED_POLL_SECONDS,
    DEFAULT_OWNED_POLL_SECONDS,
    DEFAULT_RSS_POLL_SECONDS,
    DEFAULT_SAB_POLL_SECONDS,
    DEFAULT_SWEEP_POLL_SECONDS,
    DEFAULT_WANTED_POLL_SECONDS,
    JobPoller,
    poll_interval_seconds,
)
from librarian.sabnzbd import SABClient, SABError
from librarian.web.app import create_app


def test_summarize_capabilities_fixture():
    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "nzbfinder" / "capabilities.json").read_text(encoding="utf-8")
    )
    summary = summarize_capabilities(payload)
    assert summary["ok"] is True
    assert summary["server"] == "NZBFinder"
    assert summary["books"] is True
    assert summary["search"] is True
    assert summary["category_count"] == 6


def test_sync_and_ping_indexers_table(tmp_path):
    db = Database(tmp_path / "librarian.db")
    settings = Settings(nzbfinder_url="https://nzbfinder.example", nzbfinder_api_token="tok")
    row = sync_nzbfinder(db, settings)
    assert row["id"] == "nzbfinder"
    assert row["token_set"] == 1
    assert db.list_indexers()[0]["base_url"] == "https://nzbfinder.example"

    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "nzbfinder" / "capabilities.json").read_text(encoding="utf-8")
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/api/v2/capabilities" in str(request.url)
        assert "api_token=tok" in str(request.url)
        assert "t=caps" not in str(request.url)
        return httpx.Response(200, json=fixture)

    from librarian.nzbfinder import NZBFinderClient

    client = NZBFinderClient("https://nzbfinder.example", "tok", transport=httpx.MockTransport(handler))
    ping = ping_nzbfinder(db, settings, client=client)
    assert ping["ok"] is True
    assert ping["server"] == "NZBFinder"
    stored = db.get_indexer("nzbfinder")
    assert stored["last_caps_ok"] == 1
    assert stored["last_caps_at"] > 0


def test_poller_tick_polls_active_job(tmp_path):
    complete = tmp_path / "complete" / "Le Guin - The Left Hand of Darkness 9780441478125"
    complete.mkdir(parents=True)
    (complete / "book.epub").write_bytes(b"epub")
    nzb_xml = b'<?xml version="1.0"?><nzb xmlns="http://www.newzbin.com/DTD/2003/nzb"></nzb>'

    def sab_handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if request.method == "POST" or params.get("mode") == "addfile":
            return httpx.Response(200, json={"nzo_ids": ["SABnzbd_nzo_p"]})
        if params.get("mode") == "addurl":
            raise AssertionError("addurl must not be used")
        if params.get("mode") == "queue":
            return httpx.Response(200, json={"queue": {"slots": []}})
        return httpx.Response(
            200,
            json={
                "history": {
                    "slots": [
                        {
                            "nzo_id": "SABnzbd_nzo_p",
                            "status": "Completed",
                            "storage": str(complete),
                            "name": complete.name,
                        }
                    ]
                }
            },
        )

    def nzb_handler(request: httpx.Request) -> httpx.Response:
        if "/api/v2/download" in str(request.url):
            return httpx.Response(200, content=nzb_xml, headers={"content-type": "application/x-nzb"})
        return httpx.Response(200, json={})

    settings = Settings(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "mags"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "abs"),
        incoming_music_root=str(tmp_path / "in"),
        music_root=str(tmp_path / "music"),
        sabnzbd_api_key="sab",
        nzbfinder_api_token="tok",
    )
    sab = SABClient("http://downloader.sl", "sab", transport=httpx.MockTransport(sab_handler))
    from librarian.nzbfinder import NZBFinderClient

    nzb = NZBFinderClient("https://nzbfinder.example", "tok", transport=httpx.MockTransport(nzb_handler))
    db = Database(tmp_path / "librarian.db")
    job = enqueue_indexer_item(
        db,
        settings,
        item={
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": "9780441478125",
            "guid": "g-book",
            "kind": "book",
            "category": 7020,
            "download_url": "https://example.test/book.nzb",
            "name": complete.name,
        },
        requested_by="owner-1",
        role="owner",
        sab=sab,
        nzb=nzb,
    )
    assert job["status"] == "queued"
    poller = JobPoller(db, lambda: settings, interval=999, sab=sab)
    assert poller.tick() == 1
    updated = db.get_job(job["id"])
    assert updated["status"] == "organized"
    poller.start()
    assert poller.is_running is False  # SKIP_APP_BOOT=1 in tests
    poller.stop()


def test_poller_loop_waits_between_ticks(tmp_path, monkeypatch):
    db = Database(tmp_path / "librarian.db")
    poller = JobPoller(db, lambda: Settings(), interval=12.5)
    waits = []

    def fake_wait(timeout=None):
        waits.append(timeout)
        return True

    monkeypatch.setattr(poller._stop, "wait", fake_wait)
    monkeypatch.setattr(poller, "tick", lambda: (_ for _ in ()).throw(AssertionError("tick")))
    poller._loop()
    assert waits == [12.5]


class _Clock:
    def __init__(self) -> None:
        self.now = 10_000.0

    def __call__(self) -> float:
        return self.now


_POLL_ENV = (
    "LIBRARIAN_POLL_SECONDS",
    "LIBRARIAN_ENRICH_POLL_SECONDS",
    "LIBRARIAN_RSS_POLL_SECONDS",
    "LIBRARIAN_SWEEP_POLL_SECONDS",
    "LIBRARIAN_WANTED_POLL_SECONDS",
    "LIBRARIAN_OWNED_POLL_SECONDS",
    "LIBRARIAN_NOTED_POLL_SECONDS",
    "LIBRARIAN_BACKUP_POLL_SECONDS",
)


def _always_enabled(monkeypatch) -> None:
    monkeypatch.setattr(JobPoller, "_step_enabled", lambda self, name, settings: True)


def _clear_poll_env(monkeypatch) -> None:
    for name in _POLL_ENV:
        monkeypatch.delenv(name, raising=False)


def _status(poller: JobPoller) -> dict:
    return {step["id"]: step for step in poller.step_status()["steps"]}


def _record(calls, name):
    def run(_settings):
        calls.append(name)
        return 1 if name == "sab" else 0

    return run


def test_poll_seconds_and_step_env_overrides(tmp_path, monkeypatch):
    _clear_poll_env(monkeypatch)
    monkeypatch.setenv("LIBRARIAN_POLL_SECONDS", "soon")
    assert poll_interval_seconds() == DEFAULT_SAB_POLL_SECONDS
    monkeypatch.setenv("LIBRARIAN_POLL_SECONDS", "1")
    assert poll_interval_seconds() == 5.0

    monkeypatch.setenv("LIBRARIAN_POLL_SECONDS", "15")
    monkeypatch.setenv("LIBRARIAN_ENRICH_POLL_SECONDS", "nope")
    monkeypatch.setenv("LIBRARIAN_RSS_POLL_SECONDS", "600")
    monkeypatch.setenv("LIBRARIAN_SWEEP_POLL_SECONDS", "4")
    monkeypatch.setenv("LIBRARIAN_WANTED_POLL_SECONDS", "90")
    monkeypatch.setenv("LIBRARIAN_NOTED_POLL_SECONDS", "3")
    monkeypatch.setenv("LIBRARIAN_BACKUP_POLL_SECONDS", "7200")
    poller = JobPoller(Database(tmp_path / "librarian.db"), lambda: Settings())
    status = _status(poller)
    assert poller.interval == 15
    assert status["sab"]["interval_seconds"] == 15
    assert status["watch"]["interval_seconds"] == 15
    assert status["repair"]["interval_seconds"] == 15
    assert status["enrich"]["interval_seconds"] == DEFAULT_ENRICH_POLL_SECONDS
    assert status["rss"]["interval_seconds"] == 600
    assert status["sweep"]["interval_seconds"] == 5
    assert status["wanted"]["interval_seconds"] == 90
    assert status["noted"]["interval_seconds"] == 5
    assert status["backup"]["interval_seconds"] == 7200
    assert status["backup"]["label"] == "Nightly backup"
    assert status["sab"]["last_run"] is None
    assert status["sab"]["last_error"] is None

    forced = JobPoller(Database(tmp_path / "other.db"), lambda: Settings(), interval=12.5)
    assert forced.interval == 12.5
    assert _status(forced)["sab"]["interval_seconds"] == 12.5
    assert _status(forced)["rss"]["interval_seconds"] == 600


def test_step_intervals_are_independent(tmp_path, monkeypatch):
    _clear_poll_env(monkeypatch)
    _always_enabled(monkeypatch)
    clock = _Clock()
    calls = []
    poller = JobPoller(
        Database(tmp_path / "librarian.db"),
        lambda: Settings(),
        interval=30,
        clock=clock,
    )
    for name in list(poller._runners):
        poller._runners[name] = _record(calls, name)

    poller.tick()
    assert calls == [
        "watch",
        "rss",
        "repair",
        "abs",
        "sweep",
        "owned",
        "wanted",
        "noted",
        "backup",
        "notices",
        "sab",
    ]
    assert _status(poller)["enrich"]["last_run"] is None
    assert _status(poller)["sab"]["last_run"]

    calls.clear()
    clock.now += DEFAULT_ENRICH_POLL_SECONDS
    poller.tick()
    assert "enrich" in calls
    assert "sweep" not in calls
    assert "backup" not in calls
    assert "rss" in calls
    assert _status(poller)["enrich"]["last_error"] is None
    assert DEFAULT_RSS_POLL_SECONDS == DEFAULT_ENRICH_POLL_SECONDS
    assert DEFAULT_WANTED_POLL_SECONDS == 3600.0
    assert DEFAULT_OWNED_POLL_SECONDS == 300.0
    assert DEFAULT_WANTED_POLL_SECONDS > DEFAULT_SWEEP_POLL_SECONDS > DEFAULT_SAB_POLL_SECONDS


def test_noted_refresh_is_due_after_its_interval(tmp_path, monkeypatch):
    _clear_poll_env(monkeypatch)
    clock = _Clock()
    refresh_calls = []
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        if request.url.host != "openlibrary.org":
            return httpx.Response(599, json={"error": "refused"})
        return httpx.Response(200, json={"works": []})

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("librarian.noted.httpx.Client", client_factory)

    def spy(db, settings, **kwargs):
        refresh_calls.append(kwargs.get("data_dir"))
        return run_noted_refresh(db, settings, **kwargs)

    monkeypatch.setattr("librarian.noted.run_noted_refresh", spy)

    poller = JobPoller(
        Database(tmp_path / "librarian.db"),
        lambda: Settings(),
        interval=30,
        clock=clock,
        data_dir=tmp_path,
    )
    for name in list(poller._runners):
        if name != "noted":
            poller._runners[name] = lambda _settings: 0

    noted = _status(poller)["noted"]
    assert noted["interval_seconds"] == DEFAULT_NOTED_POLL_SECONDS == 21600
    assert noted["label"] == "New & noted"
    assert poller._due("noted") is True

    poller.tick()
    assert refresh_calls == [tmp_path]
    assert hosts == ["openlibrary.org", "openlibrary.org"]
    assert _status(poller)["noted"]["last_error"] is None
    assert poller._due("noted") is False

    clock.now += DEFAULT_NOTED_POLL_SECONDS - 1
    assert poller._due("noted") is False
    poller.tick()
    assert refresh_calls == [tmp_path]

    clock.now += 1
    assert poller._due("noted") is True


def test_one_step_failure_does_not_skip_the_others(tmp_path, monkeypatch):
    _clear_poll_env(monkeypatch)
    _always_enabled(monkeypatch)
    calls = []
    poller = JobPoller(Database(tmp_path / "librarian.db"), lambda: Settings(), interval=30)
    for name in list(poller._runners):
        poller._runners[name] = _record(calls, name)

    def fail_rss(_settings):
        calls.append("rss")
        raise RuntimeError("rss down")

    poller._runners["rss"] = fail_rss
    assert poller.tick() == 1
    assert calls.index("rss") < calls.index("sweep") < calls.index("wanted") < calls.index("sab")
    assert "enrich" not in calls
    status = _status(poller)
    assert status["rss"]["last_error"] == "rss down"
    assert status["rss"]["last_run"]
    assert status["sab"]["last_error"] is None
    assert status["sweep"]["last_error"] is None
    assert status["wanted"]["last_run"]

    calls.clear()

    def fail_sab(_settings):
        calls.append("sab")
        raise SABError("downloader offline")

    poller._runners["sab"] = fail_sab
    clock_now = poller._clock()
    with poller._lock:
        poller._next_due["sab"] = clock_now
    assert poller.tick() == 0
    assert calls == ["sab"]
    assert _status(poller)["sab"]["last_error"] == "downloader offline"
    assert _status(poller)["wanted"]["last_error"] is None


def test_download_loop_does_not_run_enrich(tmp_path, monkeypatch):
    _always_enabled(monkeypatch)
    calls = []
    poller = JobPoller(Database(tmp_path / "librarian.db"), lambda: Settings(), interval=12.5)
    for name in list(poller._runners):
        poller._runners[name] = _record(calls, name)
    with poller._lock:
        poller._next_due["enrich"] = poller._clock()
    waits = []

    def fake_wait(timeout=None):
        waits.append(timeout)
        return len(waits) > 1

    monkeypatch.setattr(poller._stop, "wait", fake_wait)
    poller._loop()
    assert calls == ["sab", "watch"]
    assert waits == [12.5, 12.5]


def test_housekeeping_failure_does_not_skip_later_steps(tmp_path, monkeypatch):
    _clear_poll_env(monkeypatch)
    _always_enabled(monkeypatch)
    clock = _Clock()
    calls = []
    poller = JobPoller(
        Database(tmp_path / "librarian.db"),
        lambda: Settings(),
        interval=30,
        clock=clock,
    )

    def fail_rss(_settings):
        calls.append("rss")
        raise RuntimeError("feed down")

    def enrich(_settings):
        calls.append("enrich")
        return 0

    for name in list(poller._runners):
        poller._runners[name] = _record(calls, name)
    poller._runners["rss"] = fail_rss
    poller._runners["enrich"] = enrich
    with poller._lock:
        for name in poller._next_due:
            poller._next_due[name] = clock.now + 10_000
        poller._next_due["rss"] = clock.now
        poller._next_due["enrich"] = clock.now

    monkeypatch.setattr(poller._stop, "wait", lambda timeout=None: True)
    poller._steps_loop()
    assert calls == ["rss", "enrich"]
    assert _status(poller)["rss"]["last_error"] == "feed down"
    assert _status(poller)["enrich"]["last_error"] is None
    assert _status(poller)["sab"]["last_run"] is None


def test_slow_enrich_does_not_hold_back_downloads(tmp_path, monkeypatch):
    _clear_poll_env(monkeypatch)
    _always_enabled(monkeypatch)
    monkeypatch.delenv("LIBRARIAN_SKIP_APP_BOOT")
    monkeypatch.delenv("LIBRARIAN_DISABLE_POLLER", raising=False)
    held = threading.Event()
    entered = threading.Event()
    sab_runs = {"n": 0}
    enrich_runs = {"n": 0}

    poller = JobPoller(Database(tmp_path / "librarian.db"), lambda: Settings(), interval=0.05)
    for name in list(poller._runners):
        poller._runners[name] = lambda _settings: 0

    def enrich(_settings):
        enrich_runs["n"] += 1
        entered.set()
        held.wait(timeout=5)
        return 0

    def sab(_settings):
        sab_runs["n"] += 1
        return 0

    poller._runners["enrich"] = enrich
    poller._runners["sab"] = sab
    with poller._lock:
        poller._next_due["enrich"] = poller._clock()

    poller.start()
    try:
        assert entered.wait(2)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and sab_runs["n"] < 2:
            time.sleep(0.02)
        assert sab_runs["n"] >= 2
        assert enrich_runs["n"] == 1
    finally:
        held.set()
        poller.stop()


def test_disable_poller_and_skip_boot_do_not_start(tmp_path, monkeypatch):
    monkeypatch.delenv("LIBRARIAN_SKIP_APP_BOOT")
    monkeypatch.setenv("LIBRARIAN_DISABLE_POLLER", "1")
    poller = JobPoller(Database(tmp_path / "librarian.db"), lambda: Settings(), interval=0.05)
    poller.start()
    assert poller.is_running is False
    poller.stop()

    monkeypatch.delenv("LIBRARIAN_DISABLE_POLLER")
    monkeypatch.setenv("LIBRARIAN_SKIP_APP_BOOT", "1")
    poller.start()
    assert poller.is_running is False


def test_maintain_jobs_status_reports_poller_steps(tmp_path, monkeypatch):
    _clear_poll_env(monkeypatch)
    with TestClient(create_app(tmp_path)) as client:
        login = client.post(
            "/api/auth/local/login",
            json={"username": "owner", "password": "password123"},
        )
        assert login.status_code == 200
        body = client.get("/api/maintain/jobs/status").json()
    steps = body["poller"]["steps"]
    by_id = {step["id"]: step for step in steps}
    assert [step["id"] for step in steps[:5]] == ["sab", "enrich", "rss", "sweep", "wanted"]
    assert by_id["sab"]["interval_seconds"] == DEFAULT_SAB_POLL_SECONDS
    assert by_id["enrich"]["interval_seconds"] == DEFAULT_ENRICH_POLL_SECONDS
    assert by_id["rss"]["interval_seconds"] == DEFAULT_RSS_POLL_SECONDS
    assert by_id["sweep"]["interval_seconds"] == DEFAULT_SWEEP_POLL_SECONDS
    assert by_id["wanted"]["interval_seconds"] == DEFAULT_WANTED_POLL_SECONDS
    assert by_id["noted"]["interval_seconds"] == DEFAULT_NOTED_POLL_SECONDS
    assert by_id["noted"]["label"] == "New & noted"
    assert by_id["backup"]["interval_seconds"] == DEFAULT_BACKUP_POLL_SECONDS
    assert by_id["backup"]["label"] == "Nightly backup"
    assert body["backup"]["last_backup"] is None
    assert body["backup"]["daily_count"] == 0
    for step in steps:
        assert step["label"]
        assert step["last_run"] is None
        assert step["last_error"] is None
    assert by_id["abs"]["state"] == "off"
    assert by_id["watch"]["state"] == "off"
    assert by_id["wanted"]["state"] == "off"
    assert by_id["sab"]["state"] == "off"
    assert by_id["owned"]["state"] == "off"
    assert "Off" in by_id["abs"]["off_reason"]
    assert "indexer_budget" in body
    assert "user_id" not in json.dumps(body["indexer_budget"])
