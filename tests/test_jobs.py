import httpx

from librarian.config import Settings
from librarian.db import Database
from librarian.jobs import enqueue_indexer_item, poll_job
from librarian.nzbfinder import NZBFinderClient
from librarian.sabnzbd import SABClient


def test_reader_request_is_asked_slip(tmp_path):
    db = Database(tmp_path / "librarian.db")
    job = enqueue_indexer_item(
        db,
        Settings(),
        item={"title": "Saga #11", "guid": "g1", "kind": "comic"},
        requested_by="reader-1",
        role="reader",
    )
    assert job["status"] == "asked"
    assert job["nzo_id"] is None
    assert job["title"] == "Saga #11"


def test_owner_queue_and_poll_completed_organizes(tmp_path):
    complete = tmp_path / "complete" / "Le Guin - The Left Hand of Darkness 9780441478125"
    complete.mkdir(parents=True)
    (complete / "book.epub").write_bytes(b"epub")

    def sab_handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params.get("mode") == "addurl":
            return httpx.Response(200, json={"nzo_ids": ["SABnzbd_nzo_1"]})
        if params.get("mode") == "queue":
            return httpx.Response(200, json={"queue": {"slots": []}})
        return httpx.Response(
            200,
            json={
                "history": {
                    "slots": [
                        {
                            "nzo_id": "SABnzbd_nzo_1",
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
    nzb = NZBFinderClient("https://nzbfinder.example", "tok", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
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
    assert job["nzo_id"] == "SABnzbd_nzo_1"
    polled = poll_job(db, settings, job["id"], sab=sab)
    assert polled["status"] == "organized"
    work = db.get_work(polled["work_id"])
    assert work["title"] == "The Left Hand of Darkness"
    assert work["review_state"] == "none"
