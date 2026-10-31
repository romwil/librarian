"""PRIV-012: /api/fs lists configured roots, not all of /data."""

from pathlib import Path

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.ingest import fs_browse_roots, list_dir
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


def test_empty_listing_is_configured_roots_not_photos(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    books = tmp_path / "books"
    photos = tmp_path / "photos"
    inbox = tmp_path / "inbox"
    books.mkdir()
    photos.mkdir()
    inbox.mkdir()
    (photos / "family.jpg").write_bytes(b"jpg")
    settings = _settings(tmp_path, watch_root=str(inbox))
    listed = list_dir("", settings=settings)
    names = {row["name"] for row in listed["entries"]}
    assert "books" in names
    assert "inbox" in names
    assert "photos" not in names
    assert listed["parent"] is None


def test_photos_path_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    books = tmp_path / "books"
    photos = tmp_path / "photos"
    books.mkdir()
    photos.mkdir()
    save_settings(tmp_path, _settings(tmp_path))
    client = _client(tmp_path, monkeypatch)
    assert client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"}).status_code == 200
    denied = client.get("/api/fs", params={"path": str(photos)})
    assert denied.status_code == 400
    assert "outside" in denied.json()["detail"].lower()
    ok = client.get("/api/fs", params={"path": str(books)})
    assert ok.status_code == 200
    assert ok.json()["path"] == str(books)
    assert ok.json()["parent"] is None


def test_browse_roots_include_watch_and_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    watch = tmp_path / "inbox"
    complete = tmp_path / "usenet" / "complete"
    watch.mkdir()
    complete.mkdir(parents=True)
    settings = _settings(tmp_path, watch_root=str(watch), complete_root=str(complete))
    roots = {path.name for path in fs_browse_roots(settings)}
    assert "inbox" in roots
    assert "complete" in roots
    assert "books" in roots
