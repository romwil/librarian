"""House pulse: household aggregates, no member ids, no analytics SDK."""

import time
from pathlib import Path

from fastapi.testclient import TestClient

from librarian.auth import hash_password
from librarian.db import Database
from librarian.pulse import (
    FORBIDDEN_COLUMNS,
    assemble_pulse,
    increment,
    metrics_columns,
    snapshot_pulse,
)
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.wanted import add_wanted
from librarian.web.app import create_app

ANALYTICS_MARKERS = (
    "google-analytics",
    "gtag",
    "posthog",
    "plausible",
    "mixpanel",
    "sentry",
    "@sentry",
    "segment",
)


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    clear_rate_limits()
    return TestClient(create_app(tmp_path))


def test_metrics_daily_has_no_member_columns(tmp_path):
    db = Database(tmp_path / "librarian.db")
    names = {name.lower() for name in metrics_columns(db)}
    assert names == {"day", "version", "metric", "dim", "count", "sum_ms"}
    assert names.isdisjoint(FORBIDDEN_COLUMNS)
    increment(db, "unknown-metric", dim="user_id=abc")
    with db._connect() as conn:
        row = conn.execute(
            "SELECT metric, dim, count FROM metrics_daily"
        ).fetchone()
    assert row["metric"] == "other"
    assert row["dim"] == ""
    assert "ip" not in names
    assert "user_id" not in names


def test_north_star_suppressed_under_three_members(tmp_path):
    db = Database(tmp_path / "librarian.db")
    owner = db.create_local_user(
        user_id="u-owner",
        display_name="owner",
        role="owner",
        password_hash=hash_password("password123"),
    )
    work = db.upsert_work({"kind": "book", "title": "Dune", "author": "Herbert", "review_state": "none"})
    db.upsert_progress(user_id=owner["id"], work_id=work["id"], fraction=0.4)
    pulse = assemble_pulse(db, data_dir=tmp_path)
    assert pulse["north_star"]["suppressed"] is True
    assert pulse["north_star"]["display"] == "fewer than 3"
    assert pulse["north_star"]["value"] is None
    assert pulse["north_star"]["member_count"] == 1
    assert pulse["analytics_hosts"] == 0


def test_north_star_counts_volumes_when_three_members(tmp_path):
    db = Database(tmp_path / "librarian.db")
    users = []
    for name in ("owner", "ada", "gus"):
        users.append(
            db.create_local_user(
                user_id=f"u-{name}",
                display_name=name,
                role="reader" if name != "owner" else "owner",
                password_hash=hash_password("password123"),
            )
        )
    work = db.upsert_work({"kind": "book", "title": "Dune", "author": "Herbert", "review_state": "none"})
    db.upsert_progress(user_id=users[0]["id"], work_id=work["id"], fraction=0.2)
    db.upsert_progress(user_id=users[1]["id"], work_id=work["id"], fraction=0.9)
    pulse = assemble_pulse(db, data_dir=tmp_path)
    assert pulse["north_star"]["suppressed"] is False
    assert pulse["north_star"]["value"] == 2
    assert pulse["north_star"]["display"] == "2"


def test_always_shows_asks_waiting_arrived(tmp_path):
    db = Database(tmp_path / "librarian.db")
    add_wanted(db, {"title": "Dune", "kind": "book", "author": "Herbert"})
    db.create_job({"status": "asked", "title": "Dune", "kind": "book"})
    arrived = add_wanted(db, {"title": "Children of Dune", "kind": "book", "author": "Herbert"})
    db.mark_wanted_arrived(arrived["id"], now=time.time(), work_id=None)
    pulse = assemble_pulse(db, data_dir=tmp_path)
    assert pulse["asks_filed"]["value"] == 2
    assert pulse["confirms_waiting"]["value"] == 1
    assert pulse["arrived"]["value"] == 1
    assert pulse["beyond_error_rate"]["calls"] == 0
    assert pulse["snapshot_age"]["display"] == "No backup yet"


def test_pulse_api_owner_only(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/api/pulse").status_code == 401
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    minted = client.post("/api/invites", json={"role": "reader"})
    token = minted.json()["token"]
    ok = client.get("/api/pulse")
    assert ok.status_code == 200
    body = ok.json()
    assert body["north_star"]["display"] == "fewer than 3"
    assert body["analytics_hosts"] == 0
    client.post("/api/auth/logout")
    client.cookies.clear()
    client.post(
        "/api/invites/redeem/local",
        json={"token": token, "username": "reader1", "password": "password123"},
    )
    assert client.get("/api/pulse").status_code == 403


def test_snapshot_replaces_today_and_keeps_no_user_ids(tmp_path):
    db = Database(tmp_path / "librarian.db")
    snapshot_pulse(db, data_dir=tmp_path)
    snapshot_pulse(db, data_dir=tmp_path)
    with db._connect() as conn:
        rows = conn.execute("SELECT metric, dim, count FROM metrics_daily").fetchall()
        blob = " ".join(f"{row['metric']}:{row['dim']}:{row['count']}" for row in rows)
    assert "user" not in blob
    asks = [row["count"] for row in rows if row["metric"] == "asks_filed"]
    assert asks == [0]


def test_no_third_party_analytics_in_frontend_manifest():
    text = Path("frontend/package.json").read_text(encoding="utf-8").lower()
    for marker in ANALYTICS_MARKERS:
        assert marker not in text
