import httpx

from librarian.config import Settings
from librarian.db import Database
from librarian.jobs import enqueue_indexer_item, poll_job
from librarian.nzbfinder import NZBFinderClient
from librarian.sabnzbd import SABClient

NZB_XML = b'<?xml version="1.0"?><nzb xmlns="http://www.newzbin.com/DTD/2003/nzb"></nzb>'


def _nzb_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        if "/api/v2/download" in str(request.url) or "/api/v1/getnzb" in str(request.url):
            return httpx.Response(200, content=NZB_XML, headers={"content-type": "application/x-nzb"})
        return httpx.Response(200, json={})

    return httpx.MockTransport(handler)


def _sab_accepts_addfile(nzo_id: str, *, history_slots=None, queue_slots=None):
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if request.method == "POST" or params.get("mode") == "addfile":
            return httpx.Response(200, json={"nzo_ids": [nzo_id]})
        if params.get("mode") == "addurl":
            raise AssertionError("addurl must not be used when addfile is available")
        if params.get("mode") == "queue":
            return httpx.Response(200, json={"queue": {"slots": queue_slots or []}})
        if params.get("mode") == "get_files":
            return httpx.Response(200, json={"files": []})
        return httpx.Response(
            200,
            json={"history": {"slots": history_slots if history_slots is not None else []}},
        )

    return handler


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
    sab = SABClient(
        "http://downloader.sl",
        "sab",
        transport=httpx.MockTransport(
            _sab_accepts_addfile(
                "SABnzbd_nzo_1",
                history_slots=[
                    {
                        "nzo_id": "SABnzbd_nzo_1",
                        "status": "Completed",
                        "storage": str(complete),
                        "name": complete.name,
                    }
                ],
            )
        ),
    )
    nzb = NZBFinderClient("https://nzbfinder.example", "tok", transport=_nzb_transport())
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
    sab = SABClient(
        "http://downloader.sl",
        "sab",
        transport=httpx.MockTransport(
            _sab_accepts_addfile(
                "SABnzbd_nzo_mix",
                history_slots=[
                    {
                        "nzo_id": "SABnzbd_nzo_mix",
                        "status": "Completed",
                        "storage": sab_storage,
                        "name": complete.name,
                    }
                ],
            )
        ),
    )
    nzb = NZBFinderClient("https://nzbfinder.example", "tok", transport=_nzb_transport())
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
    return _sab_accepts_addfile(
        nzo_id,
        history_slots=[
            {
                "nzo_id": nzo_id,
                "status": status,
                "storage": storage,
                "name": name,
                "fail_message": fail_message,
                "bytes": 1234,
            }
        ],
    )


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
    nzb = NZBFinderClient("https://nzbfinder.example", "tok", transport=_nzb_transport())
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


def test_unpack_stuck_archives_go_to_review_not_silent_fail(tmp_path):
    """SAB-complete folders with only rar/par2 must park a Review slip (not failed/no work)."""
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
    nzb = NZBFinderClient("https://nzbfinder.example", "tok", transport=_nzb_transport())
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
    assert polled["status"] == "review"
    assert polled["work_id"]
    assert polled["error"] is None
    assert polled["storage_path"] == str(complete)
    work = db.get_work(polled["work_id"])
    assert work["review_state"] == "needs_review"
    assert work["review_reason"] == "unpack_stuck"
    assert work["folder_path"] == str(complete)


def test_unpack_stuck_audiobook_unar_then_organizes(tmp_path, monkeypatch):
    """When SAB leaves multipart rar, poll_job must unar before giving up."""
    complete = tmp_path / "usenet" / "complete" / "Born.to.Run.mp3.audiobook"
    complete.mkdir(parents=True)
    part1 = complete / "Born.part1.rar"
    part2 = complete / "Born.part2.rar"
    part1.write_bytes(b"Rar!\x01")
    part2.write_bytes(b"Rar!\x02")
    (complete / "Born.par2").write_bytes(b"par2")
    sab_storage = "/downloads/downloads/Born.to.Run.mp3.audiobook"
    settings = _sab_settings(tmp_path)
    calls = []

    def runner(argv, timeout=300):
        calls.append(list(argv))
        if argv and "unar" in str(argv[0]):
            (complete / "Born-Part01.mp3").write_bytes(b"mp3-audio")
            return type("R", (), {"returncode": 0})()
        return type("R", (), {"returncode": 1})()

    monkeypatch.setattr("librarian.organize.maybe_par2_repair", lambda folder, **kw: {"repaired": False})
    monkeypatch.setattr(
        "librarian.organize.maybe_unpack_archives",
        lambda folder, **kw: __import__("librarian.convert", fromlist=["maybe_unpack_archives"]).maybe_unpack_archives(
            folder, runner=runner, unar="/usr/bin/unar"
        ),
    )
    sab = SABClient(
        "http://downloader.sl",
        "sab",
        transport=httpx.MockTransport(
            _history_handler(
                "SABnzbd_nzo_ab",
                status="Completed",
                storage=sab_storage,
                name="Born.to.Run.mp3.audiobook",
            )
        ),
    )
    nzb = NZBFinderClient("https://nzbfinder.example", "tok", transport=_nzb_transport())
    db = Database(tmp_path / "librarian.db")
    job = enqueue_indexer_item(
        db,
        settings,
        item={
            "title": "Born to Run",
            "guid": "g-ab",
            "kind": "audiobook",
            "download_url": "https://example.test/ab.nzb",
        },
        requested_by="owner-1",
        role="owner",
        sab=sab,
        nzb=nzb,
    )
    polled = poll_job(db, settings, job["id"], sab=sab)
    assert any("unar" in str(call[0]) for call in calls)
    assert calls[0][-1] == str(part1)  # first volume only — not part2
    assert polled["status"] in {"organized", "review"}
    assert polled["work_id"]
    work = db.get_work(polled["work_id"])
    assert work["kind"] == "audiobook"
    assert work["review_reason"] != "unpack_stuck"

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
    nzb = NZBFinderClient("https://nzbfinder.example", "tok", transport=_nzb_transport())
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


def test_owner_prefers_addfile_over_stripped_url(tmp_path):
    """Public hits strip api_token; Librarian must push NZB bytes, not addurl the bare link."""
    seen = {"addfile": 0, "addurl": 0, "nzbname": ""}

    def nzb_handler(request: httpx.Request) -> httpx.Response:
        if "/api/v2/download" in str(request.url):
            return httpx.Response(
                200,
                content=NZB_XML,
                headers={"content-type": "application/x-nzb"},
            )
        return httpx.Response(200, json={})

    def sab_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            seen["addfile"] += 1
            # Multipart form field nzbname=
            body = request.content or b""
            if b'name="nzbname"' in body:
                start = body.find(b'name="nzbname"')
                chunk = body[start : start + 200]
                # value follows headers + blank line
                parts = chunk.split(b"\r\n\r\n", 1)
                if len(parts) == 2:
                    seen["nzbname"] = parts[1].split(b"\r\n")[0].decode()
            return httpx.Response(200, json={"nzo_ids": ["SABnzbd_nzo_push"]})
        params = dict(request.url.params)
        if params.get("mode") == "addurl":
            seen["addurl"] += 1
            return httpx.Response(200, json={"nzo_ids": ["SABnzbd_nzo_url"]})
        if params.get("mode") == "queue":
            return httpx.Response(200, json={"queue": {"slots": []}})
        return httpx.Response(200, json={"history": {"slots": []}})

    settings = Settings(sabnzbd_api_key="sab", nzbfinder_api_token="tok")
    sab = SABClient("http://downloader.sl", "sab", transport=httpx.MockTransport(sab_handler))
    nzb = NZBFinderClient("https://nzbfinder.example", "tok", transport=httpx.MockTransport(nzb_handler))
    db = Database(tmp_path / "librarian.db")
    job = enqueue_indexer_item(
        db,
        settings,
        item={
            "title": "NFL",  # Find query / sought title — must NOT become SAB nzbname
            "q": "NFL",
            "kind": "book",
            "sought": {"q": "NFL", "kind": "book", "title": "NFL"},
            "selected": {
                "guid": "g-saga",
                "title": "NFL.Week.01.DEN.KC.1080p",
                "download_url": "https://nzbfinder.example/api/v1/getnzb?id=g-saga.nzb",
                "kind": "book",
            },
            "guid": "g-saga",
            "download_url": "https://nzbfinder.example/api/v1/getnzb?id=g-saga.nzb",
        },
        requested_by="owner-1",
        role="owner",
        sab=sab,
        nzb=nzb,
    )
    assert job["nzo_id"] == "SABnzbd_nzo_push"
    assert job["title"] == "NFL"  # catalog/sought title stays for shelving
    assert seen["addfile"] == 1
    assert seen["addurl"] == 0
    assert seen["nzbname"] == "NFL.Week.01.DEN.KC.1080p"

