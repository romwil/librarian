"""CBR/PDF → CBZ and on-demand ebook-convert. Missing tools stay Review."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from librarian.identify import MEDIA_EXTENSIONS, list_payload_files
from librarian.kinds import KIND_BOOK, KIND_COMIC

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
JUNK_PAGE_SUFFIXES = {".nfo", ".url", ".txt", ".sfv", ".par2", ".nzb", ".ds_store"}
JUNK_PAGE_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
ALLOWED_EBOOK_FORMATS = ("epub", "pdf", "mobi", "azw3", "kepub")
RunTool = Callable[..., subprocess.CompletedProcess]

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_WEBP_RIFF = b"RIFF"
_WEBP_WEBP = b"WEBP"
_NATURAL_KEY = re.compile(r"(\d+)|(\D+)")


def which_unar() -> Optional[str]:
    return shutil.which("unar") or shutil.which("unrar")


def which_par2() -> Optional[str]:
    return shutil.which("par2") or shutil.which("par2cmdline")


def which_ebook_convert() -> Optional[str]:
    return shutil.which("ebook-convert")


def which_pdftoppm() -> Optional[str]:
    return shutil.which("pdftoppm")


def run_tool(
    argv: Sequence[str],
    *,
    timeout: int = 120,
    cwd: Optional[Path] = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(argv),
        check=False,
        capture_output=True,
        timeout=timeout,
        cwd=str(cwd) if cwd else None,
    )


def loose_images(folder: Path) -> List[Path]:
    if not folder.is_dir():
        return []
    found: List[Path] = []
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            found.append(path)
    return found


def collect_pdftoppm_jpegs(folder: Path, prefix_name: str) -> List[Path]:
    """Collect pdftoppm JPEG pages. prefix_name is matched literally (not as a glob)."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    found: List[Path] = []
    for path in folder.iterdir():
        if (
            path.is_file()
            and path.name.startswith(prefix_name)
            and path.suffix.lower() == ".jpg"
        ):
            found.append(path)
    return sorted(found)


def _unlink_pages(pages: Sequence[Path]) -> None:
    for page in pages:
        page.unlink(missing_ok=True)


def _natural_key(name: str) -> list:
    parts: list = []
    for chunk in _NATURAL_KEY.finditer(Path(name).name):
        digits, text = chunk.groups()
        if digits:
            parts.append(int(digits))
        else:
            parts.append(str(text).casefold())
    return parts


def is_raster_image(path: Path) -> bool:
    """True when the file starts with a known raster header (JPEG/PNG/WebP)."""
    try:
        with Path(path).open("rb") as handle:
            head = handle.read(16)
    except OSError:
        return False
    if head.startswith(_JPEG_MAGIC) or head.startswith(_PNG_MAGIC):
        return True
    if len(head) >= 12 and head.startswith(_WEBP_RIFF) and head[8:12] == _WEBP_WEBP:
        return True
    return False


def sort_comic_pages(paths: Sequence[Path]) -> List[Path]:
    return sorted(paths, key=lambda path: _natural_key(path.name))


def filter_comic_pages(paths: Sequence[Path]) -> List[Path]:
    """Drop junk sidecars; keep validated raster pages only."""
    kept: List[Path] = []
    for path in paths:
        name = path.name.lower()
        if name in JUNK_PAGE_NAMES or path.suffix.lower() in JUNK_PAGE_SUFFIXES:
            continue
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if not is_raster_image(path):
            continue
        kept.append(path)
    return sort_comic_pages(kept)


def images_to_cbz(
    images: Sequence[Path],
    dest: Path,
    *,
    identity: Optional[Dict[str, Any]] = None,
    guid: str = "",
    compression: int = zipfile.ZIP_DEFLATED,
) -> Path:
    """Zip page images into a CBZ (Deflate). Optionally embed ComicInfo.xml at archive root."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    pages = filter_comic_pages(images) if images else []
    if not pages:
        pages = sort_comic_pages(list(images))
    staging = dest.with_suffix(dest.suffix + ".partial")
    staging.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(staging, "w", compression=compression) as archive:
            for index, image in enumerate(pages, start=1):
                suffix = image.suffix.lower() or ".jpg"
                if suffix == ".jpeg":
                    suffix = ".jpg"
                arcname = f"{index:03d}{suffix}"
                archive.write(image, arcname=arcname)
            if identity is not None:
                from librarian.metadata import comicinfo_xml

                xml = comicinfo_xml(identity, guid=guid, page_count=len(pages))
                archive.writestr("ComicInfo.xml", xml)
        # Integrity check before replacing dest.
        with zipfile.ZipFile(staging, "r") as archive:
            bad = archive.testzip()
            if bad is not None:
                raise zipfile.BadZipFile(f"corrupt member {bad}")
        staging.replace(dest)
    except (OSError, zipfile.BadZipFile):
        staging.unlink(missing_ok=True)
        raise
    return dest


def clean_cbz(
    src: Path,
    dest: Optional[Path] = None,
    *,
    identity: Optional[Dict[str, Any]] = None,
    guid: str = "",
) -> Optional[Path]:
    """Remux an existing CBZ: strip junk, validate pages, embed ComicInfo, Deflate."""
    src = Path(src)
    if not src.is_file() or src.suffix.lower() != ".cbz":
        return None
    target = Path(dest) if dest is not None else src
    extract_dir = src.parent / f".librarian-clean-{src.stem}"
    if extract_dir.exists():
        shutil.rmtree(extract_dir, ignore_errors=True)
    extract_dir.mkdir(parents=True, exist_ok=True)
    try:
        try:
            with zipfile.ZipFile(src, "r") as archive:
                archive.extractall(extract_dir)
        except zipfile.BadZipFile:
            return None
        pages = filter_comic_pages(loose_images(extract_dir))
        if not pages:
            return None
        written = images_to_cbz(pages, target, identity=identity or {}, guid=guid)
        return written if written.is_file() else None
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)


def cbr_to_cbz(
    src: Path,
    *,
    runner: RunTool = run_tool,
    unar: Optional[str] = None,
) -> Optional[Path]:
    """Extract a CBR and zip pages to CBZ. Keeps original.cbr as a sibling."""
    src = Path(src)
    dest = src.with_suffix(".cbz")
    if dest.is_file():
        return dest
    tool = unar or which_unar()
    if not tool:
        return None
    extract_dir = src.parent / f".librarian-extract-{src.stem}"
    extract_dir.mkdir(parents=True, exist_ok=True)
    name = Path(tool).name.lower()
    if name == "unar":
        argv = [tool, "-o", str(extract_dir), "-f", str(src)]
    else:
        argv = [tool, "x", "-o+", str(src), str(extract_dir) + "/"]
    try:
        completed = runner(argv, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if int(getattr(completed, "returncode", 1) or 0) != 0:
        return None
    pages = loose_images(extract_dir)
    if not pages:
        shutil.rmtree(extract_dir, ignore_errors=True)
        return None
    images_to_cbz(pages, dest)
    shutil.rmtree(extract_dir, ignore_errors=True)
    return dest if dest.is_file() else None


def pdf_to_cbz(
    src: Path,
    *,
    runner: RunTool = run_tool,
    pdftoppm: Optional[str] = None,
) -> Optional[Path]:
    """Rasterize a comic PDF with pdftoppm, then zip. Keeps original.pdf."""
    src = Path(src)
    dest = src.with_suffix(".cbz")
    if dest.is_file():
        return dest
    tool = pdftoppm or which_pdftoppm()
    if not tool:
        return None
    prefix = src.parent / f".librarian-pdf-{src.stem}"
    pages: List[Path] = []
    try:
        try:
            completed = runner([tool, "-jpeg", str(src), str(prefix)], timeout=180)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if int(getattr(completed, "returncode", 1) or 0) != 0:
            return None
        pages = collect_pdftoppm_jpegs(src.parent, prefix.name)
        if not pages:
            return None
        images_to_cbz(pages, dest)
        return dest if dest.is_file() else None
    finally:
        leftover = pages or collect_pdftoppm_jpegs(src.parent, prefix.name)
        _unlink_pages(leftover)


def pdf_to_epub(
    src: Path,
    *,
    runner: RunTool = run_tool,
    ebook_convert: Optional[str] = None,
) -> Optional[Path]:
    """Convert a PDF-only book to EPUB when ebook-convert is on PATH."""
    src = Path(src)
    dest = src.with_suffix(".epub")
    if dest.is_file():
        return dest
    tool = ebook_convert or which_ebook_convert()
    if not tool:
        return None
    try:
        completed = runner([tool, str(src), str(dest)], timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if int(getattr(completed, "returncode", 1) or 0) != 0 or not dest.is_file():
        return None
    return dest


def convert_ebook(
    src: Path,
    dest_format: str,
    cache_dir: Path,
    *,
    runner: RunTool = run_tool,
    ebook_convert: Optional[str] = None,
) -> Path:
    """On-demand convert into /config/conversions/{work_id}/. Does not clutter the library folder."""
    fmt = str(dest_format or "").lower().lstrip(".")
    if fmt not in ALLOWED_EBOOK_FORMATS:
        raise ValueError(f"unsupported format {dest_format}")
    src = Path(src)
    if src.suffix.lower() == f".{fmt}":
        return src
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / f"{src.stem}.{fmt}"
    if dest.is_file():
        return dest
    tool = ebook_convert or which_ebook_convert()
    if not tool:
        raise FileNotFoundError("ebook-convert is not installed")
    completed = runner([tool, str(src), str(dest)], timeout=180)
    if int(getattr(completed, "returncode", 1) or 0) != 0 or not dest.is_file():
        raise RuntimeError("ebook-convert failed")
    return dest


ARCHIVE_SUFFIXES = {".rar", ".7z"}
_PART_RAR = re.compile(r"\.part(\d+)\.rar$", re.IGNORECASE)


def archive_is_first_volume(path: Path) -> bool:
    """True for single-volume archives and multipart RAR part1/part01 only."""
    match = _PART_RAR.search(path.name)
    if match:
        return int(match.group(1)) == 1
    return path.suffix.lower() in ARCHIVE_SUFFIXES


def list_archive_files(folder: Path) -> List[Path]:
    folder = Path(folder)
    if not folder.is_dir():
        return []
    found: List[Path] = []
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix.lower() in ARCHIVE_SUFFIXES and archive_is_first_volume(path):
            found.append(path)
    return found


def list_par2_files(folder: Path) -> List[Path]:
    """PAR2 index files in a folder (prefer *.par2 without .vol recovery slices)."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    indexes: List[Path] = []
    volumes: List[Path] = []
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        name = path.name.lower()
        if not name.endswith(".par2"):
            continue
        if ".vol" in name:
            volumes.append(path)
        else:
            indexes.append(path)
    return indexes or volumes


def unpack_archive(
    src: Path,
    *,
    runner: RunTool = run_tool,
    unar: Optional[str] = None,
) -> bool:
    """Extract rar/7z into the archive's parent folder. Returns True on success."""
    src = Path(src)
    tool = unar or which_unar()
    if not tool or not src.is_file():
        return False
    dest = src.parent
    name = Path(tool).name.lower()
    if name == "unar":
        argv = [tool, "-o", str(dest), "-f", str(src)]
    else:
        argv = [tool, "x", "-o+", str(src), str(dest) + "/"]
    try:
        completed = runner(argv, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return int(getattr(completed, "returncode", 1) or 0) == 0


def par2_repair(
    src: Path,
    *,
    runner: RunTool = run_tool,
    par2: Optional[str] = None,
) -> bool:
    """Run `par2 r` on a PAR2 index. Returns True when the tool exits 0."""
    src = Path(src)
    tool = par2 or which_par2()
    if not tool or not src.is_file():
        return False
    argv = [tool, "r", str(src)]
    try:
        completed = runner(argv, timeout=600)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return int(getattr(completed, "returncode", 1) or 0) == 0


def maybe_par2_repair(
    folder: Path,
    *,
    runner: RunTool = run_tool,
    par2: Optional[str] = None,
) -> Dict[str, Any]:
    """Best-effort PAR2 repair before unar. Missing tools leave the folder unchanged."""
    folder = Path(folder)
    tool = par2 or which_par2()
    repaired: List[str] = []
    if not tool:
        return {
            "repaired": False,
            "par2_files": [],
            "payload": [str(path) for path in list_payload_files(folder)],
        }
    for index in list_par2_files(folder):
        if par2_repair(index, runner=runner, par2=tool):
            repaired.append(str(index))
    return {
        "repaired": bool(repaired),
        "par2_files": repaired,
        "payload": [str(path) for path in list_payload_files(folder)],
    }


def maybe_unpack_archives(
    folder: Path,
    *,
    runner: RunTool = run_tool,
    unar: Optional[str] = None,
) -> Dict[str, Any]:
    """Best-effort unar of rar/7z left by SAB. Missing tools leave the folder unchanged."""
    folder = Path(folder)
    tool = unar or which_unar()
    unpacked: List[str] = []
    if not tool:
        return {
            "unpacked": False,
            "archives": [],
            "payload": [str(path) for path in list_payload_files(folder)],
        }
    for archive in list_archive_files(folder):
        if unpack_archive(archive, runner=runner, unar=tool):
            unpacked.append(str(archive))
    return {
        "unpacked": bool(unpacked),
        "archives": unpacked,
        "payload": [str(path) for path in list_payload_files(folder)],
    }


def maybe_convert_payload(
    folder: Path,
    kind: str,
    *,
    runner: RunTool = run_tool,
) -> Dict[str, Any]:
    """Best-effort convert so identify can auto-organize. Missing tools leave the folder unchanged."""
    folder = Path(folder)
    converted: List[str] = []
    if kind == KIND_COMIC:
        files = list_payload_files(folder)
        suffixes = {path.suffix.lower() for path in files}
        if ".cbr" in suffixes and ".cbz" not in suffixes:
            for cbr in [path for path in files if path.suffix.lower() == ".cbr"]:
                try:
                    written = cbr_to_cbz(cbr, runner=runner)
                except (OSError, zipfile.BadZipFile) as error:
                    logger.warning("CBR convert skipped for %s: %s", cbr, error)
                    written = None
                if written:
                    converted.append(str(written))
                    break
        files = list_payload_files(folder)
        suffixes = {path.suffix.lower() for path in files}
        if ".pdf" in suffixes and ".cbz" not in suffixes:
            for pdf in [path for path in files if path.suffix.lower() == ".pdf"]:
                try:
                    written = pdf_to_cbz(pdf, runner=runner)
                except (OSError, zipfile.BadZipFile) as error:
                    logger.warning("PDF→CBZ convert skipped for %s: %s", pdf, error)
                    written = None
                if written:
                    converted.append(str(written))
                    break
        files = list_payload_files(folder)
        images = loose_images(folder)
        if images and not any(path.suffix.lower() == ".cbz" for path in files):
            dest = folder / "converted.cbz"
            try:
                written = images_to_cbz(images, dest)
                converted.append(str(written))
            except (OSError, zipfile.BadZipFile) as error:
                logger.warning("Loose-image CBZ convert skipped for %s: %s", folder, error)
    elif kind == KIND_BOOK:
        files = [path for path in list_payload_files(folder) if path.suffix.lower() in MEDIA_EXTENSIONS]
        suffixes = {path.suffix.lower() for path in files}
        if suffixes == {".pdf"}:
            try:
                written = pdf_to_epub(files[0], runner=runner)
            except OSError as error:
                logger.warning("PDF→EPUB convert skipped for %s: %s", files[0], error)
                written = None
            if written:
                converted.append(str(written))
    return {
        "converted": bool(converted),
        "files": converted,
        "payload": [str(path) for path in list_payload_files(folder)],
    }
