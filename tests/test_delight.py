"""Focused tests for Part E delight helpers and API."""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from librarian.auth import hash_password
from librarian.db import Database
from librarian.delight import (
    celebration_candidates,
    cover_story,
    estimate_finish_eta_minutes,
    finish_set_label,
    in_quiet_hours,
    normalize_ambient,
    pick_fast_gap,
    plexamp_handoff,
    rank_regrab_candidates,
    sanitize_whisper,
    series_ribbon,
    tonight_shelf,
)
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def test_cover_story_prefers_llm_blurb_two_sentences():
    story = cover_story(
        {
            "llm_blurb": "First sentence. Second sentence. Third ignored.",
            "description": "Ignored HTML <b>desc</b>.",
        }
    )
    assert story == "First sentence. Second sentence."


def test_tonight_shelf_picks_continue_gap_surprise():
    shelf = tonight_shelf(
        continue_items=[{"id": "c1", "title": "Cont"}],
        gaps=[{"title": "Gap", "series_missing": ["2", "3"], "missing_index": "2"}],
        surprise={"id": "s1", "title": "Surprise"},
    )
    assert shelf["continue"]["id"] == "c1"
    assert shelf["gap"]["title"] == "Gap"
    assert shelf["surprise"]["id"] == "s1"
    assert shelf["empty"] is False


def test_pick_fast_gap_prefers_smaller_hole():
    best = pick_fast_gap(
        [
            {"title": "big", "series_missing": ["1", "2", "3", "4"]},
            {"title": "small", "series_missing": ["7"]},
        ]
    )
    assert best["title"] == "small"


def test_series_ribbon_states():
    beads = series_ribbon(owned_indexes=["1", "2"], missing_indexes=["3"], current="3")
    assert [b["state"] for b in beads] == ["owned", "owned", "current"]


def test_quiet_hours_overnight_window():
    settings = SimpleNamespace(
        quiet_hours_enabled=True,
        quiet_hours_start="22:00",
        quiet_hours_end="07:00",
    )
    assert in_quiet_hours(settings, now=datetime(2026, 1, 1, 23, 0)) is True
    assert in_quiet_hours(settings, now=datetime(2026, 1, 1, 6, 0)) is True
    assert in_quiet_hours(settings, now=datetime(2026, 1, 1, 12, 0)) is False


def test_estimate_finish_eta_and_label():
    minutes = estimate_finish_eta_minutes(missing_count=2, recent_seconds=[120, 180, 240])
    assert minutes == 6
    assert "Request missing (2)" in finish_set_label(missing_count=2, eta_minutes=minutes)


def test_rank_regrab_skips_failed_guid():
    ranked = rank_regrab_candidates(
        [
            {"guid": "a", "title": "Same"},
            {"guid": "b", "title": "Alt", "size": 2_000_000, "host": "nzb.example"},
        ],
        failed_guid="a",
    )
    assert len(ranked) == 1
    assert ranked[0]["guid"] == "b"
    assert "Alt" in ranked[0]["diff"]


def test_plexamp_handoff_never_audiobook():
    assert plexamp_handoff({"kind": "audiobook", "title": "Book"}) is None
    handoff = plexamp_handoff({"kind": "music", "title": "LP", "author": "Band", "id": "1", "cover_path": "/x"})
    assert handoff["href"] == "plexamp://"
    assert handoff["has_cover"] is True


def test_ambient_and_whisper_sanitize():
    assert normalize_ambient("LAMP") == "lamp"
    assert normalize_ambient("neon") == "off"
    assert len(sanitize_whisper("  hello   " * 40)) <= 280


def test_celebration_candidates_comics_and_author():
    notes = celebration_candidates(
        kind_counts={"comic": 100, "book": 10},
        author_year_counts=[{"author": "Feist", "count": 3, "year": 2026}],
    )
    assert any("comics" in n["key"] for n in notes)
    assert any("Feist" in n["message"] for n in notes)


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    clear_rate_limits()
    return TestClient(create_app(tmp_path))


def test_prefs_whispers_quiet_hours_api(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"}).status_code == 200

    prefs = client.get("/api/prefs")
    assert prefs.status_code == 200
    assert prefs.json()["ambient"] == "off"
    saved = client.put("/api/prefs", json={"ambient": "paper"})
    assert saved.status_code == 200
    assert saved.json()["ambient"] == "paper"

    quiet = client.put(
        "/api/settings/quiet-hours",
        json={"quiet_hours_enabled": True, "quiet_hours_start": "21:00", "quiet_hours_end": "06:00"},
    )
    assert quiet.status_code == 200
    assert quiet.json()["quiet_hours_enabled"] is True

    db = Database(Path(tmp_path) / "librarian.db")
    work = db.upsert_work({"kind": "book", "title": "Whispered", "author": "A"})
    posted = client.post(f"/api/works/{work['id']}/whispers", json={"body": "Leave on the table"})
    assert posted.status_code == 200
    assert posted.json()["whisper"]["body"] == "Leave on the table"
    listed = client.get(f"/api/works/{work['id']}/whispers")
    assert listed.status_code == 200
    assert len(listed.json()["whispers"]) == 1

    hall = client.get("/api/hall")
    assert hall.status_code == 200
    body = hall.json()
    assert "tonight" in body
    assert "celebrations" in body

    detail = client.get(f"/api/works/{work['id']}")
    assert detail.status_code == 200
    assert "whispers" in detail.json()
    assert "series_ribbon" in detail.json()


def test_reader_can_set_ambient_and_whisper(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    minted = client.post("/api/invites", json={"role": "reader"})
    token = minted.json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert (
        client.post(
            "/api/invites/redeem/local",
            json={"token": token, "username": "reader1", "password": "password123"},
        ).status_code
        == 200
    )
    assert client.put("/api/prefs", json={"ambient": "lamp"}).status_code == 200
    assert client.put("/api/settings/quiet-hours", json={"quiet_hours_enabled": True}).status_code == 403

    db = Database(Path(tmp_path) / "librarian.db")
    work = db.upsert_work({"kind": "comic", "title": "Issue", "author": "X"})
    assert client.post(f"/api/works/{work['id']}/whispers", json={"body": "Nice art"}).status_code == 200


def test_db_prefs_and_celebrations(tmp_path):
    db = Database(tmp_path / "librarian.db")
    user = db.create_local_user(
        user_id="u1",
        display_name="will",
        password_hash=hash_password("password123"),
        role="owner",
    )
    prefs = db.set_user_prefs(user["id"], ambient="paper")
    assert prefs["ambient"] == "paper"
    for _ in range(10):
        db.upsert_work({"kind": "comic", "title": f"C{_}", "author": "Z"})
    notes = celebration_candidates(kind_counts=db.kind_counts(), author_year_counts=[])
    unseen = db.unseen_celebrations(user["id"], notes)
    if unseen:
        db.mark_celebration_seen(user["id"], unseen[0]["key"])
        assert db.unseen_celebrations(user["id"], notes) != unseen
