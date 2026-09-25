"""Phase 2b Listen — player handoff, chapters, Continue for audiobooks."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from librarian.config import Settings
from librarian.db import Database
from librarian.listen import (
    abs_item_href,
    audiobook_player_link,
    decode_listen_position,
    encode_listen_position,
    extract_chapters,
    listen_fraction,
    listen_payload,
    player_empty_note,
    should_write_listen_progress,
    split_continue_rails,
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


def test_abs_item_href_and_player_link_honesty():
    assert abs_item_href("http://abs.local", "item-1") == "http://abs.local/item/item-1"
    assert abs_item_href("", "item-1") == ""
    work = {"kind": "audiobook", "abs_item_id": "abc", "title": "Dune"}
    abs_settings = Settings(audiobookshelf_url="http://abs.local/", audiobook_target="audiobookshelf")
    linked = audiobook_player_link(work, abs_settings)
    assert linked["provider"] == "audiobookshelf"
    assert linked["href"].endswith("/item/abc")
    plex = audiobook_player_link({"kind": "audiobook"}, Settings(audiobook_target="plex"))
    assert plex == {"href": "plex://", "label": "Open in Plex", "provider": "plex"}
    unmatched = {"kind": "audiobook", "title": "Dune"}
    assert audiobook_player_link(unmatched, abs_settings) is None
    assert "Not matched" in player_empty_note(unmatched, abs_settings)
    only = listen_payload(
        unmatched,
        can_download=True,
        settings=Settings(audiobook_target="librarian_only"),
    )
    assert only["can_listen"] is True
    assert only["player"] is None
    assert "Librarian" in only["player_note"]
    assert listen_payload({"kind": "book"}, can_download=True, settings=Settings())["can_listen"] is False


def test_listen_position_and_fraction_helpers():
    encoded = encode_listen_position(file_id="f1", seconds=12.5, rate=1.25)
    assert decode_listen_position(encoded) == {"file_id": "f1", "seconds": 12.5, "rate": 1.25}
    assert decode_listen_position("f1:9") == {"file_id": "f1", "seconds": 9.0, "rate": 0.0}
    assert listen_fraction(file_index=1, file_count=4, local_fraction=0.5) == 0.375
    assert should_write_listen_progress(ready=False, seconds=0, resume_seconds=40) is False
    assert should_write_listen_progress(ready=True, seconds=0.2, resume_seconds=40) is False
    assert should_write_listen_progress(ready=True, seconds=41, resume_seconds=40) is True
    rails = split_continue_rails(
        [
            {"kind": "book", "title": "Kindred"},
            {"kind": "audiobook", "title": "Dune"},
        ]
    )
    assert [row["title"] for row in rails["reading"]] == ["Kindred"]
    assert [row["title"] for row in rails["listening"]] == ["Dune"]


def test_extract_chapters_reads_mp4_markers(monkeypatch, tmp_path):
    path = tmp_path / "Dune.m4b"
    path.write_bytes(b"fake-m4b")

    class FakeAudio:
        chapters = [
            SimpleNamespace(start=0.0, title="Prologue"),
            SimpleNamespace(start=100.0, title="One"),
        ]

    class FakeMutagen:
        @staticmethod
        def File(name, easy=False):  # noqa: ARG004
            return FakeAudio()

    import sys

    monkeypatch.setitem(sys.modules, "mutagen", FakeMutagen())
    chapters = extract_chapters(path)
    assert [row["title"] for row in chapters] == ["Prologue", "One"]
    assert chapters[1]["start"] == 100.0
    assert extract_chapters(tmp_path / "missing.m4b") == []
    pdf = tmp_path / "notes.pdf"
    pdf.write_bytes(b"%PDF")
    assert extract_chapters(pdf) == []


def test_work_detail_listen_payload_and_chapters_api(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    db = Database(tmp_path / "librarian.db")
    audio_path = tmp_path / "shelves" / "Dune.m4b"
    audio_path.parent.mkdir(parents=True)
    audio_path.write_bytes(b"ID3fake")

    def fake_chapters(path):  # noqa: ARG001
        return [
            {"index": 0, "title": "Prologue", "start": 0.0},
            {"index": 1, "title": "Chapter One", "start": 60.0},
        ]

    monkeypatch.setattr("librarian.web.routers.catalog.extract_chapters", fake_chapters)
    work = db.upsert_work(
        {
            "kind": "audiobook",
            "title": "Dune",
            "author": "Herbert",
            "abs_item_id": "abs-9",
        }
    )
    row = db.add_file(
        {
            "work_id": work["id"],
            "path": str(audio_path),
            "filename": audio_path.name,
            "kind": "audiobook",
        }
    )
    client.put(
        "/api/settings",
        json={"audiobookshelf_url": "http://abs.lan", "audiobook_target": "audiobookshelf"},
    )
    detail = client.get(f"/api/works/{work['id']}").json()
    assert detail["listen"]["can_listen"] is True
    assert detail["listen"]["player"]["href"] == "http://abs.lan/item/abs-9"
    chapters = client.get(f"/api/works/{work['id']}/chapters", params={"file": row["id"]}).json()
    assert [c["title"] for c in chapters["chapters"]] == ["Prologue", "Chapter One"]


def test_hall_continue_includes_audiobook_progress(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    db = Database(tmp_path / "librarian.db")
    audio = db.upsert_work({"kind": "audiobook", "title": "Dune", "author": "Herbert"})
    book = db.upsert_work({"kind": "book", "title": "Kindred", "author": "Butler"})
    db.add_file({"work_id": audio["id"], "path": "/a/Dune.m4b", "filename": "Dune.m4b", "kind": "audiobook"})
    db.add_file({"work_id": book["id"], "path": "/b/Kindred.epub", "filename": "Kindred.epub", "kind": "book"})
    client.post(
        f"/api/works/{audio['id']}/progress",
        json={"fraction": 0.33, "position": encode_listen_position(file_id="f1", seconds=40)},
    )
    client.post(f"/api/works/{book['id']}/progress", json={"fraction": 0.1})
    hall = client.get("/api/hall").json()
    assert [row["title"] for row in hall["continue"]] == ["Kindred"]
    listening = hall["continue_listening"]
    assert [row["title"] for row in listening] == ["Dune"]
    dune = listening[0]
    assert dune["kind"] == "audiobook"
    assert dune["progress"] == 33
    assert decode_listen_position(dune["position"])["seconds"] == 40.0


def test_progress_save_round_trip_per_user(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work({"kind": "audiobook", "title": "Dune", "author": "Herbert"})
    marker = encode_listen_position(file_id="part-2", seconds=123.4, rate=1.5)
    saved = client.post(
        f"/api/works/{work['id']}/progress",
        json={"fraction": 0.42, "position": marker},
    ).json()["progress"]
    assert saved["fraction"] == 0.42
    detail = client.get(f"/api/works/{work['id']}").json()
    assert detail["progress"]["position"] == marker
    assert decode_listen_position(detail["progress"]["position"]) == {
        "file_id": "part-2",
        "seconds": 123.4,
        "rate": 1.5,
    }
