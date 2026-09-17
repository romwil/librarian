import zipfile
from pathlib import Path
from types import SimpleNamespace

from librarian.convert import (
    ALLOWED_EBOOK_FORMATS,
    collect_pdftoppm_jpegs,
    convert_ebook,
    images_to_cbz,
    maybe_convert_payload,
    maybe_unpack_archives,
    pdf_to_cbz,
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


def test_collect_pdftoppm_jpegs_treats_brackets_as_literal(tmp_path):
    prefix = ".librarian-pdf-Comic.[2024].[Group]"
    jpeg = b"\xff\xd8\xff" + b"\x00" * 20
    page1 = tmp_path / f"{prefix}-1.jpg"
    page2 = tmp_path / f"{prefix}-2.jpg"
    decoy = tmp_path / "other-1.jpg"
    page1.write_bytes(jpeg)
    page2.write_bytes(jpeg)
    decoy.write_bytes(jpeg)
    assert collect_pdftoppm_jpegs(tmp_path, prefix) == [page1, page2]
    assert list(tmp_path.glob(f"{prefix}*.jpg")) == []

    stem = "Comic.[2024].[Group]"
    dummy_pdf = tmp_path / f"{stem}.pdf"
    stem_page = tmp_path / f"{stem}-1.jpg"
    dummy_pdf.write_bytes(b"%PDF")
    stem_page.write_bytes(jpeg)
    assert dummy_pdf.is_file()
    assert collect_pdftoppm_jpegs(tmp_path, stem) == [stem_page]
    assert list(tmp_path.glob(f"{stem}*.jpg")) == []


def test_pdf_to_cbz_bracketed_usenet_name(tmp_path):
    src = tmp_path / "Comic.[2024].[Group].pdf"
    src.write_bytes(b"%PDF")
    jpeg = b"\xff\xd8\xff" + b"\x00" * 20

    def runner(argv, timeout=180):
        prefix = Path(argv[3])
        (prefix.parent / f"{prefix.name}-1.jpg").write_bytes(jpeg)
        (prefix.parent / f"{prefix.name}-2.jpg").write_bytes(jpeg)
        return SimpleNamespace(returncode=0)

    dest = pdf_to_cbz(src, runner=runner, pdftoppm="/usr/bin/pdftoppm")
    assert dest == tmp_path / "Comic.[2024].[Group].cbz"
    assert src.is_file()
    with zipfile.ZipFile(dest) as archive:
        assert archive.namelist() == [
            ".librarian-pdf-Comic.[2024].[Group]-1.jpg",
            ".librarian-pdf-Comic.[2024].[Group]-2.jpg",
        ]
    assert [path.name for path in tmp_path.iterdir() if path.suffix.lower() == ".jpg"] == []


def test_pdf_to_cbz_deletes_jpegs_when_pdftoppm_fails(tmp_path):
    src = tmp_path / "Comic.[2024].[Group].pdf"
    src.write_bytes(b"%PDF")
    jpeg = b"\xff\xd8\xff" + b"\x00" * 20

    def runner(argv, timeout=180):
        prefix = Path(argv[3])
        (prefix.parent / f"{prefix.name}-1.jpg").write_bytes(jpeg)
        return SimpleNamespace(returncode=1)

    dest = pdf_to_cbz(src, runner=runner, pdftoppm="/usr/bin/pdftoppm")
    assert dest is None
    assert not (tmp_path / "Comic.[2024].[Group].cbz").exists()
    assert [path.name for path in tmp_path.iterdir() if path.suffix.lower() == ".jpg"] == []


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


def test_maybe_unpack_archives_calls_unar(tmp_path):
    folder = tmp_path / "Trick"
    folder.mkdir()
    archive = folder / "Trick.rar"
    archive.write_bytes(b"Rar!\x00")
    calls = []

    def runner(argv, timeout=300):
        calls.append(list(argv))
        (folder / "Trick.cbz").write_bytes(b"cbz")
        return SimpleNamespace(returncode=0)

    result = maybe_unpack_archives(folder, runner=runner, unar="/usr/bin/unar")
    assert result["unpacked"] is True
    assert result["archives"] == [str(archive)]
    assert calls[0][:4] == ["/usr/bin/unar", "-o", str(folder), "-f"]
    assert calls[0][4] == str(archive)


def test_maybe_unpack_archives_noop_without_archives(tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir()
    (folder / "note.txt").write_text("hi")
    result = maybe_unpack_archives(folder)
    assert result["unpacked"] is False
    assert result["archives"] == []


def test_maybe_par2_repair_calls_par2_on_index(tmp_path):
    from librarian.convert import maybe_par2_repair

    folder = tmp_path / "Mix"
    folder.mkdir()
    index = folder / "mix.par2"
    index.write_bytes(b"PAR2")
    (folder / "mix.vol00+01.par2").write_bytes(b"PAR2VOL")
    calls = []

    def runner(argv, timeout=600):
        calls.append(list(argv))
        return SimpleNamespace(returncode=0)

    result = maybe_par2_repair(folder, runner=runner, par2="/usr/bin/par2")
    assert result["repaired"] is True
    assert result["par2_files"] == [str(index)]
    assert calls == [["/usr/bin/par2", "r", str(index)]]


def test_maybe_par2_repair_noop_without_tool(tmp_path, monkeypatch):
    from librarian.convert import maybe_par2_repair

    monkeypatch.setattr("librarian.convert.which_par2", lambda: None)
    folder = tmp_path / "Mix"
    folder.mkdir()
    (folder / "mix.par2").write_bytes(b"PAR2")
    result = maybe_par2_repair(folder)
    assert result["repaired"] is False
    assert result["par2_files"] == []
