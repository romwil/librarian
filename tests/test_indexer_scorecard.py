"""Indexer scorecard — lantern weather + mute without deleting."""

from pathlib import Path

from fastapi.testclient import TestClient

from librarian.config import Settings, load_merged_settings, save_settings
from librarian.indexer_scorecard import (
    LANTERN_BRIGHT,
    LANTERN_DARK,
    LANTERN_MUTED,
    assemble_indexer_scorecard,
    lantern_presence,
    lantern_weather,
    mute_host,
    record_host_probe,
)
from librarian.indexers.hosts import NZBFINDER_ID, enabled_hosts
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def test_lantern_weather_and_presence():
    assert lantern_weather(muted=True) == LANTERN_MUTED
    assert lantern_weather(configured=False) == "idle"
    assert lantern_weather(ok_count=3, error_count=0, last_ok_at="2026-01-01T00:00:00Z") == LANTERN_BRIGHT
    assert lantern_weather(ok_count=1, error_count=3, last_error="timeout") == LANTERN_DARK
    assert "rests muted" in lantern_presence(LANTERN_MUTED, name="NZBFinder")
    assert "burns steady" in lantern_presence(LANTERN_BRIGHT, name="NZBFinder")


def test_record_probe_and_assemble(tmp_path: Path):
    settings = Settings(
        nzbfinder_url="https://nzbfinder.ws",
        nzbfinder_api_token="tok",
        extra_indexers=[
            {
                "id": "alt",
                "name": "Alt Host",
                "url": "https://alt.example",
                "api_token": "x",
                "enabled": True,
            }
        ],
    )
    record_host_probe(
        tmp_path,
        host_id=NZBFINDER_ID,
        host_name="NZBFinder",
        ok=True,
        latency_ms=120.5,
        hit_count=4,
    )
    record_host_probe(
        tmp_path,
        host_id="alt",
        host_name="Alt Host",
        ok=False,
        latency_ms=900,
        error="429 Too Many Requests",
        rate_limited=True,
    )
    card = assemble_indexer_scorecard(tmp_path, settings)
    assert card["ok"] is False
    by_id = {row["id"]: row for row in card["lanterns"]}
    assert by_id[NZBFINDER_ID]["weather"] == LANTERN_BRIGHT
    assert by_id["alt"]["weather"] == LANTERN_DARK
    assert "Mute" in card["presence"] or "tending" in card["presence"].lower() or "lantern" in card["presence"].lower()


def test_mute_skips_enabled_hosts(tmp_path: Path):
    settings = Settings(
        nzbfinder_url="https://nzbfinder.ws",
        nzbfinder_api_token="tok",
        extra_indexers=[
            {
                "id": "alt",
                "name": "Alt Host",
                "url": "https://alt.example",
                "api_token": "x",
                "enabled": True,
            }
        ],
    )
    assert [h["id"] for h in enabled_hosts(settings)] == [NZBFINDER_ID, "alt"]
    mute_host(settings, NZBFINDER_ID, muted=True)
    assert settings.nzbfinder_muted is True
    assert [h["id"] for h in enabled_hosts(settings)] == ["alt"]
    mute_host(settings, "alt", muted=True)
    assert enabled_hosts(settings) == []
    mute_host(settings, NZBFINDER_ID, muted=False)
    mute_host(settings, "alt", muted=False)
    assert [h["id"] for h in enabled_hosts(settings)] == [NZBFINDER_ID, "alt"]


def test_maintain_scorecard_mute_api(tmp_path, monkeypatch):
    save_settings(
        tmp_path,
        Settings(nzbfinder_url="https://nzbfinder.ws", nzbfinder_api_token="tok"),
    )
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    clear_session_secret_cache()
    clear_rate_limits()
    client = TestClient(create_app(tmp_path))
    login = client.post(
        "/api/auth/local/login",
        json={"username": "owner", "password": "password123"},
    )
    assert login.status_code == 200

    card = client.get("/api/maintain/indexer-scorecard")
    assert card.status_code == 200
    body = card.json()
    assert "lanterns" in body
    assert body["lanterns"][0]["id"] == NZBFINDER_ID
    assert body["lanterns"][0]["muted"] is False

    muted = client.post(f"/api/maintain/indexer-scorecard/{NZBFINDER_ID}/mute")
    assert muted.status_code == 200
    assert muted.json()["lanterns"][0]["muted"] is True
    assert muted.json()["lanterns"][0]["weather"] == LANTERN_MUTED
    reloaded = load_merged_settings(tmp_path)
    assert reloaded.nzbfinder_muted is True
    assert enabled_hosts(reloaded) == []

    unmuted = client.post(f"/api/maintain/indexer-scorecard/{NZBFINDER_ID}/unmute")
    assert unmuted.status_code == 200
    assert unmuted.json()["lanterns"][0]["muted"] is False
