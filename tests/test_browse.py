"""Browse/Hall exclude catalog shells without registered media files."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def _client(tmp_path, monkeypatch, **settings_fields):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    if settings_fields:
        save_settings(tmp_path, Settings(**settings_fields))
    clear_session_secret_cache()
    clear_rate_limits()
    return TestClient(create_app(tmp_path))


def _login(client):
    resp = client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    assert resp.status_code == 200


def _shelve(db: Database, work: dict, *, filename: str = "book.epub") -> dict:
    """Register a fake media file so the work counts as on the shelf."""
    folder = Path(str(work.get("folder_path") or ""))
    if not folder.parts:
        folder = Path("/tmp") / str(work["id"])
        work = db.upsert_work({**work, "folder_path": str(folder)})
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    if not path.exists():
        path.write_bytes(b"payload")
    db.upsert_file(
        {
            "work_id": work["id"],
            "path": str(path),
            "filename": path.name,
            "kind": work.get("kind") or "book",
            "size": path.stat().st_size,
        }
    )
    return work


def _seed(db: Database):
    shining = db.upsert_work(
        {
            "kind": "book",
            "title": "The Shining",
            "author": "Stephen King",
            "series_name": "Overlook",
            "cover_path": "/tmp/shining.jpg",
            "folder_path": "/tmp/shining",
        }
    )
    _shelve(db, shining, filename="The Shining.epub")
    dune = db.upsert_work(
        {"kind": "book", "title": "Dune", "author": "Frank Herbert", "series_name": "Dune", "folder_path": "/tmp/dune"}
    )
    _shelve(db, dune)
    saga = db.upsert_work(
        {
            "kind": "comic",
            "title": "Saga #1",
            "author": "Brian K. Vaughan",
            "series_name": "Saga",
            "folder_path": "/tmp/saga",
        }
    )
    _shelve(db, saga, filename="Saga #1.cbz")
    circe = db.upsert_work(
        {"kind": "audiobook", "title": "Circe", "author": "Madeline Miller", "folder_path": "/tmp/circe"}
    )
    _shelve(db, circe, filename="Circe.m4b")
    db.upsert_work(
        {
            "kind": "book",
            "title": "Needs Review",
            "author": "Stephen King",
            "review_state": "needs_review",
        }
    )


def test_browse_filters_letter_kind_series(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    _seed(db)

    by_letter = client.get("/api/browse", params={"letter": "S"})
    assert by_letter.status_code == 200
    body = by_letter.json()
    assert body["total"] == 1
    assert [row["title"] for row in body["items"]] == ["The Shining"]
    assert body["items"][0]["has_cover"] is True

    by_kind = client.get("/api/browse", params={"kind": "comic"})
    assert by_kind.status_code == 200
    assert [row["title"] for row in by_kind.json()["items"]] == ["Saga #1"]

    by_author = client.get("/api/browse", params={"author": "Frank Herbert"})
    assert by_author.status_code == 200
    assert [row["title"] for row in by_author.json()["items"]] == ["Dune"]

    by_series = client.get("/api/browse", params={"series": "Dune"})
    assert by_series.status_code == 200
    assert [row["title"] for row in by_series.json()["items"]] == ["Dune"]


def test_browse_favorites_shelf_and_facets(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    _seed(db)
    me = client.get("/api/auth/me").json()["user"]
    shining = next(row for row in db.list_works(limit=20) if row["title"] == "The Shining")
    assert db.toggle_favorite(me["id"], shining["id"]) is True

    favorites = client.get("/api/browse", params={"shelf": "favorites"})
    assert favorites.status_code == 200
    fav_body = favorites.json()
    assert fav_body["total"] == 1
    assert fav_body["items"][0]["title"] == "The Shining"
    assert fav_body["filters"]["shelf"] == "favorites"

    facets = client.get("/api/browse/facets")
    assert facets.status_code == 200
    data = facets.json()
    letters = {row["letter"]: row["count"] for row in data["letters"]}
    assert letters.get("S") == 1
    assert letters.get("F") == 1
    kinds = {row["kind"]: row["count"] for row in data["kinds"]}
    assert kinds["book"] == 2
    assert kinds["comic"] == 1
    assert kinds["audiobook"] == 1
    assert data["genre_ready"] is False
    assert data["genres"] == []
    authors = {row["name"]: row["count"] for row in data["authors"]}
    assert authors["Stephen King"] == 1
    series = {row["name"]: row["count"] for row in data["series"]}
    assert series["Saga"] == 1


def test_hall_includes_kind_counts(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    _seed(db)

    hall = client.get("/api/hall")
    assert hall.status_code == 200
    counts = hall.json()["kind_counts"]
    assert counts["book"] == 2
    assert counts["comic"] == 1
    assert counts["audiobook"] == 1
    assert "Needs Review" not in counts  # review titles are excluded from totals


def test_browse_works_db_excludes_review(tmp_path):
    db = Database(tmp_path / "librarian.db")
    _seed(db)
    page = db.browse_works(author="Stephen King")
    assert [row["title"] for row in page["items"]] == ["The Shining"]
    assert page["total"] == 1


def test_browse_excludes_resolved_shells_without_files(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    real = db.upsert_work(
        {
            "kind": "audiobook",
            "title": "Backstage at the Lincoln Assassination",
            "author": "Thomas R. Bogar",
            "folder_path": str(tmp_path / "library" / "lincoln"),
            "review_state": "none",
        }
    )
    _shelve(db, real, filename="lincoln.m4b")
    db.upsert_work(
        {
            "kind": "audiobook",
            "title": "Backstage.at.the.Lincoln.Assassination.Audio.book",
            "author": "",
            "folder_path": str(tmp_path / "complete" / "Backstage.at.the.Lincoln.Assassination.Audio.book"),
            "review_state": "resolved",
        }
    )

    browse = client.get("/api/browse", params={"kind": "audiobook"})
    assert browse.status_code == 200
    titles = [row["title"] for row in browse.json()["items"]]
    assert titles == ["Backstage at the Lincoln Assassination"]
    assert browse.json()["total"] == 1

    hall = client.get("/api/hall")
    assert hall.status_code == 200
    assert hall.json()["kind_counts"]["audiobook"] == 1
    audio_titles = [row["title"] for row in hall.json()["areas"]["audiobooks"]]
    assert audio_titles == ["Backstage at the Lincoln Assassination"]
