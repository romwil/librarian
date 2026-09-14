from librarian.db import Database
from librarian.gaps import comic_issue_holes, gap_cards, local_gaps, magazine_month_holes


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
