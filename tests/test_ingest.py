import time
from pathlib import Path

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.identify import REVIEW_COLLISION
from librarian.ingest import (
    enqueue_ingest,
    expand_album_context,
    list_ingest_targets,
    poll_watch_folder,
    run_ingest_paths,
    watch_root_forbidden,
)
from librarian.poller import JobPoller
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def _settings(tmp_path: Path, **extra) -> Settings:
    payload = dict(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "magazines"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "audiobooks"),
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
        nzbfinder_api_token="",
        sabnzbd_api_key="",
    )
    payload.update(extra)
    return Settings.from_mapping(payload)


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    clear_rate_limits()
    return TestClient(create_app(tmp_path))


def _login(client, username="owner", password="password123"):
    assert client.post("/api/auth/local/login", json={"username": username, "password": password}).status_code == 200


def _wait_ingest_status(client, *, timeout=5.0):
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        resp = client.get("/api/ingest/status")
        assert resp.status_code == 200
        last = resp.json()
        if last.get("status") in ("completed", "failed", "idle"):
            return last
        time.sleep(0.05)
    return last


def test_add_file_confident_identify_moves_into_root(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    settings = _settings(tmp_path)
    source = tmp_path / "inbox" / "Le Guin - The Left Hand of Darkness 9780441478125.epub"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"epub")
    db = Database(tmp_path / "librarian.db")
    job = enqueue_ingest(db, settings, path=source, requested_by="owner-1", source="ingest")
    assert job["status"] == "organized"
    dest = Path(settings.books_root) / "Le Guin" / "The Left Hand of Darkness" / "The Left Hand of Darkness.epub"
    assert dest.is_file()
    assert dest.read_bytes() == b"epub"
    assert not source.exists()
    work = db.get_work(job["work_id"])
    assert work["review_state"] == "none"
    assert work["kind"] == "book"
    assert work["isbn"] == "9780441478125"


def test_add_folder_unknown_payload_goes_to_review(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    settings = _settings(tmp_path)
    folder = tmp_path / "inbox" / "weird-dump"
    folder.mkdir(parents=True)
    (folder / "mystery.epub").write_bytes(b"epub")
    db = Database(tmp_path / "librarian.db")
    job = enqueue_ingest(db, settings, path=folder, requested_by="owner-1")
    assert job["status"] == "review"
    assert (folder / "mystery.epub").is_file()
    work = db.get_work(job["work_id"])
    assert work["review_state"] == "needs_review"
    assert work["review_reason"] in {"low_confidence", "unknown_identity"}


def test_collision_goes_to_review_and_leaves_source(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    settings = _settings(tmp_path)
    dest_dir = Path(settings.books_root) / "Le Guin" / "The Left Hand of Darkness"
    dest_dir.mkdir(parents=True)
    (dest_dir / "The Left Hand of Darkness.epub").write_bytes(b"old")
    source = tmp_path / "inbox" / "Le Guin - The Left Hand of Darkness 9780441478125.epub"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"new")
    db = Database(tmp_path / "librarian.db")
    job = enqueue_ingest(db, settings, path=source, requested_by="owner-1")
    assert job["status"] == "review"
    work = db.get_work(job["work_id"])
    assert work["review_reason"] == REVIEW_COLLISION
    assert source.is_file()
    assert source.read_bytes() == b"new"
    assert (dest_dir / "The Left Hand of Darkness.epub").read_bytes() == b"old"


def test_watch_poll_picks_up_once_without_duplicate(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    watch = tmp_path / "inbox"
    watch.mkdir()
    source = watch / "Le Guin - The Left Hand of Darkness 9780441478125.epub"
    source.write_bytes(b"epub")
    settings = _settings(tmp_path, watch_root=str(watch), watch_enabled=True)
    db = Database(tmp_path / "librarian.db")
    first = poll_watch_folder(db, settings)
    assert first == 1
    jobs = db.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["status"] == "organized"
    assert jobs[0]["payload"]["source"] == "watch"
    assert not source.exists()
    (watch / "Le Guin - The Left Hand of Darkness 9780441478125.epub").write_bytes(b"again")
    second = poll_watch_folder(db, settings)
    assert second == 0
    assert len(db.list_jobs()) == 1


def test_watch_skips_hidden_and_rar_leftovers(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    watch = tmp_path / "inbox"
    watch.mkdir()
    (watch / ".DS_Store").write_bytes(b"junk")
    (watch / "stuck.rar").write_bytes(b"rar")
    settings = _settings(tmp_path, watch_root=str(watch), watch_enabled=True)
    db = Database(tmp_path / "librarian.db")
    assert poll_watch_folder(db, settings) == 0
    assert db.list_jobs() == []


def test_poller_tick_watches_without_sab_key(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    watch = tmp_path / "inbox"
    watch.mkdir()
    (watch / "Le Guin - The Left Hand of Darkness 9780441478125.epub").write_bytes(b"epub")
    settings = _settings(tmp_path, watch_root=str(watch), watch_enabled=True)
    db = Database(tmp_path / "librarian.db")
    poller = JobPoller(db, lambda: settings, interval=999)
    assert poller.tick() == 1
    jobs = db.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["status"] == "organized"


def test_path_outside_data_is_rejected(tmp_path, monkeypatch):
    save_settings(tmp_path, _settings(tmp_path))
    client = _client(tmp_path, monkeypatch)
    _login(client)
    denied = client.post("/api/ingest", json={"path": "/etc/passwd"})
    assert denied.status_code == 400
    assert "outside" in denied.json()["detail"].lower()
    escaped = client.get("/api/fs", params={"path": "/etc"})
    assert escaped.status_code == 400


def test_reader_forbidden_on_ingest_and_fs(tmp_path, monkeypatch):
    save_settings(tmp_path, _settings(tmp_path))
    client = _client(tmp_path, monkeypatch)
    _login(client)
    token = client.post("/api/invites", json={"role": "reader"}).json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert (
        client.post(
            "/api/invites/redeem/local",
            json={"token": token, "username": "reader1", "password": "password123"},
        ).status_code
        == 200
    )
    assert client.get("/api/fs").status_code == 403
    assert client.post("/api/ingest", json={"path": str(tmp_path / "inbox")}).status_code == 403
    assert client.get("/api/ingest/status").status_code == 403


def test_op_can_add_to_library(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    save_settings(tmp_path, settings)
    source = tmp_path / "inbox" / "Le Guin - The Left Hand of Darkness 9780441478125.epub"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"epub")
    client = _client(tmp_path, monkeypatch)
    _login(client)
    token = client.post("/api/invites", json={"role": "op"}).json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert (
        client.post(
            "/api/invites/redeem/local",
            json={"token": token, "username": "ops", "password": "password123"},
        ).status_code
        == 200
    )
    listed = client.get("/api/fs", params={"path": str(tmp_path / "inbox")})
    assert listed.status_code == 200
    names = [row["name"] for row in listed.json()["entries"]]
    assert "Le Guin - The Left Hand of Darkness 9780441478125.epub" in names
    added = client.post("/api/ingest", json={"path": str(source)})
    assert added.status_code == 200
    body = added.json()
    assert body["kicked_off"] is True
    assert body["status"] in ("running", "completed")
    status = _wait_ingest_status(client)
    assert status["status"] == "completed"
    assert int((status.get("result") or {}).get("shelved") or status.get("shelved") or 0) == 1
    assert not source.exists()
    queue = client.get("/api/queue")
    assert queue.status_code == 200
    job = queue.json()["jobs"][0]
    assert job["payload"]["source"] == "ingest"
    assert job["status"] == "organized"


def test_list_ingest_targets_expands_dump_parent(tmp_path):
    parent = tmp_path / "complete" / "books"
    parent.mkdir(parents=True)
    a = parent / "Christine - Stephen King"
    b = parent / "David Baldacci"
    a.mkdir()
    b.mkdir()
    (a / "Christine.epub").write_bytes(b"epub")
    (b / "book.epub").write_bytes(b"epub")
    targets = list_ingest_targets(parent)
    assert {t.name for t in targets} == {"Christine - Stephen King", "David Baldacci"}


def test_list_ingest_targets_keeps_single_volume_folder(tmp_path):
    folder = tmp_path / "inbox" / "Left Hand"
    folder.mkdir(parents=True)
    (folder / "Left Hand.epub").write_bytes(b"epub")
    assert list_ingest_targets(folder) == [folder]


def test_list_ingest_targets_expands_calibre_author_tree(tmp_path):
    library = tmp_path / "newlib"
    a1 = library / "Abby Jimenez" / "Just for the Summer (10103)"
    a2 = library / "Abby Jimenez" / "Yours Truly (983)"
    b1 = library / "A. M. Homes" / "Days of Awe (8390)"
    for folder in (a1, a2, b1):
        folder.mkdir(parents=True)
        (folder / "book.epub").write_bytes(b"epub")
        (folder / "book.azw3").write_bytes(b"azw3")
    targets = list_ingest_targets(library)
    assert {t.name for t in targets} == {
        "Just for the Summer (10103)",
        "Yours Truly (983)",
        "Days of Awe (8390)",
    }


def test_run_ingest_paths_reports_progress_and_moves(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    settings = _settings(tmp_path)
    parent = tmp_path / "inbox"
    parent.mkdir()
    first = parent / "Le Guin - The Left Hand of Darkness 9780441478125.epub"
    first.write_bytes(b"epub")
    second = parent / "mystery-dump"
    second.mkdir()
    (second / "mystery.epub").write_bytes(b"epub")
    db = Database(tmp_path / "librarian.db")

    ticks: list[dict] = []

    class FakeProgress:
        def start(self, *, total, phase="scanning"):
            ticks.append({"event": "start", "total": total, "phase": phase})

        def tick(self, **fields):
            ticks.append({"event": "tick", **fields})

        def complete(self, result):
            ticks.append({"event": "complete", "result": dict(result)})

        def fail(self, error):
            ticks.append({"event": "fail", "error": error})

    summary = run_ingest_paths(
        db,
        settings,
        paths=list_ingest_targets(parent),
        requested_by="owner-1",
        progress=FakeProgress(),
    )
    assert summary["total"] == 2
    assert summary["shelved"] == 1
    assert summary["review"] == 1
    assert not first.exists()
    assert second.is_dir()  # Review keeps staging
    assert (second / "mystery.epub").is_file()
    assert ticks[0]["event"] == "start"
    assert ticks[-1]["event"] == "complete"
    assert any(t.get("phase") == "organizing" for t in ticks if t["event"] == "tick")


def test_ingest_status_idle_then_batch(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    save_settings(tmp_path, settings)
    parent = tmp_path / "complete" / "books"
    parent.mkdir(parents=True)
    a = parent / "Le Guin - The Left Hand of Darkness 9780441478125.epub"
    a.write_bytes(b"epub")
    b = parent / "weird-dump"
    b.mkdir()
    (b / "mystery.epub").write_bytes(b"epub")
    client = _client(tmp_path, monkeypatch)
    _login(client)
    idle = client.get("/api/ingest/status")
    assert idle.status_code == 200
    assert idle.json()["status"] == "idle"
    assert idle.json()["shelved"] == 0
    started = client.post("/api/ingest", json={"path": str(parent)})
    assert started.status_code == 200
    assert started.json()["kicked_off"] is True
    assert started.json()["total"] == 2
    status = _wait_ingest_status(client)
    assert status["status"] == "completed"
    result = status.get("result") or {}
    assert int(result.get("shelved") or 0) == 1
    assert int(result.get("review") or 0) == 1
    assert status["phase"] == "done"
    assert status["source_path"] == str(parent)
    assert not a.exists()
    assert b.is_dir()


def test_ingest_dump_folder_moves_source_on_success(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    settings = _settings(tmp_path)
    dump = tmp_path / "complete" / "Le Guin - The Left Hand of Darkness 9780441478125"
    dump.mkdir(parents=True)
    (dump / "The Left Hand of Darkness.epub").write_bytes(b"epub")
    (dump / "release.nfo").write_text("nfo", encoding="utf-8")
    db = Database(tmp_path / "librarian.db")
    job = enqueue_ingest(db, settings, path=dump, requested_by="owner-1")
    assert job["status"] == "organized"
    assert not dump.exists()
    shelved = list(Path(settings.books_root).rglob("*.epub"))
    assert len(shelved) == 1
    assert shelved[0].read_bytes() == b"epub"


def test_audio_file_enqueues_sibling_album_folder(tmp_path):
    album = tmp_path / "inbox" / "Kind of Blue"
    album.mkdir(parents=True)
    first = album / "01 So What.flac"
    first.write_bytes(b"flac")
    (album / "02 Freddie.flac").write_bytes(b"flac")
    assert expand_album_context(first) == album


def test_watch_root_cannot_equal_books_root(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    save_settings(tmp_path, settings)
    client = _client(tmp_path, monkeypatch)
    _login(client)
    refused = client.put(
        "/api/settings",
        json={"watch_root": settings.books_root, "watch_enabled": True},
    )
    assert refused.status_code == 400
    assert "library root" in refused.json()["detail"].lower()


def test_watch_root_forbidden_smart_map_inbox(tmp_path):
    settings = _settings(tmp_path)
    assert watch_root_forbidden(Path("/data/media/YouTubeDownload"), settings)
    assert watch_root_forbidden(Path("/data/media/YouTubeLibrary"), settings)
    assert not watch_root_forbidden(tmp_path / "drop", settings)


def test_ingest_refuses_library_root_with_honest_copy(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    books = Path(settings.books_root)
    books.mkdir(parents=True)
    (books / "readme.txt").write_text("shelf", encoding="utf-8")
    save_settings(tmp_path, settings)
    client = _client(tmp_path, monkeypatch)
    _login(client)
    refused = client.post("/api/ingest", json={"path": str(books)})
    assert refused.status_code == 400
    detail = refused.json()["detail"].lower()
    assert "library root" in detail
    assert "scan" in detail


def test_ingest_empty_dump_parks_review_slip(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    settings = _settings(tmp_path)
    empty = tmp_path / "inbox" / "books"
    empty.mkdir(parents=True)
    db = Database(tmp_path / "librarian.db")
    job = enqueue_ingest(db, settings, path=empty, requested_by="owner-1")
    assert job["status"] == "review"
    assert job["work_id"]
    assert job["error"] is None
    assert job["title"] == "books"
    work = db.get_work(job["work_id"])
    assert work["review_state"] == "needs_review"
    assert work["review_reason"] in {"no_payload", "unknown_identity", "low_confidence"}


def test_ingest_allows_dump_under_complete_root(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    complete = tmp_path / "usenet" / "complete"
    dump = complete / "Le Guin - The Left Hand of Darkness 9780441478125.epub"
    dump.parent.mkdir(parents=True)
    dump.write_bytes(b"epub")
    settings = _settings(tmp_path, complete_root=str(complete))
    db = Database(tmp_path / "librarian.db")
    job = enqueue_ingest(db, settings, path=dump, requested_by="owner-1")
    assert job["status"] == "organized"


def test_ingest_refuses_complete_root_itself(tmp_path, monkeypatch):
    complete = tmp_path / "usenet" / "complete"
    complete.mkdir(parents=True)
    settings = _settings(tmp_path, complete_root=str(complete))
    save_settings(tmp_path, settings)
    client = _client(tmp_path, monkeypatch)
    _login(client)
    refused = client.post("/api/ingest", json={"path": str(complete)})
    assert refused.status_code == 400
    assert "complete folder" in refused.json()["detail"].lower()


def test_progress_ingest_job_parks_review_on_permission_error(tmp_path, monkeypatch):
    """OSError during organize must leave Review — not identifying forever."""
    from librarian.ingest import progress_ingest_job

    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    settings = _settings(tmp_path)
    dump = tmp_path / "inbox" / "Holly.epub"
    dump.parent.mkdir(parents=True)
    dump.write_bytes(b"epub")
    db = Database(tmp_path / "librarian.db")
    job = db.create_job(
        {
            "status": "identifying",
            "title": "Holly",
            "requested_by": "owner-1",
            "storage_path": str(dump),
            "payload": {"source": "ingest", "path": str(dump)},
        }
    )

    def boom(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied", str(settings.books_root))

    monkeypatch.setattr("librarian.ingest.organize_identified", boom)
    updated = progress_ingest_job(db, settings, job["id"])
    assert updated["status"] == "review"
    assert "Could not shelve" in (updated.get("error") or "")
    assert "Permission denied" in (updated.get("error") or "")
    assert db.get_job(job["id"])["status"] == "review"
