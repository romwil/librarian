"""Value-based tests for quiet ingest preview map (stems / twins / kinds)."""

from pathlib import Path

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.ingest_preview import (
    PREVIEW_VOLUME_CAP,
    build_ingest_preview,
    ingest_preview_presence,
    kind_label,
    preview_for_path,
)
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


def test_presence_uses_words_not_kpi():
    assert ingest_preview_presence(volumes_found=0, twins=0) == (
        "Nothing to shelve here — empty or only junk."
    )
    assert ingest_preview_presence(volumes_found=1, twins=0) == "One volume waits on the map."
    assert "Two volumes" in ingest_preview_presence(volumes_found=2, twins=0)
    assert "one twin" in ingest_preview_presence(volumes_found=3, twins=1)
    assert "Mostly books" in ingest_preview_presence(
        volumes_found=4, twins=0, kinds={"book": 4}
    )


def test_kind_label_warm():
    assert kind_label("book") == "Book"
    assert kind_label("") == "Unknown"
    assert kind_label("comic") == "Comic"


def test_build_preview_maps_stems_twins_kinds(tmp_path):
    parent = tmp_path / "inbox" / "dump"
    book_a = parent / "Le Guin - Left Hand"
    book_b = parent / "twin-Left-Hand"
    comic = parent / "Sandman 01"
    book_a.mkdir(parents=True)
    book_b.mkdir()
    comic.mkdir()
    payload = b"identical-epub-bytes"
    (book_a / "Left Hand.epub").write_bytes(payload)
    (book_b / "Left Hand.epub").write_bytes(payload)
    (comic / "Sandman #01.cbz").write_bytes(b"cbz-bytes")

    preview = build_ingest_preview([parent])
    assert preview["volumes_found"] == 3
    assert preview["files_found"] == 3
    assert preview["twins"] == 1
    assert preview["empty"] is False
    assert preview["kinds"].get("book") == 2
    assert preview["kinds"].get("comic") == 1
    assert "twin" in preview["presence"].lower() or "twins" in preview["presence"].lower()
    stems = {row["stem"] for row in preview["volumes"]}
    assert any("Left Hand" in s or "Le Guin" in s for s in stems)
    twin_rows = [row for row in preview["volumes"] if row["twin"]]
    assert len(twin_rows) == 1
    assert twin_rows[0]["role"] == "twin"
    assert twin_rows[0]["breathing"] is True


def test_preview_does_not_write_works(tmp_path):
    dump = tmp_path / "inbox" / "solo"
    dump.mkdir(parents=True)
    (dump / "Mystery.epub").write_bytes(b"epub")
    db = Database(tmp_path / "librarian.db")
    before = len(db.list_works())
    preview = preview_for_path(dump)
    assert preview["volumes_found"] == 1
    assert len(db.list_works()) == before


def test_preview_empty_folder(tmp_path):
    empty = tmp_path / "inbox" / "empty"
    empty.mkdir(parents=True)
    preview = preview_for_path(empty)
    assert preview["empty"] is True
    assert preview["volumes_found"] == 0
    assert "Nothing to shelve" in preview["presence"]


def test_preview_truncates_huge_dumps(tmp_path, monkeypatch):
    parent = tmp_path / "inbox" / "huge"
    parent.mkdir(parents=True)
    for i in range(PREVIEW_VOLUME_CAP + 5):
        folder = parent / f"Title {i:03d}"
        folder.mkdir()
        (folder / f"Title {i:03d}.epub").write_bytes(f"epub-{i}".encode())
    preview = build_ingest_preview([parent])
    assert preview["volumes_found"] == PREVIEW_VOLUME_CAP + 5
    assert len(preview["volumes"]) == PREVIEW_VOLUME_CAP
    assert preview["truncated"] is True


def test_api_ingest_preview_owner_only(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    save_settings(tmp_path, settings)
    dump = tmp_path / "inbox" / "preview-me"
    dump.mkdir(parents=True)
    (dump / "Dune.epub").write_bytes(b"epub")
    client = _client(tmp_path, monkeypatch)
    _login(client)

    outside = client.post("/api/ingest/preview", json={"path": "/etc"})
    assert outside.status_code == 400

    books = Path(settings.books_root)
    books.mkdir(parents=True)
    refused = client.post("/api/ingest/preview", json={"path": str(books)})
    assert refused.status_code == 400

    ok = client.post("/api/ingest/preview", json={"path": str(dump)})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["volumes_found"] == 1
    assert body["volumes"][0]["kind"] == "book"
    assert "presence" in body

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
    assert client.post("/api/ingest/preview", json={"path": str(dump)}).status_code == 403
