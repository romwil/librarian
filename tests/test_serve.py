from pathlib import Path

from librarian.serve import (
    annotate_work_files,
    can_read_work,
    existing_file_paths,
    media_type_for,
    primary_reading_path,
)


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


def test_annotate_work_files_marks_reading_room_source(tmp_path):
    epub = tmp_path / "King Tut.epub"
    azw3 = tmp_path / "King Tut.azw3"
    missing = tmp_path / "ghost.epub"
    epub.write_bytes(b"PK\x03\x04")
    azw3.write_bytes(b"AZW3")
    rows = [
        {"id": 1, "path": str(azw3), "filename": azw3.name},
        {"id": 2, "path": str(epub), "filename": epub.name},
        {"id": 3, "path": str(missing), "filename": missing.name},
    ]
    on_disk = existing_file_paths(rows)
    annotated = annotate_work_files(rows, on_disk)
    by_name = {row["filename"]: row for row in annotated}
    assert by_name[epub.name]["reading_room"] is True
    assert by_name[epub.name]["on_disk"] is True
    assert by_name[azw3.name]["reading_room"] is False
    assert by_name[azw3.name]["on_disk"] is True
    assert by_name[missing.name]["on_disk"] is False
    assert by_name[missing.name]["reading_room"] is False
    assert primary_reading_path(on_disk) == epub
    assert can_read_work("book", on_disk) is True
    assert can_read_work("book", [azw3]) is False
