import json
from pathlib import Path

import httpx

from librarian.config import Settings
from librarian.db import Database
from librarian.indexers.sync import ping_nzbfinder, summarize_capabilities, sync_nzbfinder
from librarian.jobs import enqueue_indexer_item
from librarian.poller import JobPoller
from librarian.sabnzbd import SABClient


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

    def sab_handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params.get("mode") == "addurl":
            return httpx.Response(200, json={"nzo_ids": ["SABnzbd_nzo_p"]})
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
    )
    assert job["status"] == "queued"
    poller = JobPoller(db, lambda: settings, interval=999, sab=sab)
    assert poller.tick() == 1
    updated = db.get_job(job["id"])
    assert updated["status"] == "organized"
    poller.start()
    assert poller.is_running is False  # SKIP_APP_BOOT=1 in tests
    poller.stop()
