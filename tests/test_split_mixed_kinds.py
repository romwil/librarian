"""Comic archive + ebook encoding mix detection and split repair."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.identify import (
    expand_organize_payload,
    identify_completed,
    ingest_targets_for_mixed_payload,
    is_mixed_comic_ebook_payload,
    partition_comic_ebook_files,
)
from librarian.ingest import list_ingest_targets
from librarian.sessions import clear_session_secret_cache
from librarian.split_mixed_kinds import (
    classify_mixed_kind_works,
    split_mixed_kind_work,
)
from librarian.web.app import create_app


def _book_settings(tmp_path):
    return Settings(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "magazines"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "audiobooks"),
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
        complete_root=str(tmp_path / "complete"),
    )


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


def _wait_status(client, *, timeout=8.0):
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        resp = client.get("/api/maintain/split-mixed-kinds/status")
        assert resp.status_code == 200
        last = resp.json()
        if last.get("status") in ("completed", "failed", "idle"):
            return last
        time.sleep(0.05)
    return last


def test_is_mixed_comic_ebook_payload_detects_blend(tmp_path):
    folder = tmp_path / "The Stand"
    folder.mkdir()
    cbz = folder / "The Stand #1990 (1990).cbz"
    epub = folder / "The Stand_ American Nightmares - Stephen King.epub"
    azw3 = folder / "The Stand_ American Nightmares - Stephen King.azw3"
    cbz.write_bytes(b"cbz")
    epub.write_bytes(b"epub")
    azw3.write_bytes(b"azw3")
    files = [cbz, epub, azw3]
    assert is_mixed_comic_ebook_payload(files) is True
    parts = partition_comic_ebook_files(files)
    assert len(parts["comic"]) == 1
    assert len(parts["book"]) == 2


def test_pdf_with_cbz_alone_is_not_mixed(tmp_path):
    folder = tmp_path / "issue"
    folder.mkdir()
    cbz = folder / "Saga #1.cbz"
    pdf = folder / "Saga #1.pdf"
    cbz.write_bytes(b"cbz")
    pdf.write_bytes(b"pdf")
    assert is_mixed_comic_ebook_payload([cbz, pdf]) is False


def test_identify_mixed_folder_stays_extra_files(tmp_path):
    folder = tmp_path / "The.Stand.Mix"
    folder.mkdir()
    (folder / "The Stand #1990 (1990).cbz").write_bytes(b"cbz")
    (folder / "The Stand_ American Nightmares - Stephen King.epub").write_bytes(b"epub")
    (folder / "The Stand_ American Nightmares - Stephen King.azw3").write_bytes(b"azw3")
    result = identify_completed(folder, category=7030)
    assert result["auto_organize"] is False
    assert result["identity"]["review_reason"] == "extra_files"


def test_ingest_targets_split_mixed_leaf_folder(tmp_path):
    folder = tmp_path / "dump" / "The Stand"
    folder.mkdir(parents=True)
    cbz = folder / "The Stand #1990 (1990).cbz"
    epub = folder / "The Stand_ American Nightmares - Stephen King.epub"
    azw3 = folder / "The Stand_ American Nightmares - Stephen King.azw3"
    cbz.write_bytes(b"cbz")
    epub.write_bytes(b"epub")
    azw3.write_bytes(b"azw3")
    targets = list_ingest_targets(folder)
    assert cbz in targets
    # One representative for the ebook stem group
    book_targets = [path for path in targets if path.suffix.lower() in {".epub", ".azw3"}]
    assert len(book_targets) == 1
    expanded = expand_organize_payload(book_targets[0])
    assert {path.suffix.lower() for path in expanded} == {".epub", ".azw3"}


def test_ingest_targets_for_mixed_payload_groups_ebook_stems(tmp_path):
    folder = tmp_path / "mix"
    folder.mkdir()
    files = [
        folder / "a.cbz",
        folder / "Title - Author.epub",
        folder / "Title - Author.azw3",
        folder / "Other.epub",
    ]
    for path in files:
        path.write_bytes(b"x")
    targets = ingest_targets_for_mixed_payload(files)
    assert files[0] in targets
    book_targets = [path for path in targets if path.suffix.lower() in {".epub", ".azw3"}]
    assert len(book_targets) == 2
    # Same-stem epub+azw3 collapse to one representative; Other stays separate.
    assert any(path.name.startswith("Title") for path in book_targets)
    assert any(path.name.startswith("Other") for path in book_targets)


def test_split_mixed_kind_work_peels_ebooks(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    settings = _book_settings(tmp_path)
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    comic_dir = Path(settings.comics_root) / "Marvel" / "The Stand (1990)"
    comic_dir.mkdir(parents=True)
    cbz = comic_dir / "The Stand #1990 (1990).cbz"
    epub = comic_dir / "The Stand_ American Nightmares - Stephen King.epub"
    azw3 = comic_dir / "The Stand_ American Nightmares - Stephen King.azw3"
    cbz.write_bytes(b"comic-bytes")
    epub.write_bytes(b"epub-bytes")
    azw3.write_bytes(b"azw3-bytes")
    work = db.upsert_work(
        {
            "kind": "comic",
            "title": "The Stand",
            "author": "Stephen King",
            "series_name": "The Stand",
            "series_index": "1990",
            "folder_path": str(comic_dir),
            "review_state": "none",
        }
    )
    for path, kind in ((cbz, "comic"), (epub, "comic"), (azw3, "comic")):
        db.upsert_file(
            {
                "work_id": work["id"],
                "path": str(path),
                "filename": path.name,
                "kind": kind,
                "size": path.stat().st_size,
            }
        )
    assert classify_mixed_kind_works(db)
    result = split_mixed_kind_work(db, settings, work_id=work["id"], move_files=True)
    comic = db.get_work(work["id"])
    book = db.get_work(result["book_work_id"])
    assert comic["kind"] == "comic"
    assert book["kind"] == "book"
    comic_files = db.files_for_work(work["id"])
    book_files = db.files_for_work(book["id"])
    assert len(comic_files) == 1
    assert comic_files[0]["filename"].endswith(".cbz")
    assert {Path(row["path"]).suffix.lower() for row in book_files} == {".epub", ".azw3"}
    assert cbz.exists()
    assert all(Path(row["path"]).exists() for row in book_files)
    assert not epub.exists()
    assert not azw3.exists()


def test_maintain_split_mixed_kinds_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    settings = _book_settings(tmp_path)
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    comic_dir = Path(settings.comics_root) / "Pub" / "Blend"
    comic_dir.mkdir(parents=True)
    cbz = comic_dir / "Blend #1.cbz"
    epub = comic_dir / "Blend Novel - Author.epub"
    cbz.write_bytes(b"c")
    epub.write_bytes(b"e")
    work = db.upsert_work(
        {
            "kind": "comic",
            "title": "Blend",
            "series_name": "Blend",
            "series_index": "1",
            "folder_path": str(comic_dir),
            "review_state": "none",
        }
    )
    for path in (cbz, epub):
        db.upsert_file(
            {
                "work_id": work["id"],
                "path": str(path),
                "filename": path.name,
                "kind": "comic",
                "size": path.stat().st_size,
            }
        )
    kicked = client.post("/api/maintain/split-mixed-kinds")
    assert kicked.status_code == 200
    assert kicked.json().get("kicked_off") is True
    status = _wait_status(client)
    assert status.get("status") == "completed"
    assert int(status.get("split") or status.get("result", {}).get("split") or 0) >= 1
    comic_files = db.files_for_work(work["id"])
    assert len(comic_files) == 1
    assert comic_files[0]["filename"].endswith(".cbz")


def test_reprocess_extra_files_splits_comic_ebook_mix(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(tmp_path))
    settings = _book_settings(tmp_path)
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    folder = tmp_path / "complete" / "The.Stand.Mix"
    folder.mkdir(parents=True)
    (folder / "The Stand #1990 (1990).cbz").write_bytes(b"cbz")
    (folder / "The Stand_ American Nightmares - Stephen King.epub").write_bytes(b"epub")
    (folder / "The Stand_ American Nightmares - Stephen King.azw3").write_bytes(b"azw3")
    work = db.upsert_work(
        {
            "kind": "comic",
            "title": "The Stand",
            "series_name": "The Stand",
            "series_index": "1990",
            "review_state": "needs_review",
            "review_reason": "extra_files",
            "folder_path": str(folder),
        }
    )
    resp = client.post(f"/api/review/{work['id']}/reprocess-extra-files")
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "split_mixed_kinds"
    assert body["targets"] >= 2
    refreshed = db.get_work(work["id"])
    assert refreshed["review_state"] == "resolved"
    assert refreshed["review_reason"] is None
