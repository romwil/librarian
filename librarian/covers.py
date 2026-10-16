"""Fetch a real cover.jpg. Never invent art or a blurb."""

from __future__ import annotations

import ipaddress
import logging
import zipfile
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import urlencode, urljoin, urlparse

import httpx

from librarian._version import __version__
from librarian.identify import extract_isbn

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = f"Librarian/{__version__} (+https://github.com/romwil/librarian)"
OPENLIB_ISBN_COVER = "https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
GOOGLE_BOOKS_ISBN_COVER = (
    "https://books.google.com/books/content?vid=ISBN{isbn}&printsec=frontcover&img=1"
)
AUDNEXUS_BOOK = "https://api.audnex.us/books/{asin}?region=us"
AUDIBLE_CATALOG = "https://api.audible.com/1.0/catalog/products"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
MIN_IMAGE_BYTES = 64

# Cover / atmosphere fetch allowlist (manual cover_url + automatic enrich/organize).
_ALLOWED_COVER_HOST_SUFFIXES = (
    "openlibrary.org",
    "coverartarchive.org",
    "hardcover.app",
    "comicvine.gamespot.com",
    "static.comicvine.com",
    "upload.wikimedia.org",
    "wikipedia.org",
    "books.google.com",
    "googleusercontent.com",
    "media-amazon.com",
    "ssl-images-amazon.com",
)
_MAX_COVER_REDIRECTS = 5


def assert_safe_cover_url(url: str) -> str:
    """Refuse non-http(s), IP literals, localhost, and non-allowlisted hosts."""
    text = str(url or "").strip()
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Cover URL must be http(s)")
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        raise ValueError("Cover URL host not allowed")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("Cover URL host not allowed")
    if not any(host == suffix or host.endswith("." + suffix) for suffix in _ALLOWED_COVER_HOST_SUFFIXES):
        raise ValueError("Cover URL host not allowed")
    return text


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
    require_safe_url: bool = True,
) -> bytes:
    if not url:
        return b""
    if require_safe_url:
        try:
            url = assert_safe_cover_url(url)
        except ValueError:
            return b""
    own = client is None
    http = client or httpx.Client(
        timeout=20.0,
        transport=transport,
        follow_redirects=not require_safe_url,
    )
    headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "image/*"}
    try:
        if require_safe_url:
            current = url
            response = None
            for _ in range(_MAX_COVER_REDIRECTS + 1):
                try:
                    current = assert_safe_cover_url(current)
                except ValueError:
                    return b""
                response = http.get(current, headers=headers, follow_redirects=False)
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location") or ""
                    if not location:
                        return b""
                    current = urljoin(current, location)
                    continue
                break
            else:
                return b""
            if response is None or response.status_code >= 400:
                return b""
            data = response.content or b""
            return data if looks_like_image(data) else b""
        response = http.get(url, headers=headers)
        if response.status_code >= 400:
            return b""
        data = response.content or b""
        return data if looks_like_image(data) else b""
    except httpx.HTTPError:
        return b""
    finally:
        if own:
            http.close()


def _get_json(
    url: str,
    *,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
) -> Any:
    """GET JSON from a fixed catalog host. Empty on any failure."""
    if not url:
        return None
    own = client is None
    http = client or httpx.Client(timeout=20.0, transport=transport, follow_redirects=True)
    try:
        response = http.get(
            url,
            headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"},
        )
    except httpx.HTTPError:
        return None
    finally:
        if own:
            http.close()
    if response.status_code >= 400:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _catalog_image(raw: Mapping[str, Any]) -> str:
    cover = str(raw.get("image") or raw.get("cover") or "").strip()
    images = raw.get("product_images")
    if not cover and isinstance(images, dict):
        for key in ("500", "1000", "300", "large"):
            candidate = str(images.get(key) or "").strip()
            if candidate:
                cover = candidate
                break
    return cover if cover.startswith("http") else ""


def _openlibrary_title_cover_url(
    identity: Mapping[str, Any],
    *,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
) -> str:
    """Open Library cover by title and author. Only when the work has no ISBN."""
    if extract_isbn(str(identity.get("isbn") or "")):
        return ""
    title = str(identity.get("title") or "").strip()
    if not title:
        return ""
    from librarian.enrich import lookup_author
    from librarian.openlibrary import OpenLibraryClient

    author = lookup_author(identity)
    year = identity.get("year") if isinstance(identity.get("year"), int) else None
    library = OpenLibraryClient(transport=transport, client=client)
    try:
        found = library.lookup_by_title(title, author, year=year)
    except Exception:
        logger.warning("Open Library title cover lookup failed", exc_info=True)
        return ""
    finally:
        library.close()
    return str(found.get("cover_url") or "").strip()


def _hardcover_cover_url(
    identity: Mapping[str, Any],
    *,
    hardcover_token: str = "",
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
) -> str:
    token = str(hardcover_token or "").strip()
    if not token:
        return ""
    from librarian.enrich import lookup_author
    from librarian.hardcover import HardcoverClient, HardcoverError

    title = str(identity.get("title") or "").strip()
    author = lookup_author(identity)
    isbn = extract_isbn(str(identity.get("isbn") or ""))
    if not isbn and not title:
        return ""
    hardcover = HardcoverClient(token, transport=transport, client=client)
    try:
        found = hardcover.lookup_by_isbn(isbn) if isbn else {}
        if not found and title:
            found = hardcover.lookup_by_title(title, author)
    except (HardcoverError, httpx.HTTPError):
        return ""
    except Exception:
        logger.warning("Hardcover cover lookup failed", exc_info=True)
        return ""
    finally:
        hardcover.close()
    return str((found or {}).get("cover_url") or "").strip()


def _audnexus_cover_url(
    identity: Mapping[str, Any],
    *,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
) -> str:
    """Audnexus / Audible cover for an audiobook. Skip when the hit does not match."""
    if str(identity.get("kind") or "").strip().lower() != "audiobook":
        return ""
    from librarian.audnexus import is_valid_asin, jaccard
    from librarian.enrich import lookup_author

    asin = str(identity.get("asin") or "").strip().upper()
    if is_valid_asin(asin):
        payload = _get_json(
            AUDNEXUS_BOOK.format(asin=asin),
            transport=transport,
            client=client,
        )
        if isinstance(payload, dict):
            return _catalog_image(payload)
        return ""

    title = str(identity.get("title") or "").strip()
    author = lookup_author(identity)
    if not title and not author:
        return ""
    params = {
        "num_results": "5",
        "products_sort_by": "Relevance",
        "response_groups": "media,product_attrs,contributors",
    }
    if title:
        params["title"] = title
    if author:
        params["author"] = author
    payload = _get_json(
        f"{AUDIBLE_CATALOG}?{urlencode(params)}",
        transport=transport,
        client=client,
    )
    products = payload.get("products") if isinstance(payload, dict) else None
    if not isinstance(products, list):
        return ""
    for product in products:
        if not isinstance(product, dict):
            continue
        image = _catalog_image(product)
        if not image:
            continue
        got = str(product.get("title") or "")
        if title and jaccard(title, got) < 0.45 and title.lower() not in got.lower():
            continue
        return image
    return ""


class _CoverUnwritable(Exception):
    """Shelf folder rejected cover.jpg. Stop; do not keep fetching art."""


def _try_cover_url(
    dest: Path,
    url: str,
    *,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
    require_safe_url: bool = True,
) -> Optional[Path]:
    if not str(url or "").strip():
        return None
    data = download_image(
        url,
        transport=transport,
        client=client,
        require_safe_url=require_safe_url,
    )
    if not data:
        return None
    try:
        dest.write_bytes(data)
    except OSError:
        logger.warning("Cannot write cover %s", dest, exc_info=True)
        raise _CoverUnwritable from None
    return dest


def fetch_cover(
    folder: Path,
    identity: Mapping[str, Any],
    *,
    indexer_cover_url: str = "",
    hardcover_token: str = "",
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
    require_safe_url: bool = True,
) -> Optional[Path]:
    """Write cover.jpg from a real image URL or the first CBZ page.

    Order: indexer URL, Open Library ISBN, Open Library title+author when there
    is no ISBN, Hardcover when a token is set, Audnexus for audiobooks, Google
    Books by ISBN, then CBZ page 1. Fail-soft. Never invents art.
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

    download_kwargs = {
        "transport": transport,
        "client": client,
        "require_safe_url": require_safe_url,
    }
    try:
        return _fetch_cover_sources(
            folder,
            dest,
            identity,
            indexer_cover_url=indexer_cover_url,
            hardcover_token=hardcover_token,
            **download_kwargs,
        )
    except _CoverUnwritable:
        return None


def _fetch_cover_sources(
    folder: Path,
    dest: Path,
    identity: Mapping[str, Any],
    *,
    indexer_cover_url: str = "",
    hardcover_token: str = "",
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
    require_safe_url: bool = True,
) -> Optional[Path]:
    download_kwargs = {
        "transport": transport,
        "client": client,
        "require_safe_url": require_safe_url,
    }
    urls: list[str] = []
    cover_url = str(indexer_cover_url or identity.get("cover") or "").strip()
    if cover_url:
        urls.append(cover_url)
    isbn = extract_isbn(str(identity.get("isbn") or ""))
    if isbn:
        urls.append(OPENLIB_ISBN_COVER.format(isbn=isbn))
    for url in urls:
        written = _try_cover_url(dest, url, **download_kwargs)
        if written is not None:
            return written

    if not isbn:
        ol_title = _openlibrary_title_cover_url(identity, transport=transport, client=client)
        written = _try_cover_url(dest, ol_title, **download_kwargs)
        if written is not None:
            return written

    hardcover = _hardcover_cover_url(
        identity,
        hardcover_token=hardcover_token,
        transport=transport,
        client=client,
    )
    written = _try_cover_url(dest, hardcover, **download_kwargs)
    if written is not None:
        return written

    audnexus = _audnexus_cover_url(identity, transport=transport, client=client)
    written = _try_cover_url(dest, audnexus, **download_kwargs)
    if written is not None:
        return written

    if isbn:
        written = _try_cover_url(
            dest,
            GOOGLE_BOOKS_ISBN_COVER.format(isbn=isbn),
            **download_kwargs,
        )
        if written is not None:
            return written

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
                template.format(mbid=group_id),
                transport=transport,
                client=client,
                require_safe_url=True,
            )
            if data:
                dest.write_bytes(data)
                return dest
    return None
