import json

import httpx
from fastapi.testclient import TestClient

from librarian.config import Settings
from librarian.db import Database
from librarian.gaps import (
    audiobook_part_holes,
    catalog_gaps,
    comic_issue_holes,
    gap_cards,
    local_gaps,
    magazine_month_holes,
    music_track_holes,
)
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def test_magazine_month_holes_exact():
    assert magazine_month_holes(["2026-08", "2026-10"]) == ["2026-09"]
    assert magazine_month_holes(["2026-12", "2027-02"]) == ["2027-01"]
    assert magazine_month_holes(["2026-08"]) == []


def test_comic_issue_holes_exact():
    assert comic_issue_holes(["1", "2", "4", "10"]) == ["3", "5", "6", "7", "8", "9"]
    assert comic_issue_holes(["1"]) == []


def test_local_gaps_from_catalog(tmp_path):
    db = Database(tmp_path / "librarian.db")
    db.upsert_work({"kind": "magazine", "title": "Linux Magazin", "series_name": "Linux Magazin", "series_index": "2026-08"})
    db.upsert_work({"kind": "magazine", "title": "Linux Magazin", "series_name": "Linux Magazin", "series_index": "2026-10"})
    db.upsert_work({"kind": "comic", "title": "Saga #1", "series_name": "Saga", "series_index": "1"})
    db.upsert_work({"kind": "comic", "title": "Saga #3", "series_name": "Saga", "series_index": "3"})
    rows = local_gaps(db)
    mag = next(row for row in rows if row["series_name"] == "Linux Magazin")
    comic = next(row for row in rows if row["series_name"] == "Saga")
    assert mag["missing"] == ["2026-09"]
    assert comic["missing"] == ["2"]
    cards = gap_cards(rows)
    mag_card = next(card for card in cards if card["series_name"] == "Linux Magazin")
    assert mag_card["missing_index"] == "2026-09"
    assert mag_card["title"] == "Linux Magazin 2026-09"
    assert mag_card["provenance"] == "local"
    assert mag_card["series_index"] == "2026-09"
    assert mag_card["year"] == 2026


def test_audiobook_part_and_music_track_holes():
    assert audiobook_part_holes(["Dune Part 1.mp3", "Dune Part 3.mp3"]) == ["2"]
    assert music_track_holes(["01 Intro.flac", "03 Solo.flac"]) == ["2"]
    assert audiobook_part_holes(["Dune.m4b"]) == []


def test_local_audiobook_and_music_gaps(tmp_path):
    db = Database(tmp_path / "librarian.db")
    audio = db.upsert_work({"kind": "audiobook", "title": "Dune", "author": "Herbert"})
    db.add_file({"work_id": audio["id"], "path": "/a/Dune Part 1.mp3", "filename": "Dune Part 1.mp3", "kind": "audiobook"})
    db.add_file({"work_id": audio["id"], "path": "/a/Dune Part 3.mp3", "filename": "Dune Part 3.mp3", "kind": "audiobook"})
    album = db.upsert_work({"kind": "music", "title": "Kind of Blue", "author": "Miles", "series_name": "Kind of Blue"})
    db.add_file({"work_id": album["id"], "path": "/m/01 So What.flac", "filename": "01 So What.flac", "kind": "music"})
    db.add_file({"work_id": album["id"], "path": "/m/03 Blue in Green.flac", "filename": "03 Blue in Green.flac", "kind": "music"})
    rows = local_gaps(db)
    audio_row = next(row for row in rows if row["kind"] == "audiobook")
    music_row = next(row for row in rows if row["kind"] == "music")
    assert audio_row["missing"] == ["2"]
    assert music_row["missing"] == ["2"]
    cards = gap_cards(rows)
    assert any(card["title"] == "Dune 2" and card["gap_type"] == "audiobook_parts" for card in cards)
    assert any(card["title"] == "Kind of Blue 2" and card["gap_type"] == "music_tracks" for card in cards)


def test_multipart_owned_gaps_vs_part_total(tmp_path):
    """B3: owned holes use part_set.total — not series_index and not min/max-only file holes."""
    from librarian.gaps import multipart_owned_gaps

    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "audiobook",
            "title": "Magician",
            "author": "Feist",
            "part_total": 5,
            "part_style": "part",
            "part_base": "Raymond E Feist Magician",
        }
    )
    db.add_file(
        {
            "work_id": work["id"],
            "path": "/a/Magician Part 3.m4b",
            "filename": "Magician Part 3.m4b",
            "kind": "audiobook",
            "part": 3,
        }
    )
    db.add_file(
        {
            "work_id": work["id"],
            "path": "/a/Magician Part 5.m4b",
            "filename": "Magician Part 5.m4b",
            "kind": "audiobook",
            "part": 5,
        }
    )
    rails = multipart_owned_gaps(db)
    assert len(rails) == 1
    assert rails[0]["gap_type"] == "multipart"
    assert rails[0]["missing"] == ["1", "2", "4"]
    assert rails[0]["owned_indexes"] == ["3", "5"]
    assert rails[0]["part_set"]["total"] == 5
    cards = gap_cards(rails)
    assert any(card["gap_type"] == "multipart" and card["missing_index"] == "1" for card in cards)
    assert all(card.get("part_set", {}).get("total") == 5 for card in cards if card.get("gap_type") == "multipart")
    # Distinct from comic series_index gaps.
    assert all(card.get("gap_type") != "comic_issue" for card in cards)


def _dune_series_payload():
    return {
        "id": 7,
        "name": "Dune",
        "author": {"name": "Frank Herbert"},
        "book_series": [
            {"position": 1.0, "book": {"id": 1, "title": "Dune", "release_year": 1965}},
            {"position": 2.0, "book": {"id": 2, "title": "Dune Messiah", "release_year": 1969}},
            {"position": 3.0, "book": {"id": 3, "title": "Children of Dune", "release_year": 1976}},
        ],
    }


def _catalog_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if request.method == "POST" and "hardcover.app" in url:
        body = json.loads(request.content.decode("utf-8"))
        query = str(body.get("query") or "")
        if "SeriesByName" in query or "SeriesByPk" in query or "SeriesBySlug" in query:
            key = "series_by_pk" if "SeriesByPk" in query else "series"
            payload = _dune_series_payload()
            data = {key: [payload] if key == "series" else payload}
            return httpx.Response(200, json={"data": data})
        if "SeriesSearch" in query:
            return httpx.Response(
                200,
                json={"data": {"search": {"results": [{"id": 7, "name": "Dune", "slug": "dune"}]}}},
            )
        return httpx.Response(200, json={"data": {}})
    if "openlibrary.org/search.json" in url:
        return httpx.Response(
            200,
            json={
                "docs": [
                    {
                        "title": "Dune",
                        "author_name": ["Frank Herbert"],
                        "first_publish_year": 1965,
                        "series": ["Dune (1)"],
                        "isbn": ["9780441172719"],
                    },
                    {
                        "title": "Dune Messiah",
                        "author_name": ["Frank Herbert"],
                        "first_publish_year": 1969,
                        "series": ["Dune (2)"],
                    },
                    {
                        "title": "Children of Dune",
                        "author_name": ["Frank Herbert"],
                        "first_publish_year": 1976,
                        "series": ["Dune (3)"],
                    },
                ]
            },
        )
    if "comicvine.gamespot.com/api/search/" in url:
        assert "api_key=" in url
        return httpx.Response(
            200,
            json={
                "status_code": 1,
                "error": "OK",
                "results": [{"id": 42311, "name": "Saga", "start_year": "2012"}],
            },
        )
    if "comicvine.gamespot.com/api/volume/" in url:
        return httpx.Response(
            200,
            json={
                "status_code": 1,
                "error": "OK",
                "results": {
                    "id": 42311,
                    "name": "Saga",
                    "start_year": "2012",
                    "publisher": {"name": "Image"},
                    "issues": [
                        {"id": 1, "name": "The Beginning", "issue_number": "1"},
                        {"id": 2, "name": "Chapter Two", "issue_number": "2"},
                        {"id": 3, "name": "Chapter Three", "issue_number": "3"},
                        {"id": 4, "name": "Chapter Four", "issue_number": "4"},
                    ],
                },
            },
        )
    if "musicbrainz.org/ws/2/release-group" in url and "query=" in url:
        return httpx.Response(
            200,
            json={"release-groups": [{"id": "mb-kob", "title": "Kind of Blue", "primary-type": "Album"}]},
        )
    if "musicbrainz.org/ws/2/release?" in url or "/ws/2/release?" in url:
        return httpx.Response(
            200,
            json={
                "releases": [
                    {
                        "id": "mb-rel",
                        "media": [
                            {
                                "tracks": [
                                    {"number": "1", "title": "So What"},
                                    {"number": "2", "title": "Freddie Freeloader"},
                                    {"number": "3", "title": "Blue in Green"},
                                    {"number": "4", "title": "All Blues"},
                                ]
                            }
                        ],
                    }
                ]
            },
        )
    if "musicbrainz.org/ws/2/artist" in url:
        return httpx.Response(200, json={"artists": [{"id": "mb-miles", "name": "Miles"}]})
    if "musicbrainz.org/ws/2/release-group" in url:
        return httpx.Response(200, json={"release-groups": []})
    return httpx.Response(404, json={"error": "missing"})


def test_book_series_missing_volume_is_gap(tmp_path):
    db = Database(tmp_path / "librarian.db")
    db.upsert_work(
        {
            "kind": "book",
            "title": "Dune",
            "author": "Frank Herbert",
            "series_name": "Dune",
            "series_index": "1",
            "isbn": "9780441172719",
        }
    )
    db.upsert_work(
        {
            "kind": "book",
            "title": "Children of Dune",
            "author": "Frank Herbert",
            "series_name": "Dune",
            "series_index": "3",
        }
    )
    settings = Settings(hardcover_api_token="hardcover-test-token")
    rows = catalog_gaps(db, settings, transport=httpx.MockTransport(_catalog_handler))
    dune = next(row for row in rows if row["kind"] == "book" and row["series_name"] == "Dune")
    missing_indexes = [
        str(item["series_index"] if isinstance(item, dict) else item) for item in dune["missing"]
    ]
    assert missing_indexes == ["2"]
    cards = gap_cards(rows)
    messiah = next(card for card in cards if card["title"] == "Dune Messiah")
    assert messiah["missing_index"] == "2"
    assert messiah["author"] == "Frank Herbert"
    assert messiah["year"] == 1969
    assert messiah["provenance"].startswith("hardcover")
    assert "isbn" not in messiah


def test_owned_series_volume_is_not_a_gap(tmp_path):
    db = Database(tmp_path / "librarian.db")
    db.upsert_work({"kind": "book", "title": "Dune", "author": "Herbert", "series_name": "Dune", "series_index": "1"})
    db.upsert_work(
        {"kind": "book", "title": "Dune Messiah", "author": "Herbert", "series_name": "Dune", "series_index": "2"}
    )
    db.upsert_work(
        {
            "kind": "book",
            "title": "Children of Dune",
            "author": "Herbert",
            "series_name": "Dune",
            "series_index": "3",
        }
    )
    settings = Settings(hardcover_api_token="hardcover-test-token")
    rows = catalog_gaps(db, settings, transport=httpx.MockTransport(_catalog_handler))
    book_rows = [row for row in rows if row["kind"] == "book"]
    assert book_rows == []
    cards = gap_cards(rows)
    assert [card for card in cards if card["kind"] == "book"] == []


def test_no_token_no_remote_catalog_local_holes_still_work(tmp_path):
    db = Database(tmp_path / "librarian.db")
    db.upsert_work(
        {"kind": "magazine", "title": "Linux Magazin", "series_name": "Linux Magazin", "series_index": "2026-08"}
    )
    db.upsert_work(
        {"kind": "magazine", "title": "Linux Magazin", "series_name": "Linux Magazin", "series_index": "2026-10"}
    )
    db.upsert_work({"kind": "comic", "title": "Saga #1", "series_name": "Saga", "series_index": "1"})
    db.upsert_work({"kind": "comic", "title": "Saga #3", "series_name": "Saga", "series_index": "3"})
    db.upsert_work(
        {"kind": "book", "title": "Dune", "author": "Herbert", "series_name": "Dune", "series_index": "1"}
    )

    def refuse_secrets(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        assert "hardcover.app" not in url
        assert "comicvine.gamespot.com" not in url
        if "openlibrary.org" in url:
            return httpx.Response(200, json={"docs": []})
        return httpx.Response(404, json={"error": "missing"})

    rows = catalog_gaps(
        db,
        Settings(hardcover_api_token="", comicvine_api_key=""),
        transport=httpx.MockTransport(refuse_secrets),
    )
    mag = next(row for row in rows if row["series_name"] == "Linux Magazin")
    comic = next(row for row in rows if row["series_name"] == "Saga")
    assert mag["missing"] == ["2026-09"]
    assert comic["missing"] == ["2"]
    assert comic["provenance"] == "local"
    assert [row for row in rows if row["kind"] == "book"] == []


def test_comic_catalog_lists_issues_beyond_local_minmax(tmp_path):
    db = Database(tmp_path / "librarian.db")
    db.upsert_work({"kind": "comic", "title": "Saga #1", "series_name": "Saga", "series_index": "1", "author": "Vaughan"})
    db.upsert_work({"kind": "comic", "title": "Saga #2", "series_name": "Saga", "series_index": "2", "author": "Vaughan"})
    settings = Settings(comicvine_api_key="comicvine-test-key")
    rows = catalog_gaps(db, settings, transport=httpx.MockTransport(_catalog_handler))
    comic = next(row for row in rows if row["kind"] == "comic" and row["series_name"] == "Saga")
    indexes = [
        str(item["series_index"] if isinstance(item, dict) else item) for item in comic["missing"]
    ]
    assert indexes == ["3", "4"]
    assert comic["provenance"] == "comicvine"
    cards = gap_cards([comic])
    three = next(card for card in cards if card["missing_index"] == "3")
    assert three["title"] == "Chapter Three"
    assert three["author"] == "Image"
    assert "isbn" not in three


def test_music_musicbrainz_track_hole(tmp_path):
    db = Database(tmp_path / "librarian.db")
    album = db.upsert_work(
        {"kind": "music", "title": "Kind of Blue", "author": "Miles", "series_name": "Kind of Blue"}
    )
    db.add_file(
        {"work_id": album["id"], "path": "/m/01 So What.flac", "filename": "01 So What.flac", "kind": "music"}
    )
    db.add_file(
        {
            "work_id": album["id"],
            "path": "/m/03 Blue in Green.flac",
            "filename": "03 Blue in Green.flac",
            "kind": "music",
        }
    )
    rows = catalog_gaps(db, Settings(), transport=httpx.MockTransport(_catalog_handler), mb_min_interval=0)
    music = next(
        row
        for row in rows
        if row["kind"] == "music" and row.get("provenance") == "musicbrainz" and row["gap_type"] == "music_tracks"
    )
    indexes = [
        str(item["series_index"] if isinstance(item, dict) else item) for item in music["missing"]
    ]
    assert indexes == ["2", "4"]
    assert music["provenance"] == "musicbrainz"
    cards = gap_cards([music])
    assert next(card for card in cards if card["missing_index"] == "2")["title"] == "Freddie Freeloader"
    assert next(card for card in cards if card["missing_index"] == "4")["title"] == "All Blues"


def test_hall_gaps_do_not_queue_sab(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    clear_rate_limits()
    db = Database(tmp_path / "librarian.db")
    db.upsert_work(
        {"kind": "magazine", "title": "Linux Magazin", "series_name": "Linux Magazin", "series_index": "2026-08"}
    )
    db.upsert_work(
        {"kind": "magazine", "title": "Linux Magazin", "series_name": "Linux Magazin", "series_index": "2026-10"}
    )
    sab_calls = []

    def forbid_addurl(self, *args, **kwargs):
        sab_calls.append((args, kwargs))
        raise AssertionError("SAB must not fire from Hall browse")

    monkeypatch.setattr("librarian.sabnzbd.SABClient.addurl", forbid_addurl)
    client = TestClient(create_app(tmp_path))
    assert client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"}).status_code == 200
    hall = client.get("/api/hall")
    assert hall.status_code == 200
    gaps = hall.json()["gaps"]
    hole = next(card for card in gaps if card["missing_index"] == "2026-09")
    assert hole["kind"] == "magazine"
    assert hole["series_name"] == "Linux Magazin"
    assert not hole.get("guid")
    assert not hole.get("download_url")
    assert sab_calls == []
    listed = client.get("/api/gaps")
    assert listed.status_code == 200
    assert any(card["missing_index"] == "2026-09" for card in listed.json()["cards"])

