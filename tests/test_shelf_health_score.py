"""Shelf health score — living pulse + one tend (weather, not KPI)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from librarian.shelf_health_score import (
    assemble_shelf_health_score,
    pulse_weather,
    shelf_health_score,
)
from librarian.web.app import create_app


def test_pulse_weather_calm_when_clear():
    assert pulse_weather(locked_roots=0, other_signals=0) == "calm"


def test_pulse_weather_needs_you_beats_stirring():
    assert pulse_weather(locked_roots=1, other_signals=9) == "needs_you"
    assert pulse_weather(locked_roots=0, other_signals=2) == "stirring"


def test_shelf_health_score_calm_has_no_tend():
    score = shelf_health_score()
    assert score["pulse"] == "calm"
    assert score["ok"] is True
    assert score["tend"] is None
    assert "settled" in score["presence"].lower()
    assert score["signals"]["locked_roots"] == 0


def test_shelf_health_score_picks_one_tend_locked_first():
    score = shelf_health_score(
        locked_roots=2,
        extra_files=5,
        unshelved_shells=3,
        comic_book_blends=4,
    )
    assert score["pulse"] == "needs_you"
    assert score["ok"] is False
    assert score["tend"]["kind"] == "shelf_health"
    assert score["tend"]["cta"]
    assert "Two" in score["tend"]["presence"]
    # Presence is weather voice, not a KPI strip of every count.
    assert "5" not in score["presence"]


def test_shelf_health_score_shells_before_blends():
    score = shelf_health_score(unshelved_shells=1, comic_book_blends=9)
    assert score["pulse"] == "stirring"
    assert score["tend"]["kind"] == "unshelved_shells"
    assert "Purge" in score["tend"]["cta"]


def test_assemble_reads_locked_count():
    score = assemble_shelf_health_score(
        shelf_health={"locked_count": 1},
        extra_files=0,
        unshelved_shells=0,
        comic_book_blends=0,
    )
    assert score["tend"]["kind"] == "shelf_health"


def test_maintain_shelf_health_includes_score(tmp_path):
    client = TestClient(create_app(tmp_path))
    login = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
    )
    assert login.status_code == 200
    response = client.get("/api/maintain/shelf-health")
    assert response.status_code == 200
    body = response.json()
    assert "roots" in body
    score = body["score"]
    assert score["pulse"] in {"calm", "stirring", "needs_you"}
    assert "presence" in score
    assert "tend" in score
    assert "signals" in score
    # No numeric grade / percent — weather only.
    assert "grade" not in score
    assert "percent" not in score
    assert "value" not in score
