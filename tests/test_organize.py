from pathlib import Path

import pytest

from librarian.config import Settings
from librarian.db import Database
from librarian.organize import (
    MISSING_FOLDER_APPLY_ERROR,
    apply_review,
    organize_identified,
    promote_music,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "magazines"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "audiobooks"),
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
    )


def test_organize_epub_book_writes_opf(tmp_path):
    folder = tmp_path / "complete" / "Le Guin - The Left Hand of Darkness 9780441478125"
    folder.mkdir(parents=True)
    (folder / "book.epub").write_bytes(b"epub")
    db = Database(tmp_path / "librarian.db")
    result = organize_identified(
        db,
        _settings(tmp_path),
        folder=folder,
        indexer_item={
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": "9780441478125",
            "category": 7020,
            "guid": "guid-1",
            "name": folder.name,
        },
    )
    assert result["organized"] is True
    dest = Path(result["files"][0])
    assert dest.name == "The Left Hand of Darkness.epub"
    assert dest.parent.name == "The Left Hand of Darkness"
    assert dest.parent.parent.name == "Le Guin"
    assert (dest.parent / "metadata.opf").is_file()
    opf = (dest.parent / "metadata.opf").read_text(encoding="utf-8")
    assert "The Left Hand of Darkness" in opf
    assert "9780441478125" in opf
    work = db.get_work(result["work"]["id"])
    assert work["review_state"] == "none"
    assert work["kind"] == "book"


def test_collision_goes_to_review(tmp_path):
    settings = _settings(tmp_path)
    dest_dir = Path(settings.books_root) / "Le Guin" / "The Left Hand of Darkness"
    dest_dir.mkdir(parents=True)
    (dest_dir / "The Left Hand of Darkness.epub").write_bytes(b"old")
    folder = tmp_path / "complete" / "fresh"
    folder.mkdir(parents=True)
    (folder / "book.epub").write_bytes(b"new")
    db = Database(tmp_path / "librarian.db")
    result = organize_identified(
        db,
        settings,
        folder=folder,
        indexer_item={
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": "9780441478125",
            "category": 7020,
            "name": "Le Guin - The Left Hand of Darkness 9780441478125",
        },
    )
    assert result["organized"] is False
    assert result["identity"]["review_reason"] == "collision"
    assert result["work"]["review_state"] == "needs_review"


def test_promote_music_moves_tree(tmp_path):
    settings = _settings(tmp_path)
    incoming = Path(settings.incoming_music_root) / "Miles" / "Kind of Blue"
    incoming.mkdir(parents=True)
    track = incoming / "track.flac"
    track.write_bytes(b"flac")
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "music",
            "title": "Kind of Blue",
            "author": "Miles",
            "folder_path": str(incoming),
            "music_state": "incoming",
        }
    )
    db.add_file(
        {
            "work_id": work["id"],
            "path": str(track),
            "filename": track.name,
            "kind": "music",
            "size": 4,
        }
    )
    promoted = promote_music(db, settings, work["id"])
    dest = Path(settings.music_root) / "Miles" / "Kind of Blue"
    assert dest.is_dir()
    assert (dest / "track.flac").is_file()
    assert not incoming.exists()
    assert promoted["music_state"] == "promoted"
    assert promoted["folder_path"] == str(dest)
    stored = db.files_for_work(work["id"])
    assert stored[0]["path"] == str(dest / "track.flac")
    assert Path(stored[0]["path"]).is_file()


def test_loose_comic_images_convert_and_cover(tmp_path):
    folder = tmp_path / "Saga.2024.001.Digital"
    folder.mkdir()
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 80
    (folder / "page-01.jpg").write_bytes(jpeg)
    (folder / "page-02.jpg").write_bytes(jpeg)
    db = Database(tmp_path / "librarian.db")
    result = organize_identified(db, _settings(tmp_path), folder=folder)
    assert result["organized"] is True
    dest = Path(result["files"][0])
    assert dest.suffix == ".cbz"
    assert dest.name == "Saga v2024 #1 (2024).cbz"
    assert dest.parent.name == "Saga (2024)"
    assert dest.parent.parent.name == "Unknown Publisher"
    assert (dest.parent / "ComicInfo.xml").is_file()
    assert (dest.parent / "cover.jpg").read_bytes() == jpeg
    work = db.get_work(result["work"]["id"])
    assert work["cover_path"] == str(dest.parent / "cover.jpg")
    assert work["kind"] == "comic"
    assert work["series_index"] == "1"


def test_review_persists_source_folder_and_apply_uses_identity(tmp_path):
    folder = tmp_path / "complete" / "Mystery.Release"
    folder.mkdir(parents=True)
    (folder / "book.epub").write_bytes(b"epub")
    db = Database(tmp_path / "librarian.db")
    parked = organize_identified(db, _settings(tmp_path), folder=folder, apply=False)
    assert parked["organized"] is False
    assert parked["work"]["folder_path"] == str(folder)
    result = apply_review(
        db,
        _settings(tmp_path),
        work_id=parked["work"]["id"],
        folder=folder,
        identity_overrides={
            "title": "Christine",
            "author": "Stephen King",
            "isbn": "9780670800000",
            "kind": "book",
        },
    )
    assert result["organized"] is True
    stored = db.get_work(parked["work"]["id"])
    assert stored["title"] == "Christine"
    assert stored["author"] == "Stephen King"
    assert stored["review_state"] == "none"
    dest = Path(result["files"][0])
    assert dest.parent.name == "Christine"
    assert dest.parent.parent.name == "Stephen King"


def test_apply_review_no_payload_raises(tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir()
    db = Database(tmp_path / "librarian.db")
    parked = organize_identified(
        db,
        _settings(tmp_path),
        folder=folder,
        indexer_item={"title": "Mystery", "category": 7020},
    )
    assert parked["work"]["review_reason"] == "no_payload"
    assert parked["work"]["folder_path"] == str(folder)
    with pytest.raises(ValueError, match="cannot invent"):
        apply_review(
            db,
            _settings(tmp_path),
            work_id=parked["work"]["id"],
            folder=folder,
            identity_overrides={"title": "Nope", "kind": "book"},
        )


def test_apply_review_empty_folder_does_not_scan_cwd(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {"kind": "book", "title": "Mystery", "review_state": "needs_review", "review_reason": "no_payload"}
    )
    with pytest.raises(ValueError, match="No complete folder"):
        apply_review(db, _settings(tmp_path), work_id=work["id"], folder=Path(""), identity_overrides={})
    assert MISSING_FOLDER_APPLY_ERROR


def test_apply_review_complete_root_remap(tmp_path):
    host = tmp_path / "downloads" / "books" / "King"
    host.mkdir(parents=True)
    (host / "book.epub").write_bytes(b"epub")
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Christine",
            "author": "King",
            "isbn": "9780670800000",
            "review_state": "needs_review",
            "review_reason": "no_payload",
            "folder_path": "/downloads/books/King",
        }
    )
    settings = _settings(tmp_path)
    settings.complete_root = str(tmp_path / "downloads")
    result = apply_review(
        db,
        settings,
        work_id=work["id"],
        folder=Path("/downloads/books/King"),
        identity_overrides={"title": "Christine", "author": "King", "isbn": "9780670800000", "kind": "book"},
    )
    assert result["organized"] is True
    stored = db.get_work(work["id"])
    assert stored["review_state"] == "none"
    assert Path(result["files"][0]).parent.name == "Christine"


def _flac_with_tags(path: Path, tags: dict[str, str]) -> None:
    comments = []
    for key, value in tags.items():
        raw = f"{key}={value}".encode("utf-8")
        comments.append(len(raw).to_bytes(4, "little") + raw)
    vendor = b"librarian"
    body = len(vendor).to_bytes(4, "little") + vendor
    body += len(comments).to_bytes(4, "little") + b"".join(comments)
    header = bytes([0x80 | 4]) + len(body).to_bytes(3, "big")
    path.write_bytes(b"fLaC" + header + body)


def _epub_with_isbn(path: Path, *, isbn: str, title: str = "", creator: str = "") -> None:
    from zipfile import ZipFile

    opf = f"""<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="id" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{title}</dc:title>
    <dc:creator>{creator}</dc:creator>
    <dc:identifier id="id">urn:isbn:{isbn}</dc:identifier>
  </metadata>
</package>
"""
    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
        )
        archive.writestr("OEBPS/content.opf", opf)


def test_organize_epub_opf_isbn_uses_catalog_title_not_filename(tmp_path):
    folder = tmp_path / "Herbert-Dune-ebook-GROUP"
    folder.mkdir()
    _epub_with_isbn(folder / "dump.epub", isbn="9780441172719", creator="Herbert")

    def catalog_lookup(identity):
        assert identity.isbn == "9780441172719"
        return {"title": "Dune", "author": "Frank Herbert"}

    db = Database(tmp_path / "librarian.db")
    result = organize_identified(
        db,
        _settings(tmp_path),
        folder=folder,
        catalog_lookup=catalog_lookup,
    )
    assert result["organized"] is True
    dest = Path(result["files"][0])
    assert dest.parent.name == "Dune"
    assert dest.parent.parent.name == "Herbert"
    assert dest.name == "Dune.epub"
    assert dest.is_relative_to(Path(_settings(tmp_path).books_root)) or str(_settings(tmp_path).books_root) in str(dest)


def test_organize_cbz_comicinfo_layout(tmp_path):
    from zipfile import ZipFile

    folder = tmp_path / "complete" / "random-comic-dump"
    folder.mkdir(parents=True)
    with ZipFile(folder / "dump.cbz", "w") as archive:
        archive.writestr("page-01.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 80)
        archive.writestr(
            "ComicInfo.xml",
            """<?xml version="1.0"?><ComicInfo><Series>Saga</Series><Number>54</Number><Year>2018</Year></ComicInfo>""",
        )
    db = Database(tmp_path / "librarian.db")
    result = organize_identified(db, _settings(tmp_path), folder=folder)
    assert result["organized"] is True
    dest = Path(result["files"][0])
    assert dest.parent.parent.name == "Unknown Publisher"
    assert dest.parent.name == "Saga"
    assert dest.name == "Saga #54 (2018).cbz"
    assert (dest.parent / "ComicInfo.xml").is_file()


def test_organize_flac_album_from_tags(tmp_path):
    folder = tmp_path / "complete" / "VA-Dump.Name-202"
    folder.mkdir(parents=True)
    tags = {"ALBUM": "Kind of Blue", "ALBUMARTIST": "Miles Davis", "ARTIST": "Miles Davis"}
    _flac_with_tags(folder / "01 So What.flac", {**tags, "TITLE": "So What", "TRACKNUMBER": "1"})
    _flac_with_tags(folder / "02 Freddie.flac", {**tags, "TITLE": "Freddie Freeloader", "TRACKNUMBER": "2"})
    db = Database(tmp_path / "librarian.db")
    result = organize_identified(db, _settings(tmp_path), folder=folder)
    assert result["organized"] is True
    dests = [Path(path) for path in result["files"]]
    album = dests[0].parent
    assert album.name == "Kind of Blue"
    assert album.parent.name == "Miles Davis"
    assert album.parent.parent == Path(_settings(tmp_path).incoming_music_root)
    assert {path.name for path in dests} == {"01 - So What.flac", "02 - Freddie Freeloader.flac"}
    work = db.get_work(result["work"]["id"])
    assert work["title"] == "Kind of Blue"
    assert work["kind"] == "music"
    assert work["music_state"] == "incoming"


def test_organize_single_track_joins_existing_incoming_album(tmp_path):
    settings = _settings(tmp_path)
    album = Path(settings.incoming_music_root) / "Miles Davis" / "Kind of Blue"
    album.mkdir(parents=True)
    existing_track = album / "01 So What.flac"
    _flac_with_tags(
        existing_track,
        {
            "ALBUM": "Kind of Blue",
            "ALBUMARTIST": "Miles Davis",
            "TITLE": "So What",
            "TRACKNUMBER": "1",
        },
    )
    db = Database(tmp_path / "librarian.db")
    existing = db.upsert_work(
        {
            "kind": "music",
            "title": "Kind of Blue",
            "author": "Miles Davis",
            "series_name": "Kind of Blue",
            "folder_path": str(album),
            "music_state": "incoming",
        }
    )
    dump = tmp_path / "complete" / "single-track-dump"
    dump.mkdir(parents=True)
    _flac_with_tags(
        dump / "track.flac",
        {
            "ALBUM": "Kind of Blue",
            "ALBUMARTIST": "Miles Davis",
            "TITLE": "Freddie Freeloader",
            "TRACKNUMBER": "2",
        },
    )
    result = organize_identified(db, settings, folder=dump)
    assert result["organized"] is True
    dest = Path(result["files"][0])
    assert dest.parent == album
    assert dest.name == "02 - Freddie Freeloader.flac"
    assert dest.is_file()
    assert existing_track.is_file()
    assert result["work"]["id"] == existing["id"]
    assert db.get_work(existing["id"])["title"] == "Kind of Blue"


def test_organize_sought_title_wins_over_dump_folder(tmp_path):
    folder = tmp_path / "complete" / "Herbert-Dune-1977-ebook-GROUP"
    folder.mkdir(parents=True)
    (folder / "dump.epub").write_bytes(b"epub")
    db = Database(tmp_path / "librarian.db")
    result = organize_identified(
        db,
        _settings(tmp_path),
        folder=folder,
        indexer_item={
            "title": "Herbert-Dune-1977-ebook-GROUP",
            "kind": "book",
            "sought": {"kind": "book", "title": "Dune", "author": "Herbert", "isbn": "9780441172719"},
            "selected": {"title": "Herbert-Dune-1977-ebook-GROUP"},
            "retrieved": {"book_title": "Dune", "isbn": "9780441172719"},
        },
    )
    assert result["organized"] is True
    dest = Path(result["files"][0])
    assert dest.parent.name == "Dune"
    assert dest.name == "Dune.epub"
    assert result["work"]["title"] == "Dune"


def test_organize_title_only_stays_review_without_invented_isbn(tmp_path):
    folder = tmp_path / "complete" / "A Mysterious Novel"
    folder.mkdir(parents=True)
    (folder / "book.epub").write_bytes(b"epub")
    db = Database(tmp_path / "librarian.db")
    result = organize_identified(db, _settings(tmp_path), folder=folder)
    assert result["organized"] is False
    assert result["identity"]["isbn"] in ("", None)
    assert result["work"]["review_state"] == "needs_review"
    assert result["work"]["isbn"] in ("", None)


def test_organize_audiobook_tags_never_music_root(tmp_path):
    folder = tmp_path / "complete" / "audio-dump"
    folder.mkdir(parents=True)
    _flac_with_tags(
        folder / "part01.flac",
        {
            "ALBUM": "The Left Hand of Darkness",
            "ALBUMARTIST": "Le Guin",
            "TITLE": "Chapter 1",
            "GENRE": "Audiobook",
            "MEDIA": "Audiobook",
        },
    )
    db = Database(tmp_path / "librarian.db")
    settings = _settings(tmp_path)
    # Audnexus is required for auto-organize; force shelves once kind is spoken-word.
    result = organize_identified(
        db,
        settings,
        folder=folder,
        force=True,
        identity_overrides={"kind": "audiobook", "asin": "B000TEST01"},
    )
    assert result["organized"] is True
    dest = Path(result["files"][0])
    assert dest.is_relative_to(Path(settings.audiobooks_root))
    assert not dest.is_relative_to(Path(settings.music_root))
    assert not dest.is_relative_to(Path(settings.incoming_music_root))
    assert result["work"]["kind"] == "audiobook"


def test_organize_persists_part_set_from_nzb_title(tmp_path):
    folder = tmp_path / "complete" / "feist-magician-p3"
    folder.mkdir(parents=True)
    (folder / "Magician Part 3.m4b").write_bytes(b"m4b")
    db = Database(tmp_path / "librarian.db")
    result = organize_identified(
        db,
        _settings(tmp_path),
        folder=folder,
        force=True,
        identity_overrides={
            "kind": "audiobook",
            "title": "Magician",
            "author": "Raymond E. Feist",
        },
        indexer_item={
            "title": "Raymond E. Feist - Magician Part 3/5",
            "author": "Feist",
            "guid": "guid-part-3",
            "name": folder.name,
            "kind": "audiobook",
        },
    )
    assert result["organized"] is True
    work = db.get_work(result["work"]["id"])
    assert work["part_total"] == 5
    assert work["part_style"] == "part"
    assert work["part_base"]
    files = db.files_for_work(work["id"])
    assert len(files) == 1
    assert files[0]["part"] == 3


def test_organize_music_writes_cover_from_caa(tmp_path):
    import httpx

    settings = _settings(tmp_path)
    folder = tmp_path / "complete" / "Miles Davis - Kind of Blue"
    folder.mkdir(parents=True)
    _flac_with_tags(
        folder / "01 So What.flac",
        {
            "ALBUM": "Kind of Blue",
            "ALBUMARTIST": "Miles Davis",
            "TITLE": "So What",
            "TRACKNUMBER": "1",
            "MUSICBRAINZ_ALBUMID": "f5099ac0-b5c3-4d4a-b3b8-example0001",
        },
    )
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 80

    def handler(request):
        return httpx.Response(200, content=jpeg, headers={"content-type": "image/jpeg"})

    db = Database(tmp_path / "librarian.db")
    result = organize_identified(
        db,
        settings,
        folder=folder,
        indexer_item={
            "title": "Kind of Blue",
            "author": "Miles Davis",
            "kind": "music",
            "category": 3010,
            "name": folder.name,
            "mbid": "f5099ac0-b5c3-4d4a-b3b8-example0001",
        },
        cover_transport=httpx.MockTransport(handler),
    )
    assert result["organized"] is True
    cover = Path(result["work"]["cover_path"])
    assert cover.name == "cover.jpg"
    assert cover.read_bytes() == jpeg


def test_organize_par2_then_unar_when_archives_stuck(tmp_path, monkeypatch):
    from types import SimpleNamespace

    folder = tmp_path / "complete" / "VA-Guardians.Mix"
    folder.mkdir(parents=True)
    (folder / "mix.rar").write_bytes(b"Rar!")
    (folder / "mix.par2").write_bytes(b"PAR2")
    calls = []

    def runner(argv, timeout=120):
        calls.append(list(argv))
        if len(argv) >= 2 and argv[1] == "r":
            return SimpleNamespace(returncode=0)
        (folder / "01 Track.flac").write_bytes(b"flac")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("librarian.convert.which_par2", lambda: "/usr/bin/par2")
    monkeypatch.setattr("librarian.convert.which_unar", lambda: "/usr/bin/unar")
    db = Database(tmp_path / "librarian.db")
    result = organize_identified(
        db,
        _settings(tmp_path),
        folder=folder,
        indexer_item={
            "title": "Awesome Mix Vol. 1",
            "author": "Various Artists",
            "kind": "music",
            "category": 3010,
            "name": folder.name,
            "guid": "g-mix",
        },
        convert_runner=runner,
    )
    assert any(call[:2] == ["/usr/bin/par2", "r"] for call in calls)
    assert any(call[0] == "/usr/bin/unar" for call in calls)
    assert calls.index(next(c for c in calls if c[:2] == ["/usr/bin/par2", "r"])) < calls.index(
        next(c for c in calls if c[0] == "/usr/bin/unar")
    )
    assert result["organized"] is True
    assert result["work"]["kind"] == "music"
    assert Path(result["files"][0]).suffix == ".flac"
