"""Enrichment corrections: identifiers, strong-match fixes, metadata_locked, audiobook
ASIN/narrator via Audnexus, and magazine masthead/issue/cover rules.

HTTP is mocked (Open Library, Hardcover, Audnexus/Audible). SQLite is real. No Playwright.
"""

from __future__ import annotations

import zipfile

import httpx

from librarian.config import Settings
from librarian.db import Database
from librarian.enrich import (
    Enrichment,
    apply_enrichment,
    correct_magazine_work,
    enrich_corrections_backlog_batch,
    enrich_work,
    update_work_metadata,
)

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 80
ISBN13 = "9780593230572"


def _no_hardcover_404(request: httpx.Request) -> httpx.Response:
    return httpx.Response(404, json={"error": "missing"})


# ---------------------------------------------------------------------------
# Pure apply_enrichment: what a strong match writes, what a locked field refuses.
# ---------------------------------------------------------------------------


def test_strong_match_corrects_title_author_series_year_and_writes_identifiers(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Teh 1619 Project",
            "author": "Hannah-Jones, Nikole",
            "isbn": ISBN13,
        }
    )
    found = Enrichment(
        title="The 1619 Project",
        author="Nikole Hannah-Jones",
        series_name="Hainish Cycle",
        series_index="4",
        year=2021,
        ol_work_key="/works/OL123W",
        hardcover_id="456",
        isbn13s=[ISBN13],
        source="openlibrary",
        identifier_strength="strong",
    )
    updated = apply_enrichment(db, work, found, data_dir=tmp_path)

    assert updated["title"] == "The 1619 Project"
    assert updated["author"] == "Nikole Hannah-Jones"
    assert updated["series_name"] == "Hainish Cycle"
    assert updated["series_index"] == "4"
    assert updated["year"] == 2021

    identifiers = {row["scheme"]: row["value"] for row in db.list_work_identifiers(updated["id"])}
    assert identifiers["ol_work"] == "/works/OL123W"
    assert identifiers["hardcover"] == "456"
    assert identifiers["isbn13"] == ISBN13


def test_weak_title_search_match_never_corrects_an_existing_field(tmp_path):
    """A fuzzy title search (identifier_strength='weak') may fill blanks, not correct."""
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work({"kind": "book", "title": "The 1619 Project", "author": "Hannah-Jones, Nikole"})
    found = Enrichment(
        title="Some Other Title Entirely",
        author="A Different Author",
        source="openlibrary",
        identifier_strength="weak",
    )
    updated = apply_enrichment(db, work, found, data_dir=tmp_path)
    assert updated["title"] == "The 1619 Project"
    assert updated["author"] == "Hannah-Jones, Nikole"


def test_metadata_locked_refuses_strong_correction_but_identifiers_still_write(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "My Own Title For This",
            "author": "My Own Author Spelling",
            "isbn": ISBN13,
            "series_name": "My Own Series Name",
            "year": 1999,
            "metadata_locked": 1,
        }
    )
    found = Enrichment(
        title="The 1619 Project",
        author="Nikole Hannah-Jones",
        series_name="Hainish Cycle",
        year=2021,
        ol_work_key="/works/OL123W",
        hardcover_id="456",
        isbn13s=[ISBN13],
        source="openlibrary",
        identifier_strength="strong",
    )
    updated = apply_enrichment(db, work, found, data_dir=tmp_path)

    # The hand-typed fields refuse the correction, verbatim — locked protects
    # values the owner already set, not blanks (a blank field still fills in).
    assert updated["title"] == "My Own Title For This"
    assert updated["author"] == "My Own Author Spelling"
    assert updated["series_name"] == "My Own Series Name"
    assert updated["year"] == 1999

    # Canonical identifiers are reference data, not a hand-typed field — they still land.
    identifiers = {row["scheme"]: row["value"] for row in db.list_work_identifiers(updated["id"])}
    assert identifiers["ol_work"] == "/works/OL123W"
    assert identifiers["hardcover"] == "456"
    assert identifiers["isbn13"] == ISBN13


def test_update_work_metadata_sets_metadata_locked_on_hand_edit(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work({"kind": "book", "title": "Dune", "author": "Frank Herbert"})
    assert not work.get("metadata_locked")

    updated = update_work_metadata(
        db, work["id"], {"title": "Dune (Deluxe)"}, data_dir=tmp_path
    )
    assert updated["metadata_locked"] == 1

    # A patch that only touches a non-correctable field must not lock the work.
    work2 = db.upsert_work({"kind": "book", "title": "Dune Messiah", "author": "Frank Herbert"})
    updated2 = update_work_metadata(
        db, work2["id"], {"genre": "Science fiction"}, data_dir=tmp_path
    )
    assert not updated2.get("metadata_locked")


# ---------------------------------------------------------------------------
# End-to-end lookup_enrichment -> apply_enrichment, HTTP mocked.
# ---------------------------------------------------------------------------


def test_openlibrary_isbn_lookup_is_strong_and_corrects_wrong_title(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/isbn/" in url:
            return httpx.Response(
                200,
                json={
                    "title": "The 1619 Project",
                    "publish_date": "2021",
                    "works": [{"key": "/works/OL123W"}],
                    "authors": [{"name": "Nikole Hannah-Jones"}],
                },
            )
        if "/works/OL123W" in url:
            return httpx.Response(
                200,
                json={"title": "The 1619 Project", "description": "A reframing of US history."},
            )
        return httpx.Response(404, json={"error": "missing"})

    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Teh 1619 Project",
            "author": "Hannah-Jones, Nikole",
            "isbn": ISBN13,
        }
    )
    result = enrich_work(
        db,
        Settings(hardcover_api_token=""),
        work["id"],
        data_dir=tmp_path,
        transport=httpx.MockTransport(handler),
    )
    assert result["work"]["title"] == "The 1619 Project"
    assert result["work"]["author"] == "Nikole Hannah-Jones"
    identifiers = {row["scheme"]: row["value"] for row in db.list_work_identifiers(work["id"])}
    assert identifiers["ol_work"] == "/works/OL123W"
    assert identifiers["isbn13"] == ISBN13


def test_hardcover_isbn_lookup_writes_hardcover_id(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "POST" and "hardcover.app" in url:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "editions": [
                            {
                                "isbn_13": ISBN13,
                                "isbn_10": "",
                                "book": {"id": 789, "title": "The 1619 Project"},
                            }
                        ]
                    }
                },
            )
        return httpx.Response(404, json={"error": "missing"})

    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {"kind": "book", "title": "The 1619 Project", "author": "Nikole Hannah-Jones", "isbn": ISBN13}
    )
    enrich_work(
        db,
        Settings(hardcover_api_token="token"),
        work["id"],
        data_dir=tmp_path,
        transport=httpx.MockTransport(handler),
    )
    identifiers = {row["scheme"]: row["value"] for row in db.list_work_identifiers(work["id"])}
    assert identifiers["hardcover"] == "789"
    assert identifiers["isbn13"] == ISBN13


# ---------------------------------------------------------------------------
# Audiobooks: ASIN + narrator from Audnexus, stored as an identifier, never in isbn.
# ---------------------------------------------------------------------------


def _audnexus_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "api.audible.com" in url:
        return httpx.Response(200, json={"products": [{"asin": "B0TESTASIN"}]})
    if "api.audnex.us" in url:
        return httpx.Response(
            200,
            json={
                "asin": "B0TESTASIN",
                "title": "Dune",
                "authors": [{"name": "Frank Herbert"}],
                "narrators": [{"name": "Scott Brick"}],
                "releaseDate": "1965-01-01",
            },
        )
    return httpx.Response(404, json={"error": "missing"})


def test_audiobook_asin_and_narrator_fill_from_audnexus_not_isbn_column(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {"kind": "audiobook", "title": "Dune", "author": "Frank Herbert", "year": 1965}
    )
    result = enrich_work(
        db,
        Settings(hardcover_api_token=""),
        work["id"],
        data_dir=tmp_path,
        transport=httpx.MockTransport(_audnexus_handler),
    )
    assert result["work"]["asin"] == "B0TESTASIN"
    assert result["work"]["narrator"] == "Scott Brick"
    assert result["work"]["isbn"] in (None, "")

    identifiers = {row["scheme"]: row["value"] for row in db.list_work_identifiers(work["id"])}
    assert identifiers["asin"] == "B0TESTASIN"


def test_audiobook_asin_links_to_existing_book_work_via_resolver(tmp_path):
    db = Database(tmp_path / "librarian.db")
    book_work = db.upsert_work(
        {"kind": "book", "title": "Dune", "author": "Frank Herbert", "isbn": "9780441172719"}
    )
    audiobook_work = db.upsert_work({"kind": "audiobook", "title": "Dune", "author": "Frank Herbert"})

    enrich_work(
        db,
        Settings(hardcover_api_token=""),
        audiobook_work["id"],
        data_dir=tmp_path,
        transport=httpx.MockTransport(_audnexus_handler),
    )

    asin_owner = db.get_work_by_identifier(scheme="asin", value="B0TESTASIN")
    assert asin_owner is not None
    assert asin_owner["id"] == book_work["id"]


# ---------------------------------------------------------------------------
# Magazines: masthead/issue/year rules, no external API, cover from the first page.
# ---------------------------------------------------------------------------


def test_correct_magazine_work_fixes_title_when_reparse_matches_issue(tmp_path):
    folder = tmp_path / "library" / "Scientific American 2024-03"
    folder.mkdir(parents=True)
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "magazine",
            "title": "Scientific Americann",  # typo — the folder name is the truth
            "series_name": "Scientific American",
            "series_index": "2024-03",
            "year": 2024,
            "folder_path": str(folder),
        }
    )
    updated = correct_magazine_work(db, work, data_dir=tmp_path)
    assert updated["title"] == "Scientific American"


def test_correct_magazine_work_skips_when_identity_does_not_match():
    """A folder rename to an unrelated issue must not donate its title."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "Scientific American 2024-03"
        folder.mkdir(parents=True)
        db = Database(Path(tmp) / "librarian.db")
        work = db.upsert_work(
            {
                "kind": "magazine",
                "title": "National Geographic",
                "series_name": "National Geographic",
                "series_index": "2024-07",
                "folder_path": str(folder),
            }
        )
        updated = correct_magazine_work(db, work, data_dir=Path(tmp))
        assert updated["title"] == "National Geographic"


def test_correct_magazine_work_respects_metadata_locked(tmp_path):
    folder = tmp_path / "library" / "Scientific American 2024-03"
    folder.mkdir(parents=True)
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "magazine",
            "title": "Scientific Americann",
            "series_name": "Scientific American",
            "series_index": "2024-03",
            "folder_path": str(folder),
            "metadata_locked": 1,
        }
    )
    updated = correct_magazine_work(db, work, data_dir=tmp_path)
    assert updated["title"] == "Scientific Americann"


def test_correct_magazine_work_extracts_cover_from_cbz_first_page(tmp_path):
    folder = tmp_path / "library" / "Scientific American 2024-03"
    folder.mkdir(parents=True)
    cbz_path = folder / "issue.cbz"
    with zipfile.ZipFile(cbz_path, "w") as archive:
        archive.writestr("001.jpg", JPEG)
        archive.writestr("002.jpg", b"\xff\xd8\xff\xe0not the first page")

    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "magazine",
            "title": "Scientific American",
            "series_name": "Scientific American",
            "series_index": "2024-03",
            "folder_path": str(folder),
        }
    )
    updated = correct_magazine_work(db, work, data_dir=tmp_path)
    assert updated["cover_path"]
    from pathlib import Path

    assert Path(updated["cover_path"]).read_bytes() == JPEG


def test_enrich_corrections_backlog_batch_runs_magazine_pass(tmp_path):
    folder = tmp_path / "library" / "Scientific American 2024-03"
    folder.mkdir(parents=True)
    cbz_path = folder / "issue.cbz"
    with zipfile.ZipFile(cbz_path, "w") as archive:
        archive.writestr("001.jpg", JPEG)

    db = Database(tmp_path / "librarian.db")
    db.upsert_work(
        {
            "kind": "magazine",
            "title": "Scientific American",
            "series_name": "Scientific American",
            "series_index": "2024-03",
            "folder_path": str(folder),
        }
    )
    result = enrich_corrections_backlog_batch(
        db,
        Settings(hardcover_api_token=""),
        data_dir=tmp_path,
        limit=5,
        pause_seconds=0,
        transport=httpx.MockTransport(_no_hardcover_404),
    )
    assert result["magazines_scanned"] == 1
    assert result["magazines_updated"] == 1
