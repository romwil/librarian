from pathlib import Path

from librarian.serve import can_read_work, media_type_for, primary_reading_path


def test_primary_reading_path_prefers_payload_over_cover(tmp_path):
    cover = tmp_path / "cover.jpg"
    pdf = tmp_path / "Linux Magazine 2026-10.pdf"
    epub = tmp_path / "Linux Magazine 2026-10.epub"
    cover.write_bytes(b"jpeg")
    pdf.write_bytes(b"%PDF-")
    epub.write_bytes(b"PK\x03\x04")
    picked = primary_reading_path([cover, pdf, epub])
    assert picked == epub
    assert can_read_work("magazine", [cover, pdf]) is True
    assert can_read_work("music", [cover]) is False
    assert can_read_work("audiobook", [tmp_path / "Dune.m4b"]) is False
    assert can_read_work("book", []) is False


def test_media_type_for_epub_and_cbz():
    assert media_type_for(Path("Piranesi.epub")) == "application/epub+zip"
    assert media_type_for(Path("Saga #54.cbz")) == "application/vnd.comicbook+zip"
    assert media_type_for(Path("issue.pdf")) == "application/pdf"
