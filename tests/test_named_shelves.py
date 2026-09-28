"""Named household shelves — living collections beyond Favorites."""

from fastapi.testclient import TestClient

from librarian.db import Database
from librarian.named_shelves import normalize_shelf_name, shelf_name_ok, shelf_presence
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def test_shelf_name_helpers():
    assert shelf_name_ok("Beach")
    assert not shelf_name_ok("Favorites")
    assert not shelf_name_ok("  ")
    assert normalize_shelf_name("  Kids   comics ") == "Kids comics"
    assert "Name a shelf" in shelf_presence([])


def test_named_shelf_db_and_hall(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    clear_rate_limits()

    db = Database(tmp_path / "librarian.db")
    owner = db.create_local_user(
        user_id="local-owner",
        display_name="owner",
        password_hash="x$y",
        role="owner",
    )
    work = db.upsert_work(
        {"id": "w-beach", "title": "Summer Read", "kind": "book", "author": "A. Lamp", "review_state": "none"}
    )
    db.add_file(
        {
            "work_id": work["id"],
            "path": str(tmp_path / "Summer.epub"),
            "filename": "Summer.epub",
            "kind": "book",
            "size": 12,
        }
    )
    (tmp_path / "Summer.epub").write_bytes(b"epub")

    shelf = db.create_named_shelf(owner["id"], "Beach", shared=True)
    assert shelf["name"] == "Beach"
    assert shelf["shared"] is True
    assert db.add_to_named_shelf(shelf["id"], owner["id"], work["id"]) is True
    works = db.shelf_works(shelf["id"])
    assert len(works) == 1
    assert works[0]["id"] == work["id"]

    # API path uses env-seeded owner (separate from the db helper above).
    client = TestClient(create_app(tmp_path))
    login = client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    assert login.status_code == 200
    created = client.post("/api/shelves", json={"name": "Kids comics", "shared": True})
    assert created.status_code == 200
    assert created.json()["shelf"]["name"] == "Kids comics"
    hall = client.get("/api/hall")
    assert hall.status_code == 200
    names = [row["name"] for row in hall.json().get("named_shelves") or []]
    assert "Kids comics" in names
