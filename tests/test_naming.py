"""Real folder and release names through the one naming parser."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from librarian.naming import (
    Identity,
    library_file_fields,
    parse_library_volume,
    parse_usenet_name,
    restore_path_punctuation,
)
from librarian.slip_gate import folder_is_path_clear, sign_path_clear_book

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "naming" / "real_folder_names.json"
ROWS = json.loads(FIXTURES.read_text(encoding="utf-8"))


def _rows(layer: str):
    return [pytest.param(row, id=row["id"]) for row in ROWS if row["layer"] == layer]


def _volume(tmp_path: Path, row) -> Path:
    folder = tmp_path.joinpath(*row["path"])
    folder.mkdir(parents=True)
    return folder


def test_fixture_table_covers_every_layer():
    layers = {row["layer"] for row in ROWS}
    assert layers == {"release", "library", "scan"}
    assert len({row["id"] for row in ROWS}) == len(ROWS)


@pytest.mark.parametrize("row", _rows("release"))
def test_release_names(row):
    identity = parse_usenet_name(row["name"], kind=row["kind"], category=row["category"])
    got = identity.as_dict()
    for key, wanted in row["expect"].items():
        assert got[key] == wanted, f"{row['id']}.{key}: {got[key]!r} != {wanted!r}"


@pytest.mark.parametrize("row", _rows("library"))
def test_library_volumes(tmp_path, row):
    folder = _volume(tmp_path, row)
    assert parse_library_volume(folder) == row["expect"]


@pytest.mark.parametrize("row", _rows("scan"))
def test_scanned_files(tmp_path, row):
    folder = _volume(tmp_path, row)
    payload = folder / row["file"]
    payload.write_bytes(b"x")
    assert library_file_fields(row["kind"], folder, [payload]) == row["expect"]


@pytest.mark.parametrize(
    "row",
    [param for param in _rows("library") if param.values[0]["expect"]],
)
def test_clear_library_volumes_sign_high_without_isbn(tmp_path, row):
    folder = _volume(tmp_path, row)
    book = folder / "book.epub"
    book.write_bytes(b"epub")
    assert folder_is_path_clear(folder) is True
    identity = Identity(kind="book", title="", confidence="low", review_reason="low_confidence")
    sign_path_clear_book(identity, folder, [book])
    assert identity.confidence == "high"
    assert identity.review_reason is None
    assert identity.author == row["expect"]["author"]
    assert identity.title == row["expect"]["title"]


@pytest.mark.parametrize(
    "row",
    [param for param in _rows("library") if not param.values[0]["expect"]],
)
def test_staging_and_dump_volumes_stay_unsigned(tmp_path, row):
    folder = _volume(tmp_path, row)
    book = folder / "book.epub"
    book.write_bytes(b"epub")
    assert folder_is_path_clear(folder) is False
    identity = Identity(kind="book", title="Dune", author="Frank Herbert", review_reason="low_confidence")
    sign_path_clear_book(identity, folder, [book])
    assert identity.confidence == "low"
    assert identity.review_reason == "low_confidence"


@pytest.mark.parametrize(
    ("raw", "restored"),
    [
        ("Box, C.J_", "Box, C.J."),
        ("Vandagriff, G.G_", "Vandagriff, G.G."),
        ("Resist_ Tales from a Future", "Resist: Tales from a Future"),
        ("Some_Author_Collection", "Some_Author_Collection"),
        ("snake_case", "snake_case"),
        ("Ursula K. Le Guin", "Ursula K. Le Guin"),
    ],
)
def test_restore_path_punctuation(raw, restored):
    assert restore_path_punctuation(raw) == restored


def test_old_import_paths_resolve_to_naming():
    import librarian.audiobook_normalize as audiobook_normalize
    import librarian.comic_normalize as comic_normalize
    import librarian.identify as identify
    import librarian.naming as naming
    import librarian.slip_gate as slip_gate

    assert identify.parse_usenet_name is naming.parse_usenet_name
    assert identify.Identity is naming.Identity
    assert identify.tidy_title is naming.tidy_title
    assert identify.filename_identity is naming.release_file_fields
    assert slip_gate.parse_library_volume is naming.parse_library_volume
    assert audiobook_normalize.normalize_audiobook_name is naming.normalize_audiobook_name
    assert comic_normalize.normalize_comic_name is naming.normalize_comic_name
