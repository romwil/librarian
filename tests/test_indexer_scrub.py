"""P3-CRIT-02 — public indexer scrub drops tokens and raw Newznab blobs."""

from __future__ import annotations

from librarian.indexers.rank import compact_candidate, remember_candidates
from librarian.indexers.scrub import (
    public_indexer_hit,
    public_indexer_hits,
    public_job,
    public_job_payload,
)


def _leaky_hit(**extra):
    row = {
        "guid": "g-dune",
        "title": "Herbert-Dune-ebook",
        "book_title": "Dune",
        "author": "Frank Herbert",
        "kind": "book",
        "download_url": "https://nzb.example/get?id=g-dune.nzb&api_token=secret-tok&apikey=secret-tok",
        "link": "https://nzb.example/details?id=1&apikey=secret-tok",
        "cover": "https://cdn.example/cover.jpg?api_token=cover-tok",
        "raw": {"enclosure": "https://nzb.example/get?api_token=secret-tok", "attrs": {"x": 1}},
        "description": "full HTML dump",
        "host_id": "nzbfinder",
        "host_name": "NZBFinder",
    }
    row.update(extra)
    return row


def test_public_indexer_hit_strips_tokens_and_drops_raw():
    scrubbed = public_indexer_hit(_leaky_hit())
    assert scrubbed is not None
    assert scrubbed["guid"] == "g-dune"
    assert scrubbed["title"] == "Herbert-Dune-ebook"
    assert "api_token" not in scrubbed["download_url"]
    assert "apikey" not in scrubbed["download_url"]
    assert "secret-tok" not in scrubbed["download_url"]
    assert "apikey" not in scrubbed["link"]
    assert "api_token" not in scrubbed["cover"]
    assert "raw" not in scrubbed
    assert "description" not in scrubbed
    assert "secret-tok" not in str(scrubbed)
    assert scrubbed["download_url"] == "https://nzb.example/get?id=g-dune.nzb"


def test_public_indexer_hits_skips_non_dicts():
    rows = public_indexer_hits([_leaky_hit(), "skip", None, 3, _leaky_hit(guid="g2")])
    assert len(rows) == 2
    assert rows[0]["guid"] == "g-dune"
    assert rows[1]["guid"] == "g2"
    assert all("raw" not in row for row in rows)


def test_compact_candidate_never_keeps_token_query():
    row = compact_candidate(_leaky_hit())
    assert "api_token" not in row["download_url"]
    assert "secret-tok" not in row["download_url"]
    assert "api_token" not in row.get("cover", "")
    assert "raw" not in row


def test_remember_candidates_stores_scrubbed_urls():
    rows = remember_candidates([_leaky_hit(), _leaky_hit(guid="g2")])
    assert len(rows) == 2
    blob = str(rows)
    assert "secret-tok" not in blob
    assert "api_token" not in blob
    assert "apikey" not in blob


def test_public_job_payload_scrubs_nested_selected_and_candidates():
    payload = public_job_payload(
        {
            "title": "Dune",
            "kind": "book",
            "guid": "g-dune",
            "raw": {"should": "drop"},
            "selected": {
                "guid": "g-dune",
                "download_url": "https://x.test/d?id=1&api_token=job-secret",
                "raw": {"nested": True},
            },
            "candidates": [
                {
                    "guid": "g-alt",
                    "download_url": "https://x.test/d?apikey=cand-secret&id=2",
                    "raw": {"x": 1},
                }
            ],
            "download_url": "https://x.test/top?api_token=top-secret",
        }
    )
    assert "raw" not in payload
    assert "raw" not in payload["selected"]
    assert "job-secret" not in payload["selected"]["download_url"]
    assert "api_token" not in payload["selected"]["download_url"]
    assert payload["candidates"][0]["download_url"] == "https://x.test/d?id=2"
    assert "raw" not in payload["candidates"][0]
    assert "top-secret" not in payload["download_url"]
    assert "secret" not in str(payload)


def test_public_job_wraps_payload():
    job = public_job(
        {
            "id": "j1",
            "status": "queued",
            "payload": {
                "selected": {"download_url": "https://x.test/?api_token=z", "guid": "g"},
                "raw": {"nope": 1},
            },
        }
    )
    assert job is not None
    assert job["id"] == "j1"
    assert "raw" not in job["payload"]
    assert "api_token" not in job["payload"]["selected"]["download_url"]


def test_queue_api_scrubs_leaky_job_payload(tmp_path, monkeypatch):
    """P3-CRIT-02: GET /api/queue never re-surfaces stored api_token / raw blobs."""
    from fastapi.testclient import TestClient

    from librarian.config import Settings, save_settings
    from librarian.db import Database
    from librarian.rate_limit import clear_rate_limits
    from librarian.sessions import clear_session_secret_cache
    from librarian.web.app import create_app

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    monkeypatch.setattr("librarian.config.load_dotenv", lambda path=None: None)
    save_settings(tmp_path, Settings(llm_api_key=""))
    clear_session_secret_cache()
    clear_rate_limits()
    db = Database(tmp_path / "librarian.db")
    db.create_job(
        {
            "status": "asked",
            "title": "Dune",
            "kind": "book",
            "requested_by": "owner",
            "payload": {
                "title": "Dune",
                "guid": "g-dune",
                "selected": {
                    "guid": "g-dune",
                    "download_url": "https://nzb.example/get?id=1&api_token=queue-secret",
                    "raw": {"enclosure": "https://nzb.example/?api_token=queue-secret"},
                },
                "candidates": [
                    {
                        "guid": "g-alt",
                        "download_url": "https://nzb.example/get?apikey=cand-secret&id=2",
                        "raw": {"x": 1},
                    }
                ],
                "raw": {"should": "never-leave"},
            },
        }
    )
    client = TestClient(create_app(tmp_path))
    login = client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    assert login.status_code == 200
    resp = client.get("/api/queue")
    assert resp.status_code == 200
    body = resp.json()
    blob = str(body)
    assert "queue-secret" not in blob
    assert "cand-secret" not in blob
    assert "api_token" not in blob
    assert "apikey" not in blob
    jobs = body["jobs"]
    assert jobs
    payload = jobs[0]["payload"]
    assert "raw" not in payload
    assert "raw" not in payload["selected"]
    assert payload["selected"]["download_url"] == "https://nzb.example/get?id=1"
    assert payload["candidates"][0]["download_url"] == "https://nzb.example/get?id=2"
    assert "raw" not in payload["candidates"][0]
