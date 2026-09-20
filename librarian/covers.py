"""Fetch a real cover.jpg. Never invent art or a blurb."""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import Any, Mapping, Optional

import httpx

from librarian._version import __version__
from librarian.identify import extract_isbn

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = f"Librarian/{__version__} (+https://github.com/romwil/librarian)"
OPENLIB_ISBN_COVER = "https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
MIN_IMAGE_BYTES = 64


def looks_like_image(data: bytes) -> bool:
    if len(data) < MIN_IMAGE_BYTES:
        return False
    if data[:3] == b"\xff\xd8\xff":
        return True
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if data[:2] == b"BM":
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    return False


def cover_from_cbz(cbz: Path, dest: Path) -> Optional[Path]:
    """First image page in a CBZ becomes cover.jpg."""
    if not cbz.is_file():
        return None
    try:
        with zipfile.ZipFile(cbz) as archive:
            names = sorted(
                name
                for name in archive.namelist()
                if not name.endswith("/") and Path(name).suffix.lower() in IMAGE_SUFFIXES
            )
            if not names:
                return None
            data = archive.read(names[0])
    except zipfile.BadZipFile:
        return None
    if not looks_like_image(data):
        return None
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    except OSError:
        logger.warning("Cannot write CBZ cover to %s", dest, exc_info=True)
        return None
    return dest


def download_image(
    url: str,
    *,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
) -> bytes:
    if not url:
        return b""
    own = client is None
    http = client or httpx.Client(timeout=20.0, transport=transport, follow_redirects=True)
    try:
        response = http.get(
            url,
            headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "image/*"},
        )
        if response.status_code >= 400:
            return b""
        data = response.content or b""
        return data if looks_like_image(data) else b""
    except httpx.HTTPError:
        return b""
    finally:
        if own:
            http.close()


def fetch_cover(
    folder: Path,
    identity: Mapping[str, Any],
    *,
    indexer_cover_url: str = "",
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
) -> Optional[Path]:
    """Write cover.jpg from indexer URL, Open Library ISBN, or CBZ page 1.

    Fail-soft on filesystem errors (PermissionError / other OSError): log and
    return None so callers can fall back to an owned cache or skip art.
    """
    folder = Path(folder)
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.warning("Cannot create cover folder %s", folder, exc_info=True)
        return None
    dest = folder / "cover.jpg"
    try:
        if dest.is_file() and dest.stat().st_size >= MIN_IMAGE_BYTES:
            return dest
    except OSError:
        logger.warning("Cannot stat cover %s", dest, exc_info=True)
        return None

    urls: list[str] = []
    cover_url = str(indexer_cover_url or identity.get("cover") or "").strip()
    if cover_url:
        urls.append(cover_url)
    isbn = extract_isbn(str(identity.get("isbn") or ""))
    if isbn:
        urls.append(OPENLIB_ISBN_COVER.format(isbn=isbn))

    for url in urls:
        data = download_image(url, transport=transport, client=client)
        if data:
            try:
                dest.write_bytes(data)
            except OSError:
                logger.warning("Cannot write cover %s", dest, exc_info=True)
                return None
            return dest

    try:
        cbz_paths = sorted(folder.glob("*.cbz"))
    except OSError:
        cbz_paths = []
    for cbz in cbz_paths:
        extracted = cover_from_cbz(cbz, dest)
        if extracted:
            return extracted
    return None


AUDIO_COVER_SUFFIXES = {".flac", ".mp3", ".m4a", ".m4b", ".ogg", ".opus", ".aac", ".mp4"}
CAA_RELEASE_GROUP = "https://coverartarchive.org/release-group/{mbid}/front-500"
CAA_RELEASE = "https://coverartarchive.org/release/{mbid}/front-500"


def ensure_music_cover(
    folder: Path,
    *,
    mbid: str = "",
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
) -> Optional[Path]:
    """Write cover.jpg from embedded front art or Cover Art Archive. Never invents art."""
    directory = Path(folder)
    if not directory.is_dir():
        return None
    dest = directory / "cover.jpg"
    if dest.is_file() and dest.stat().st_size >= MIN_IMAGE_BYTES:
        return dest

    from librarian.metadata import extract_embedded_cover_bytes

    try:
        audio_files = sorted(
            path
            for path in directory.rglob("*")
            if path.is_file() and path.suffix.lower() in AUDIO_COVER_SUFFIXES
        )
    except OSError:
        audio_files = []
    for audio in audio_files:
        data = extract_embedded_cover_bytes(audio)
        if data and looks_like_image(data):
            dest.write_bytes(data)
            return dest

    group_id = str(mbid or "").strip()
    if group_id:
        for template in (CAA_RELEASE_GROUP, CAA_RELEASE):
            data = download_image(
                template.format(mbid=group_id), transport=transport, client=client
            )
            if data:
                dest.write_bytes(data)
                return dest
    return None
