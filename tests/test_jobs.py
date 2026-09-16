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


def test_music_request_keeps_kind_through_complete(tmp_path):
    complete = tmp_path / "usenet" / "complete" / "downloads" / "VA-Guardians.Of.The.Galaxy.Awesome.Mix.Vol.1-202"
    complete.mkdir(parents=True)
    (complete / "01 Hooked on a Feeling.flac").write_bytes(b"flac")
    sab_storage = "/downloads/downloads/VA-Guardians.Of.The.Galaxy.Awesome.Mix.Vol.1-202"

    def sab_handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params.get("mode") == "addurl":
            return httpx.Response(200, json={"nzo_ids": ["SABnzbd_nzo_mix"]})
        if params.get("mode") == "queue":
            return httpx.Response(200, json={"queue": {"slots": []}})
        return httpx.Response(
            200,
            json={
                "history": {
                    "slots": [
                        {
                            "nzo_id": "SABnzbd_nzo_mix",
                            "status": "Completed",
                            "storage": sab_storage,
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
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
        complete_root=str(tmp_path / "usenet" / "complete"),
        sabnzbd_api_key="sab",
        nzbfinder_api_token="tok",
    )
    sab = SABClient("http://downloader.sl", "sab", transport=httpx.MockTransport(sab_handler))
    nzb = NZBFinderClient(
        "https://nzbfinder.example", "tok", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    )
    db = Database(tmp_path / "librarian.db")
    job = enqueue_indexer_item(
        db,
        settings,
        item={
            "title": "VA-Guardians.Of.The.Galaxy.Awesome.Mix.Vol.1-202",
            "guid": "04ddff33-bcf4-464d-a680-07ffa7dbd918",
            "kind": "music",
            "download_url": "https://example.test/mix.nzb",
        },
        requested_by="owner-1",
        role="owner",
        sab=sab,
        nzb=nzb,
    )
    assert job["kind"] == "music"
    polled = poll_job(db, settings, job["id"], sab=sab)
    work = db.get_work(polled["work_id"])
    assert work["kind"] == "music"
    assert polled["storage_path"] == str(complete)
    assert work["music_state"] == "incoming"
    assert "/downloads/downloads/" not in str(polled["storage_path"])


def _sab_settings(tmp_path):
    return Settings(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "mags"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "abs"),
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
        complete_root=str(tmp_path / "usenet" / "complete"),
        sabnzbd_api_key="sab",
        nzbfinder_api_token="tok",
    )


def _history_handler(nzo_id, *, status, storage="", name="", fail_message=""):
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params.get("mode") == "addurl":
            return httpx.Response(200, json={"nzo_ids": [nzo_id]})
        if params.get("mode") == "queue":
            return httpx.Response(200, json={"queue": {"slots": []}})
        return httpx.Response(
            200,
            json={
                "history": {
                    "slots": [
                        {
                            "nzo_id": nzo_id,
                            "status": status,
                            "storage": storage,
                            "name": name,
                            "fail_message": fail_message,
                            "bytes": 1234,
                        }
                    ]
                }
            },
        )

    return handler


def test_history_fail_message_marks_job_failed(tmp_path):
    settings = _sab_settings(tmp_path)
    sab = SABClient(
        "http://downloader.sl",
        "sab",
        transport=httpx.MockTransport(
            _history_handler(
                "SABnzbd_nzo_fail",
                status="Failed",
                name="VA-Dump.Name-202",
                fail_message="Unpacking failed, archive is damaged",
            )
        ),
    )
    nzb = NZBFinderClient(
        "https://nzbfinder.example", "tok", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    )
    db = Database(tmp_path / "librarian.db")
    job = enqueue_indexer_item(
        db,
        settings,
        item={
            "title": "Awesome Mix Vol. 1",
            "guid": "g-fail",
            "kind": "music",
            "download_url": "https://example.test/mix.nzb",
        },
        requested_by="owner-1",
        role="owner",
        sab=sab,
        nzb=nzb,
    )
    polled = poll_job(db, settings, job["id"], sab=sab)
    assert polled["status"] == "failed"
    assert polled["error"] == "Unpacking failed, archive is damaged"
    assert polled["title"] == "Awesome Mix Vol. 1"
    assert polled["nzo_name"] == "VA-Dump.Name-202"
    assert polled["work_id"] is None


def test_unpack_stuck_archives_are_not_organized(tmp_path):
    complete = tmp_path / "usenet" / "complete" / "VA-Dump.Name-202"
    complete.mkdir(parents=True)
    (complete / "cd1.rar").write_bytes(b"Rar!")
    (complete / "cd1.par2").write_bytes(b"par2")
    sab_storage = "/downloads/downloads/VA-Dump.Name-202"
    settings = _sab_settings(tmp_path)
    sab = SABClient(
        "http://downloader.sl",
        "sab",
        transport=httpx.MockTransport(
            _history_handler(
                "SABnzbd_nzo_rar",
                status="Completed",
                storage=sab_storage,
                name="VA-Dump.Name-202",
            )
        ),
    )
    nzb = NZBFinderClient(
        "https://nzbfinder.example", "tok", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    )
    db = Database(tmp_path / "librarian.db")
    job = enqueue_indexer_item(
        db,
        settings,
        item={
            "title": "Awesome Mix Vol. 1",
            "guid": "g-rar",
            "kind": "music",
            "download_url": "https://example.test/mix.nzb",
        },
        requested_by="owner-1",
        role="owner",
        sab=sab,
        nzb=nzb,
    )
    polled = poll_job(db, settings, job["id"], sab=sab)
    assert polled["status"] == "failed"
    assert "archives remain" in polled["error"]
    assert polled["work_id"] is None
    assert polled["storage_path"] == str(complete)
    assert db.list_works() == []


def test_requested_title_survives_usenet_nzo_name(tmp_path):
    complete = tmp_path / "usenet" / "complete" / "VA-Guardians.Of.The.Galaxy.Awesome.Mix.Vol.1-202"
    complete.mkdir(parents=True)
    (complete / "01 Hooked on a Feeling.flac").write_bytes(b"flac")
    settings = _sab_settings(tmp_path)
    sab = SABClient(
        "http://downloader.sl",
        "sab",
        transport=httpx.MockTransport(
            _history_handler(
                "SABnzbd_nzo_title",
                status="Completed",
                storage="/downloads/downloads/VA-Guardians.Of.The.Galaxy.Awesome.Mix.Vol.1-202",
                name="VA-Guardians.Of.The.Galaxy.Awesome.Mix.Vol.1-202",
            )
        ),
    )
    nzb = NZBFinderClient(
        "https://nzbfinder.example", "tok", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    )
    db = Database(tmp_path / "librarian.db")
    job = enqueue_indexer_item(
        db,
        settings,
        item={
            "title": "Awesome Mix Vol. 1",
            "author": "Various Artists",
            "guid": "g-title",
            "kind": "music",
            "isbn": "",
            "download_url": "https://example.test/mix.nzb",
        },
        requested_by="owner-1",
        role="owner",
        sab=sab,
        nzb=nzb,
    )
    assert job["title"] == "Awesome Mix Vol. 1"
    assert job["kind"] == "music"
    polled = poll_job(db, settings, job["id"], sab=sab)
    assert polled["status"] in {"organized", "review"}
    assert polled["title"] == "Awesome Mix Vol. 1"
    assert polled["nzo_name"] == "VA-Guardians.Of.The.Galaxy.Awesome.Mix.Vol.1-202"
    assert polled["storage_path"] == str(complete)
    work = db.get_work(polled["work_id"])
    assert work["title"] == "Awesome Mix Vol. 1"
    assert work["kind"] == "music"
    assert work["author"] == "Various Artists"


def test_request_persists_sought_selected_retrieved(tmp_path):
    db = Database(tmp_path / "librarian.db")
    details = {
        "results": [
            {
                "title": "Herbert-Dune-ebook",
                "details": "https://nzbfinder.example/details/g-dune",
                "url": "https://nzbfinder.example/api/v2/download?id=g-dune.nzb",
                "category": 7020,
                "size": 42,
                "author": "Frank Herbert",
                "book_title": "Dune",
                "isbn13": "9780441172719",
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/api/v2/details" in str(request.url)
        assert "api_token=tok" in str(request.url)
        return httpx.Response(200, json=details)

    nzb = NZBFinderClient("https://nzbfinder.example", "tok", transport=httpx.MockTransport(handler))
    job = enqueue_indexer_item(
        db,
        Settings(nzbfinder_api_token="tok"),
        item={
            "title": "Herbert-Dune-ebook",
            "guid": "g-dune",
            "kind": "book",
            "download_url": "https://example.test/dune.nzb",
            "sought": {"kind": "book", "title": "Dune", "author": "Herbert", "isbn": "9780441172719"},
            "selected": {
                "guid": "g-dune",
                "title": "Herbert-Dune-ebook",
                "download_url": "https://example.test/dune.nzb",
                "category": 7020,
            },
        },
        requested_by="reader-1",
        role="reader",
        nzb=nzb,
    )
    payload = job["payload"]
    assert job["title"] == "Dune"
    assert payload["sought"]["title"] == "Dune"
    assert payload["sought"]["isbn"] == "9780441172719"
    assert payload["selected"]["guid"] == "g-dune"
    assert payload["selected"]["title"] == "Herbert-Dune-ebook"
    assert payload["retrieved"]["isbn"] == "9780441172719"
    assert payload["retrieved"]["book_title"] == "Dune"
    assert payload["retrieved"]["details"]["guid"] == "g-dune"
    assert "api_token" not in str(payload)
    assert "tok" not in str(payload)
