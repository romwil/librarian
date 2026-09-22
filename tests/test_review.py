import time
from pathlib import Path

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
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
    assert client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"}).status_code == 200
    return client, app


def _wait_extra_files_reprocess_status(client, *, timeout=8.0):
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        resp = client.get("/api/review/reprocess-extra-files/status")
        assert resp.status_code == 200
        last = resp.json()
        if last.get("status") in ("completed", "failed", "idle"):
            return last
        time.sleep(0.05)
    return last


def test_review_list_diagnoses_unpack_stuck_and_soft_repairs(tmp_path, monkeypatch):
    stuck = tmp_path / "usenet" / "complete" / "downloads" / "VA-Guardians.Mix"
    stuck.mkdir(parents=True)
    (stuck / "mix.rar").write_bytes(b"Rar!")
    (stuck / "mix.par2").write_bytes(b"par2")
    settings = Settings(
        books_root=str(tmp_path / "books"),
        complete_root=str(tmp_path / "usenet" / "complete"),
    )
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    work = db.upsert_work(
        {
            "kind": "music",
            "title": "Guardians of the Galaxy Awesome Mix Vol. 1",
            "author": "Various Artists",
            "review_state": "needs_review",
            "review_reason": "no_payload",
            "folder_path": str(stuck),
        }
    )
    listed = client.get("/api/review")
    assert listed.status_code == 200
    row = listed.json()["works"][0]
    assert row["id"] == work["id"]
    assert row["review_reason"] == "unpack_stuck"
    assert row["folder_diagnosis"]["problem"] == "unpack_stuck"
    assert row["folder_diagnosis"]["archive_count"] >= 1
    assert row["folder_diagnosis"]["par2_count"] >= 1
    assert "complete/downloads" in row["folder_diagnosis"]["path_note"]
    assert "PAR2" in row["folder_diagnosis"]["tried"]
    assert row["actions"]["can_repair"] is True
    assert row["actions"]["can_retry"] is True
    assert "Guardians" in row["actions"]["find_query"]
    refreshed = db.get_work(work["id"])
    assert refreshed["review_reason"] == "unpack_stuck"


def test_review_list_fills_folder_from_job_storage(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    db = app.state.db
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Christine Stephen King",
            "author": "Christine Dougherty",
            "review_state": "needs_review",
            "review_reason": "no_payload",
        }
    )
    db.create_job(
        {
            "status": "review",
            "work_id": work["id"],
            "title": "Christine - Stephen King",
            "kind": "book",
            "storage_path": "/downloads/books/Christine - Stephen King/Christine - Stephen King.epub",
        }
    )
    listed = client.get("/api/review")
    assert listed.status_code == 200
    row = listed.json()["works"][0]
    assert row["review_reason"] == "no_payload"
    assert row["storage_path"].endswith("Christine - Stephen King.epub")
    assert row["folder_path"].endswith("Christine - Stephen King.epub")


def test_queue_review_job_includes_work_review_reason(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    db = app.state.db
    work = db.upsert_work(
        {
            "kind": "music",
            "title": "Guardians Mix",
            "review_state": "needs_review",
            "review_reason": "unknown_identity",
        }
    )
    db.create_job(
        {
            "status": "review",
            "work_id": work["id"],
            "title": "VA-Guardians Mix",
            "kind": "music",
            "nzo_id": "3ed43dc9-188e-48db-91ba-487a96bc7084",
        }
    )
    listed = client.get("/api/queue")
    assert listed.status_code == 200
    job = next(row for row in listed.json()["jobs"] if row["work_id"] == work["id"])
    assert job["status"] == "review"
    assert job["review_reason"] == "unknown_identity"
    assert job["review_state"] == "needs_review"


def test_review_apply_no_payload_is_400(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    db = app.state.db
    empty = tmp_path / "empty-release"
    empty.mkdir()
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Mystery",
            "review_state": "needs_review",
            "review_reason": "no_payload",
            "folder_path": str(empty),
        }
    )
    resp = client.post(
        f"/api/review/{work['id']}/apply",
        json={"title": "Mystery", "author": "Someone", "kind": "book", "folder": str(empty)},
    )
    assert resp.status_code == 400
    assert "cannot invent" in resp.json()["detail"]


def test_review_apply_identity_organizes(tmp_path, monkeypatch):
    settings = Settings(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "magazines"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "audiobooks"),
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
    )
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    folder = tmp_path / "complete" / "Mystery.Release"
    folder.mkdir(parents=True)
    (folder / "book.epub").write_bytes(b"epub")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Mystery",
            "review_state": "needs_review",
            "review_reason": "unknown_identity",
            "folder_path": str(folder),
        }
    )
    resp = client.post(
        f"/api/review/{work['id']}/apply",
        json={
            "title": "The Return of the King",
            "author": "J. R. R. Tolkien",
            "isbn": "9780000000000",
            "kind": "book",
            "folder": str(folder),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["organized"] is True
    stored = db.get_work(work["id"])
    assert stored["title"] == "The Return of the King"
    assert stored["review_state"] == "none"


def test_review_apply_collision_is_400_without_overwrite(tmp_path, monkeypatch):
    settings = Settings(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "magazines"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "audiobooks"),
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
    )
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    dest_dir = Path(settings.books_root) / "Le Guin" / "The Left Hand of Darkness"
    dest_dir.mkdir(parents=True)
    dest_file = dest_dir / "The Left Hand of Darkness.epub"
    dest_file.write_bytes(b"old")
    folder = tmp_path / "complete" / "fresh"
    folder.mkdir(parents=True)
    (folder / "book.epub").write_bytes(b"new")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": "9780441478125",
            "review_state": "needs_review",
            "review_reason": "collision",
            "folder_path": str(folder),
        }
    )
    resp = client.post(
        f"/api/review/{work['id']}/apply",
        json={
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": "9780441478125",
            "kind": "book",
            "folder": str(folder),
        },
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "already exists" in detail
    assert "will not overwrite" in detail.lower()
    assert dest_file.read_bytes() == b"old"
    assert (folder / "book.epub").read_bytes() == b"new"
    stored = db.get_work(work["id"])
    assert stored["review_state"] == "needs_review"
    assert stored["review_reason"] == "collision"


def test_review_list_links_shelf_work_on_collision(tmp_path, monkeypatch):
    settings = Settings(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "magazines"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "audiobooks"),
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
    )
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    shelf = db.upsert_work(
        {
            "kind": "book",
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": "9780441478125",
            "folder_path": str(Path(settings.books_root) / "Le Guin" / "The Left Hand of Darkness"),
            "review_state": "none",
        }
    )
    colliding = db.upsert_work(
        {
            "kind": "book",
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": "9780441478125",
            "folder_path": str(tmp_path / "complete" / "dup"),
            "review_state": "needs_review",
            "review_reason": "collision",
        }
    )
    listed = client.get("/api/review")
    assert listed.status_code == 200
    row = next(item for item in listed.json()["works"] if item["id"] == colliding["id"])
    assert row["review_reason"] == "collision"
    assert row["shelf_work"]["id"] == shelf["id"]
    assert row["shelf_work"]["title"] == "The Left Hand of Darkness"


def test_review_skip_keeps_shelf_and_dismisses(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    db = app.state.db
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "To the Edge",
            "author": "Cindy Gerard",
            "isbn": "9780312990916",
            "review_state": "needs_review",
            "review_reason": "collision",
            "folder_path": "/data/media/books/Cindy Gerard/To the Edge (1216)",
        }
    )
    resp = client.post(f"/api/review/{work['id']}/skip")
    assert resp.status_code == 200
    assert resp.json()["work"]["review_state"] == "resolved"
    assert client.get("/api/review").json()["works"] == []


def test_review_repair_endpoint_returns_diagnosis(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from librarian.convert import maybe_par2_repair, maybe_unpack_archives

    stuck = tmp_path / "complete" / "VA-Mix"
    stuck.mkdir(parents=True)
    (stuck / "mix.rar").write_bytes(b"Rar!")
    (stuck / "mix.par2").write_bytes(b"PAR2")
    settings = Settings(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "magazines"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "audiobooks"),
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
        complete_root=str(tmp_path / "complete"),
    )
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    work = db.upsert_work(
        {
            "kind": "music",
            "title": "Awesome Mix",
            "author": "Various Artists",
            "review_state": "needs_review",
            "review_reason": "unpack_stuck",
            "folder_path": str(stuck),
        }
    )
    calls = []

    def runner(argv, timeout=120):
        calls.append(list(argv))
        if len(argv) >= 2 and argv[1] == "r":
            return SimpleNamespace(returncode=0)
        (stuck / "01 Track.flac").write_bytes(b"flac")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(
        "librarian.organize.maybe_par2_repair",
        lambda folder, **kw: maybe_par2_repair(folder, runner=runner, par2="/usr/bin/par2"),
    )
    monkeypatch.setattr(
        "librarian.organize.maybe_unpack_archives",
        lambda folder, **kw: maybe_unpack_archives(folder, runner=runner, unar="/usr/bin/unar"),
    )

    resp = client.post(f"/api/review/{work['id']}/repair")
    assert resp.status_code == 200
    body = resp.json()
    assert body["repaired"]["repaired"] is True
    assert body["unpacked"]["unpacked"] is True
    assert body["folder_diagnosis"]["problem"] is None
    assert body["work"]["review_reason"] == "unknown_identity"
    assert body["actions"]["can_repair"] is False
    assert any(call[:2] == ["/usr/bin/par2", "r"] for call in calls)
    assert any(call[0] == "/usr/bin/unar" for call in calls)


def test_review_retry_force_organizes_after_payload(tmp_path, monkeypatch):
    settings = Settings(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "magazines"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "audiobooks"),
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
    )
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    folder = tmp_path / "complete" / "Mystery.Release"
    folder.mkdir(parents=True)
    (folder / "book.epub").write_bytes(b"epub")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "The Return of the King",
            "author": "J. R. R. Tolkien",
            "isbn": "9780000000000",
            "review_state": "needs_review",
            "review_reason": "unknown_identity",
            "folder_path": str(folder),
        }
    )
    resp = client.post(f"/api/review/{work['id']}/retry")
    assert resp.status_code == 200
    body = resp.json()
    assert body["organized"] is True
    stored = db.get_work(work["id"])
    assert stored["review_state"] == "none"
    assert stored["title"] == "The Return of the King"


def test_review_suggest_fail_closed_without_llm(tmp_path, monkeypatch):
    settings = Settings(
        books_root=str(tmp_path / "books"),
        complete_root=str(tmp_path / "usenet" / "complete"),
        llm_base_url="",
        llm_api_key="",
    )
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    work = db.upsert_work(
        {
            "kind": "audiobook",
            "title": "102.Minutes.The.Untold.Story.Audio.book",
            "author": "",
            "review_state": "needs_review",
            "review_reason": "unknown_identity",
            "folder_path": str(tmp_path / "missing"),
        }
    )
    response = client.post(f"/api/review/{work['id']}/suggest")
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is False
    assert body["suggestion"] is None
    assert "BYO LLM" in body["note"]


def test_review_suggest_prefills_from_mocked_llm(tmp_path, monkeypatch):
    import httpx

    from librarian.llm import LLMClient
    from librarian.organize import suggest_review_identity

    folder = tmp_path / "usenet" / "complete" / "102.Minutes.Dump"
    folder.mkdir(parents=True)
    (folder / "01.mp3").write_bytes(b"ID3")
    settings = Settings(
        books_root=str(tmp_path / "books"),
        audiobooks_root=str(tmp_path / "audiobooks"),
        complete_root=str(tmp_path / "usenet" / "complete"),
        llm_base_url="http://llm.example/v1",
        llm_api_key="k",
        llm_model="gpt-test",
    )
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    work = db.upsert_work(
        {
            "kind": "audiobook",
            "title": "102.Minutes.The.Untold.Story.of.the.Fight.to.Survive.Inside.the.Twin.Towers.Audio.book",
            "author": "",
            "review_state": "needs_review",
            "review_reason": "unknown_identity",
            "folder_path": str(folder),
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"kind":"audiobook","title":"102 Minutes",'
                                '"author_or_artist":"Jim Dwyer","series":null,'
                                '"isbn":"9780805076820","confidence":0.91,'
                                '"rationale":"famous title"}'
                            )
                        }
                    }
                ]
            },
        )

    llm = LLMClient("http://llm.example/v1", "k", "gpt-test", transport=httpx.MockTransport(handler))
    result = suggest_review_identity(db, settings, work_id=work["id"], llm_client=llm)
    assert result["configured"] is True
    assert result["auto_apply"] is False
    assert result["suggestion"]["title"] == "102 Minutes"
    assert result["suggestion"]["author"] == "Jim Dwyer"
    assert result["suggestion"]["kind"] == "audiobook"
    assert "isbn" not in result["suggestion"]

    listed = client.get("/api/review")
    assert listed.status_code == 200
    row = next(w for w in listed.json()["works"] if w["id"] == work["id"])
    assert row["actions"]["llm_configured"] is True
    assert row["actions"]["needs_llm_suggest"] is True
    assert row["actions"]["can_suggest_llm"] is True


def test_review_extra_files_hides_retry_and_repair(tmp_path, monkeypatch):
    folder = tmp_path / "complete" / "Camino"
    folder.mkdir(parents=True)
    (folder / "Camino Ghosts.epub").write_bytes(b"epub")
    (folder / "Camino Ghosts.mobi").write_bytes(b"mobi")
    settings = Settings(
        books_root=str(tmp_path / "books"),
        complete_root=str(tmp_path / "complete"),
    )
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Camino Ghosts",
            "author": "John Grisham",
            "isbn": "9788835735151",
            "review_state": "needs_review",
            "review_reason": "extra_files",
            "folder_path": str(folder),
        }
    )
    listed = client.get("/api/review")
    assert listed.status_code == 200
    row = next(w for w in listed.json()["works"] if w["id"] == work["id"])
    assert row["actions"]["can_repair"] is False
    assert row["actions"]["can_retry"] is False


def test_review_reprocess_extra_files_splits_calibre_author(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    settings = Settings(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "magazines"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "audiobooks"),
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
        complete_root=str(tmp_path / "complete"),
    )
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    author = tmp_path / "media" / "newlib" / "Abby Jimenez"
    t1 = author / "Just for the Summer (10103)"
    t2 = author / "Yours Truly (983)"
    for folder, title, isbn in (
        (t1, "Just for the Summer", "9781538704448"),
        (t2, "Yours Truly", "9781538704431"),
    ):
        folder.mkdir(parents=True)
        (folder / f"{title} - Abby Jimenez.epub").write_bytes(b"epub")
        (folder / f"{title} - Abby Jimenez.azw3").write_bytes(b"azw3")
        (folder / "metadata.opf").write_text(
            f"""<?xml version='1.0'?>
<package><metadata>
<dc:title xmlns:dc="http://purl.org/dc/elements/1.1/">{title}</dc:title>
<dc:creator xmlns:dc="http://purl.org/dc/elements/1.1/">Abby Jimenez</dc:creator>
<dc:identifier xmlns:dc="http://purl.org/dc/elements/1.1/" opf:scheme="ISBN" xmlns:opf="http://www.idpf.org/2007/opf">{isbn}</dc:identifier>
</metadata></package>""",
            encoding="utf-8",
        )
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Just for the Summer",
            "author": "Abby Jimenez",
            "isbn": "9781538704448",
            "review_state": "needs_review",
            "review_reason": "extra_files",
            "folder_path": str(author),
        }
    )
    resp = client.post("/api/review/reprocess-extra-files")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kicked_off"] is True
    assert body["status"] in ("running", "completed")
    status = _wait_extra_files_reprocess_status(client)
    assert status["status"] == "completed"
    result = status.get("result") or {}
    assert int(result.get("split") or status.get("split") or 0) == 1
    assert int(result.get("considered") or status.get("total") or 0) == 1
    assert int(result.get("shelved") or status.get("shelved") or 0) >= 1
    refreshed = db.get_work(work["id"])
    assert refreshed["review_state"] == "resolved"
    remaining = db.list_works(review_state="needs_review", limit=50)
    assert all(str(row.get("folder_path") or "").rstrip("/") != str(author) for row in remaining)


def test_review_reprocess_extra_files_status_idle(tmp_path, monkeypatch):
    client, _app = _client(tmp_path, monkeypatch)
    idle = client.get("/api/review/reprocess-extra-files/status")
    assert idle.status_code == 200
    body = idle.json()
    assert body["status"] == "idle"
    assert body["done"] == 0
    assert body["total"] == 0
    assert body["extra_files_remaining"] == 0


def test_review_list_reports_extra_files_backlog_beyond_page(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    db = app.state.db
    for index in range(3):
        db.upsert_work(
            {
                "kind": "book",
                "title": f"Extra File {index}",
                "author": "Anon",
                "review_state": "needs_review",
                "review_reason": "extra_files",
                "folder_path": str(tmp_path / f"extra-{index}"),
            }
        )
    db.upsert_work(
        {
            "kind": "book",
            "title": "Steel Me Away",
            "author": "Vivian Lux",
            "review_state": "needs_review",
            "review_reason": "low_confidence",
            "folder_path": str(tmp_path / "steel"),
        }
    )
    resp = client.get("/api/review")
    assert resp.status_code == 200
    body = resp.json()
    assert body["extra_files_count"] == 3
    status = client.get("/api/review/reprocess-extra-files/status")
    assert status.status_code == 200
    assert status.json()["extra_files_remaining"] == 3


def test_review_reprocess_extra_files_applies_multiformat_volume(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    settings = Settings(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "magazines"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "audiobooks"),
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
    )
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    folder = tmp_path / "complete" / "You.Like.It.Darker"
    folder.mkdir(parents=True)
    for name in ("You Like It Darker.epub", "You Like It Darker.mobi", "You Like It Darker.azw3"):
        (folder / name).write_bytes(b"book")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "You Like It Darker",
            "author": "Stephen King",
            "isbn": "9781668037737",
            "review_state": "needs_review",
            "review_reason": "extra_files",
            "folder_path": str(folder),
        }
    )
    resp = client.post(f"/api/review/{work['id']}/reprocess-extra-files")
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "apply"
    assert body["organized"] is True
    refreshed = db.get_work(work["id"])
    assert refreshed["review_state"] == "none"
    assert refreshed["review_reason"] is None
