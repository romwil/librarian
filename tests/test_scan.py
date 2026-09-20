from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.identify import REVIEW_COLLISION
from librarian.metadata import write_comicinfo, write_opf
from librarian.organize import organize_identified
from librarian.rate_limit import clear_rate_limits
from librarian.scan import identity_from_library_folder, scan_library
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "magazines"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "audiobooks"),
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
        nzbfinder_api_token="",
        sabnzbd_api_key="",
    )


def _flac_with_tags(path: Path, tags: dict[str, str]) -> None:
    comments = []
    for key, value in tags.items():
        raw = f"{key}={value}".encode("utf-8")
        comments.append(len(raw).to_bytes(4, "little") + raw)
    vendor = b"librarian"
    body = len(vendor).to_bytes(4, "little") + vendor
    body += len(comments).to_bytes(4, "little") + b"".join(comments)
    header = bytes([0x80 | 4]) + len(body).to_bytes(3, "big")
    path.write_bytes(b"fLaC" + header + body)


def _book_tree(root: Path) -> Path:
    folder = root / "Le Guin" / "The Left Hand of Darkness"
    folder.mkdir(parents=True)
    (folder / "The Left Hand of Darkness.epub").write_bytes(b"epub")
    write_opf(
        folder,
        {
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": "9780441478125",
            "year": 1969,
        },
    )
    return folder


def _comic_tree(root: Path) -> Path:
    folder = root / "Saga" / "1"
    folder.mkdir(parents=True)
    cbz = folder / "Saga #1.cbz"
    with ZipFile(cbz, "w") as archive:
        archive.writestr("page-01.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 80)
    write_comicinfo(
        folder,
        {
            "title": "Saga #1",
            "series_name": "Saga",
            "series_index": "1",
            "author": "Vaughan",
            "year": 2012,
        },
    )
    return folder


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    clear_rate_limits()
    return TestClient(create_app(tmp_path))


def test_scan_book_comic_and_incoming_flacs(tmp_path):
    settings = _settings(tmp_path)
    book = _book_tree(Path(settings.books_root))
    comic = _comic_tree(Path(settings.comics_root))
    incoming = Path(settings.incoming_music_root) / "Miles Davis" / "Kind of Blue"
    incoming.mkdir(parents=True)
    track = incoming / "01 So What.flac"
    _flac_with_tags(track, {"ARTIST": "Miles Davis", "ALBUM": "Kind of Blue", "DATE": "1959"})
    promoted = Path(settings.music_root) / "Radiohead" / "In Rainbows"
    promoted.mkdir(parents=True)
    (promoted / "01 15 Step.flac").write_bytes(b"flac")

    db = Database(tmp_path / "librarian.db")
    counts = scan_library(db, settings)
    assert counts["scanned"] == 4
    assert counts["created"] == 4
    assert counts["updated"] == 0
    assert counts["review"] == 0

    book_work = next(row for row in db.list_works(kind="book", limit=8))
    assert book_work["title"] == "The Left Hand of Darkness"
    assert book_work["author"] == "Le Guin"
    assert book_work["isbn"] == "9780441478125"
    assert book_work["folder_path"] == str(book)
    assert book_work["review_state"] == "none"
    book_files = db.files_for_work(book_work["id"])
    assert [Path(row["path"]).name for row in book_files] == ["The Left Hand of Darkness.epub"]
    assert Path(book_files[0]["path"]).is_file()

    comic_work = next(row for row in db.list_works(kind="comic", limit=8))
    assert comic_work["series_name"] == "Saga"
    assert comic_work["series_index"] == "1"
    assert comic_work["title"] == "Saga #1"
    assert comic_work["folder_path"] == str(comic)

    incoming_work = next(row for row in db.list_works(kind="music", music_state="incoming", limit=8))
    assert incoming_work["title"] == "Kind of Blue"
    assert incoming_work["author"] == "Miles Davis"
    assert incoming_work["music_state"] == "incoming"
    assert incoming_work["year"] == 1959

    promoted_work = next(row for row in db.list_works(kind="music", music_state="promoted", limit=8))
    assert promoted_work["title"] == "In Rainbows"
    assert promoted_work["music_state"] == "promoted"
    assert promoted_work["author"] == "Radiohead"

    again = scan_library(db, settings)
    assert again["scanned"] == 4
    assert again["created"] == 0
    assert again["updated"] == 4
    assert again["review"] == 0
    assert len(db.list_works(limit=20)) == 4
    assert len(db.files_for_work(book_work["id"])) == 1
    assert (book / "The Left Hand of Darkness.epub").read_bytes() == b"epub"


def test_scan_collision_goes_to_review_without_moving(tmp_path):
    settings = _settings(tmp_path)
    first = _book_tree(Path(settings.books_root))
    second = Path(settings.books_root) / "Ursula K. Le Guin" / "Left Hand"
    second.mkdir(parents=True)
    (second / "copy.epub").write_bytes(b"other")
    write_opf(
        second,
        {
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": "9780441478125",
        },
    )
    db = Database(tmp_path / "librarian.db")
    counts = scan_library(db, settings)
    assert counts["scanned"] == 2
    assert counts["created"] == 2
    assert counts["review"] == 1
    works = db.list_works(kind="book", limit=8)
    by_folder = {row["folder_path"]: row for row in works}
    assert by_folder[str(first)]["review_state"] == "none"
    colliding = by_folder[str(second)]
    assert colliding["review_state"] == "needs_review"
    assert colliding["review_reason"] == REVIEW_COLLISION
    assert (second / "copy.epub").is_file()
    assert (first / "The Left Hand of Darkness.epub").is_file()

    again = scan_library(db, settings)
    assert again["created"] == 0
    assert again["updated"] == 2
    assert again["review"] == 1
    assert len(db.list_works(kind="book", limit=8)) == 2


def test_scan_pdf_on_shelf_is_not_sab_convert_review(tmp_path):
    settings = _settings(tmp_path)
    folder = Path(settings.books_root) / "Herbert" / "Dune"
    folder.mkdir(parents=True)
    (folder / "Dune.pdf").write_bytes(b"%PDF")
    db = Database(tmp_path / "librarian.db")
    counts = scan_library(db, settings)
    assert counts["created"] == 1
    assert counts["review"] == 0
    work = db.list_works(kind="book", limit=1)[0]
    assert work["title"] == "Dune"
    assert work["author"] == "Herbert"
    assert work["review_state"] == "none"


def test_scan_is_idempotent_with_organized_work(tmp_path):
    settings = _settings(tmp_path)
    complete = tmp_path / "complete" / "Le Guin - The Left Hand of Darkness 9780441478125"
    complete.mkdir(parents=True)
    (complete / "book.epub").write_bytes(b"epub")
    db = Database(tmp_path / "librarian.db")
    result = organize_identified(
        db,
        settings,
        folder=complete,
        indexer_item={
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": "9780441478125",
            "category": 7020,
            "guid": "guid-scan",
            "name": complete.name,
        },
    )
    assert result["organized"] is True
    dest = Path(result["files"][0])
    assert dest.is_file()
    counts = scan_library(db, settings)
    assert counts["created"] == 0
    assert counts["updated"] == 1
    assert len(db.list_works(kind="book", limit=8)) == 1
    assert len(db.files_for_work(result["work"]["id"])) == 1


def test_identity_from_library_folder_uses_layout(tmp_path):
    root = tmp_path / "comics"
    folder = root / "Monstress" / "12"
    folder.mkdir(parents=True)
    cbz = folder / "Monstress #12.cbz"
    cbz.write_bytes(b"cbz")
    identity = identity_from_library_folder("comic", folder, [cbz], root=root)
    assert identity["series_name"] == "Monstress"
    assert identity["series_index"] == "12"
    assert identity["kind"] == "comic"


def test_scan_empty_roots(tmp_path):
    db = Database(tmp_path / "librarian.db")
    counts = scan_library(db, _settings(tmp_path))
    assert counts == {
        "scanned": 0,
        "created": 0,
        "updated": 0,
        "review": 0,
        "skipped": 0,
        "errors": 0,
    }


def _wait_scan_status(client, *, timeout=5.0):
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get("/api/settings/scan/status")
        assert resp.status_code == 200
        body = resp.json()
        if body.get("status") in ("completed", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError("scan did not finish")


def test_scan_api_owner_without_indexer(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    _book_tree(Path(settings.books_root))
    save_settings(tmp_path, settings)
    client = _client(tmp_path, monkeypatch)
    login = client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    assert login.status_code == 200
    idle = client.get("/api/settings/scan/status")
    assert idle.status_code == 200
    assert idle.json()["status"] == "idle"
    resp = client.post("/api/settings/scan")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kicked_off"] is True
    assert body["status"] in ("running", "completed")
    status = _wait_scan_status(client)
    assert status["status"] == "completed"
    result = status.get("result") or {}
    assert int(result.get("scanned") or status.get("done") or 0) == 1
    assert int(result.get("created") or status.get("created") or 0) == 1
    assert int(result.get("updated") or status.get("updated") or 0) == 0
    assert int(result.get("review") or status.get("review") or 0) == 0
    hall = client.get("/api/hall")
    assert hall.status_code == 200
    titles = [row["title"] for row in hall.json()["areas"]["books"]]
    assert "The Left Hand of Darkness" in titles


def test_scan_api_op_and_reader_forbidden(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    op_token = client.post("/api/invites", json={"role": "op"}).json()["token"]
    reader_token = client.post("/api/invites", json={"role": "reader"}).json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert (
        client.post(
            "/api/invites/redeem/local",
            json={"token": op_token, "username": "ops", "password": "password123"},
        ).status_code
        == 200
    )
    assert client.post("/api/settings/scan").status_code == 403
    assert client.get("/api/settings/scan/status").status_code == 403
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert (
        client.post(
            "/api/invites/redeem/local",
            json={"token": reader_token, "username": "reader1", "password": "password123"},
        ).status_code
        == 200
    )
    assert client.post("/api/settings/scan").status_code == 403
    assert client.get("/api/settings/scan/status").status_code == 403
    assert client.get("/api/settings").status_code == 403


def test_scan_reports_progress_and_continues_after_folder_error(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    _book_tree(Path(settings.books_root))
    bad = Path(settings.comics_root) / "Broken" / "1"
    bad.mkdir(parents=True)
    (bad / "Broken #1.cbz").write_bytes(b"cbz")

    ticks: list[dict] = []

    class Recorder:
        def start(self, *, total: int, phase: str = "scanning") -> None:
            ticks.append({"event": "start", "total": total, "phase": phase})

        def log(self, line: str) -> None:
            ticks.append({"event": "log", "line": line})

        def tick(self, **fields) -> None:
            ticks.append({"event": "tick", **fields})

        def complete(self, result) -> None:
            ticks.append({"event": "complete", "result": dict(result)})

        def fail(self, error: str) -> None:
            ticks.append({"event": "fail", "error": error})

    import librarian.scan as scan_mod

    real = scan_mod._ingest_folder

    def sometimes(db, **kwargs):
        if kwargs.get("kind") == "comic":
            raise OSError("disk hiccup")
        return real(db, **kwargs)

    monkeypatch.setattr(scan_mod, "_ingest_folder", sometimes)

    db = Database(tmp_path / "librarian.db")
    counts = scan_library(db, settings, progress=Recorder())
    assert counts["scanned"] == 2
    assert counts["created"] == 1
    assert counts["errors"] == 1
    assert any(t.get("event") == "complete" for t in ticks)
    assert any(t.get("event") == "tick" and t.get("errors") == 1 for t in ticks)
    works = db.list_works(kind="book", limit=10)
    assert any(row["title"] == "The Left Hand of Darkness" for row in works)
