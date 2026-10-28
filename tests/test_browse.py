"""Browse/Hall exclude catalog shells without registered media files."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.db import BROWSE_EXPORT_ROW_CAP, BROWSE_PAGE_MAX_LIMIT, Database
from librarian.identity.authors import sort_name
from librarian.identity.titles import title_sort
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

    by_letter = client.get("/api/browse", params={"letter": "K"})
    assert by_letter.status_code == 200
    body = by_letter.json()
    assert body["total"] == 1
    assert [row["title"] for row in body["items"]] == ["The Shining"]
    # Seeded cover_path has no file on disk — cards must not claim art.
    assert body["items"][0]["has_cover"] is False

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
    assert letters.get("K") == 1
    assert letters.get("H") == 1
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


def test_browse_annotates_listen_and_wanted(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    dune = _shelve(
        db,
        db.upsert_work(
            {
                "kind": "book",
                "title": "Dune",
                "author": "Frank Herbert",
                "isbn": "9780441172719",
                "folder_path": str(tmp_path / "dune-book"),
            }
        ),
    )
    audio = _shelve(
        db,
        db.upsert_work(
            {
                "kind": "audiobook",
                "title": "Dune",
                "author": "Frank Herbert",
                "isbn": "9780441172719",
                "folder_path": str(tmp_path / "dune-audio"),
            }
        ),
        filename="Dune.m4b",
    )
    circe = _shelve(
        db,
        db.upsert_work(
            {
                "kind": "book",
                "title": "Circe",
                "author": "Madeline Miller",
                "folder_path": str(tmp_path / "circe-book"),
            }
        ),
        filename="Circe.epub",
    )
    from librarian.wanted import add_wanted

    row = add_wanted(db, {"work_id": circe["id"], "kind": "audiobook", "title": "Circe"})

    browse = client.get("/api/browse", params={"kind": "book"})
    assert browse.status_code == 200
    by_title = {item["title"]: item for item in browse.json()["items"]}
    assert by_title["Dune"]["audiobook"]["shelved"]["id"] == audio["id"]
    assert by_title["Circe"]["audiobook"]["shelved"] is None
    assert by_title["Circe"]["wanted"]["id"] == row["id"]
    assert by_title["Circe"]["wanted"]["status"] == "wanted"

    detail = client.get(f"/api/works/{circe['id']}")
    assert detail.status_code == 200
    assert detail.json()["wanted"]["status"] == "wanted"
    assert client.get(f"/api/works/{dune['id']}").json()["audiobook"]["shelved"]["id"] == audio["id"]
def _stamp(db: Database, sql: str, params: tuple) -> None:
    def _write() -> None:
        with db._connect() as conn:
            conn.execute(sql, params)

    db.run_write(_write, label="test_stamp")


def _titles(response) -> list[str]:
    return [row["title"] for row in response.json()["items"]]


def _csv_title(title: str) -> str:
    if title[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + title
    return title


def _csv_rows(response) -> list[list[str]]:
    return list(csv.reader(io.StringIO(response.text)))


def _seed_catalog(db: Database, root: Path) -> dict[str, dict]:
    """Shelved stacks used to prove sort, filters, and CSV shape."""
    root.mkdir(parents=True, exist_ok=True)
    specs = [
        {
            "key": "formula",
            "title": "=1+1",
            "author": "@cmd",
            "kind": "book",
            "series_name": "+series",
            "genre": "-genre",
            "updated": 10,
            "added": 10,
        },
        {
            "key": "hello",
            "title": 'Say "hello", José',
            "author": "Ada Lovelace",
            "year": 1843,
            "kind": "book",
            "series_name": "Analytical",
            "genre": "Computing",
            "updated": 150,
            "added": 20,
        },
        {
            "key": "saga",
            "title": "Saga #1",
            "author": "Brian K. Vaughan",
            "year": 2012,
            "kind": "comic",
            "series_name": "Saga",
            "updated": 400,
            "added": 30,
        },
        {
            "key": "dune",
            "title": "Dune",
            "author": "Frank Herbert",
            "year": 1965,
            "kind": "book",
            "series_name": "Dune",
            "genre": "Science Fiction",
            "updated": 200,
            "added": 40,
        },
        {
            "key": "carrie",
            "title": "Carrie",
            "author": "Stephen King",
            "year": 1974,
            "kind": "book",
            "genre": "Horror",
            "updated": 100,
            "added": 50,
        },
        {
            "key": "shining",
            "title": "The Shining",
            "author": "Stephen King",
            "year": 1977,
            "kind": "book",
            "series_name": "Overlook",
            "genre": "Horror",
            "updated": 300,
            "added": 60,
            "cover_path": str(root / "SECRET-COVER-PATH.jpg"),
            "atmosphere_path": str(root / "SECRET-ATMOSPHERE-PATH.jpg"),
            "isbn": "SECRET-ISBN-TOKEN",
            "asin": "SECRET-ASIN-TOKEN",
            "description": "SECRET-BLURB-TOKEN",
            "llm_blurb": "SECRET-LLM-TOKEN",
            "narrator": "SECRET-NARRATOR-TOKEN",
            "abs_item_id": "SECRET-ABS-TOKEN",
            "indexer_guid": "SECRET-GUID-TOKEN",
        },
        {
            "key": "undated",
            "title": "Undated",
            "author": "Zora Neale Hurston",
            "kind": "book",
            "genre": "Fiction",
            "updated": 50,
            "added": 70,
        },
    ]
    works: dict[str, dict] = {}
    for spec in specs:
        updated = spec.pop("updated")
        added = spec.pop("added")
        key = spec.pop("key")
        folder = root / "SECRET-HOST-PATH" / key
        work = db.upsert_work({**spec, "folder_path": str(folder)})
        _shelve(db, work, filename=f"{key}.epub")
        _stamp(db, "UPDATE works SET updated_at = ? WHERE id = ?", (updated, work["id"]))
        _stamp(db, "UPDATE works SET created_at = ? WHERE id = ?", (added, work["id"]))
        works[key] = work
    review_folder = root / "SECRET-HOST-PATH" / "review"
    review = db.upsert_work(
        {
            "kind": "book",
            "title": "Needs Review Marker",
            "author": "Stephen King",
            "folder_path": str(review_folder),
            "review_state": "needs_review",
            "isbn": "SECRET-REVIEW-TOKEN",
        }
    )
    _shelve(db, review, filename="review.epub")
    works["review"] = review
    return works


# Author order is author_sort (Last, First), then title_sort. @cmd stays first.
_AUTHOR_ASC = [
    "=1+1",
    "Dune",
    "Undated",
    "Carrie",
    "The Shining",
    'Say "hello", José',
    "Saga #1",
]
_AUTHOR_DESC = [
    "Saga #1",
    'Say "hello", José',
    "Carrie",
    "The Shining",
    "Undated",
    "Dune",
    "=1+1",
]
_TITLE_ASC = [
    "=1+1",
    "Carrie",
    "Dune",
    "Saga #1",
    'Say "hello", José',
    "The Shining",
    "Undated",
]
_TITLE_DESC = list(reversed(_TITLE_ASC))
_YEAR_DESC = [
    "Saga #1",
    "The Shining",
    "Carrie",
    "Dune",
    'Say "hello", José',
    "=1+1",
    "Undated",
]
_YEAR_ASC = [
    'Say "hello", José',
    "Dune",
    "Carrie",
    "The Shining",
    "Saga #1",
    "=1+1",
    "Undated",
]
# Date added is works.created_at, which is stamped independently of updated_at.
_ADDED_DESC = [
    "Undated",
    "The Shining",
    "Carrie",
    "Dune",
    "Saga #1",
    'Say "hello", José',
    "=1+1",
]
_ADDED_ASC = list(reversed(_ADDED_DESC))
_LEAK_MARKERS = (
    "SECRET-HOST-PATH",
    "SECRET-COVER-PATH",
    "SECRET-ATMOSPHERE-PATH",
    "SECRET-ISBN-TOKEN",
    "SECRET-ASIN-TOKEN",
    "SECRET-BLURB-TOKEN",
    "SECRET-LLM-TOKEN",
    "SECRET-NARRATOR-TOKEN",
    "SECRET-ABS-TOKEN",
    "SECRET-GUID-TOKEN",
    "SECRET-REVIEW-TOKEN",
)


def test_browse_sort_direction_and_year(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    _seed_catalog(db, tmp_path / "catalog")

    default = client.get("/api/browse")
    assert default.status_code == 200
    assert default.json()["sort"] == "updated"
    assert default.json()["sort_dir"] == "desc"
    assert _titles(default) == _ADDED_DESC
    assert "Needs Review Marker" not in _titles(default)

    exported = client.get("/api/browse/export.csv")
    assert [row[0] for row in _csv_rows(exported)[1:]] == [_csv_title(title) for title in _ADDED_DESC]

    author_desc = client.get("/api/browse", params={"sort": "author", "sort_dir": "desc"})
    assert _titles(author_desc) == _AUTHOR_DESC
    assert author_desc.json()["sort_dir"] == "desc"

    title_asc = client.get("/api/browse", params={"sort": "Title"})
    assert title_asc.json()["sort"] == "title"
    assert title_asc.json()["sort_dir"] == "asc"
    assert _titles(title_asc) == _TITLE_ASC

    title_desc = client.get("/api/browse", params={"sort": "title", "sort_dir": "DESC"})
    assert _titles(title_desc) == _TITLE_DESC

    updated = client.get("/api/browse", params={"sort": "updated"})
    assert updated.json()["sort"] == "updated"
    assert updated.json()["sort_dir"] == "desc"
    assert _titles(updated) == _ADDED_DESC

    updated_asc = client.get("/api/browse", params={"sort": "updated", "sort_dir": "asc"})
    assert _titles(updated_asc) == _ADDED_ASC

    year = client.get("/api/browse", params={"sort": "year"})
    assert year.json()["sort"] == "year"
    assert year.json()["sort_dir"] == "desc"
    assert _titles(year) == _YEAR_DESC

    year_asc = client.get("/api/browse", params={"sort": " Year ", "sort_dir": "asc"})
    assert year_asc.json()["sort"] == "year"
    assert year_asc.json()["sort_dir"] == "asc"
    assert _titles(year_asc) == _YEAR_ASC

    page = client.get("/api/browse", params={"sort": "author", "limit": 1, "offset": 1})
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 7
    assert body["limit"] == 1
    assert body["offset"] == 1
    assert _titles(page) == ["Dune"]
    assert "folder_path" not in body["items"][0]
    assert "cover_path" not in body["items"][0]

    skipped = client.get("/api/browse", params={"kind": "comic", "offset": 1, "limit": 10})
    assert skipped.json()["total"] == 1
    assert skipped.json()["offset"] == 1
    assert _titles(skipped) == []

    negative = client.get("/api/browse", params={"offset": -4, "limit": 1, "sort": "author"})
    assert negative.json()["offset"] == 0
    assert _titles(negative) == ["=1+1"]


def test_browse_hostile_query_params(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    _seed_catalog(db, tmp_path / "catalog")

    injected = client.get(
        "/api/browse",
        params={
            "sort": "title; DROP TABLE works--",
            "sort_dir": "desc UNION SELECT password_hash FROM users",
            "letter": "K",
        },
    )
    assert injected.status_code == 200
    assert injected.json()["sort"] == "updated"
    assert injected.json()["sort_dir"] == "desc"
    assert _titles(injected) == ["The Shining", "Carrie"]
    for marker in ("SECRET-HOST-PATH", "SECRET-COVER-PATH", "SECRET-GUID-TOKEN"):
        assert marker not in injected.text

    still_there = client.get("/api/browse", params={"sort": "year;drop", "sort_dir": "sideways"})
    assert still_there.status_code == 200
    assert still_there.json()["sort"] == "updated"
    assert still_there.json()["sort_dir"] == "desc"
    assert _titles(still_there) == _ADDED_DESC

    unknown_kind = client.get("/api/browse", params={"kind": "book'; DROP TABLE works--"})
    assert unknown_kind.status_code == 200
    assert unknown_kind.json()["filters"]["kind"] == ""
    assert unknown_kind.json()["total"] == 7

    huge = client.get("/api/browse", params={"limit": 999999})
    assert huge.status_code == 200
    assert huge.json()["limit"] == BROWSE_PAGE_MAX_LIMIT == 100
    assert huge.json()["total"] == 7
    assert len(huge.json()["items"]) == 7

    capped = db.browse_works(limit=999999, max_limit=2, sort="author")
    assert capped["limit"] == 2
    assert capped["total"] == 7
    assert [row["title"] for row in capped["items"]] == _AUTHOR_ASC[:2]
    wide = db.browse_works(limit=999999, max_limit=999999)
    assert wide["limit"] == BROWSE_EXPORT_ROW_CAP == 5000
    assert len(wide["items"]) == 7

    bogus_limit = client.get("/api/browse", params={"limit": "nope"})
    assert bogus_limit.status_code == 422

    for shelf in ("../../etc/passwd", "not-a-shelf", "favorites'; DROP TABLE shelves--"):
        missing = client.get("/api/browse", params={"shelf": shelf})
        assert missing.status_code == 404
        assert "SECRET-HOST-PATH" not in missing.text

    export_shelf = client.get("/api/browse/export.csv", params={"shelf": "../../etc/passwd"})
    assert export_shelf.status_code == 404
    assert "The Shining" not in export_shelf.text


def test_browse_shelf_updated_direction_follows_added_at(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    root = tmp_path / "favs"
    older = db.upsert_work(
        {
            "kind": "book",
            "title": "Older Shelf",
            "author": "Ann Author",
            "year": 2001,
            "folder_path": str(root / "older"),
        }
    )
    newer = db.upsert_work(
        {
            "kind": "book",
            "title": "Newer Shelf",
            "author": "Ann Author",
            "year": 1990,
            "folder_path": str(root / "newer"),
        }
    )
    _shelve(db, older)
    _shelve(db, newer)
    me = client.get("/api/auth/me").json()["user"]
    assert db.add_favorite(me["id"], older["id"]) is True
    assert db.add_favorite(me["id"], newer["id"]) is True
    shelf_id = db.favorites_shelf(me["id"])["id"]
    _stamp(
        db,
        "UPDATE shelf_items SET added_at = ? WHERE shelf_id = ? AND work_id = ?",
        (10, shelf_id, older["id"]),
    )
    _stamp(
        db,
        "UPDATE shelf_items SET added_at = ? WHERE shelf_id = ? AND work_id = ?",
        (20, shelf_id, newer["id"]),
    )
    # created_at runs the other way, so a shelf sort that used it would flip.
    _stamp(db, "UPDATE works SET created_at = ? WHERE id = ?", (50, older["id"]))
    _stamp(db, "UPDATE works SET created_at = ? WHERE id = ?", (10, newer["id"]))

    off_shelf = client.get("/api/browse")
    assert off_shelf.json()["sort"] == "updated"
    assert off_shelf.json()["sort_dir"] == "desc"
    assert _titles(off_shelf) == ["Older Shelf", "Newer Shelf"]

    omitted = client.get("/api/browse", params={"shelf": "favorites"})
    assert omitted.json()["sort"] == "updated"
    assert omitted.json()["sort_dir"] == "desc"
    assert _titles(omitted) == ["Newer Shelf", "Older Shelf"]

    desc = client.get("/api/browse", params={"shelf": "favorites", "sort": "updated"})
    assert desc.status_code == 200
    assert desc.json()["sort_dir"] == "desc"
    assert desc.json()["filters"]["shelf"] == "favorites"
    assert _titles(desc) == ["Newer Shelf", "Older Shelf"]

    asc = client.get(
        "/api/browse",
        params={"shelf": "favorites", "sort": "updated", "sort_dir": "asc"},
    )
    assert _titles(asc) == ["Older Shelf", "Newer Shelf"]

    by_year = client.get(
        "/api/browse",
        params={"shelf": "favorites", "sort": "year", "sort_dir": "asc"},
    )
    assert _titles(by_year) == ["Newer Shelf", "Older Shelf"]


def test_browse_export_csv_matches_filters_and_hides_secrets(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    _seed_catalog(db, tmp_path / "catalog")
    me = client.get("/api/auth/me").json()["user"]
    shining = next(row for row in db.list_works(limit=20) if row["title"] == "The Shining")
    dune = next(row for row in db.list_works(limit=20) if row["title"] == "Dune")
    assert db.add_favorite(me["id"], shining["id"]) is True
    assert db.add_favorite(me["id"], dune["id"]) is True

    client.cookies.clear()
    assert client.get("/api/browse/export.csv").status_code == 401
    _login(client)

    exported = client.get("/api/browse/export.csv", params={"sort": "year", "sort_dir": "desc"})
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert 'filename="librarian-stacks.csv"' in exported.headers["content-disposition"]
    assert exported.headers["cache-control"] == "private, no-store"
    assert exported.headers["x-librarian-export-cap"] == str(BROWSE_EXPORT_ROW_CAP) == "5000"
    assert exported.headers["x-librarian-export-total"] == "7"
    assert exported.headers["x-librarian-export-returned"] == "7"
    table = _csv_rows(exported)
    assert table[0] == [
        "title",
        "author",
        "title_sort",
        "author_sort",
        "year",
        "kind",
        "series",
        "genre",
        "work_id",
        "isbn13",
        "asin",
        "ol_work",
        "hardcover",
        "comicvine",
        "calibre",
    ]
    assert [row[0] for row in table[1:]] == [_csv_title(title) for title in _YEAR_DESC]
    shining_row = next(row for row in table[1:] if row[0] == "The Shining")
    assert shining_row[:8] == [
        "The Shining",
        "Stephen King",
        title_sort("The Shining"),
        sort_name("Stephen King"),
        "1977",
        "book",
        "Overlook",
        "Horror",
    ]
    assert shining_row[8] == shining["id"]
    assert shining_row[9:] == ["", "", "", "", "", ""]
    hello_row = next(row for row in table[1:] if row[0] == 'Say "hello", José')
    assert hello_row[:8] == [
        'Say "hello", José',
        "Ada Lovelace",
        title_sort('Say "hello", José'),
        sort_name("Ada Lovelace"),
        "1843",
        "book",
        "Analytical",
        "Computing",
    ]
    formula = next(row for row in table[1:] if row[0] == "'=1+1")
    assert formula[:8] == [
        "'=1+1",
        "'@cmd",
        title_sort("=1+1"),
        "'" + sort_name("@cmd"),
        "",
        "book",
        "'+series",
        "'-genre",
    ]
    assert "Needs Review Marker" not in exported.text
    for marker in _LEAK_MARKERS:
        assert marker not in exported.text

    visible = client.get("/api/browse/export.csv", params={"columns": "title, year"})
    visible_rows = _csv_rows(visible)
    assert visible_rows[0] == ["title", "year"]
    assert all(len(row) == 2 for row in visible_rows)
    assert "Stephen King" not in visible.text
    assert "Overlook" not in visible.text

    ordered = client.get("/api/browse/export.csv", params={"columns": "genre,title,title"})
    assert _csv_rows(ordered)[0] == ["genre", "title"]

    every = client.get("/api/browse/export.csv", params={"columns": "all"})
    assert _csv_rows(every)[0] == [
        "title",
        "author",
        "title_sort",
        "author_sort",
        "year",
        "kind",
        "series",
        "genre",
        "work_id",
        "isbn13",
        "asin",
        "ol_work",
        "hardcover",
        "comicvine",
        "calibre",
    ]

    ignored_page = client.get(
        "/api/browse/export.csv",
        params={"limit": 1, "offset": 6, "sort": "author"},
    )
    assert _csv_rows(ignored_page)[0][0] == "title"
    assert [row[0] for row in _csv_rows(ignored_page)[1:]] == [
        "'=1+1" if title == "=1+1" else title for title in _AUTHOR_ASC
    ]
    assert ignored_page.headers["x-librarian-export-returned"] == "7"

    cases = [
        {"kind": "comic"},
        {"author": "Frank Herbert"},
        {"letter": "K", "sort": "title", "sort_dir": "desc"},
        {"series": "Dune"},
        {"genre": "horror", "sort": "year", "sort_dir": "asc"},
        {"shelf": "favorites", "sort": "title", "sort_dir": "asc"},
    ]
    expected = {
        "kind": ["Saga #1"],
        "author": ["Dune"],
        "letter": ["The Shining", "Carrie"],
        "series": ["Dune"],
        "genre": ["Carrie", "The Shining"],
        "shelf": ["Dune", "The Shining"],
    }
    for params in cases:
        key = next(iter(params))
        browse = client.get("/api/browse", params={**params, "limit": 50})
        csv_response = client.get("/api/browse/export.csv", params=params)
        assert browse.status_code == 200, params
        assert csv_response.status_code == 200, params
        assert _titles(browse) == expected[key]
        assert [row[0] for row in _csv_rows(csv_response)[1:]] == expected[key]
        assert csv_response.headers["x-librarian-export-total"] == str(len(expected[key]))
        for marker in _LEAK_MARKERS:
            assert marker not in csv_response.text


def test_browse_export_rejects_bad_columns_and_caps_rows(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    _seed_catalog(db, tmp_path / "catalog")

    for columns in (
        "folder_path",
        "cover_path",
        "title,folder_path",
        "indexer_guid",
        "isbn",
        "description",
        ",,,",
        "title\r\nSet-Cookie: leaked",
    ):
        rejected = client.get("/api/browse/export.csv", params={"columns": columns})
        assert rejected.status_code == 400, columns
        if columns == ",,,":
            assert rejected.json()["detail"] == "columns must name at least one export column"
        else:
            assert rejected.json()["detail"] == "Unknown export column"
        assert "The Shining" not in rejected.text
        assert "SECRET-HOST-PATH" not in rejected.text

    blank = client.get("/api/browse/export.csv", params={"columns": ",,,"})
    assert blank.status_code == 400
    assert blank.json()["detail"] == "columns must name at least one export column"

    monkeypatch.setattr("librarian.services.search.BROWSE_EXPORT_ROW_CAP", 2)
    capped = client.get("/api/browse/export.csv", params={"sort": "author", "sort_dir": "asc"})
    assert capped.status_code == 200
    assert capped.headers["x-librarian-export-cap"] == "2"
    assert capped.headers["x-librarian-export-total"] == "7"
    assert capped.headers["x-librarian-export-returned"] == "2"
    assert [row[0] for row in _csv_rows(capped)[1:]] == ["'=1+1", "Dune"]


def test_browse_sort_keys_letter_and_one_row_per_work(tmp_path, monkeypatch):
    """Title sort ignores a leading article and pads numbers. The letter is the surname.

    Two files and two editions of one work stay a single Stacks card.
    """
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    root = tmp_path / "shelf"

    project = _shelve(
        db,
        db.upsert_work(
            {
                "id": "1619",
                "kind": "book",
                "title": "The 1619 Project: A New Origin Story",
                "author": "Nikole Hannah-Jones",
                "folder_path": str(root / "1619"),
            }
        ),
        filename="1619.epub",
    )
    _shelve(db, project, filename="1619.azw3")
    db.upsert_edition(
        {
            "id": "ed-hard",
            "work_id": project["id"],
            "kind": "book",
            "isbn13": "9780593230572",
            "format": "Hardcover",
            "folder_path": str(root / "secret-edition-path"),
        }
    )
    db.upsert_edition(
        {
            "id": "ed-ebook",
            "work_id": project["id"],
            "kind": "book",
            "isbn13": "9780593230589",
            "format": "ebook",
        }
    )
    _shelve(
        db,
        db.upsert_work(
            {
                "kind": "book",
                "title": "1984",
                "author": "George Orwell",
                "folder_path": str(root / "1984"),
            }
        ),
    )
    _shelve(
        db,
        db.upsert_work(
            {
                "kind": "book",
                "title": "Apple",
                "author": "Ann Apple",
                "folder_path": str(root / "apple"),
            }
        ),
    )
    _shelve(
        db,
        db.upsert_work(
            {
                "kind": "book",
                "title": "The Zoo",
                "author": "Zoe Zebra",
                "folder_path": str(root / "zoo"),
            }
        ),
    )

    by_title = client.get("/api/browse", params={"sort": "title", "sort_dir": "asc"})
    assert by_title.status_code == 200
    assert _titles(by_title) == ["The 1619 Project: A New Origin Story", "1984", "Apple", "The Zoo"]
    assert by_title.json()["total"] == 4

    stored = db.get_work("1619")
    assert stored["title_sort"].startswith("0000001619")
    assert stored["author_sort"].startswith("Hannah-Jones")

    by_surname = client.get("/api/browse", params={"letter": "H"})
    assert _titles(by_surname) == ["The 1619 Project: A New Origin Story"]
    given_name = client.get("/api/browse", params={"letter": "N"})
    assert given_name.json()["total"] == 0
    assert _titles(client.get("/api/browse", params={"letter": "O"})) == ["1984"]
    assert _titles(client.get("/api/browse", params={"letter": "Z"})) == ["The Zoo"]

    page = db.browse_works(sort="title")
    assert page["total"] == 4
    assert [row["id"] for row in page["items"]].count("1619") == 1


def test_more_by_uses_author_id_and_dedupes_1619_pair(tmp_path, monkeypatch):
    """More by follows work_authors, one card per title, and skips the current work."""
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    root = tmp_path / "more"
    author = db.upsert_author(
        {"display_name": "Nikole Hannah-Jones", "sort_name": "Hannah-Jones, Nikole"}
    )
    project = _shelve(
        db,
        db.upsert_work(
            {
                "id": "86f007ee",
                "kind": "book",
                "title": "The 1619 Project: A New Origin Story",
                "author": "Nikole Hannah-Jones",
                "folder_path": str(root / "project"),
            }
        ),
    )
    sibling = _shelve(
        db,
        db.upsert_work(
            {
                "id": "5172a6bf",
                "kind": "book",
                "title": "The 1619 Project",
                "author": "Hannah-Jones, Nikole",
                "folder_path": str(root / "sibling"),
            }
        ),
    )
    caste = _shelve(
        db,
        db.upsert_work(
            {
                "id": "caste-long",
                "kind": "book",
                "title": "Caste: The Origins of Our Discontents",
                "author": "Nikole Hannah-Jones",
                "folder_path": str(root / "caste-long"),
            }
        ),
    )
    caste_short = _shelve(
        db,
        db.upsert_work(
            {
                "id": "caste-short",
                "kind": "book",
                "title": "Caste",
                "author": "Hannah-Jones, Nikole",
                "folder_path": str(root / "caste-short"),
            }
        ),
    )
    born = _shelve(
        db,
        db.upsert_work(
            {
                "id": "born",
                "kind": "book",
                "title": "Born on the Water",
                "author": "Nikole Hannah-Jones",
                "folder_path": str(root / "born"),
            }
        ),
    )
    decoy = _shelve(
        db,
        db.upsert_work(
            {
                "id": "decoy",
                "kind": "book",
                "title": "Nikole Hannah-Jones: A Life",
                "author": "Someone Else",
                "folder_path": str(root / "decoy"),
            }
        ),
    )
    for work in (project, sibling, caste, caste_short, born):
        db.add_work_author(work_id=work["id"], author_id=author["id"])
    db.upsert_edition(
        {
            "id": "ed-hard",
            "work_id": project["id"],
            "kind": "book",
            "isbn13": "9780593230572",
            "format": "Hardcover",
            "folder_path": str(root / "secret-edition-folder"),
            "cover_path": str(root / "secret-edition-cover"),
        }
    )
    db.upsert_edition(
        {
            "id": "ed-audio",
            "work_id": project["id"],
            "kind": "audiobook",
            "asin": "B09LISTEN",
            "format": "Audiobook",
            "folder_path": str(root / "secret-audio-folder"),
        }
    )

    detail = client.get(f"/api/works/{project['id']}")
    assert detail.status_code == 200
    body = detail.json()
    related_ids = [row["id"] for row in body["related"]]
    related_titles = [row["title"] for row in body["related"]]
    assert project["id"] not in related_ids
    assert sibling["id"] not in related_ids
    assert decoy["id"] not in related_ids
    assert len(related_titles) == 2
    assert related_titles[0] == "Born on the Water"
    assert related_titles[1].startswith("Caste")
    assert related_ids.count("caste-long") + related_ids.count("caste-short") == 1
    assert "secret-edition-folder" not in detail.text
    assert "secret-edition-cover" not in detail.text
    editions = body["editions"]
    assert [(row["format"], row["isbn13"], row["asin"]) for row in editions] == [
        ("Audiobook", None, "B09LISTEN"),
        ("Hardcover", "9780593230572", None),
    ]
    assert all("folder_path" not in row and "cover_path" not in row for row in editions)

    other = client.get(f"/api/works/{born['id']}")
    other_titles = [row["title"] for row in other.json()["related"]]
    assert sum(title.startswith("The 1619 Project") for title in other_titles) == 1
    assert sum(title == "Caste" or title.startswith("Caste:") for title in other_titles) == 1
    assert decoy["title"] not in other_titles


def test_browse_export_csv_includes_sort_keys_and_canonical_ids(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    work = _shelve(
        db,
        db.upsert_work(
            {
                "id": "1619",
                "kind": "book",
                "title": "The 1619 Project",
                "author": "Nikole Hannah-Jones",
                "isbn": "SECRET-RAW-ISBN",
                "asin": "SECRET-RAW-ASIN",
                "folder_path": str(tmp_path / "export" / "secret-folder"),
            }
        ),
    )
    db.upsert_work_identifier(scheme="isbn13", value="9780593230572", work_id=work["id"])
    db.upsert_work_identifier(scheme="ol_work", value="OL27326673W", work_id=work["id"])
    db.upsert_edition(
        {
            "id": "ed-audio",
            "work_id": work["id"],
            "kind": "audiobook",
            "asin": "B09LISTEN",
            "format": "Audiobook",
        }
    )

    exported = client.get(
        "/api/browse/export.csv",
        params={"columns": "title,title_sort,author_sort,work_id,isbn13,asin,ol_work"},
    )
    assert exported.status_code == 200
    table = _csv_rows(exported)
    assert table[0] == ["title", "title_sort", "author_sort", "work_id", "isbn13", "asin", "ol_work"]
    assert table[1] == [
        "The 1619 Project",
        title_sort("The 1619 Project"),
        sort_name("Nikole Hannah-Jones"),
        work["id"],
        "9780593230572",
        "B09LISTEN",
        "OL27326673W",
    ]
    assert table[1][1].startswith("0000001619")
    assert table[1][2].startswith("Hannah-Jones")
    assert "SECRET-RAW-ISBN" not in exported.text
    assert "SECRET-RAW-ASIN" not in exported.text
    assert "secret-folder" not in exported.text
