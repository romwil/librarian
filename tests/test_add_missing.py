"""Add all missing files Wanted rows in one confirm. Owned titles are skipped."""

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.lists import file_missing_as_wanted
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def _book(db: Database, **work):
    row = db.upsert_work({"kind": "book", "review_state": "none", **work})
    db.add_file(
        {
            "work_id": row["id"],
            "path": f"/b/{row['id']}.epub",
            "filename": f"{row['id']}.epub",
            "kind": "book",
        }
    )
    return row


def test_add_missing_skips_owned_and_files_one_batch(tmp_path):
    db = Database(tmp_path / "librarian.db")
    _book(db, title="Other Title", author="Someone", isbn="9780441172719")
    _book(db, title="Dune", author="Frank Herbert")
    _book(db, title="Dune: The Butlerian Jihad", author="Brian Herbert", series_name="Legends of Dune", series_index="1")
    _book(db, title="Dune Messiah", author="Frank Herbert", series_name="Dune", series_index="2")

    result = file_missing_as_wanted(
        db,
        [
            {"title": "Wrong name", "author": "Nobody", "isbn": "9780441172719"},
            {"title": "Dune", "author": "Frank Herbert"},
            {"title": "Dune", "author": "Brian Herbert"},
            {"title": "Not the Messiah", "author": "Frank Herbert", "series_name": "Dune", "series_index": "2"},
            {"title": "Neuromancer", "author": "William Gibson"},
            {"title": "Snow Crash", "author": "Neal Stephenson"},
        ],
    )
    assert [row["title"] for row in result["filed"]] == ["Neuromancer", "Snow Crash"]
    assert result["jobs_created"] == 0
    assert len(result["skipped"]) == 4
    assert {row["reason"] for row in result["skipped"]} == {"on_shelf"}
    with db._connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM wanted").fetchone()["n"] == 2
        assert (
            conn.execute("SELECT COUNT(*) AS n FROM works WHERE review_state = 'needs_review'").fetchone()["n"]
            == 0
        )


def test_add_missing_confirm_is_one_request(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    save_settings(tmp_path, Settings(books_root=str(tmp_path / "books")))
    clear_session_secret_cache()
    clear_rate_limits()
    client = TestClient(create_app(tmp_path))
    login = client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    assert login.status_code == 200
    db = Database(tmp_path / "librarian.db")
    _book(db, title="Dune", author="Frank Herbert")

    response = client.post(
        "/api/lists/add-missing",
        json={
            "items": [
                {"title": "Dune", "author": "Frank Herbert"},
                {"title": "Neuromancer", "author": "William Gibson"},
            ]
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert [row["title"] for row in body["filed"]] == ["Neuromancer"]
    assert body["skipped"][0]["reason"] == "on_shelf"
    assert body["jobs_created"] == 0
    with db._connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM wanted").fetchone()["n"] == 1
