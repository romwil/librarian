from pathlib import Path

from librarian.serve import (
    annotate_work_files,
    can_read_work,
    existing_file_paths,
    is_streamable_audio,
    media_type_for,
    primary_reading_path,
    resolve_catalog_file,
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


def test_is_streamable_audio_allows_mutagen_formats_not_ebooks():
    assert is_streamable_audio(Path("01-track.flac")) is True
    assert is_streamable_audio(Path("02-track.mp3")) is True
    assert is_streamable_audio(Path("03-track.m4a")) is True
    assert is_streamable_audio(Path("04-track.wav")) is True
    assert is_streamable_audio(Path("notes.pdf")) is False
    assert is_streamable_audio(Path("Piranesi.epub")) is False
    assert is_streamable_audio(Path("cover.jpg")) is False


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


def test_annotate_marks_every_magazine_pdf_for_reading_room(tmp_path):
    vol1 = tmp_path / "The Hacker Digest - Volume 01.pdf"
    vol2 = tmp_path / "The Hacker Digest - Volume 02.pdf"
    cover = tmp_path / "cover.jpg"
    vol1.write_bytes(b"%PDF-1")
    vol2.write_bytes(b"%PDF-2")
    cover.write_bytes(b"jpeg")
    rows = [
        {"id": "a", "path": str(vol1), "filename": vol1.name},
        {"id": "b", "path": str(vol2), "filename": vol2.name},
        {"id": "c", "path": str(cover), "filename": cover.name},
    ]
    on_disk = existing_file_paths(rows)
    annotated = annotate_work_files(rows, on_disk)
    by_name = {row["filename"]: row for row in annotated}
    assert by_name[vol1.name]["reading_room"] is True
    assert by_name[vol2.name]["reading_room"] is True
    assert by_name[cover.name]["reading_room"] is False
    assert primary_reading_path(on_disk) == vol1
    assert resolve_catalog_file(rows, "b") == vol2
    assert resolve_catalog_file(rows, "missing") is None
