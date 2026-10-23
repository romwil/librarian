import zipfile
from pathlib import Path

import httpx

from librarian.covers import (
    GOOGLE_BOOKS_ISBN_COVER,
    OPENLIB_ISBN_COVER,
    assert_safe_cover_url,
    cover_from_cbz,
    download_image,
    fetch_cover,
    looks_like_image,
)

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
    indexer = "https://static.comicvine.com/uploads/scale_large/saga.jpg"
    cover = fetch_cover(
        folder,
        {"isbn": "9780441478125"},
        indexer_cover_url=indexer,
        transport=httpx.MockTransport(handler),
    )
    assert cover == folder / "cover.jpg"
    assert captured[0] == indexer


def test_fetch_cover_blocks_unsafe_indexer_url_falls_back_to_isbn(tmp_path):
    """P3-HIGH-01: automatic indexer covers must not hit LAN / non-allowlisted hosts."""
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})

    folder = tmp_path / "book"
    folder.mkdir()
    cover = fetch_cover(
        folder,
        {"isbn": "9780441478125"},
        indexer_cover_url="http://169.254.169.254/latest/meta-data/",
        transport=httpx.MockTransport(handler),
    )
    assert cover == folder / "cover.jpg"
    assert captured == [OPENLIB_ISBN_COVER.format(isbn="9780441478125")]


def test_fetch_cover_skips_unsafe_indexer_without_isbn(tmp_path):
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        return httpx.Response(200, content=JPEG)

    folder = tmp_path / "book"
    folder.mkdir()
    cover = fetch_cover(
        folder,
        {"title": "No ISBN"},
        indexer_cover_url="https://evil.example/cover.jpg",
        transport=httpx.MockTransport(handler),
    )
    assert cover is None
    assert captured
    assert all("evil.example" not in url for url in captured)


def test_download_image_default_requires_safe_url():
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        return httpx.Response(200, content=JPEG)

    assert download_image("http://127.0.0.1/cover.jpg", transport=httpx.MockTransport(handler)) == b""
    assert captured == []
    assert (
        download_image(
            "https://covers.openlibrary.org/b/id/1-L.jpg",
            transport=httpx.MockTransport(handler),
        )
        == JPEG
    )


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


def test_assert_safe_cover_url_allowlist_and_blocks():
    assert assert_safe_cover_url("https://covers.openlibrary.org/b/id/1-L.jpg").startswith("https://")
    assert assert_safe_cover_url("https://coverartarchive.org/release/x/front-500")
    assert assert_safe_cover_url(
        "https://books.google.com/books/content?vid=ISBN9780441478125&printsec=frontcover&img=1"
    )
    assert assert_safe_cover_url("https://books.googleusercontent.com/books/content/x.jpg")
    assert assert_safe_cover_url("https://m.media-amazon.com/images/I/example.jpg")
    assert assert_safe_cover_url("https://images-na.ssl-images-amazon.com/images/I/example.jpg")
    assert assert_safe_cover_url("https://img.audible.com/covers/example.jpg")
    assert assert_safe_cover_url("https://api.audnex.us/books/B08G9PRS1K")
    for bad in (
        "http://127.0.0.1/cover.jpg",
        "http://169.254.169.254/latest/meta-data/",
        "https://evil.example/cover.jpg",
        "file:///etc/passwd",
        "ftp://covers.openlibrary.org/x.jpg",
        "https://localhost/cover.jpg",
    ):
        try:
            assert_safe_cover_url(bad)
            raise AssertionError(f"expected refusal for {bad}")
        except ValueError as error:
            assert "not allowed" in str(error).lower() or "http(s)" in str(error).lower()


def test_download_image_require_safe_revalidates_redirects():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "openlibrary.org" in url:
            return httpx.Response(302, headers={"location": "http://127.0.0.1/secret.jpg"})
        return httpx.Response(200, content=JPEG)

    data = download_image(
        "https://covers.openlibrary.org/b/id/1-L.jpg",
        transport=httpx.MockTransport(handler),
        require_safe_url=True,
    )
    assert data == b""

    def ok_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})

    assert (
        download_image(
            "https://covers.openlibrary.org/b/id/1-L.jpg",
            transport=httpx.MockTransport(ok_handler),
            require_safe_url=True,
        )
        == JPEG
    )


def test_fetch_cover_open_library_title_author_when_no_isbn(tmp_path):
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        captured.append(url)
        if "search.json" in url:
            return httpx.Response(
                200,
                json={
                    "docs": [
                        {
                            "title": "Piranesi",
                            "key": "/works/OL1W",
                            "author_name": ["Susanna Clarke"],
                            "cover_i": 4242,
                        }
                    ]
                },
            )
        if "/works/OL1W" in url:
            return httpx.Response(200, json={"title": "Piranesi"})
        if url == "https://covers.openlibrary.org/b/id/4242-L.jpg":
            return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
        return httpx.Response(404)

    folder = tmp_path / "book"
    cover = fetch_cover(
        folder,
        {"title": "Piranesi", "author": "Susanna Clarke"},
        transport=httpx.MockTransport(handler),
    )
    assert cover == folder / "cover.jpg"
    assert cover.read_bytes() == JPEG
    assert "https://covers.openlibrary.org/b/id/4242-L.jpg" in captured


def test_fetch_cover_does_not_invent_art_for_unmatched_title(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if "search.json" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "docs": [
                        {
                            "title": "Unrelated",
                            "key": "/works/OL9W",
                            "author_name": ["Someone Else"],
                            "cover_i": 1,
                        }
                    ]
                },
            )
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})

    folder = tmp_path / "book"
    cover = fetch_cover(
        folder,
        {"title": "Piranesi", "author": "Susanna Clarke"},
        transport=httpx.MockTransport(handler),
    )
    assert cover is None
    assert not (folder / "cover.jpg").exists()


def test_fetch_cover_hardcover_when_token_set_and_skips_without_token(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "POST" and "hardcover.app" in url:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "search": {
                            "results": [
                                {
                                    "title": "Piranesi",
                                    "image": {"url": "https://covers.hardcover.app/piranesi.jpg"},
                                }
                            ]
                        }
                    }
                },
            )
        if url == "https://covers.hardcover.app/piranesi.jpg":
            return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
        if "search.json" in url:
            return httpx.Response(200, json={"docs": []})
        return httpx.Response(404)

    folder = tmp_path / "token"
    cover = fetch_cover(
        folder,
        {"title": "Piranesi", "author": "Susanna Clarke"},
        hardcover_token="hardcover-test-token",
        transport=httpx.MockTransport(handler),
    )
    assert cover == folder / "cover.jpg"
    assert cover.read_bytes() == JPEG

    def no_token(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            raise AssertionError("Hardcover must not be called without a token")
        if "search.json" in str(request.url):
            return httpx.Response(200, json={"docs": []})
        return httpx.Response(404)

    missed = tmp_path / "no-token"
    assert (
        fetch_cover(
            missed,
            {"title": "Piranesi", "author": "Susanna Clarke"},
            transport=httpx.MockTransport(no_token),
        )
        is None
    )


def test_fetch_cover_audnexus_for_audiobook(tmp_path):
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        captured.append(url)
        if "search.json" in url:
            return httpx.Response(200, json={"docs": []})
        if url.startswith("https://api.audnex.us/books/B00TEST123"):
            return httpx.Response(
                200,
                json={
                    "asin": "B00TEST123",
                    "title": "Project Hail Mary",
                    "image": "https://m.media-amazon.com/images/I/hail.jpg",
                },
            )
        if url == "https://m.media-amazon.com/images/I/hail.jpg":
            return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
        return httpx.Response(404)

    folder = tmp_path / "audio"
    cover = fetch_cover(
        folder,
        {
            "kind": "audiobook",
            "title": "Project Hail Mary",
            "author": "Andy Weir",
            "asin": "B00TEST123",
            "narrator": "Ray Porter",
        },
        transport=httpx.MockTransport(handler),
    )
    assert cover == folder / "cover.jpg"
    assert cover.read_bytes() == JPEG
    assert any("api.audnex.us/books/B00TEST123" in url for url in captured)

    def mismatch(request: httpx.Request) -> httpx.Response:
        if "search.json" in str(request.url):
            return httpx.Response(200, json={"docs": []})
        if "api.audible.com" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "products": [
                        {
                            "asin": "B00OTHER999",
                            "title": "Completely Different",
                            "product_images": {"500": "https://m.media-amazon.com/images/I/wrong.jpg"},
                        }
                    ]
                },
            )
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})

    missed = tmp_path / "audio-miss"
    assert (
        fetch_cover(
            missed,
            {"kind": "audiobook", "title": "Project Hail Mary", "author": "Andy Weir"},
            transport=httpx.MockTransport(mismatch),
        )
        is None
    )
    assert not (missed / "cover.jpg").exists()


def test_fetch_cover_google_books_isbn_after_open_library_miss(tmp_path):
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        captured.append(url)
        if "books.google.com" in url:
            return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
        return httpx.Response(404)

    folder = tmp_path / "isbn"
    isbn = "9780441478125"
    cover = fetch_cover(
        folder,
        {"isbn": isbn, "title": "The Left Hand of Darkness"},
        transport=httpx.MockTransport(handler),
    )
    assert cover == folder / "cover.jpg"
    assert captured[0] == OPENLIB_ISBN_COVER.format(isbn=isbn)
    assert captured[1] == GOOGLE_BOOKS_ISBN_COVER.format(isbn=isbn)


def test_fetch_cover_cbz_still_used_when_catalogs_miss(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if "search.json" in str(request.url):
            return httpx.Response(200, json={"docs": []})
        return httpx.Response(404)

    folder = tmp_path / "comic"
    folder.mkdir()
    cbz = folder / "Saga #1.cbz"
    with zipfile.ZipFile(cbz, "w") as archive:
        archive.writestr("page-01.jpg", JPEG)
    cover = fetch_cover(
        folder,
        {"title": "Saga", "author": "Brian K. Vaughan", "kind": "comic"},
        transport=httpx.MockTransport(handler),
    )
    assert cover == folder / "cover.jpg"
    assert cover.read_bytes() == JPEG


def test_fetch_cover_audiobook_skips_open_library_jacket(tmp_path):
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        captured.append(url)
        if "search.json" in url or "openlibrary.org" in url:
            return httpx.Response(
                200,
                json={
                    "docs": [
                        {
                            "title": "Project Hail Mary",
                            "key": "/works/OL1W",
                            "author_name": ["Andy Weir"],
                            "cover_i": 99,
                        }
                    ]
                },
            )
        if url.startswith("https://api.audnex.us/books/B00TEST123"):
            return httpx.Response(
                200,
                json={"asin": "B00TEST123", "image": "https://m.media-amazon.com/images/I/hail.jpg"},
            )
        if url == "https://m.media-amazon.com/images/I/hail.jpg":
            return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
        return httpx.Response(404)

    folder = tmp_path / "audio"
    cover = fetch_cover(
        folder,
        {
            "kind": "audiobook",
            "title": "Project Hail Mary",
            "author": "Andy Weir",
            "asin": "B00TEST123",
        },
        transport=httpx.MockTransport(handler),
    )
    assert cover == folder / "cover.jpg"
    assert not any("openlibrary.org" in url for url in captured)
    assert any("api.audnex.us/books/B00TEST123" in url for url in captured)


def test_fetch_cover_comic_skips_open_library_and_uses_cbz(tmp_path):
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        return httpx.Response(
            200, json={"docs": [{"title": "Saga", "key": "/works/OL9W", "cover_i": 1}]}
        )

    folder = tmp_path / "comic-kind"
    folder.mkdir()
    with zipfile.ZipFile(folder / "Saga #1.cbz", "w") as archive:
        archive.writestr("page-01.jpg", JPEG)
    cover = fetch_cover(
        folder,
        {"kind": "comic", "title": "Saga", "author": "Vaughan"},
        transport=httpx.MockTransport(handler),
    )
    assert cover == folder / "cover.jpg"
    assert cover.read_bytes() == JPEG
    assert captured == []
