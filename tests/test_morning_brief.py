"""Morning desk ranking — tend these three, never a KPI strip."""

from __future__ import annotations

from fastapi.testclient import TestClient

from librarian.morning_brief import assemble_morning_brief, morning_brief, morning_tend_presence
from librarian.web.app import create_app


def test_morning_tend_presence_never_scores():
    assert morning_tend_presence(0) == "The shelves are quiet this morning."
    assert morning_tend_presence(1) == "Tend this one."
    assert morning_tend_presence(2) == "Tend these two."
    assert morning_tend_presence(3) == "Tend these three."


def test_morning_brief_empty_when_nothing_to_tend():
    payload = morning_brief()
    assert payload["empty"] is True
    assert payload["items"] == []
    assert "quiet" in payload["presence"].lower()


def test_morning_brief_prefers_locked_roots_then_holds_desk():
    payload = morning_brief(
        locked_roots=2,
        holds_desk_slips=5,
        extra_files=4,
        unshelved_shells=3,
        comic_book_blends=9,
    )
    assert payload["empty"] is False
    kinds = [item["kind"] for item in payload["items"]]
    assert kinds == ["shelf_health", "holds_desk", "extra_files"]
    assert payload["items"][0]["label"] == "Shelf health"
    assert payload["items"][1]["label"] == "Holds desk"
    assert "lamp" in payload["items"][0]["presence"].lower()


def test_morning_brief_stuck_jobs_breathe_first():
    payload = morning_brief(
        stuck_jobs=[{"id": "scan", "label": "Scan is walking the shelves", "detail": "roots"}],
        locked_roots=2,
        holds_desk_slips=5,
        extra_files=4,
    )
    kinds = [item["kind"] for item in payload["items"]]
    assert kinds == ["stuck_job", "shelf_health", "holds_desk"]
    assert payload["items"][0]["breathing"] is True


def test_morning_brief_honours_limit_and_skips_zero_counts():
    payload = morning_brief(
        locked_roots=0,
        holds_desk_slips=1,
        extra_files=0,
        unshelved_shells=2,
        comic_book_blends=3,
        limit=2,
    )
    kinds = [item["kind"] for item in payload["items"]]
    assert kinds == ["holds_desk", "unshelved_shells"]
    assert morning_brief(holds_desk_slips=1, limit=0)["empty"] is True


def test_assemble_morning_brief_reads_locked_count():
    payload = assemble_morning_brief(
        shelf_health={"locked_count": 1, "ok": False},
        holds_desk_slips=0,
        extra_files=2,
    )
    assert [item["kind"] for item in payload["items"]] == ["shelf_health", "extra_files"]


def test_maintain_morning_brief_owner_only(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/maintain/morning-brief")
    assert response.status_code == 401

    login = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
    )
    assert login.status_code == 200
    response = client.get("/api/maintain/morning-brief")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "empty" in body
    assert "presence" in body
    assert isinstance(body["items"], list)
    assert len(body["items"]) <= 3
