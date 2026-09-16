import io
import zipfile

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
