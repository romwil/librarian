"""API exposure of owned multipart part_set (B3)."""

from fastapi.testclient import TestClient

from librarian.db import Database
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    clear_rate_limits()
    return TestClient(create_app(tmp_path))


def _login(client):
    resp = client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    assert resp.status_code == 200


def test_work_detail_exposes_incomplete_part_set(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "audiobook",
            "title": "Magician",
            "author": "Feist",
            "part_total": 5,
            "part_style": "part",
            "part_base": "Raymond E Feist Magician",
        }
    )
    db.add_file(
        {
            "work_id": work["id"],
            "path": str(tmp_path / "Magician Part 3.m4b"),
            "filename": "Magician Part 3.m4b",
            "kind": "audiobook",
            "part": 3,
        }
    )
    (tmp_path / "Magician Part 3.m4b").write_bytes(b"m4b")
    resp = client.get(f"/api/works/{work['id']}")
    assert resp.status_code == 200
    body = resp.json()
    part_set = body["work"]["part_set"]
    assert part_set["total"] == 5
    assert part_set["owned"] == [3]
    assert part_set["style"] == "part"
    assert "Magician" in part_set["base"]


def test_hall_gaps_include_multipart_cards(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "audiobook",
            "title": "Magician",
            "author": "Feist",
            "part_total": 5,
            "part_style": "part",
            "part_base": "Raymond E Feist Magician",
        }
    )
    db.add_file(
        {
            "work_id": work["id"],
            "path": "/virt/Magician Part 3.m4b",
            "filename": "Magician Part 3.m4b",
            "kind": "audiobook",
            "part": 3,
        }
    )
    hall = client.get("/api/hall").json()
    multipart = [card for card in hall.get("gaps") or [] if card.get("gap_type") == "multipart"]
    assert multipart
    assert {card["missing_index"] for card in multipart} >= {"1", "2", "4", "5"}
    assert all(card["part_set"]["total"] == 5 for card in multipart)
