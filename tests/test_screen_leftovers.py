"""Maintain lists leftover movie and TV catalog rows and does not touch their files."""

from __future__ import annotations

from fastapi.testclient import TestClient

from librarian.db import Database
from librarian.screen_leftovers import screen_leftover_report
from librarian.web.app import create_app


def test_screen_leftover_report_lists_movie_and_tv_only(tmp_path):
    folder = tmp_path / "movies" / "Dune"
    folder.mkdir(parents=True)
    video = folder / "dune.mkv"
    video.write_bytes(b"leave-this-file")
    db = Database(tmp_path / "librarian.db")
    movie = db.upsert_work(
        {
            "kind": "movie",
            "title": "Dune",
            "author": "Villeneuve",
            "folder_path": str(folder),
        }
    )
    db.upsert_work({"kind": "tv", "title": "The Expanse", "author": "SA Corey"})
    db.upsert_work({"kind": "book", "title": "Dune", "author": "Herbert"})
    db.upsert_work({"kind": "xxx", "title": "Clip"})

    report = screen_leftover_report(db)
    listed = {(row["kind"], row["title"]) for row in report["items"]}
    assert listed == {("movie", "Dune"), ("tv", "The Expanse")}
    assert report["count"] == 2
    assert report["truncated"] is False
    assert "left in place" in report["note"]
    assert video.is_file()
    assert db.get_work(movie["id"])["folder_path"] == str(folder)


def test_maintain_morning_brief_includes_screen_leftovers(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    db = Database(tmp_path / "librarian.db")
    db.upsert_work({"kind": "tv", "title": "Andor"})
    client = TestClient(create_app(tmp_path))
    assert (
        client.post(
            "/api/auth/local/login",
            json={"username": "owner", "password": "password123"},
        ).status_code
        == 200
    )
    body = client.get("/api/maintain/morning-brief").json()
    titles = [row["title"] for row in body["screen_leftovers"]["items"]]
    assert titles == ["Andor"]
    assert body["screen_leftovers"]["count"] == 1
