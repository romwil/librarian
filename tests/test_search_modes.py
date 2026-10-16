"""Search field modes stay on one column."""

from librarian.db import Database


def _shelf(db: Database, **work):
    row = db.upsert_work(work)
    db.add_file(
        {
            "work_id": row["id"],
            "path": f"/b/{row['id']}.epub",
            "filename": f"{row['id']}.epub",
            "kind": work.get("kind") or "book",
        }
    )
    return row


def test_search_modes_do_not_cross_fields(tmp_path):
    db = Database(tmp_path / "librarian.db")
    _shelf(db, kind="book", title="Dune", author="Frank Herbert", isbn="9780441172719", series_name="Dune", series_index="1")
    _shelf(db, kind="book", title="Dune Messiah", author="Frank Herbert", series_name="Dune", series_index="2")
    _shelf(db, kind="book", title="Kindred", author="Octavia Butler", isbn="9780807083697")
    _shelf(
        db,
        kind="audiobook",
        title="Project Hail Mary",
        author="Andy Weir",
        narrator="Ray Porter",
    )
    _shelf(db, kind="book", title="Herbert", author="Someone Else")

    def titles(rows):
        return [row["title"] for row in rows]

    assert titles(db.search_works_mode("Dune", "title")) == ["Dune", "Dune Messiah"]
    assert "Kindred" not in titles(db.search_works_mode("Butler", "title"))
    assert titles(db.search_works_mode("Butler", "author")) == ["Kindred"]
    assert titles(db.search_works_mode("Herbert", "author")) == ["Dune", "Dune Messiah"]
    assert titles(db.search_works_mode("9780441172719", "isbn")) == ["Dune"]
    assert titles(db.search_works_mode("Dune", "isbn")) == []
    assert titles(db.search_works_mode("Dune", "series")) == ["Dune", "Dune Messiah"]
    assert titles(db.search_works_mode("Ray Porter", "narrator")) == ["Project Hail Mary"]
    assert db.search_works_mode("Ray Porter", "title") == []
    assert db.search_works_mode("Dune", "narrator") == []
