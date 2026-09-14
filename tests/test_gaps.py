from librarian.db import Database
from librarian.gaps import (
    audiobook_part_holes,
    comic_issue_holes,
    gap_cards,
    local_gaps,
    magazine_month_holes,
    music_track_holes,
)


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
    assert {"kind": "magazine", "series_name": "Linux Magazin", "missing_index": "2026-09", "title": "Linux Magazin 2026-09", "provenance": "local"} in cards


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
