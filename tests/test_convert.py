import zipfile
from pathlib import Path
from types import SimpleNamespace

from librarian.convert import (
    ALLOWED_EBOOK_FORMATS,
    convert_ebook,
    images_to_cbz,
    maybe_convert_payload,
    pdf_to_epub,
)


def test_images_to_cbz_namelist_is_exact(tmp_path):
    page1 = tmp_path / "page-01.jpg"
    page2 = tmp_path / "page-02.jpg"
    page1.write_bytes(b"\xff\xd8\xff" + b"\x00" * 20)
    page2.write_bytes(b"\xff\xd8\xff" + b"\x00" * 20)
    dest = tmp_path / "Saga #1.cbz"
    written = images_to_cbz([page1, page2], dest)
    assert written == dest
    with zipfile.ZipFile(dest) as archive:
        assert archive.namelist() == ["page-01.jpg", "page-02.jpg"]


def test_maybe_convert_loose_comic_images(tmp_path):
    folder = tmp_path / "Saga.2024.001"
    folder.mkdir()
    (folder / "01.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 20)
    (folder / "02.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 20)
    result = maybe_convert_payload(folder, "comic")
    assert result["converted"] is True
    dest = Path(result["files"][0])
    assert dest.name == "converted.cbz"
    with zipfile.ZipFile(dest) as archive:
        assert archive.namelist() == ["01.jpg", "02.jpg"]


def test_cbr_to_cbz_with_injected_unar(tmp_path):
    from librarian.convert import cbr_to_cbz

    src = tmp_path / "saga.cbr"
    src.write_bytes(b"Rar!")
    jpeg = b"\xff\xd8\xff" + b"\x00" * 20

    def runner(argv, timeout=120):
        out_dir = Path(argv[2])
        (out_dir / "01.jpg").write_bytes(jpeg)
        return SimpleNamespace(returncode=0)

    dest = cbr_to_cbz(src, runner=runner, unar="/usr/bin/unar")
    assert dest == tmp_path / "saga.cbz"
    assert src.is_file()
    with zipfile.ZipFile(dest) as archive:
        assert archive.namelist() == ["01.jpg"]


def test_cbr_without_unar_stays_unconverted(tmp_path, monkeypatch):
    monkeypatch.setattr("librarian.convert.which_unar", lambda: None)
    folder = tmp_path / "Saga.2024.001"
    folder.mkdir()
    (folder / "saga.cbr").write_bytes(b"Rar!\x1a")
    result = maybe_convert_payload(folder, "comic")
    assert result["converted"] is False
    assert not list(folder.glob("*.cbz"))


def test_pdf_book_convert_uses_ebook_convert(tmp_path):
    src = tmp_path / "Dune.pdf"
    src.write_bytes(b"%PDF")
    calls = []

    def runner(argv, timeout=180):
        calls.append(list(argv))
        Path(argv[2]).write_bytes(b"epub")
        return SimpleNamespace(returncode=0)

    dest = pdf_to_epub(src, runner=runner, ebook_convert="/usr/bin/ebook-convert")
    assert dest == tmp_path / "Dune.epub"
    assert dest.read_bytes() == b"epub"
    assert calls == [["/usr/bin/ebook-convert", str(src), str(dest)]]
    assert src.is_file()


def test_on_demand_convert_caches_under_conversions(tmp_path):
    src = tmp_path / "Dune.epub"
    src.write_bytes(b"epub")
    cache = tmp_path / "conversions" / "work-1"
    calls = []

    def runner(argv, timeout=180):
        calls.append(list(argv))
        Path(argv[2]).write_bytes(b"pdf")
        return SimpleNamespace(returncode=0)

    dest = convert_ebook(src, "pdf", cache, runner=runner, ebook_convert="/usr/bin/ebook-convert")
    assert dest == cache / "Dune.pdf"
    again = convert_ebook(src, "pdf", cache, runner=runner, ebook_convert="/usr/bin/ebook-convert")
    assert again == dest
    assert calls == [["/usr/bin/ebook-convert", str(src), str(dest)]]
    assert "epub" in ALLOWED_EBOOK_FORMATS
