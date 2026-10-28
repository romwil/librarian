"""Value tests for canonical identity resolution against real SQLite."""

from __future__ import annotations

from librarian.db import Database
from librarian.identity.authors import author_match_key, display_name, sort_name, split_authors
from librarian.identity.isbn import canonical_isbn13
from librarian.identity.resolve import resolve_work
from librarian.identity.titles import base_title, title_sort


def _work(db: Database, *, work_id: str, title: str, author: str, kind: str = "book") -> dict:
    return db.upsert_work({"id": work_id, "kind": kind, "title": title, "author": author})


def test_isbn10_1619_resolves_to_the_isbn13_work(tmp_path):
    db = Database(tmp_path / "library.sqlite")
    try:
        work = _work(
            db,
            work_id="1619",
            title="The 1619 Project: A New Origin Story",
            author="Nikole Hannah-Jones",
        )
        db.upsert_work_identifier(scheme="isbn13", value="9780593230572", work_id=work["id"])

        assert canonical_isbn13("0593230574") == "9780593230572"
        assert resolve_work(db, {"kind": "book", "isbn": "0593230574"}) == work["id"]
    finally:
        db.close()


def test_1619_last_first_and_base_title_is_a_normalized_match(tmp_path):
    db = Database(tmp_path / "library.sqlite")
    try:
        work = _work(
            db,
            work_id="1619",
            title="The 1619 Project: A New Origin Story",
            author="Nikole Hannah-Jones",
        )
        candidate = {
            "kind": "book",
            "title": "The 1619 Project",
            "author": "Hannah-Jones, Nikole",
        }

        assert resolve_work(db, candidate) == work["id"]
        assert candidate["match_confidence"] == "normalized"
        assert base_title(work["title"]) == "The 1619 Project"
    finally:
        db.close()


def test_author_variants_aliases_and_title_sorting(tmp_path):
    db = Database(tmp_path / "library.sqlite")
    try:
        author = db.upsert_author(
            {"display_name": "William W. Johnstone", "sort_name": "Johnstone, William W."}
        )
        db.upsert_author_alias(author_id=author["id"], alias="Johnstone, William W.")

        assert display_name("Hannah-Jones, Nikole") == "Nikole Hannah-Jones"
        assert display_name("William W Johnstone") == "William W. Johnstone"
        assert display_name("J.R.R. Tolkien") == "J.R.R. Tolkien"
        assert sort_name("Nikole Hannah-Jones") == "Hannah-Jones, Nikole"
        assert split_authors("James Patterson & Philip Dick; William W Johnstone") == [
            "James Patterson",
            "Philip Dick",
            "William W Johnstone",
        ]
        assert author_match_key("Johnstone, William W.", db) == author_match_key(
            "William W Johnstone", db
        )
        assert author_match_key("Patterson, James") == author_match_key("James Patterson")
        assert author_match_key("Dick, Philip K.") == author_match_key("Philip K. Dick")
        assert title_sort("The 1619 Project").startswith("0000001619")
        assert title_sort("The xxx") == title_sort("xxx")
    finally:
        db.close()
