import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from librarian.db import Database
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    clear_rate_limits()
    return TestClient(create_app(tmp_path))


def _login(client, username="owner", password="password123"):
    resp = client.post("/api/auth/local/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp


def test_download_requires_auth_and_404s_when_missing(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/api/works/missing/download").status_code == 401
    _login(client)
    missing = client.get("/api/works/missing/download")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Work not found"
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work({"kind": "book", "title": "Dune", "author": "Herbert"})
    empty = client.get(f"/api/works/{work['id']}/download")
    assert empty.status_code == 404
    assert empty.json()["detail"] == "File missing"


def test_download_serves_primary_file_and_inline_audio(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    folder = tmp_path / "incoming" / "Mix"
    folder.mkdir(parents=True)
    flac = folder / "01-mr_blue_sky.flac"
    flac.write_bytes(b"fLaCfake")
    work = db.upsert_work(
        {
            "kind": "music",
            "title": "Awesome Mix Vol. 2",
            "author": "Various Artists",
            "music_state": "incoming",
            "folder_path": str(folder),
        }
    )
    db.add_file({"work_id": work["id"], "path": str(flac), "filename": flac.name, "kind": "music", "size": 8})
    detail = client.get(f"/api/works/{work['id']}")
    assert detail.status_code == 200
    assert detail.json()["can_download"] is True
    assert detail.json()["file_count"] == 1
    assert detail.json()["can_read"] is False
    attachment = client.get(f"/api/works/{work['id']}/download")
    assert attachment.status_code == 200
    assert attachment.content == b"fLaCfake"
    assert "attachment" in (attachment.headers.get("content-disposition") or "")
    assert "01-mr_blue_sky.flac" in (attachment.headers.get("content-disposition") or "")
    inline = client.get(f"/api/works/{work['id']}/download", params={"inline": 1})
    assert inline.status_code == 200
    assert "inline" in (inline.headers.get("content-disposition") or "")
    assert inline.headers.get("content-type", "").startswith("audio/")


def test_download_zips_album_when_multiple_files(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    folder = tmp_path / "incoming" / "Mix"
    folder.mkdir(parents=True)
    one = folder / "01-a.flac"
    two = folder / "02-b.flac"
    one.write_bytes(b"one")
    two.write_bytes(b"two")
    work = db.upsert_work(
        {
            "kind": "music",
            "title": "Awesome Mix Vol. 2",
            "music_state": "incoming",
            "folder_path": str(folder),
        }
    )
    db.add_file({"work_id": work["id"], "path": str(one), "filename": one.name, "kind": "music"})
    db.add_file({"work_id": work["id"], "path": str(two), "filename": two.name, "kind": "music"})
    resp = client.get(f"/api/works/{work['id']}/download")
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("application/zip")
    disposition = resp.headers.get("content-disposition") or ""
    assert disposition.startswith("attachment")
    assert "Awesome" in disposition and ".zip" in disposition
    names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
    assert names == ["01-a.flac", "02-b.flac"]
    opened = client.get(f"/api/works/{work['id']}/download", params={"inline": 1})
    assert opened.status_code == 200
    assert opened.content == b"one"


def test_stream_serves_single_album_track_and_refuses_non_audio(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/api/works/missing/stream", params={"file": "x"}).status_code == 401
    _login(client)
    db = Database(tmp_path / "librarian.db")
    folder = tmp_path / "incoming" / "Mix"
    folder.mkdir(parents=True)
    one = folder / "01-a.flac"
    two = folder / "02-b.mp3"
    note = folder / "liner.pdf"
    one.write_bytes(b"one")
    two.write_bytes(b"two")
    note.write_bytes(b"%PDF")
    work = db.upsert_work(
        {
            "kind": "music",
            "title": "Awesome Mix Vol. 2",
            "music_state": "incoming",
            "folder_path": str(folder),
        }
    )
    row_one = db.add_file({"work_id": work["id"], "path": str(one), "filename": one.name, "kind": "music"})
    row_two = db.add_file({"work_id": work["id"], "path": str(two), "filename": two.name, "kind": "music"})
    row_note = db.add_file({"work_id": work["id"], "path": str(note), "filename": note.name, "kind": "music"})
    first = client.get(f"/api/works/{work['id']}/stream", params={"file": row_one["id"]})
    assert first.status_code == 200
    assert first.content == b"one"
    assert first.headers.get("content-type", "").startswith("audio/")
    assert "inline" in (first.headers.get("content-disposition") or "")
    second = client.get(f"/api/works/{work['id']}/stream", params={"file": row_two["id"]})
    assert second.status_code == 200
    assert second.content == b"two"
    refused = client.get(f"/api/works/{work['id']}/stream", params={"file": row_note["id"]})
    assert refused.status_code == 422
    assert "streamable audio" in refused.json()["detail"]
    missing = client.get(f"/api/works/{work['id']}/stream", params={"file": "nope"})
    assert missing.status_code == 404
    # Per-file download still works; album zip is separate from stream.
    attachment = client.get(f"/api/works/{work['id']}/download", params={"file": row_two["id"]})
    assert attachment.status_code == 200
    assert attachment.content == b"two"
    assert "attachment" in (attachment.headers.get("content-disposition") or "")


def test_reader_can_download(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    minted = client.post("/api/invites", json={"role": "reader"})
    token = minted.json()["token"]
    db = Database(tmp_path / "librarian.db")
    epub = tmp_path / "Dune.epub"
    epub.write_bytes(b"epub-bytes")
    work = db.upsert_work({"kind": "book", "title": "Dune", "author": "Herbert", "folder_path": str(tmp_path)})
    db.add_file({"work_id": work["id"], "path": str(epub), "filename": epub.name, "kind": "book"})
    client.post("/api/auth/logout")
    client.cookies.clear()
    redeemed = client.post(
        "/api/invites/redeem/local",
        json={"token": token, "username": "reader1", "password": "password123"},
    )
    assert redeemed.status_code == 200
    resp = client.get(f"/api/works/{work['id']}/download")
    assert resp.status_code == 200
    assert resp.content == b"epub-bytes"
    assert resp.headers.get("content-type", "").startswith("application/epub+zip")
    detail = client.get(f"/api/works/{work['id']}")
    assert detail.json()["can_read"] is True


def test_inline_open_serves_magazine_pdf_not_cover(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    folder = tmp_path / "magazines" / "Linux Magazine" / "2026-10"
    folder.mkdir(parents=True)
    cover = folder / "cover.jpg"
    pdf = folder / "Linux Magazine 2026-10.pdf"
    cover.write_bytes(b"jpeg-bytes")
    pdf.write_bytes(b"%PDF-fake")
    work = db.upsert_work(
        {
            "kind": "magazine",
            "title": "Linux Magazine 2026-10",
            "folder_path": str(folder),
        }
    )
    db.add_file({"work_id": work["id"], "path": str(cover), "filename": cover.name, "kind": "magazine"})
    db.add_file({"work_id": work["id"], "path": str(pdf), "filename": pdf.name, "kind": "magazine"})
    detail = client.get(f"/api/works/{work['id']}")
    assert detail.json()["can_read"] is True
    assert detail.json()["can_download"] is True
    inline = client.get(f"/api/works/{work['id']}/download", params={"inline": 1})
    assert inline.status_code == 200
    assert inline.content == b"%PDF-fake"
    assert inline.headers.get("content-type", "").startswith("application/pdf")
    assert "inline" in (inline.headers.get("content-disposition") or "")


def test_inline_reading_room_serves_epub_never_kindle_or_zip(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    folder = tmp_path / "books" / "Stephen King" / "Box Set"
    folder.mkdir(parents=True)
    azw3 = folder / "Box Set.azw3"
    epub = folder / "Box Set.epub"
    cover = folder / "cover.jpg"
    azw3.write_bytes(b"AZW3-bytes")
    epub.write_bytes(b"PK\x03\x04epub")
    cover.write_bytes(b"jpeg")
    work = db.upsert_work(
        {"kind": "book", "title": "Box Set", "author": "Stephen King", "folder_path": str(folder)}
    )
    # Kindle first in DB — must not win for Reading Room.
    db.add_file({"work_id": work["id"], "path": str(azw3), "filename": azw3.name, "kind": "book"})
    db.add_file({"work_id": work["id"], "path": str(cover), "filename": cover.name, "kind": "book"})
    db.add_file({"work_id": work["id"], "path": str(epub), "filename": epub.name, "kind": "book"})
    detail = client.get(f"/api/works/{work['id']}")
    body = detail.json()
    assert body["can_read"] is True
    reading = [row for row in body["files"] if row.get("reading_room")]
    assert len(reading) == 1
    assert reading[0]["filename"] == "Box Set.epub"
    inline = client.get(f"/api/works/{work['id']}/download", params={"inline": 1})
    assert inline.status_code == 200
    assert inline.content == b"PK\x03\x04epub"
    assert inline.headers.get("content-type", "").startswith("application/epub+zip")
    assert "inline" in (inline.headers.get("content-disposition") or "")
    assert "Box%20Set.epub" in (inline.headers.get("content-disposition") or "") or "Box Set.epub" in (
        inline.headers.get("content-disposition") or ""
    )
    attachment = client.get(f"/api/works/{work['id']}/download")
    assert attachment.status_code == 200
    assert attachment.headers.get("content-type", "").startswith("application/zip")


def test_kindle_only_is_download_not_read(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    folder = tmp_path / "books" / "Author" / "Title"
    folder.mkdir(parents=True)
    azw3 = folder / "Title.azw3"
    azw3.write_bytes(b"AZW3-only")
    work = db.upsert_work(
        {"kind": "book", "title": "Title", "author": "Author", "folder_path": str(folder)}
    )
    db.add_file({"work_id": work["id"], "path": str(azw3), "filename": azw3.name, "kind": "book"})
    detail = client.get(f"/api/works/{work['id']}")
    body = detail.json()
    assert body["can_read"] is False
    assert body["can_download"] is True
    assert all(not row.get("reading_room") for row in body["files"])
    inline = client.get(f"/api/works/{work['id']}/download", params={"inline": 1})
    assert inline.status_code == 422
    assert "readable EPUB" in inline.json()["detail"]
    download = client.get(f"/api/works/{work['id']}/download")
    assert download.status_code == 200
    assert download.content == b"AZW3-only"


def test_stale_epub_path_does_not_enable_read(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    folder = tmp_path / "books" / "Author" / "Ghost"
    folder.mkdir(parents=True)
    azw3 = folder / "Ghost.azw3"
    missing = folder / "Ghost.epub"
    azw3.write_bytes(b"AZW3")
    work = db.upsert_work(
        {"kind": "book", "title": "Ghost", "author": "Author", "folder_path": str(folder)}
    )
    db.add_file({"work_id": work["id"], "path": str(missing), "filename": missing.name, "kind": "book"})
    db.add_file({"work_id": work["id"], "path": str(azw3), "filename": azw3.name, "kind": "book"})
    detail = client.get(f"/api/works/{work['id']}")
    body = detail.json()
    assert body["can_read"] is False
    assert body["can_download"] is True
    by_name = {row["filename"]: row for row in body["files"]}
    assert by_name["Ghost.epub"]["on_disk"] is False
    assert by_name["Ghost.azw3"]["on_disk"] is True
    inline = client.get(f"/api/works/{work['id']}/download", params={"inline": 1})
    assert inline.status_code == 422


def test_multi_pdf_magazine_opens_any_volume_by_file_id(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    folder = tmp_path / "magazines" / "Archive Historical"
    folder.mkdir(parents=True)
    vol1 = folder / "The Hacker Digest - Volume 01.pdf"
    vol2 = folder / "The Hacker Digest - Volume 02.pdf"
    vol1.write_bytes(b"%PDF-vol1")
    vol2.write_bytes(b"%PDF-vol2")
    work = db.upsert_work(
        {
            "kind": "magazine",
            "title": "Archive Historical",
            "folder_path": str(folder),
        }
    )
    one = db.add_file({"work_id": work["id"], "path": str(vol1), "filename": vol1.name, "kind": "magazine"})
    two = db.add_file({"work_id": work["id"], "path": str(vol2), "filename": vol2.name, "kind": "magazine"})
    detail = client.get(f"/api/works/{work['id']}")
    body = detail.json()
    assert body["can_read"] is True
    reading = [row for row in body["files"] if row.get("reading_room")]
    assert {row["filename"] for row in reading} == {vol1.name, vol2.name}

    primary = client.get(f"/api/works/{work['id']}/download", params={"inline": 1})
    assert primary.status_code == 200
    assert primary.content == b"%PDF-vol1"

    second = client.get(
        f"/api/works/{work['id']}/download",
        params={"inline": 1, "file": two["id"]},
    )
    assert second.status_code == 200
    assert second.content == b"%PDF-vol2"
    assert second.headers.get("content-type", "").startswith("application/pdf")
    assert "inline" in (second.headers.get("content-disposition") or "")

    attachment = client.get(f"/api/works/{work['id']}/download", params={"file": one["id"]})
    assert attachment.status_code == 200
    assert attachment.content == b"%PDF-vol1"
    assert "attachment" in (attachment.headers.get("content-disposition") or "")

    missing = client.get(
        f"/api/works/{work['id']}/download",
        params={"inline": 1, "file": "no-such-file"},
    )
    assert missing.status_code == 404


def test_inline_file_id_never_serves_kindle(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    folder = tmp_path / "books" / "Author" / "Mixed"
    folder.mkdir(parents=True)
    azw3 = folder / "Title.azw3"
    epub = folder / "Title.epub"
    azw3.write_bytes(b"AZW3-bytes")
    epub.write_bytes(b"PK\x03\x04epub")
    work = db.upsert_work(
        {"kind": "book", "title": "Title", "author": "Author", "folder_path": str(folder)}
    )
    kindle = db.add_file({"work_id": work["id"], "path": str(azw3), "filename": azw3.name, "kind": "book"})
    db.add_file({"work_id": work["id"], "path": str(epub), "filename": epub.name, "kind": "book"})
    inline = client.get(
        f"/api/works/{work['id']}/download",
        params={"inline": 1, "file": kindle["id"]},
    )
    assert inline.status_code == 422
    assert "readable EPUB" in inline.json()["detail"]
    download = client.get(f"/api/works/{work['id']}/download", params={"file": kindle["id"]})
    assert download.status_code == 200
    assert download.content == b"AZW3-bytes"


def test_cover_and_download_reject_paths_outside_fs_root(tmp_path, monkeypatch):
    """Poisoned cover_path / file rows outside the /data jail must 404."""
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    secret = Path("/etc/hosts")
    assert secret.is_file()
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Poisoned Cover",
            "author": "Nobody",
            "cover_path": str(secret),
        }
    )
    cover = client.get(f"/api/works/{work['id']}/cover")
    assert cover.status_code == 404
    assert cover.json()["detail"] == "Cover not found"

    leak = db.upsert_work({"kind": "book", "title": "Poisoned File", "author": "Nobody"})
    db.add_file(
        {
            "work_id": leak["id"],
            "path": str(secret),
            "filename": secret.name,
            "kind": "book",
            "size": secret.stat().st_size,
        }
    )
    missing = client.get(f"/api/works/{leak['id']}/download")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "File missing"


def test_cover_serves_owned_cache_under_data_dir(tmp_path, monkeypatch):
    """Cover cache under DATA_DIR/covers remains readable when media lives on /data."""
    fs_root = tmp_path / "data"
    config = tmp_path / "config"
    fs_root.mkdir()
    config.mkdir()
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(fs_root))
    monkeypatch.setenv("DATA_DIR", str(config))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    clear_rate_limits()
    client = TestClient(create_app(config))
    _login(client)
    db = Database(config / "librarian.db")
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 80
    work = db.upsert_work({"kind": "book", "title": "Cached Cover", "author": "Author"})
    cached = config / "covers" / work["id"] / "cover.jpg"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(jpeg)
    db.upsert_work({**work, "cover_path": str(cached)})
    resp = client.get(f"/api/works/{work['id']}/cover")
    assert resp.status_code == 200
    assert resp.content == jpeg
    # Settings under DATA_DIR must not be serveable via cover_path.
    settings_path = config / "settings.json"
    settings_path.write_text("{}")
    poisoned = db.upsert_work(
        {"kind": "book", "title": "Settings Leak", "author": "Nope", "cover_path": str(settings_path)}
    )
    assert client.get(f"/api/works/{poisoned['id']}/cover").status_code == 404
