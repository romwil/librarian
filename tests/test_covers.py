import zipfile
from pathlib import Path

import httpx

from librarian.covers import OPENLIB_ISBN_COVER, cover_from_cbz, fetch_cover, looks_like_image

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 80


def test_looks_like_image_rejects_gif_placeholder():
    assert looks_like_image(JPEG) is True
    assert looks_like_image(b"GIF89a" + b"\x00" * 80) is False
    assert looks_like_image(b"\xff\xd8") is False


def test_cover_from_cbz_uses_first_page(tmp_path):
    cbz = tmp_path / "Saga #1.cbz"
    with zipfile.ZipFile(cbz, "w") as archive:
        archive.writestr("page-02.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 80)
        archive.writestr("page-01.jpg", JPEG)
    dest = tmp_path / "cover.jpg"
    written = cover_from_cbz(cbz, dest)
    assert written == dest
    assert dest.read_bytes() == JPEG


def test_fetch_cover_open_library_isbn_url_is_exact(tmp_path):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})

    folder = tmp_path / "book"
    folder.mkdir()
    cover = fetch_cover(
        folder,
        {"isbn": "9780441478125", "title": "The Left Hand of Darkness"},
        transport=httpx.MockTransport(handler),
    )
    assert cover == folder / "cover.jpg"
    assert cover.read_bytes() == JPEG
    assert captured["url"] == OPENLIB_ISBN_COVER.format(isbn="9780441478125")


def test_fetch_cover_prefers_indexer_url(tmp_path):
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        return httpx.Response(200, content=JPEG)

    folder = tmp_path / "comic"
    folder.mkdir()
    cover = fetch_cover(
        folder,
        {"isbn": "9780441478125"},
        indexer_cover_url="https://covers.example/saga.jpg",
        transport=httpx.MockTransport(handler),
    )
    assert cover == folder / "cover.jpg"
    assert captured[0] == "https://covers.example/saga.jpg"


def test_ensure_music_cover_from_caa(tmp_path):
    from librarian.covers import CAA_RELEASE_GROUP, ensure_music_cover

    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})

    folder = tmp_path / "album"
    folder.mkdir()
    (folder / "01.flac").write_bytes(b"fLaC")
    mbid = "f5099ac0-b5c3-4d4a-b3b8-example0001"
    cover = ensure_music_cover(
        folder,
        mbid=mbid,
        transport=httpx.MockTransport(handler),
    )
    assert cover == folder / "cover.jpg"
    assert cover.read_bytes() == JPEG
    assert captured[0] == CAA_RELEASE_GROUP.format(mbid=mbid)


def test_ensure_music_cover_from_embedded_flac_picture(tmp_path):
    from librarian.covers import ensure_music_cover

    folder = tmp_path / "album"
    folder.mkdir()
    # Minimal FLAC with a PICTURE block (type 6) carrying JPEG bytes.
    mime = b"image/jpeg"
    desc = b""
    picture = (
        (3).to_bytes(4, "big")  # front cover
        + len(mime).to_bytes(4, "big")
        + mime
        + len(desc).to_bytes(4, "big")
        + desc
        + (0).to_bytes(4, "big") * 4  # width/height/depth/colors
        + len(JPEG).to_bytes(4, "big")
        + JPEG
    )
    header = bytes([0x80 | 6]) + len(picture).to_bytes(3, "big")
    (folder / "track.flac").write_bytes(b"fLaC" + header + picture)
    cover = ensure_music_cover(folder)
    assert cover == folder / "cover.jpg"
    assert cover.read_bytes() == JPEG


def test_fetch_cover_permission_error_returns_none(tmp_path, monkeypatch):
    """Locked shelf folders must not raise — enrich callers need a soft miss."""
    folder = tmp_path / "locked"
    folder.mkdir()

    def boom(self, *_args, **_kwargs):
        raise PermissionError(13, "Permission denied", str(folder / "cover.jpg"))

    monkeypatch.setattr(Path, "write_bytes", boom)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})

    cover = fetch_cover(
        folder,
        {"isbn": "9780441478125"},
        transport=httpx.MockTransport(handler),
    )
    assert cover is None
