"""P1-HIGH-02 / P4-HIGH-01 / P4-HIGH-02 — public_work allowlist hides storage paths."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.rate_limit import clear_rate_limits
from librarian.serve import annotate_work_files, existing_file_paths
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app
from librarian.web.serializers import public_work, public_work_admin, public_works


def _leaky_row(**extra):
    row = {
        "id": "w-dune",
        "kind": "book",
        "title": "Dune",
        "author": "Frank Herbert",
        "series_name": "Dune",
        "series_index": "1",
        "year": 1965,
        "isbn": "9780441172719",
        "description": "Desert planet. Arrakis. Spice.",
        "publisher": "Chilton",
        "genre": "SF",
        "cover_path": "/data/media/books/Herbert/Dune/cover.jpg",
        "folder_path": "/data/media/books/Herbert/Dune",
        "atmosphere_path": "/data/media/books/Herbert/Dune/atmosphere.jpg",
        "indexer_guid": "nzb-secret-guid",
        "repair_fail_count": 3,
        "abs_item_id": "abs-1",
        "synopsis_source": "openlibrary",
        "llm_blurb": "A boy inherits a desert world.",
        "review_state": "none",
        "created_at": 1.0,
        "updated_at": 2.0,
    }
    row.update(extra)
    return row


def test_public_work_strips_storage_paths_and_sets_has_cover():
    shaped = public_work(_leaky_row())
    assert shaped is not None
    assert shaped["id"] == "w-dune"
    assert shaped["title"] == "Dune"
    assert shaped["has_cover"] is True
    assert shaped["cover_story"]
    assert "cover_path" not in shaped
    assert "folder_path" not in shaped
    assert "atmosphere_path" not in shaped
    assert "indexer_guid" not in shaped
    assert "repair_fail_count" not in shaped
    blob = str(shaped)
    assert "/data/media" not in blob
    assert "cover.jpg" not in blob


def test_public_work_none_and_empty_cover():
    assert public_work(None) is None
    shaped = public_work(_leaky_row(cover_path="", atmosphere_path=None))
    assert shaped["has_cover"] is False
    assert "cover_path" not in shaped


def test_public_works_skips_falsy_rows():
    rows = public_works([_leaky_row(), None, {}, _leaky_row(id="w2")])
    # empty dict is falsy → skipped
    assert [row["id"] for row in rows] == ["w-dune", "w2"]
    assert all("folder_path" not in row for row in rows)


def test_public_work_admin_keeps_folder_not_cover_paths():
    shaped = public_work_admin(_leaky_row())
    assert shaped is not None
    assert shaped["folder_path"] == "/data/media/books/Herbert/Dune"
    assert shaped["repair_fail_count"] == 3
    assert shaped["indexer_guid"] == "nzb-secret-guid"
    assert shaped["has_cover"] is True
    assert "cover_path" not in shaped
    assert "atmosphere_path" not in shaped


def test_annotate_work_files_omits_absolute_path(tmp_path):
    epub = tmp_path / "Dune.epub"
    epub.write_bytes(b"PK\x03\x04")
    rows = [
        {
            "id": "f1",
            "path": str(epub),
            "filename": epub.name,
            "kind": "book",
            "size": epub.stat().st_size,
            "storage_path": str(tmp_path / "secret"),
        }
    ]
    annotated = annotate_work_files(rows, existing_file_paths(rows))
    assert len(annotated) == 1
    item = annotated[0]
    assert item["id"] == "f1"
    assert item["filename"] == "Dune.epub"
    assert item["on_disk"] is True
    assert item["reading_room"] is True
    assert "path" not in item
    assert "storage_path" not in item
    blob = str(annotated)
    assert str(tmp_path) not in blob
    assert str(epub) not in blob


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    save_settings(tmp_path, Settings())
    clear_session_secret_cache()
    clear_rate_limits()
    return TestClient(create_app(tmp_path))


def _login(client):
    resp = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
    )
    assert resp.status_code == 200


def test_hall_and_work_detail_omit_storage_paths(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    folder = tmp_path / "library" / "Dune"
    folder.mkdir(parents=True)
    epub = folder / "Dune.epub"
    epub.write_bytes(b"epub")
    cover = folder / "cover.jpg"
    cover.write_bytes(b"jpg")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Dune",
            "author": "Frank Herbert",
            "folder_path": str(folder),
            "cover_path": str(cover),
            "atmosphere_path": str(folder / "atmosphere.jpg"),
            "indexer_guid": "guid-secret",
            "repair_fail_count": 2,
        }
    )
    db.upsert_file(
        {
            "work_id": work["id"],
            "path": str(epub),
            "filename": epub.name,
            "kind": "book",
            "size": epub.stat().st_size,
        }
    )

    hall = client.get("/api/hall")
    assert hall.status_code == 200
    body = hall.json()
    blob = str(body)
    assert str(folder) not in blob
    assert str(cover) not in blob
    assert "guid-secret" not in blob
    assert "atmosphere" not in blob or "atmosphere_path" not in blob

    detail = client.get(f"/api/works/{work['id']}")
    assert detail.status_code == 200
    payload = detail.json()
    shaped = payload["work"]
    assert shaped["title"] == "Dune"
    assert shaped["has_cover"] is True
    assert "folder_path" not in shaped
    assert "cover_path" not in shaped
    assert "atmosphere_path" not in shaped
    assert "indexer_guid" not in shaped
    assert "repair_fail_count" not in shaped
    files = payload["files"]
    assert files
    assert all("path" not in row for row in files)
    assert all(row.get("filename") == "Dune.epub" for row in files)
    detail_blob = str(payload)
    assert str(epub) not in detail_blob
    assert str(folder) not in detail_blob


def test_review_list_admin_keeps_folder_path(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    folder = tmp_path / "complete" / "stuck-title"
    folder.mkdir(parents=True)
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Stuck",
            "author": "Anon",
            "folder_path": str(folder),
            "cover_path": str(folder / "cover.jpg"),
            "review_state": "needs_review",
            "review_reason": "no_payload",
        }
    )

    resp = client.get("/api/review")
    assert resp.status_code == 200
    rows = resp.json()["works"]
    assert rows
    match = next(row for row in rows if row["id"] == work["id"])
    assert match["folder_path"] == str(folder)
    assert "cover_path" not in match
    assert "atmosphere_path" not in match


def test_music_promote_response_uses_admin_serializer(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    folder = tmp_path / "inbox" / "Radiohead" / "In Rainbows"
    folder.mkdir(parents=True)
    track = folder / "01 15 Step.flac"
    track.write_bytes(b"flac")
    cover = folder / "cover.jpg"
    cover.write_bytes(b"jpg")
    raw = {
        "id": "music-1",
        "kind": "music",
        "title": "In Rainbows",
        "author": "Radiohead",
        "folder_path": str(folder),
        "cover_path": str(cover),
        "atmosphere_path": str(folder / "atmosphere.jpg"),
        "music_state": "promoted",
        "indexer_guid": "music-guid",
        "repair_fail_count": 0,
    }
    with patch("librarian.web.routers.works.promote_music", return_value=raw):
        with patch(
            "librarian.web.routers.works.plexamp_handoff",
            return_value={"url": "plexamp://album"},
        ):
            resp = client.post("/api/music/music-1/promote")
    assert resp.status_code == 200
    body = resp.json()
    work = body["work"]
    assert work["title"] == "In Rainbows"
    assert work["folder_path"] == str(folder)
    assert work["music_state"] == "promoted"
    assert "cover_path" not in work
    assert "atmosphere_path" not in work
    assert body["plexamp"]["url"] == "plexamp://album"
    assert str(cover) not in str(body)


def test_enrich_response_strips_storage_paths(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    folder = tmp_path / "library" / "Dune"
    folder.mkdir(parents=True)
    cover = folder / "cover.jpg"
    cover.write_bytes(b"jpg")
    shaped_work = {
        "id": "w-enrich",
        "kind": "book",
        "title": "Dune",
        "author": "Frank Herbert",
        "folder_path": str(folder),
        "cover_path": str(cover),
        "atmosphere_path": str(folder / "atmosphere.jpg"),
        "description": "Desert planet.",
    }
    with patch(
        "librarian.web.routers.works.enrich_work",
        return_value={
            "work": shaped_work,
            "updated": True,
            "source": "openlibrary",
            "thin": False,
            "match_key": "ol-1",
            "match_confidence": "high",
        },
    ):
        resp = client.post("/api/works/w-enrich/enrich")
    assert resp.status_code == 200
    body = resp.json()
    work = body["work"]
    assert work["title"] == "Dune"
    assert work["description"] == "Desert planet."
    assert work["has_cover"] is True
    assert "folder_path" not in work
    assert "cover_path" not in work
    assert "atmosphere_path" not in work
    assert str(folder) not in str(body)
    assert str(cover) not in str(body)
    assert body["updated"] is True
    assert body["source"] == "openlibrary"
