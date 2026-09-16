from pathlib import Path

from librarian.config import Settings
from librarian.identify import (
    dest_layout,
    identify_completed,
    inspect_complete_folder,
    parse_usenet_name,
    resolve_storage_path,
)


class _RaiseLLM:
    def identify(self, evidence: str):
        raise RuntimeError("llm unavailable")


class _StubLLM:
    def __init__(self, payload):
        self.payload = payload

    def identify(self, evidence: str):
        return self.payload


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


def test_resolve_storage_path_maps_downloads_prefix(tmp_path):
    host = tmp_path / "downloads" / "books" / "Christine - Stephen King"
    host.mkdir(parents=True)
    epub = host / "Christine - Stephen King.epub"
    epub.write_bytes(b"epub")
    mapped = resolve_storage_path(
        Path("/downloads/books/Christine - Stephen King/Christine - Stephen King.epub"),
        str(tmp_path / "downloads"),
    )
    assert mapped == epub
    missing = resolve_storage_path(Path("/downloads/books/Missing"), str(tmp_path / "downloads"))
    assert missing == tmp_path / "downloads" / "books" / "Missing"


def test_resolve_storage_path_does_not_double_downloads_prefix(tmp_path):
    complete = tmp_path / "downloads"
    complete.mkdir()
    doubled = resolve_storage_path(Path("/downloads/VA-Guardians.Mix"), str(complete))
    assert doubled == complete / "VA-Guardians.Mix"
    assert doubled != complete / "downloads" / "VA-Guardians.Mix"


def test_resolve_storage_path_maps_sab_category_downloads_folder(tmp_path):
    host = tmp_path / "usenet" / "complete" / "downloads" / "VA-Guardians.Of.The.Galaxy.Awesome.Mix.Vol.1-202"
    host.mkdir(parents=True)
    (host / "01 Track.flac").write_bytes(b"flac")
    mapped = resolve_storage_path(
        Path("/downloads/downloads/VA-Guardians.Of.The.Galaxy.Awesome.Mix.Vol.1-202"),
        str(tmp_path / "usenet" / "complete"),
    )
    assert mapped == host


def test_resolve_storage_path_guesses_leaf_under_complete_root(tmp_path):
    complete = tmp_path / "usenet" / "complete"
    complete.mkdir(parents=True)
    mapped = resolve_storage_path(
        Path("/downloads/downloads/VA-Guardians.Mix"),
        str(complete),
    )
    assert mapped == complete / "VA-Guardians.Mix"
    assert mapped != complete / "downloads" / "VA-Guardians.Mix"


def test_inspect_complete_folder_skips_junk_and_flags_archives(tmp_path):
    stuck = tmp_path / "stuck"
    stuck.mkdir()
    (stuck / "release.rar").write_bytes(b"Rar!")
    (stuck / "release.par2").write_bytes(b"par2")
    (stuck / "file.nfo").write_bytes(b"nfo")
    macos = stuck / "__MACOSX" / "._junk"
    macos.parent.mkdir()
    macos.write_bytes(b"junk")
    inspection = inspect_complete_folder(stuck)
    assert inspection["problem"] == "unpack_stuck"
    assert [path.name for path in inspection["archives"]] == ["release.rar"]
    assert inspection["payload"] == []

    good = tmp_path / "good"
    good.mkdir()
    (good / "book.epub").write_bytes(b"epub")
    (good / "book.par2").write_bytes(b"par2")
    found = inspect_complete_folder(good)
    assert found["problem"] is None
    assert [path.name for path in found["payload"]] == ["book.epub"]


def test_resolve_storage_path_empty_root_uses_fallback(tmp_path, monkeypatch):
    host = tmp_path / "usenet" / "complete" / "downloads" / "VA-Mix"
    host.mkdir(parents=True)
    (host / "01.flac").write_bytes(b"flac")
    monkeypatch.setattr(
        "librarian.identify.COMPLETE_ROOT_FALLBACKS",
        (str(tmp_path / "usenet" / "complete"),),
    )
    mapped = resolve_storage_path(Path("/downloads/downloads/VA-Mix"), "")
    assert mapped == host


def test_identity_from_indexer_keeps_requested_music_kind():
    from librarian.identify import identity_from_indexer

    identity = identity_from_indexer(
        {
            "title": "Awesome Mix Vol. 1",
            "kind": "music",
            "category": None,
            "name": "VA-Guardians.Of.The.Galaxy.Awesome.Mix.Vol.1-202",
        }
    )
    assert identity.kind == "music"
    assert identity.title == "Awesome Mix Vol. 1"


def test_identity_prefers_sought_catalog_over_usenet_dump():
    from librarian.identify import identity_from_indexer

    identity = identity_from_indexer(
        {
            "title": "Herbert-Dune-1977-ebook-GROUP",
            "kind": "book",
            "sought": {"kind": "book", "title": "Dune", "author": "Herbert", "isbn": "9780441172719"},
            "selected": {"title": "Herbert-Dune-1977-ebook-GROUP", "guid": "g-dune"},
            "retrieved": {"book_title": "Dune", "author": "Frank Herbert", "isbn": "9780441172719"},
        }
    )
    assert identity.kind == "book"
    assert identity.title == "Dune"
    assert identity.author == "Herbert"
    assert identity.isbn == "9780441172719"
    assert identity.confidence == "high"


def test_identity_uses_sought_comic_series_and_issue():
    from librarian.identify import identity_from_indexer

    identity = identity_from_indexer(
        {
            "title": "Saga.2012.054.Digital-Group",
            "kind": "comic",
            "sought": {"kind": "comic", "series": "Saga", "issue": "54"},
            "selected": {"title": "Saga.2012.054.Digital-Group", "category": 7030},
        }
    )
    assert identity.kind == "comic"
    assert identity.series_name == "Saga"
    assert identity.series_index == "54"
    assert identity.title == "Saga #54"
    assert identity.confidence == "high"


def test_identify_music_request_without_files_stays_music(tmp_path):
    folder = tmp_path / "VA-Guardians.Of.The.Galaxy.Awesome.Mix.Vol.1-202"
    folder.mkdir()
    result = identify_completed(
        folder,
        indexer_item={
            "title": "VA-Guardians.Of.The.Galaxy.Awesome.Mix.Vol.1-202",
            "kind": "music",
            "guid": "04ddff33-bcf4-464d-a680-07ffa7dbd918",
        },
    )
    assert result["auto_organize"] is False
    assert result["identity"]["kind"] == "music"
    assert result["identity"]["review_reason"] == "no_payload"


def test_identify_pdf_only_book_goes_to_review(tmp_path):
    folder = tmp_path / "Le Guin - A Book 9780441478125"
    folder.mkdir()
    (folder / "A Book.pdf").write_bytes(b"%PDF")
    result = identify_completed(folder, category=7020)
    assert result["auto_organize"] is False
    assert result["identity"]["review_reason"] == "convert_failed"


def test_comic_extra_files_llm_failure_keeps_extra_files(tmp_path):
    folder = tmp_path / "Saga.2012.001.Digital"
    folder.mkdir()
    (folder / "saga-1.cbz").write_bytes(b"cbz")
    (folder / "bonus.cbz").write_bytes(b"cbz")
    result = identify_completed(folder, category=7030, llm_client=_RaiseLLM())
    assert result["auto_organize"] is False
    assert result["identity"]["review_reason"] == "extra_files"
    assert result["identity"]["confidence"] == "low"
    assert result["identity"]["series_name"] == "Saga"
    assert result["identity"]["series_index"] == "1"


def test_comic_extra_files_high_llm_still_needs_review(tmp_path):
    folder = tmp_path / "Saga.2012.001.Digital"
    folder.mkdir()
    (folder / "saga-1.cbz").write_bytes(b"cbz")
    (folder / "bonus.cbz").write_bytes(b"cbz")
    result = identify_completed(
        folder,
        category=7030,
        llm_client=_StubLLM(
            {
                "kind": "comic",
                "title": "Saga #1",
                "series": "Saga",
                "issue": "1",
                "confidence": 0.95,
                "rationale": "series parse",
            }
        ),
    )
    assert result["auto_organize"] is False
    assert result["identity"]["review_reason"] == "extra_files"
    assert result["identity"]["series_name"] == "Saga"
    assert result["identity"]["series_index"] == "1"


def test_comic_low_confidence_llm_keeps_review_reason(tmp_path):
    folder = tmp_path / "Mystery.Release"
    folder.mkdir()
    (folder / "issue.cbz").write_bytes(b"cbz")
    result = identify_completed(
        folder,
        category=7030,
        llm_client=_StubLLM(
            {
                "kind": "comic",
                "title": "Saga #1",
                "series": "Saga",
                "issue": "1",
                "confidence": 0.4,
                "rationale": "guess",
            }
        ),
    )
    assert result["auto_organize"] is False
    assert result["identity"]["review_reason"] == "unknown_identity"
    assert result["identity"]["confidence"] == "low"
    assert result["identity"]["series_name"] == "Saga"
    assert result["identity"]["series_index"] == "1"


def test_comic_high_llm_auto_organizes_clean_folder(tmp_path):
    folder = tmp_path / "Mystery.Release"
    folder.mkdir()
    (folder / "issue.cbz").write_bytes(b"cbz")
    result = identify_completed(
        folder,
        category=7030,
        llm_client=_StubLLM(
            {
                "kind": "comic",
                "title": "Saga #1",
                "series": "Saga",
                "issue": "1",
                "confidence": 0.95,
                "rationale": "series parse",
            }
        ),
    )
    assert result["auto_organize"] is True
    assert result["identity"]["review_reason"] is None
    assert result["identity"]["confidence"] == "high"
    assert result["identity"]["series_name"] == "Saga"
    assert result["identity"]["series_index"] == "1"


def test_magazine_low_confidence_llm_keeps_review_reason(tmp_path):
    folder = tmp_path / "Mystery.Release"
    folder.mkdir()
    (folder / "issue.pdf").write_bytes(b"%PDF")
    result = identify_completed(
        folder,
        category=7010,
        llm_client=_StubLLM(
            {
                "kind": "magazine",
                "title": "Linux Magazin",
                "series": "Linux Magazin",
                "issue": "2026-10",
                "confidence": 0.4,
                "rationale": "guess",
            }
        ),
    )
    assert result["auto_organize"] is False
    assert result["identity"]["review_reason"] == "unknown_identity"
    assert result["identity"]["confidence"] == "low"
    assert result["identity"]["series_name"] == "Linux Magazin"
    assert result["identity"]["series_index"] == "2026-10"


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


def test_comic_filename_variants():
    hashed = parse_usenet_name("Saga #1 (2024).cbz", kind="comic")
    assert hashed.series_name == "Saga"
    assert hashed.series_index == "1"
    assert hashed.year == 2024
    volume = parse_usenet_name("Saga v1 003", kind="comic")
    assert volume.series_name == "Saga"
    assert volume.series_index == "3"
    padded = parse_usenet_name("Saga 001", kind="comic")
    assert padded.series_name == "Saga"
    assert padded.series_index == "1"


def test_magazine_iso_month_filename():
    identity = parse_usenet_name("Linux Magazin 2026-09", kind="magazine")
    assert identity.kind == "magazine"
    assert identity.series_name == "Linux Magazin"
    assert identity.series_index == "2026-09"
    assert identity.year == 2026


def test_identify_epub_opf_isbn_uses_catalog_title(tmp_path):
    from zipfile import ZipFile

    folder = tmp_path / "Some.Dump.GROUP"
    folder.mkdir()
    epub = folder / "dump.epub"
    opf = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="id" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="id">urn:isbn:9780441478125</dc:identifier>
    <dc:creator>Le Guin</dc:creator>
  </metadata>
</package>
"""
    with ZipFile(epub, "w") as archive:
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

    def catalog_lookup(identity):
        assert identity.isbn == "9780441478125"
        assert identity.title in ("", "Some Dump GROUP")
        return {"title": "The Left Hand of Darkness", "author": "Le Guin"}

    result = identify_completed(folder, catalog_lookup=catalog_lookup)
    assert result["auto_organize"] is True
    assert result["identity"]["kind"] == "book"
    assert result["identity"]["isbn"] == "9780441478125"
    assert result["identity"]["title"] == "The Left Hand of Darkness"
    assert "Dump" not in result["identity"]["title"]


def test_identify_cbz_comicinfo_series_number(tmp_path):
    from zipfile import ZipFile

    folder = tmp_path / "random-dump"
    folder.mkdir()
    cbz = folder / "issue.cbz"
    with ZipFile(cbz, "w") as archive:
        archive.writestr("page-01.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 80)
        archive.writestr(
            "ComicInfo.xml",
            """<?xml version="1.0"?>
<ComicInfo>
  <Series>Saga</Series>
  <Number>1</Number>
  <Year>2012</Year>
  <Title>Saga #1</Title>
</ComicInfo>
""",
        )
    result = identify_completed(folder)
    assert result["auto_organize"] is True
    assert result["identity"]["kind"] == "comic"
    assert result["identity"]["series_name"] == "Saga"
    assert result["identity"]["series_index"] == "1"


def test_identify_title_only_book_goes_to_review(tmp_path):
    folder = tmp_path / "A Mysterious Novel"
    folder.mkdir()
    (folder / "book.epub").write_bytes(b"epub")

    def catalog_lookup(identity):
        raise AssertionError("title-only must not call catalog")

    result = identify_completed(folder, catalog_lookup=catalog_lookup)
    assert result["auto_organize"] is False
    assert result["identity"]["isbn"] == ""
    assert result["identity"]["review_reason"] in {"low_confidence", "unknown_identity"}


def test_identify_audiobook_tags_not_music(tmp_path):
    folder = tmp_path / "dump-audio"
    folder.mkdir()
    _flac_with_tags(
        folder / "part01.flac",
        {
            "ALBUM": "The Left Hand of Darkness",
            "ALBUMARTIST": "Le Guin",
            "ARTIST": "Le Guin",
            "TITLE": "Chapter 1",
            "GENRE": "Audiobook",
        },
    )
    result = identify_completed(folder)
    assert result["identity"]["kind"] == "audiobook"
    dest = dest_layout(result["identity"], Settings(), filename="part01.flac")
    assert dest.parts[-3] == "audiobooks" or "audiobooks" in str(dest)
    assert "incoming-music" not in str(dest)
    assert "/music/" not in str(dest).replace("incoming-music", "")


def test_dest_layout_joins_existing_incoming_album(tmp_path):
    settings = Settings(
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
    )
    album = Path(settings.incoming_music_root) / "Miles Davis" / "Kind of Blue"
    album.mkdir(parents=True)
    dest = dest_layout(
        {"kind": "music", "title": "Kind of Blue", "author": "Miles Davis", "series_name": "Kind of Blue"},
        settings,
        filename="Freddie.flac",
    )
    assert dest.parent == album
    assert dest.name == "Freddie.flac"


def test_dest_layout_music_keeps_original_filename_without_tags(tmp_path):
    settings = Settings(
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
    )
    dump = "VA-Dump.Name-GROUP.flac"
    dest = dest_layout(
        {
            "kind": "music",
            "title": "Kind of Blue",
            "author": "Miles Davis",
            "series_name": "Kind of Blue",
            "track_title": "So What",
            "tracknumber": "1",
        },
        settings,
        filename=dump,
    )
    assert dest.name == dump
    assert dest.parent.name == "Kind of Blue"
    assert dest.parent.parent.name == "Miles Davis"
    assert dest.parent.parent.parent == Path(settings.incoming_music_root)


def test_dest_layout_music_tagged_track_uses_nn_title(tmp_path):
    settings = Settings(
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
    )
    source = tmp_path / "01 So What.flac"
    _flac_with_tags(
        source,
        {
            "ALBUM": "Kind of Blue",
            "ALBUMARTIST": "Miles Davis",
            "TITLE": "So What",
            "TRACKNUMBER": "1",
        },
    )
    dest = dest_layout(
        {"kind": "music", "title": "Kind of Blue", "author": "Miles Davis", "series_name": "Kind of Blue"},
        settings,
        filename=source.name,
        source=source,
    )
    assert dest.name == "01 - So What.flac"
    assert dest.parent.name == "Kind of Blue"


def test_dest_layout_music_join_keeps_dump_name_without_tags(tmp_path):
    settings = Settings(
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
    )
    album = Path(settings.music_root) / "Miles Davis" / "Kind of Blue"
    album.mkdir(parents=True)
    dest = dest_layout(
        {
            "kind": "music",
            "title": "Kind of Blue",
            "author": "Miles Davis",
            "series_name": "Kind of Blue",
            "track_title": "Freddie Freeloader",
            "tracknumber": "2",
        },
        settings,
        filename="single.track-GROUP.flac",
    )
    assert dest.parent == album
    assert dest.name == "single.track-GROUP.flac"


def test_dest_layout_music_title_tag_without_number_keeps_original(tmp_path):
    settings = Settings(
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
    )
    source = tmp_path / "dump-track.flac"
    _flac_with_tags(
        source,
        {"ALBUM": "Kind of Blue", "ALBUMARTIST": "Miles Davis", "TITLE": "So What"},
    )
    dest = dest_layout(
        {"kind": "music", "title": "Kind of Blue", "author": "Miles Davis", "series_name": "Kind of Blue"},
        settings,
        filename=source.name,
        source=source,
    )
    assert dest.name == "dump-track.flac"


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
