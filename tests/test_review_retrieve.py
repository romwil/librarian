"""Slip Smart re-grab and Request new version search and queue in place."""

import httpx
from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.review_retrieve import retrieve_slip_release
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def _client(tmp_path, monkeypatch, settings=None):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    if settings is not None:
        save_settings(tmp_path, settings)
    app = create_app(tmp_path)
    client = TestClient(app)
    assert client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
    ).status_code == 200
    return client, app

NZB = b'<?xml version="1.0"?><nzb xmlns="http://www.newzbin.com/DTD/2003/nzb"></nzb>'


def _settings(tmp_path):
    return Settings(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "magazines"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "audiobooks"),
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
        complete_root=str(tmp_path / "complete"),
        sabnzbd_url="http://downloader.test",
        sabnzbd_api_key="sab-key",
        nzbfinder_url="https://indexer.test",
        nzbfinder_api_token="tok",
        llm_base_url="",
        llm_api_key="",
    )


def _hit(guid, title, author="Adam Grant"):
    return {
        "title": title,
        "guid": guid,
        "author": author,
        "size": "1200000",
        "category": "7000",
    }


def _install(monkeypatch, nzb_handler, sab_handler=None):
    from librarian.indexers.hosts import NZBFinderClient
    from librarian.sabnzbd import SABClient

    def nzb_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(nzb_handler)
        return NZBFinderClient(*args, **kwargs)

    monkeypatch.setattr("librarian.indexers.hosts.NZBFinderClient", nzb_factory)
    if sab_handler is not None:
        def sab_factory(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(sab_handler)
            return SABClient(*args, **kwargs)

        monkeypatch.setattr("librarian.review_retrieve.SABClient", sab_factory)


def _sab_ok(adds):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            adds.append(str(request.url))
            return httpx.Response(200, json={"nzo_ids": ["nzo-slip"]})
        return httpx.Response(200, json={"queue": {"slots": []}})

    return handler


def _indexer(books, searches, seen):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen.append(url)
        if "/api/v2/books" in url:
            return httpx.Response(200, json={"results": books})
        if "/api/v2/search" in url:
            return httpx.Response(200, json={"results": searches})
        if "/api/v2/download" in url:
            return httpx.Response(200, content=NZB, headers={"content-type": "application/x-nzb"})
        return httpx.Response(200, json={"results": []})

    return handler


def _work(db, *, guid="guid-de"):
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Think Again",
            "author": "Adam Grant",
            "review_state": "needs_review",
            "review_reason": "unpack_stuck",
            "indexer_guid": guid,
            "repair_fail_count": 2,
            "folder_path": "/data/usenet/complete/downloads/think",
        }
    )
    db.create_job(
        {
            "status": "review",
            "indexer_guid": guid,
            "title": "Think Again",
            "kind": "book",
            "work_id": work["id"],
            "payload": {
                "selected": {
                    "title": "Think Again GERMAN Retail EPUB",
                    "guid": guid,
                },
                "candidates": [
                    {"title": "Think Again GERMAN Retail EPUB", "guid": guid},
                ],
            },
        }
    )
    return work


def test_request_new_version_queues_english_epub_on_the_slip(tmp_path, monkeypatch):
    seen = []
    adds = []
    books = [
        _hit("guid-de", "Think Again GERMAN Retail EPUB"),
        _hit("guid-en", "Think Again English Retail EPUB"),
    ]
    _install(monkeypatch, _indexer(books, [], seen), _sab_ok(adds))
    client, app = _client(tmp_path, monkeypatch, settings=_settings(tmp_path))
    work = _work(app.state.db)
    resp = client.post(f"/api/review/{work['id']}/retrieve", json={"intent": "new_version"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["searched"] is True
    assert body["queued"] is True
    assert body["chosen"]["guid"] == "guid-en"
    assert "English Retail EPUB" in body["note"]
    assert "/find" not in body["note"]
    job = app.state.db.get_job(body["job"]["id"])
    assert job["status"] == "queued"
    assert job["work_id"] == work["id"]
    assert job["indexer_guid"] == "guid-en"
    assert len(adds) == 1
    assert any("/api/v2/books" in url for url in seen)
    assert not any("/api/v2/search" in url for url in seen)


def test_request_new_version_follows_up_when_first_page_is_only_the_wrong_language(tmp_path, monkeypatch):
    seen = []
    adds = []
    _install(
        monkeypatch,
        _indexer(
            [_hit("guid-de", "Think Again GERMAN Retail EPUB")],
            [_hit("guid-en", "Think Again English Retail EPUB")],
            seen,
        ),
        _sab_ok(adds),
    )
    client, app = _client(tmp_path, monkeypatch, settings=_settings(tmp_path))
    work = _work(app.state.db)
    resp = client.post(f"/api/review/{work['id']}/retrieve", json={"intent": "new_version"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["chosen"]["guid"] == "guid-en"
    assert any("/api/v2/search" in url and "english" in url for url in seen)
    assert len(adds) == 1


def test_smart_regrab_queues_a_better_release_without_a_second_send(tmp_path, monkeypatch):
    seen = []
    adds = []
    _install(
        monkeypatch,
        _indexer(
            [
                _hit("guid-de", "Think Again GERMAN Retail EPUB"),
                _hit("guid-alt", "Think Again Retail EPUB"),
            ],
            [],
            seen,
        ),
        _sab_ok(adds),
    )
    client, app = _client(tmp_path, monkeypatch, settings=_settings(tmp_path))
    work = _work(app.state.db)
    first = client.post(f"/api/review/{work['id']}/retrieve", json={"intent": "regrab"})
    assert first.status_code == 200, first.text
    assert first.json()["queued"] is True
    assert first.json()["chosen"]["guid"] == "guid-alt"
    books_before = sum("/api/v2/books" in url for url in seen)
    second = client.post(f"/api/review/{work['id']}/retrieve", json={"intent": "regrab"})
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["already_active"] is True
    assert body["searched"] is False
    assert body["queued"] is False
    assert "already active" in body["note"]
    assert sum("/api/v2/books" in url for url in seen) == books_before
    assert len(adds) == 1


def test_unreachable_downloader_does_not_pretend_the_search_ran(tmp_path, monkeypatch):
    seen = []

    def down(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    _install(monkeypatch, _indexer([], [], seen), down)
    client, app = _client(tmp_path, monkeypatch, settings=_settings(tmp_path))
    work = _work(app.state.db)
    resp = client.post(f"/api/review/{work['id']}/retrieve", json={"intent": "new_version"})
    assert resp.status_code == 502
    detail = resp.json()["detail"].lower()
    assert "sabnzbd" in detail
    assert "did not answer" in detail
    assert seen == []
    assert app.state.db.list_jobs(statuses=("queued", "asked", "downloading")) == []


def test_version_probe_success_does_not_say_the_downloader_is_down(tmp_path, monkeypatch):
    seen = []
    modes = []
    books = [_hit("guid-en", "Think Again English Retail EPUB")]

    def sab_handler(request: httpx.Request) -> httpx.Response:
        mode = request.url.params.get("mode")
        modes.append(mode)
        if mode == "version":
            return httpx.Response(200, json={"version": "5.1.3"})
        if mode == "queue":
            return httpx.Response(200, json={"queue": {"slots": []}})
        if request.method == "POST":
            return httpx.Response(200, json={"nzo_ids": ["nzo-slip"]})
        return httpx.Response(200, json={"version": "5.1.3"})

    _install(monkeypatch, _indexer(books, [], seen), sab_handler)
    client, app = _client(tmp_path, monkeypatch, settings=_settings(tmp_path))
    work = _work(app.state.db)
    resp = client.post(f"/api/review/{work['id']}/retrieve", json={"intent": "new_version"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sab_error"] is None
    assert "did not answer" not in str(body.get("note") or "").lower()
    assert body["queued"] is True
    assert "version" in modes
    assert "queue" not in modes


def test_queue_probe_succeeds_when_version_mode_is_missing(tmp_path, monkeypatch):
    seen = []
    modes = []

    def sab_handler(request: httpx.Request) -> httpx.Response:
        mode = request.url.params.get("mode")
        modes.append(mode)
        if mode == "version":
            return httpx.Response(200, json={"queue": {"slots": []}})
        if mode == "queue":
            return httpx.Response(200, json={"queue": {"slots": []}})
        if request.method == "POST":
            return httpx.Response(200, json={"nzo_ids": ["nzo-slip"]})
        return httpx.Response(200, json={})

    _install(
        monkeypatch,
        _indexer([_hit("guid-en", "Think Again English Retail EPUB")], [], seen),
        sab_handler,
    )
    client, app = _client(tmp_path, monkeypatch, settings=_settings(tmp_path))
    work = _work(app.state.db)
    resp = client.post(f"/api/review/{work['id']}/retrieve", json={"intent": "new_version"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["sab_error"] is None
    assert "did not answer" not in resp.text.lower()
    assert modes[:2] == ["version", "queue"]


def test_reader_files_an_asked_slip_without_calling_sab(tmp_path, monkeypatch):
    from librarian.db import Database

    seen = []
    adds = []
    _install(
        monkeypatch,
        _indexer([_hit("guid-en", "Think Again English Retail EPUB")], [], seen),
        _sab_ok(adds),
    )
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Think Again",
            "author": "Adam Grant",
            "review_state": "needs_review",
            "review_reason": "no_payload",
            "folder_path": "/missing",
        }
    )
    body = retrieve_slip_release(
        db,
        _settings(tmp_path),
        work_id=work["id"],
        intent="new_version",
        role="reader",
        requested_by="reader-1",
    )
    assert body["queued"] is True
    assert body["job"]["status"] == "asked"
    assert adds == []
    assert any("/api/v2/books" in url for url in seen)
