"""PRIV-002 export checklist, PRIV-007 multi-reader isolation, PRIV-009 deletion cascade."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from librarian.db import Database
from librarian.privacy import (
    EXPORT_SCHEMA_VERSION,
    PERSONAL_DATA_REGISTRY,
    deletion_cascade_checklist,
    export_field_checklist,
    included_export_keys,
)
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


def _mint_reader(client, *, username: str) -> dict:
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    minted = client.post("/api/invites", json={"role": "reader"})
    assert minted.status_code == 200, minted.text
    token = minted.json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    redeemed = client.post(
        "/api/invites/redeem/local",
        json={"token": token, "username": username, "password": "password123"},
    )
    assert redeemed.status_code == 200, redeemed.text
    return redeemed.json()["user"]


def _login(client, username: str) -> None:
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert (
        client.post(
            "/api/auth/local/login",
            json={"username": username, "password": "password123"},
        ).status_code
        == 200
    )


def test_registry_covers_person_linked_stores():
    keys = {row["key"] for row in PERSONAL_DATA_REGISTRY}
    for required in (
        "user",
        "prefs",
        "progress",
        "shelves",
        "shelf_items",
        "whispers",
        "notifications",
        "sessions",
        "jobs_requested",
        "security_events_subject",
        "catalog_snapshots",
        "password_hash",
    ):
        assert required in keys
    assert included_export_keys() == [
        "user",
        "prefs",
        "progress",
        "shelves",
        "shelf_items",
        "whispers",
        "notifications",
    ]
    assert all(row["export"] in ("include", "exclude", "summarize") for row in PERSONAL_DATA_REGISTRY)
    assert any(row["delete"] == "age_out" for row in deletion_cascade_checklist())
    assert len(export_field_checklist()) == len(PERSONAL_DATA_REGISTRY)


def test_export_checklist_contract_and_no_cross_member(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    alice = _mint_reader(client, username="alice-export")
    bob = _mint_reader(client, username="bob-export")
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work({"kind": "book", "title": "Export Title", "author": "A"})
    db.add_file(
        {
            "work_id": work["id"],
            "path": "/b/Export.epub",
            "filename": "Export.epub",
            "kind": "book",
        }
    )
    db.upsert_progress(user_id=alice["id"], work_id=work["id"], fraction=0.33, position="ch-1")
    db.upsert_progress(user_id=bob["id"], work_id=work["id"], fraction=0.91, position="ch-9")
    private = db.create_named_shelf(alice["id"], "Alice private", shared=False)
    db.add_to_named_shelf(private["id"], alice["id"], work["id"])
    shared = db.create_named_shelf(bob["id"], "Bob shared", shared=True)
    db.add_to_named_shelf(shared["id"], bob["id"], work["id"])
    db.add_whisper(work_id=work["id"], user_id=alice["id"], body="alice note")
    db.add_whisper(work_id=work["id"], user_id=bob["id"], body="bob note")
    db.create_notification(
        notification_id=uuid.uuid4().hex,
        user_id=alice["id"],
        kind="arrived",
        title="Alice inbox",
        body="for alice",
    )
    db.create_notification(
        notification_id=uuid.uuid4().hex,
        user_id=bob["id"],
        kind="arrived",
        title="Bob inbox",
        body="for bob",
    )

    _login(client, "alice-export")
    resp = client.get("/api/auth/export")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["export_version"] == EXPORT_SCHEMA_VERSION
    assert isinstance(payload["generated_at"], (int, float))
    assert payload["exported_from"] == "librarian"
    assert [row["key"] for row in payload["checklist"]] == [row["key"] for row in PERSONAL_DATA_REGISTRY]

    for key in included_export_keys():
        assert key in payload, f"missing included category {key}"

    assert payload["user"]["display_name"] == "alice-export"
    assert payload["user"]["id"] == alice["id"]
    assert "password_hash" not in payload["user"]
    assert all(row["work_id"] == work["id"] for row in payload["progress"])
    assert all(abs(float(row["fraction"]) - 0.33) < 0.001 for row in payload["progress"])
    assert not any(abs(float(row["fraction"]) - 0.91) < 0.001 for row in payload["progress"])
    shelf_names = {row["name"] for row in payload["shelves"]}
    assert "Alice private" in shelf_names
    assert "Favorites" in shelf_names  # auto shelf on redeem
    assert "Bob shared" not in shelf_names
    assert all(row["body"] == "alice note" for row in payload["whispers"])
    assert all(row["title"] == "Alice inbox" for row in payload["notifications"])
    dumped = str(payload)
    assert "password123" not in dumped
    assert bob["id"] not in dumped
    assert "Bob inbox" not in dumped
    assert "bob note" not in dumped


def test_multi_reader_progress_isolation(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    alice = _mint_reader(client, username="alice-iso")
    bob = _mint_reader(client, username="bob-iso")
    db = Database(tmp_path / "librarian.db")
    dune = db.upsert_work({"kind": "book", "title": "Dune Iso", "author": "Herbert"})
    kindred = db.upsert_work({"kind": "book", "title": "Kindred Iso", "author": "Butler"})
    for work, path in (
        (dune, "/b/DuneIso.epub"),
        (kindred, "/b/KindredIso.epub"),
    ):
        db.add_file(
            {
                "work_id": work["id"],
                "path": path,
                "filename": path.rsplit("/", 1)[-1],
                "kind": "book",
            }
        )

    _login(client, "alice-iso")
    assert client.post(f"/api/works/{dune['id']}/progress", json={"fraction": 0.4}).status_code == 200
    assert client.post(f"/api/works/{dune['id']}/favorite").status_code == 200
    priv = client.post("/api/shelves", json={"name": "Alice alone", "shared": False})
    assert priv.status_code == 200
    alice_shelf = priv.json()["shelf"]["id"]
    assert client.post(f"/api/shelves/{alice_shelf}/works/{kindred['id']}").status_code == 200
    db.create_notification(
        notification_id=uuid.uuid4().hex,
        user_id=alice["id"],
        kind="arrived",
        title="Only Alice",
        body="secret slip",
    )

    _login(client, "bob-iso")
    assert client.post(f"/api/works/{dune['id']}/progress", json={"fraction": 0.75}).status_code == 200
    shared = client.post("/api/shelves", json={"name": "Bob open", "shared": True})
    assert shared.status_code == 200
    bob_shelf = shared.json()["shelf"]["id"]
    assert client.post(f"/api/shelves/{bob_shelf}/works/{dune['id']}").status_code == 200
    db.create_notification(
        notification_id=uuid.uuid4().hex,
        user_id=bob["id"],
        kind="arrived",
        title="Only Bob",
        body="bob slip",
    )

    # Bob work detail / Hall / card never show Alice's progress or private shelf.
    detail = client.get(f"/api/works/{dune['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert abs(float(body["progress"]["fraction"]) - 0.75) < 0.001
    assert body["favorite"] is False
    hall = client.get("/api/hall").json()
    continue_titles = [row["title"] for row in hall["continue"]]
    assert "Dune Iso" in continue_titles
    assert all(row.get("progress") != 40 for row in hall["continue"])
    fav_titles = [row["title"] for row in hall["favorites"]]
    assert "Dune Iso" not in fav_titles
    named = {row["name"]: row for row in hall["named_shelves"]}
    assert "Bob open" in named
    assert "Alice alone" not in named
    card = client.get("/api/library-card").json()
    assert [row["title"] for row in card["continue"]] == ["Dune Iso"]
    assert all(abs(float(row.get("progress") or 0) - 75) < 1 for row in card["continue"])
    bob_inbox = client.get("/api/notifications").json()
    bob_titles = {row["title"] for row in bob_inbox.get("items") or []}
    assert "Only Bob" in bob_titles
    assert "Only Alice" not in bob_titles
    export = client.get("/api/auth/export").json()
    assert export["user"]["id"] == bob["id"]
    assert all(abs(float(row["fraction"]) - 0.75) < 0.001 for row in export["progress"])
    assert not any(abs(float(row["fraction"]) - 0.4) < 0.001 for row in export["progress"])

    # Alice still isolated the other way; shared shelf content without Bob progress.
    _login(client, "alice-iso")
    alice_detail = client.get(f"/api/works/{dune['id']}").json()
    assert abs(float(alice_detail["progress"]["fraction"]) - 0.4) < 0.001
    alice_hall = client.get("/api/hall").json()
    alice_named = {row["name"] for row in alice_hall["named_shelves"]}
    assert "Alice alone" in alice_named
    assert "Bob open" in alice_named  # shared content visible
    # Shared shelf listing must not attach Bob's fraction onto Alice's rails.
    assert all(
        abs(float(row.get("progress") or 0) - 75) > 1 for row in alice_hall["continue"]
    )
    assert alice_hall["favorites"][0]["title"] == "Dune Iso"
    alice_inbox = client.get("/api/notifications").json()
    alice_titles = {row["title"] for row in alice_inbox.get("items") or []}
    assert "Only Alice" in alice_titles
    assert "Only Bob" not in alice_titles


def test_deletion_cascade_matches_registry(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    member = _mint_reader(client, username="cascade-me")
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work({"kind": "book", "title": "Cascade Book", "author": "C"})
    db.add_file(
        {
            "work_id": work["id"],
            "path": "/b/Cascade.epub",
            "filename": "Cascade.epub",
            "kind": "book",
        }
    )
    db.upsert_progress(user_id=member["id"], work_id=work["id"], fraction=0.5)
    shelf = db.create_named_shelf(member["id"], "Cascade shelf", shared=False)
    db.add_to_named_shelf(shelf["id"], member["id"], work["id"])
    db.add_whisper(work_id=work["id"], user_id=member["id"], body="gone soon")
    db.set_user_prefs(member["id"], ambient="lamp")
    db.mark_celebration_seen(member["id"], "welcome")
    note_id = uuid.uuid4().hex
    db.create_notification(
        notification_id=note_id,
        user_id=member["id"],
        kind="arrived",
        title="Cascade notice",
        from_user_id=member["id"],
    )
    job = db.create_job(
        {
            "kind": "book",
            "title": "Cascade ask",
            "status": "asked",
            "requested_by": member["id"],
        }
    )
    db.add_security_event(kind="export", user_id=member["id"], actor_id=member["id"])

    _login(client, "owner")
    paused = client.post(f"/api/people/{member['id']}/disable", json={"disabled": True})
    assert paused.status_code == 200
    with db._connect() as conn:
        active = conn.execute(
            "SELECT COUNT(*) AS n FROM sessions WHERE user_id = ? AND revoked_at IS NULL",
            (member["id"],),
        ).fetchone()
    assert int(active["n"]) == 0

    gone = client.delete(f"/api/people/{member['id']}")
    assert gone.status_code == 200
    assert db.get_user(member["id"]) is None

    uid = member["id"]
    with db._connect() as conn:
        assert int(conn.execute("SELECT COUNT(*) AS n FROM progress WHERE user_id = ?", (uid,)).fetchone()["n"]) == 0
        assert int(conn.execute("SELECT COUNT(*) AS n FROM user_prefs WHERE user_id = ?", (uid,)).fetchone()["n"]) == 0
        assert int(
            conn.execute("SELECT COUNT(*) AS n FROM shelves WHERE owner_user_id = ?", (uid,)).fetchone()["n"]
        ) == 0
        assert int(conn.execute("SELECT COUNT(*) AS n FROM shelf_items WHERE shelf_id = ?", (shelf["id"],)).fetchone()["n"]) == 0
        assert int(conn.execute("SELECT COUNT(*) AS n FROM whispers WHERE user_id = ?", (uid,)).fetchone()["n"]) == 0
        assert int(
            conn.execute("SELECT COUNT(*) AS n FROM celebrations_seen WHERE user_id = ?", (uid,)).fetchone()["n"]
        ) == 0
        assert int(
            conn.execute("SELECT COUNT(*) AS n FROM user_notifications WHERE user_id = ?", (uid,)).fetchone()["n"]
        ) == 0
        assert int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM notification_digest_queue WHERE user_id = ?", (uid,)
            ).fetchone()["n"]
        ) == 0
        assert int(conn.execute("SELECT COUNT(*) AS n FROM sessions WHERE user_id = ?", (uid,)).fetchone()["n"]) == 0
        assert int(
            conn.execute("SELECT COUNT(*) AS n FROM password_resets WHERE user_id = ?", (uid,)).fetchone()["n"]
        ) == 0
        assert int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM jobs WHERE requested_by = ?", (uid,)
            ).fetchone()["n"]
        ) == 0
        job_row = conn.execute("SELECT requested_by FROM jobs WHERE id = ?", (job["id"],)).fetchone()
        assert str(job_row["requested_by"] or "") == ""
        assert int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM security_events WHERE user_id = ? OR actor_id = ?",
                (uid, uid),
            ).fetchone()["n"]
        ) == 0
        assert int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM user_notifications WHERE from_user_id = ?", (uid,)
            ).fetchone()["n"]
        ) == 0

    # Registry delete treatments are exhaustive for live-DB stores we claim to handle.
    live_delete = {row["key"] for row in PERSONAL_DATA_REGISTRY if row["delete"] in ("delete", "anonymize", "detach", "revoke")}
    assert live_delete >= {
        "user",
        "prefs",
        "progress",
        "shelves",
        "shelf_items",
        "whispers",
        "notifications",
        "sessions",
        "password_resets",
        "celebrations_seen",
        "notification_digest_queue",
        "invites_created",
        "invites_redeemed",
        "jobs_requested",
        "notifications_from",
        "security_events_subject",
        "security_events_actor",
    }
