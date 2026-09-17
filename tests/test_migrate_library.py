"""Books blend / library roots migration (dry-run safe)."""

from __future__ import annotations

from pathlib import Path

from librarian.migrate_library import (
    create_library_roots,
    migrate_books,
    strip_calibre_id,
)


def _calibre_title(root: Path, author: str, title_with_id: str, *, files: dict[str, bytes]) -> Path:
    folder = root / author / title_with_id
    folder.mkdir(parents=True)
    for name, body in files.items():
        (folder / name).write_bytes(body)
    return folder


def test_strip_calibre_id():
    assert strip_calibre_id("To the Edge (1216)") == "To the Edge"
    assert strip_calibre_id("Plain Title") == "Plain Title"


def test_create_library_roots_dry_run(tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    created = create_library_roots(media, dry_run=True)
    assert any(path.endswith("library/books") for path in created)
    assert not (media / "library" / "books").exists()
    created = create_library_roots(media, dry_run=False)
    assert (media / "library" / "books").is_dir()
    assert (media / "library" / "audiobooks").is_dir()
    assert (media / "library" / "incoming-music").is_dir()
    # music stays outside library/
    assert not (media / "library" / "music").exists()


def test_migrate_calibre_prefers_epub_and_strips_id(tmp_path):
    media = tmp_path / "media"
    calibre = media / "books" / "LonesomeLib" / "Calibre Library"
    _calibre_title(
        calibre,
        "Cindy Gerard",
        "To the Edge (1216)",
        files={
            "To the Edge - Cindy Gerard.epub": b"EPUB",
            "To the Edge - Cindy Gerard.azw3": b"AZW3",
            "cover.jpg": b"JPEG",
            "metadata.opf": b"""<?xml version='1.0'?>
<package xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>To the Edge</dc:title>
    <dc:creator>Cindy Gerard</dc:creator>
    <dc:identifier>9781234567890</dc:identifier>
  </metadata>
</package>
""",
        },
    )
    # junk must be ignored
    (calibre / ".calnotes").mkdir()
    (media / "books" / ".config").mkdir(parents=True)

    dest = media / "library" / "books"
    report = migrate_books(media / "books", dest, dry_run=False)
    counts = report.counts()
    assert counts.get("copy") == 1
    assert counts.get("junk") in (None, 0)
    dest_dir = dest / "Cindy Gerard" / "To the Edge"
    assert (dest_dir / "To the Edge - Cindy Gerard.epub").is_file()
    assert (dest_dir / "To the Edge - Cindy Gerard.azw3").is_file()
    assert (dest_dir / "cover.jpg").is_file()
    # source preserved (copy-then-cutover)
    assert (calibre / "Cindy Gerard" / "To the Edge (1216)" / "To the Edge - Cindy Gerard.epub").is_file()


def test_migrate_collision_does_not_overwrite(tmp_path):
    media = tmp_path / "media"
    calibre = media / "books" / "LonesomeLib" / "Calibre Library"
    _calibre_title(
        calibre,
        "Author",
        "Same Title (1)",
        files={"Same Title.epub": b"NEW"},
    )
    dest = media / "library" / "books"
    existing = dest / "Author" / "Same Title"
    existing.mkdir(parents=True)
    (existing / "Same Title.epub").write_bytes(b"OLD")

    report = migrate_books(media / "books", dest, dry_run=False)
    assert report.counts().get("collision") == 1
    assert (existing / "Same Title.epub").read_bytes() == b"OLD"


def test_migrate_same_isbn_skips(tmp_path):
    media = tmp_path / "media"
    calibre = media / "books" / "LonesomeLib" / "Calibre Library"
    opf = b"""<?xml version='1.0'?>
<package xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Duped</dc:title>
    <dc:creator>Author</dc:creator>
    <dc:identifier id="isbn">9780000000002</dc:identifier>
  </metadata>
</package>
"""
    _calibre_title(
        calibre,
        "Author",
        "Duped (9)",
        files={"Duped.epub": b"A", "metadata.opf": opf},
    )
    dest = media / "library" / "books"
    existing = dest / "Author" / "Duped"
    existing.mkdir(parents=True)
    (existing / "Duped.epub").write_bytes(b"SHELF")
    (existing / "metadata.opf").write_bytes(opf)

    report = migrate_books(media / "books", dest, dry_run=False)
    assert report.counts().get("skip") == 1
    assert (existing / "Duped.epub").read_bytes() == b"SHELF"


def test_cli_dry_run_default(tmp_path, capsys):
    from librarian.migrate_library import main

    media = tmp_path / "media"
    calibre = media / "books" / "LonesomeLib" / "Calibre Library"
    _calibre_title(
        calibre,
        "A",
        "T (1)",
        files={"T.epub": b"E"},
    )
    code = main(
        [
            "--media-root",
            str(media),
            "--migrate-books",
            "--create-roots",
        ]
    )
    assert code == 0
    assert not (media / "library" / "books" / "A" / "T").exists()
    out = capsys.readouterr().out
    assert "dry-run" in out
