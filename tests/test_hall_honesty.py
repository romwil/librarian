"""Hall payload honesty, robots, and model-picks toggle."""

from __future__ import annotations

from fastapi.testclient import TestClient

from librarian.asks import public_asks
from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.noted import MODEL_PICKS_ORIGIN_LABEL, cached_noted_desk
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    monkeypatch.setattr("librarian.config.load_dotenv", lambda path=None: None)
    save_settings(tmp_path, Settings(llm_api_key=""))
    clear_session_secret_cache()
    clear_rate_limits()
    return TestClient(create_app(tmp_path))


def test_hall_omits_dead_keys_and_exposes_chips(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"}).status_code == 200
    db = Database(tmp_path / "librarian.db")
    try:
        work = db.upsert_work({"kind": "book", "title": "The Left Hand of Darkness", "author": "Ursula K. Le Guin"})
        folder = tmp_path / str(work["id"])
        folder.mkdir()
        path = folder / "left.epub"
        path.write_bytes(b"epub")
        db.upsert_work({**work, "folder_path": str(folder)})
        db.upsert_file(
            {
                "work_id": work["id"],
                "path": str(path),
                "filename": path.name,
                "kind": "book",
                "size": 4,
            }
        )
        user = client.get("/api/auth/me").json()["user"]
        shelf = db.create_named_shelf(user["id"], "Bedside", shared=True)
        db.add_to_named_shelf(shelf["id"], user["id"], work["id"])
    finally:
        db.close()
    hall = client.get("/api/hall")
    assert hall.status_code == 200
    body = hall.json()
    assert "areas" not in body
    assert "celebrations" not in body
    assert "tonight" not in body
    assert body["kind_counts"]["book"] >= 1
    names = [row["name"] for row in body["named_shelves"]]
    assert "Bedside" in names
    bedside = next(row for row in body["named_shelves"] if row["name"] == "Bedside")
    assert bedside["work_count"] == 1
    assert "works" not in bedside


def test_robots_txt_and_noindex_header(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "Disallow: /" in robots.text
    assert robots.headers.get("x-robots-tag") == "noindex, nofollow"
    health = client.get("/api/health")
    assert health.headers.get("x-robots-tag") == "noindex, nofollow"


def test_model_picks_hidden_until_toggle(tmp_path):
    db = Database(tmp_path / "library.db")
    try:
        hidden = cached_noted_desk(db, Settings(), data_dir=tmp_path)
        assert all(not row["id"].startswith("nyt-") for row in hidden["lanes"])
        shown = cached_noted_desk(
            db, Settings(show_model_suggested_lists=True), data_dir=tmp_path
        )
        lane = next(row for row in shown["lanes"] if row["id"] == "nyt-hardcover-fiction")
        assert lane["label"].startswith("Model picks")
        assert lane["origin_label"] in {"", MODEL_PICKS_ORIGIN_LABEL}
    finally:
        db.close()


def test_public_asks_labels():
    looking = public_asks(
        [{"id": "j1", "title": "Kindred", "kind": "audiobook", "status": "asked", "payload": {"source": "ask"}}]
    )
    assert looking[0]["label"] == "Looking"
    waiting = public_asks(
        [
            {
                "id": "j2",
                "title": "Kindred",
                "kind": "audiobook",
                "status": "asked",
                "indexer_guid": "guid-1",
                "payload": {},
            }
        ]
    )
    assert waiting[0]["label"] == "Waiting for the owner"
    arrived = public_asks(
        [
            {
                "id": "j3",
                "title": "Kindred",
                "kind": "audiobook",
                "status": "organized",
                "work_id": "w1",
                "payload": {},
            }
        ]
    )
    assert arrived[0]["label"] == "On the shelf"
    assert arrived[0]["href"] == "/works/w1"
