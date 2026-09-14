from pathlib import Path

from librarian.config import Settings
from librarian.identify import dest_layout, identify_completed, parse_usenet_name


def test_magazine_no_10_2026():
    identity = parse_usenet_name("Linux-Magazin.No.10.2026.eBook-GROUP", category=7010)
    assert identity.kind == "magazine"
    assert identity.title == "Linux Magazin"
    assert identity.series_index == "2026-10"
    assert identity.year == 2026
    assert identity.confidence == "high"


def test_comic_series_year_issue():
    identity = parse_usenet_name("Saga.2012.001.Digital", category=7030)
    assert identity.kind == "comic"
    assert identity.series_name == "Saga"
    assert identity.series_index == "1"
    assert identity.year == 2012
    assert identity.title == "Saga #1"


def test_book_isbn_author_title_high():
    identity = parse_usenet_name("Le Guin - The Left Hand of Darkness 9780441478125 eBook-GROUP", category=7020)
    assert identity.kind == "book"
    assert identity.author == "Le Guin"
    assert "Left Hand of Darkness" in identity.title
    assert identity.isbn.startswith("978")
    assert identity.confidence == "high"


def test_movie_category_refused_as_book_fallback_low():
    identity = parse_usenet_name("Some.Movie.2024", category=2000)
    assert identity.kind == "book"
    assert identity.confidence == "low"


def test_identify_no_payload_review(tmp_path):
    folder = tmp_path / "empty-release"
    folder.mkdir()
    result = identify_completed(folder, indexer_item={"title": "Mystery", "category": 7020})
    assert result["auto_organize"] is False
    assert result["identity"]["review_reason"] == "no_payload"
    assert result["files"] == []


def test_identify_pdf_only_book_goes_to_review(tmp_path):
    folder = tmp_path / "Le Guin - A Book 9780441478125"
    folder.mkdir()
    (folder / "A Book.pdf").write_bytes(b"%PDF")
    result = identify_completed(folder, category=7020)
    assert result["auto_organize"] is False
    assert result["identity"]["review_reason"] == "convert_failed"


def test_dest_layout_book_and_comic():
    settings = Settings()
    book = dest_layout(
        {"kind": "book", "title": "Dune", "author": "Herbert"},
        settings,
        filename="Dune.epub",
    )
    assert book == Path("/data/media/books/Herbert/Dune/Dune.epub")
    comic = dest_layout(
        {"kind": "comic", "title": "Saga #1", "series_name": "Saga", "series_index": "1"},
        settings,
        filename="saga.cbz",
    )
    assert comic == Path("/data/media/comics/Saga/1/Saga #1.cbz")
