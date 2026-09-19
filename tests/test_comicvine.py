"""ComicVine client — mocked HTTP, real SQLite cache."""

from __future__ import annotations

import json

import httpx
import pytest

from librarian.comicvine import ComicVineCache, ComicVineClient, score_volume_match


def _handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    assert "api_key=" in url
    if "/search/" in url:
        return httpx.Response(
            200,
            json={
                "status_code": 1,
                "error": "OK",
                "results": [
                    {
                        "id": 10,
                        "name": "Moon Knight",
                        "start_year": "1980",
                        "publisher": {"name": "Marvel"},
                        "site_detail_url": "https://comicvine.example/vol/10",
                    },
                    {
                        "id": 20,
                        "name": "Moon Knight",
                        "start_year": "2014",
                        "publisher": {"name": "Marvel"},
                        "site_detail_url": "https://comicvine.example/vol/20",
                    },
                ],
            },
        )
    if "/volume/4050-10/" in url:
        return httpx.Response(
            200,
            json={
                "status_code": 1,
                "error": "OK",
                "results": {
                    "id": 10,
                    "name": "Moon Knight",
                    "start_year": "1980",
                    "publisher": {"name": "Marvel"},
                    "issues": [{"id": 100, "issue_number": "1", "name": "The Bottom"}],
                },
            },
        )
    if "/volume/4050-20/" in url:
        return httpx.Response(
            200,
            json={
                "status_code": 1,
                "error": "OK",
                "results": {
                    "id": 20,
                    "name": "Moon Knight",
                    "start_year": "2014",
                    "publisher": {"name": "Marvel"},
                    "issues": [{"id": 200, "issue_number": "1", "name": "Welcome to New York"}],
                },
            },
        )
    if "/issue/4000-100/" in url:
        return httpx.Response(
            200,
            json={
                "status_code": 1,
                "error": "OK",
                "results": {
                    "id": 100,
                    "name": "The Bottom",
                    "issue_number": "1",
                    "cover_date": "1980-11-01",
                    "description": "<p>Fist of Khonshu.</p>",
                    "site_detail_url": "https://comicvine.example/issue/100",
                    "volume": {"id": 10, "name": "Moon Knight"},
                    "publisher": {"name": "Marvel"},
                    "person_credits": [{"name": "Doug Moench", "role": "writer"}],
                    "image": {"super_url": "https://comicvine.example/cover.jpg"},
                },
            },
        )
    if "/issue/4000-200/" in url:
        return httpx.Response(
            200,
            json={
                "status_code": 1,
                "error": "OK",
                "results": {
                    "id": 200,
                    "name": "Welcome to New York",
                    "issue_number": "1",
                    "cover_date": "2014-04-01",
                    "description": "",
                    "site_detail_url": "https://comicvine.example/issue/200",
                    "volume": {"id": 20, "name": "Moon Knight"},
                    "publisher": {"name": "Marvel"},
                    "person_credits": [],
                    "image": {},
                },
            },
        )
    return httpx.Response(404, json={"error": "missing"})


def test_volume_year_beats_cover_year(tmp_path):
    transport = httpx.MockTransport(_handler)
    client = ComicVineClient(
        "test-key",
        transport=transport,
        cache_path=tmp_path / "cv.db",
        rate_limit=False,
    )
    try:
        matched = client.match_issue("Moon Knight", "1", volume_year=1980, cover_year=2014)
    finally:
        client.close()
    assert matched["band"] == "high"
    assert matched["best"]["volume_id"] == 10
    assert matched["best"]["year"] == 1980
    assert matched["best"]["writer"] == "Doug Moench"
    assert len(matched["candidates"]) >= 2


def test_score_volume_match_prefers_start_year():
    vol_1980 = {"name": "Moon Knight", "start_year": 1980}
    vol_2014 = {"name": "Moon Knight", "start_year": 2014}
    assert score_volume_match(
        query_name="Moon Knight", volume=vol_1980, volume_year=1980, issue="1", issue_indexes=["1"]
    ) > score_volume_match(
        query_name="Moon Knight", volume=vol_2014, volume_year=1980, issue="1", issue_indexes=["1"]
    )


def test_sqlite_cache_roundtrip(tmp_path):
    cache = ComicVineCache(tmp_path / "cv.db")
    cache.set("k1", {"status_code": 1, "results": [{"id": 1}]})
    assert cache.get("k1")["results"][0]["id"] == 1
