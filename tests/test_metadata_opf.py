from pathlib import Path

from librarian.metadata import parse_opf_bytes, write_opf


def test_opf_subject_round_trip(tmp_path):
    folder = tmp_path / "book"
    write_opf(
        folder,
        {
            "title": "Dune",
            "author": "Frank Herbert",
            "isbn": "9780441172719",
            "genre": "Science fiction, Planets",
            "description": "Desert planet.",
            "year": 1965,
        },
    )
    parsed = parse_opf_bytes((folder / "metadata.opf").read_bytes())
    assert parsed["genre"] == "Science fiction, Planets"
    assert parsed["title"] == "Dune"
    xml = (folder / "metadata.opf").read_text(encoding="utf-8")
    assert xml.count("<dc:subject>") == 2
    assert "Science fiction" in xml
    assert "Planets" in xml


def test_parse_opf_reads_multiple_subjects():
    xml = b"""<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Kindred</dc:title>
    <dc:creator>Butler</dc:creator>
    <dc:subject>Fiction</dc:subject>
    <dc:subject>Time travel</dc:subject>
  </metadata>
</package>
"""
    parsed = parse_opf_bytes(xml)
    assert parsed["genre"] == "Fiction, Time travel"
