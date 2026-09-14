"""CBR/PDF → CBZ and on-demand ebook-convert. Missing tools stay Review."""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from librarian.identify import MEDIA_EXTENSIONS, list_payload_files
from librarian.kinds import KIND_BOOK, KIND_COMIC

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_EBOOK_FORMATS = ("epub", "pdf", "mobi", "azw3", "kepub")
RunTool = Callable[..., subprocess.CompletedProcess]


def which_unar() -> Optional[str]:
    return shutil.which("unar") or shutil.which("unrar")


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


def images_to_cbz(images: Sequence[Path], dest: Path) -> Path:
    """Zip page images into a CBZ. Exact namelist is the sorted basenames."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_STORED) as archive:
        for image in images:
            archive.write(image, arcname=image.name)
    return dest


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
                written = cbr_to_cbz(cbr, runner=runner)
                if written:
                    converted.append(str(written))
                    break
        files = list_payload_files(folder)
        suffixes = {path.suffix.lower() for path in files}
        if ".pdf" in suffixes and ".cbz" not in suffixes:
            for pdf in [path for path in files if path.suffix.lower() == ".pdf"]:
                written = pdf_to_cbz(pdf, runner=runner)
                if written:
                    converted.append(str(written))
                    break
        files = list_payload_files(folder)
        images = loose_images(folder)
        if images and not any(path.suffix.lower() == ".cbz" for path in files):
            dest = folder / "converted.cbz"
            written = images_to_cbz(images, dest)
            converted.append(str(written))
    elif kind == KIND_BOOK:
        files = [path for path in list_payload_files(folder) if path.suffix.lower() in MEDIA_EXTENSIONS]
        suffixes = {path.suffix.lower() for path in files}
        if suffixes == {".pdf"}:
            written = pdf_to_epub(files[0], runner=runner)
            if written:
                converted.append(str(written))
    return {
        "converted": bool(converted),
        "files": converted,
        "payload": [str(path) for path in list_payload_files(folder)],
    }
