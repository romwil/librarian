"""Sprint D1 — series catch-up invitation (Hall for every role, real SQLite)."""

from pathlib import Path

from fastapi.testclient import TestClient

from librarian.db import Database
from librarian.delight import (
    catch_up_invitation,
    catch_up_noun,
    series_catch_up,
)
from librarian.gaps import gap_cards, local_gaps
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def _shelve_magazine(db: Database, series: str, months: list[str]) -> None:
    for month in months:
        work = db.upsert_work(
            {
                "kind": "magazine",
                "title": series,
                "series_name": series,
                "series_index": month,
            }
        )
        db.add_file(
            {
                "work_id": work["id"],
                "path": f"/mags/{series}/{month}.pdf",
                "filename": f"{month}.pdf",
                "kind": "magazine",
            }
        )


def _shelve_comics(db: Database, series: str, issues: list[str]) -> None:
    for issue in issues:
        work = db.upsert_work(
            {
                "kind": "comic",
                "title": f"{series} {issue}",
                "author": "Gilt Pen",
                "series_name": series,
                "series_index": issue,
            }
        )
        db.add_file(
            {
                "work_id": work["id"],
                "path": f"/comics/{series}/{issue}.cbz",
                "filename": f"{issue}.cbz",
                "kind": "comic",
            }
        )


def test_catch_up_noun_follows_the_shelf():
    assert catch_up_noun("comic") == "issue"
    assert catch_up_noun("comic", plural=True) == "issues"
    assert catch_up_noun("magazine") == "issue"
    assert catch_up_noun("music", "music_album", plural=True) == "albums"
    assert catch_up_noun("audiobook", "multipart") == "part"
    assert catch_up_noun("book") == "volume"
    assert catch_up_noun("", "", plural=True) == "volumes"


def test_catch_up_invitation_counts_in_words():
    assert (
        catch_up_invitation(series_name="Saga", kind="comic", missing_count=1)
        == "One issue from a whole Saga."
    )
    assert (
        catch_up_invitation(series_name="Saga", kind="comic", missing_count=2)
        == "Two issues from a whole Saga."
    )
    assert (
        catch_up_invitation(series_name="Saga", kind="comic", missing_count=11)
        == "A few issues from a whole Saga."
    )
    assert catch_up_invitation(series_name="", kind="book", missing_count=1) == (
        "One volume from a whole run."
    )
    assert catch_up_invitation(series_name="Saga", kind="comic", missing_count=0) == ""


def test_series_catch_up_is_empty_without_holes():
    payload = series_catch_up([])
    assert payload == {"series": [], "empty": True}
    assert series_catch_up(None)["empty"] is True


def test_series_catch_up_skips_cards_missing_kind_or_series():
    payload = series_catch_up(
        [
            {"kind": "", "series_name": "Nameless", "missing_index": "2"},
            {"kind": "comic", "series_name": "", "missing_index": "2"},
        ]
    )
    assert payload["empty"] is True


def test_series_catch_up_prefers_few_missing_from_real_local_gaps(tmp_path):
    db = Database(tmp_path / "librarian.db")
    # One hole (#3) — should lead.
    _shelve_comics(db, "Saga", ["1", "2", "4"])
    # Two holes (#2, #4).
    _shelve_comics(db, "Bone", ["1", "3", "5"])
    # One hole (2026-09) but a shorter shelf than Saga — ties break on owned depth.
    _shelve_magazine(db, "Linux Magazin", ["2026-08", "2026-10"])

    payload = series_catch_up(gap_cards(local_gaps(db)))
    assert payload["empty"] is False
    names = [row["series_name"] for row in payload["series"]]
    assert names == ["Saga", "Linux Magazin", "Bone"]

    saga = payload["series"][0]
    assert saga["kind"] == "comic"
    assert saga["missing"] == ["3"]
    assert saga["missing_count"] == 1
    assert saga["invitation"] == "One issue from a whole Saga."
    assert saga["author"] == "Gilt Pen"
    assert saga["next_gap"]["missing_index"] == "3"
    assert saga["next_gap"]["series_name"] == "Saga"
    assert [bead["state"] for bead in saga["ribbon"]] == ["owned", "owned", "missing", "owned"]

    bone = payload["series"][2]
    assert bone["missing"] == ["2", "4"]
    assert bone["invitation"] == "Two issues from a whole Bone."

    mag = payload["series"][1]
    assert mag["kind"] == "magazine"
    assert mag["missing"] == ["2026-09"]
    assert mag["invitation"] == "One issue from a whole Linux Magazin."
    assert [bead["value"] for bead in mag["ribbon"]] == ["2026-08", "2026-09", "2026-10"]


def test_series_catch_up_honours_limit_and_max_missing(tmp_path):
    db = Database(tmp_path / "librarian.db")
    _shelve_comics(db, "Saga", ["1", "3"])
    _shelve_comics(db, "Bone", ["1", "4"])
    _shelve_comics(db, "Chew", ["1", "5"])
    # 8 holes — too far from whole to be an invitation.
    _shelve_comics(db, "Locke", ["1", "10"])

    cards = gap_cards(local_gaps(db))
    payload = series_catch_up(cards)
    assert len(payload["series"]) == 3
    assert "Locke" not in [row["series_name"] for row in payload["series"]]

    narrow = series_catch_up(cards, limit=1, max_missing=2)
    assert len(narrow["series"]) == 1
    assert narrow["series"][0]["missing_count"] == 1

    wide = series_catch_up(cards, limit=9, max_missing=99)
    assert "Locke" in [row["series_name"] for row in wide["series"]]
    locke = next(row for row in wide["series"] if row["series_name"] == "Locke")
    assert locke["invitation"] == "A few issues from a whole Locke."

    assert series_catch_up(cards, limit=0)["empty"] is True


def test_series_catch_up_keeps_filenames_out_of_the_ribbon(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {"kind": "audiobook", "title": "Long Listen", "series_name": "Long Listen"}
    )
    for part in ("1", "3"):
        db.add_file(
            {
                "work_id": work["id"],
                "path": f"/audio/Long Listen/part {part}.m4b",
                "filename": f"part {part}.m4b",
                "kind": "audiobook",
            }
        )

    payload = series_catch_up(gap_cards(local_gaps(db)))
    row = next(r for r in payload["series"] if r["series_name"] == "Long Listen")
    assert row["gap_type"] == "audiobook_parts"
    assert row["missing"] == ["2"]
    assert row["invitation"] == "One part from a whole Long Listen."
    # owned_indexes are filenames here — beads must stay real positions only.
    assert [bead["value"] for bead in row["ribbon"]] == ["2"]


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    clear_rate_limits()
    return TestClient(create_app(tmp_path))


def test_hall_invites_every_role_to_catch_up(tmp_path, monkeypatch):
    db = Database(Path(tmp_path) / "librarian.db")
    _shelve_comics(db, "Saga", ["1", "2", "4"])
    client = _client(tmp_path, monkeypatch)

    assert (
        client.post(
            "/api/auth/local/login", json={"username": "owner", "password": "password123"}
        ).status_code
        == 200
    )
    owner_hall = client.get("/api/hall")
    assert owner_hall.status_code == 200
    owner_body = owner_hall.json()
    owner_catch_up = owner_body["series_catch_up"]
    assert owner_catch_up["empty"] is False
    assert owner_catch_up["series"][0]["invitation"] == "One issue from a whole Saga."
    # Owner gaps rail (catalog fan-out) stays its own thing.
    assert any(card["missing_index"] == "3" for card in owner_body["gaps"])

    token = client.post("/api/invites", json={"role": "reader"}).json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert (
        client.post(
            "/api/invites/redeem/local",
            json={"token": token, "username": "reader1", "password": "password123"},
        ).status_code
        == 200
    )

    reader_hall = client.get("/api/hall")
    assert reader_hall.status_code == 200
    reader_body = reader_hall.json()
    # Readers still get no catalog gaps rail, but they do get the invitation.
    assert reader_body["gaps"] == []
    reader_catch_up = reader_body["series_catch_up"]
    assert reader_catch_up["empty"] is False
    saga = reader_catch_up["series"][0]
    assert saga["series_name"] == "Saga"
    assert saga["missing"] == ["3"]
    assert saga["invitation"] == "One issue from a whole Saga."
    # Invitation only — never a queued request.
    assert not saga["next_gap"].get("guid")
    assert not saga["next_gap"].get("download_url")


def test_hall_catch_up_empty_on_a_whole_shelf(tmp_path, monkeypatch):
    db = Database(Path(tmp_path) / "librarian.db")
    _shelve_comics(db, "Saga", ["1", "2", "3"])
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})

    body = client.get("/api/hall").json()
    assert body["series_catch_up"] == {"series": [], "empty": True}
