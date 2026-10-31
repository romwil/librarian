"""Nightly retention: seen notices, closed invites, terminal job PII."""

import time

from librarian.auth import hash_password
from librarian.db import Database
from librarian.retention import (
    INVITE_CLOSED_DAYS,
    JOB_TERMINAL_DAYS,
    SEEN_NOTICE_DAYS,
    run_retention,
)


def test_retention_purges_old_seen_notices_and_keeps_fresh(tmp_path):
    db = Database(tmp_path / "librarian.db")
    user = db.create_local_user(
        user_id="u-owner",
        display_name="owner",
        role="owner",
        password_hash=hash_password("password123"),
    )
    now = time.time()
    old = now - ((SEEN_NOTICE_DAYS + 2) * 86400)
    fresh = now - 3600

    def _insert() -> None:
        with db._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_notifications
                    (id, user_id, kind, title, body, payload_json, created_at, seen_at)
                VALUES
                    ('n-old', ?, 'arrived', 'Old', '', NULL, ?, ?),
                    ('n-new', ?, 'arrived', 'New', '', NULL, ?, ?)
                """,
                (user["id"], old, old, user["id"], fresh, fresh),
            )

    db.run_write(_insert, label="seed_notices")
    counts = run_retention(db, data_dir=tmp_path, now=now)
    assert counts["notifications"] == 1
    with db._connect() as conn:
        left = [row["id"] for row in conn.execute("SELECT id FROM user_notifications").fetchall()]
    assert left == ["n-new"]


def test_retention_strips_old_terminal_jobs_and_drops_closed_invites(tmp_path):
    db = Database(tmp_path / "librarian.db")
    now = time.time()
    ancient = now - ((JOB_TERMINAL_DAYS + 5) * 86400)
    invite_old = now - ((INVITE_CLOSED_DAYS + 2) * 86400)

    def _insert() -> None:
        with db._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, status, title, kind, requested_by, payload_json, created_at, updated_at
                ) VALUES (?, 'organized', 'Dune', 'book', 'u-reader', '{"wanted_id":"w1"}', ?, ?)
                """,
                ("j-old", ancient, ancient),
            )
            conn.execute(
                """
                INSERT INTO jobs (
                    id, status, title, kind, requested_by, payload_json, created_at, updated_at
                ) VALUES (?, 'asked', 'Messiah', 'book', 'u-reader', '{"wanted_id":"w2"}', ?, ?)
                """,
                ("j-open", now, now),
            )
            conn.execute(
                """
                INSERT INTO invites (
                    id, token_hash, created_by, role, status, expires_at, redeemed_at, created_at
                ) VALUES (?, 'hash', 'u-owner', 'reader', 'redeemed', ?, ?, ?)
                """,
                ("inv-old", invite_old, invite_old, invite_old),
            )

    db.run_write(_insert, label="seed_retention")
    counts = run_retention(db, data_dir=tmp_path, now=now)
    assert counts["jobs_stripped"] == 1
    assert counts["invites"] == 1
    with db._connect() as conn:
        old_job = conn.execute("SELECT requested_by, payload_json FROM jobs WHERE id = 'j-old'").fetchone()
        open_job = conn.execute("SELECT requested_by, payload_json FROM jobs WHERE id = 'j-open'").fetchone()
        invites = conn.execute("SELECT id FROM invites").fetchall()
    assert old_job["requested_by"] is None
    assert old_job["payload_json"] is None
    assert open_job["requested_by"] == "u-reader"
    assert open_job["payload_json"] is not None
    assert invites == []
