from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def _client(tmp_path, monkeypatch, settings=None):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    if settings is not None:
        save_settings(tmp_path, settings)
    app = create_app(tmp_path)
    client = TestClient(app)
    assert client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"}).status_code == 200
    return client, app


def test_review_list_fills_folder_from_job_storage(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    db = app.state.db
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Christine Stephen King",
            "author": "Christine Dougherty",
            "review_state": "needs_review",
            "review_reason": "no_payload",
        }
    )
    db.create_job(
        {
            "status": "review",
            "work_id": work["id"],
            "title": "Christine - Stephen King",
            "kind": "book",
            "storage_path": "/downloads/books/Christine - Stephen King/Christine - Stephen King.epub",
        }
    )
    listed = client.get("/api/review")
    assert listed.status_code == 200
    row = listed.json()["works"][0]
    assert row["review_reason"] == "no_payload"
    assert row["storage_path"].endswith("Christine - Stephen King.epub")
    assert row["folder_path"].endswith("Christine - Stephen King.epub")


def test_review_apply_no_payload_is_400(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    db = app.state.db
    empty = tmp_path / "empty-release"
    empty.mkdir()
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Mystery",
            "review_state": "needs_review",
            "review_reason": "no_payload",
            "folder_path": str(empty),
        }
    )
    resp = client.post(
        f"/api/review/{work['id']}/apply",
        json={"title": "Mystery", "author": "Someone", "kind": "book", "folder": str(empty)},
    )
    assert resp.status_code == 400
    assert "cannot invent" in resp.json()["detail"]


def test_review_apply_identity_organizes(tmp_path, monkeypatch):
    settings = Settings(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "magazines"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "audiobooks"),
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
    )
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    folder = tmp_path / "complete" / "Mystery.Release"
    folder.mkdir(parents=True)
    (folder / "book.epub").write_bytes(b"epub")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Mystery",
            "review_state": "needs_review",
            "review_reason": "unknown_identity",
            "folder_path": str(folder),
        }
    )
    resp = client.post(
        f"/api/review/{work['id']}/apply",
        json={
            "title": "The Return of the King",
            "author": "J. R. R. Tolkien",
            "isbn": "9780000000000",
            "kind": "book",
            "folder": str(folder),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["organized"] is True
    stored = db.get_work(work["id"])
    assert stored["title"] == "The Return of the King"
    assert stored["review_state"] == "none"
