"""Indexer scorecard — lantern weather + mute without deleting."""

from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from librarian.config import Settings, load_merged_settings, save_settings
from librarian.indexer_scorecard import (
    LANTERN_BRIGHT,
    LANTERN_DARK,
    LANTERN_MUTED,
    assemble_indexer_scorecard,
    catalog_db_path,
    lantern_presence,
    lantern_weather,
    load_kind_stats,
    match_rate,
    mute_host,
    record_host_probe,
    summarize_host_stats,
)
from librarian.indexers.hosts import NZBFINDER_ID, enabled_hosts, search_beyond
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def test_lantern_weather_and_presence():
    assert lantern_weather(muted=True) == LANTERN_MUTED
    assert lantern_weather(configured=False) == "idle"
    assert lantern_weather(ok_count=3, error_count=0, last_ok_at="2026-01-01T00:00:00Z") == LANTERN_BRIGHT
    assert lantern_weather(ok_count=1, error_count=3, last_error="timeout") == LANTERN_DARK
    assert lantern_weather(
        ok_count=1,
        error_count=4,
        last_ok_at="2026-10-23T18:50:00Z",
        last_error="",
    ) == LANTERN_BRIGHT
    assert lantern_weather(
        ok_count=1,
        error_count=4,
        empty_count=1,
        last_ok_at="2026-10-23T18:50:00Z",
        last_error="",
    ) == "dim"
    assert "host failed" not in lantern_presence(LANTERN_BRIGHT, name="DrunkenSlug")
    assert "rests muted" in lantern_presence(LANTERN_MUTED, name="NZBFinder")
    assert "burns steady" in lantern_presence(LANTERN_BRIGHT, name="NZBFinder")


def test_match_rate_is_hits_over_spoken():
    assert match_rate(8, 2) == 0.8
    assert match_rate(0, 0) is None
    assert match_rate(0, 4) == 0.0


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
    assert unmuted.json()["lanterns"][0]["stats"]["searches"] == 0
    assert unmuted.json()["lanterns"][0]["stats"]["by_kind"] == []


def test_kind_stats_persist_in_sqlite_and_scorecard(tmp_path: Path):
    settings = Settings(
        nzbfinder_url="https://nzbfinder.ws",
        nzbfinder_api_token="tok",
        extra_indexers=[
            {
                "id": "slug",
                "name": "DrunkenSlug",
                "url": "https://drunkenslug.com",
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
        hit_count=3,
        kind="book",
    )
    record_host_probe(
        tmp_path,
        host_id=NZBFINDER_ID,
        host_name="NZBFinder",
        ok=True,
        hit_count=0,
        kind="book",
    )
    record_host_probe(
        tmp_path,
        host_id=NZBFINDER_ID,
        host_name="NZBFinder",
        ok=True,
        hit_count=2,
        kind="audiobook",
    )
    record_host_probe(
        tmp_path,
        host_id="slug",
        host_name="DrunkenSlug",
        ok=False,
        error="429 Too Many Requests",
        rate_limited=True,
        kind="comic",
    )
    record_host_probe(
        tmp_path,
        host_id=NZBFINDER_ID,
        host_name="NZBFinder",
        ok=True,
        hit_count=1,
        kind="movie",
    )
    assert catalog_db_path(tmp_path).is_file()
    stored = load_kind_stats(tmp_path)
    nzb_kinds = {row["kind"]: row for row in stored[NZBFINDER_ID]}
    assert nzb_kinds["book"]["searches"] == 2
    assert nzb_kinds["book"]["hits"] == 1
    assert nzb_kinds["book"]["empty"] == 1
    assert nzb_kinds["book"]["match_rate"] == 0.5
    assert nzb_kinds["audiobook"]["hits"] == 1
    assert "movie" in nzb_kinds

    card = assemble_indexer_scorecard(tmp_path, settings)
    by_id = {row["id"]: row for row in card["lanterns"]}
    nzb = by_id[NZBFINDER_ID]["stats"]
    assert nzb["hits"] == 2
    assert nzb["empty"] == 1
    assert nzb["match_rate"] == round(2 / 3, 4)
    labels = [row["label"] for row in nzb["by_kind"]]
    assert labels == ["Books", "Audiobooks"]
    slug = by_id["slug"]["stats"]
    assert slug["searches"] == 1
    assert slug["errors"] == 1
    assert slug["rate_limited"] == 1
    assert slug["match_rate"] is None
    assert slug["by_kind"][0]["label"] == "Comics"

    extra_on = Settings(
        nzbfinder_url="https://nzbfinder.ws",
        nzbfinder_api_token="tok",
        show_extra_categories=True,
    )
    extra_card = assemble_indexer_scorecard(tmp_path, extra_on)
    extra_labels = [row["label"] for row in extra_card["lanterns"][0]["stats"]["by_kind"]]
    assert "Movies" in extra_labels


def test_summarize_ignores_hostile_kind_rows():
    summary = summarize_host_stats(
        [
            {"kind": "book", "searches": 4, "hits": 3, "empty": 1, "errors": 0, "rate_limited": 0},
            {"kind": "<script>", "searches": 9, "hits": 9, "empty": 0},
            "nope",
        ]
    )
    assert [row["kind"] for row in summary["by_kind"]] == ["book"]
    assert summary["match_rate"] == 0.75


def test_search_beyond_records_kind_stats(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        if "Dune" in str(request.url) or "dune" in str(request.url).lower():
            return httpx.Response(
                200,
                json={"results": [{"title": "Dune", "guid": "g-dune", "category": 7020}]},
            )
        if "empty" in str(request.url).lower() or "Quiet" in str(request.url):
            return httpx.Response(200, json={"results": []})
        return httpx.Response(200, json={"results": []})

    settings = Settings(
        nzbfinder_url="https://nzbfinder.example",
        nzbfinder_api_token="tok",
    )
    hits, error = search_beyond(
        settings,
        transport=httpx.MockTransport(handler),
        data_dir=tmp_path,
        kind="book",
        title="Dune",
    )
    assert error is None
    assert hits
    empty_hits, empty_error = search_beyond(
        settings,
        transport=httpx.MockTransport(handler),
        data_dir=tmp_path,
        kind="book",
        title="Quiet",
    )
    assert empty_error is None
    assert empty_hits == []
    stored = load_kind_stats(tmp_path)[NZBFINDER_ID]
    book = next(row for row in stored if row["kind"] == "book")
    assert book["searches"] == 2
    assert book["hits"] == 1
    assert book["empty"] == 1
    assert book["match_rate"] == 0.5


def test_search_beyond_records_errors_by_kind(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "rate limited"})

    settings = Settings(
        nzbfinder_url="https://nzbfinder.example",
        nzbfinder_api_token="tok",
    )
    hits, error = search_beyond(
        settings,
        transport=httpx.MockTransport(handler),
        data_dir=tmp_path,
        kind="audiobook",
        title="Dune",
        author="Herbert",
    )
    assert hits == []
    assert error
    stored = load_kind_stats(tmp_path)[NZBFINDER_ID]
    audio = next(row for row in stored if row["kind"] == "audiobook")
    assert audio["searches"] == 1
    assert audio["errors"] == 1
    assert audio["rate_limited"] == 1
    assert audio["match_rate"] is None
