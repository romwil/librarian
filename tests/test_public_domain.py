"""Public-domain hits only when the query is that edition. Shelve skips SABnzbd."""

import httpx

from librarian.config import Settings
from librarian.db import Database
from librarian.public_domain import (
    match_public_domain,
    search_public_domain,
    shelve_edition,
)

EPUB = b"PK\x03\x04not-a-real-epub-but-a-zip"


def _gutenberg(title, author, url, *, book_id="1342"):
    return {
        "source": "gutenberg",
        "id": book_id,
        "title": title,
        "author": author,
        "isbn": "",
        "download_url": url,
        "kind": "book",
    }


def _standard(title, author, url):
    return {
        "source": "standard_ebooks",
        "id": title.lower().replace(" ", "-"),
        "title": title,
        "author": author,
        "isbn": "",
        "download_url": url,
        "kind": "book",
    }


def test_public_domain_requires_a_clear_edition():
    gutenberg_url = "https://www.gutenberg.org/ebooks/1342.epub"
    standard_url = "https://standardebooks.org/ebooks/jane-austen/pride-and-prejudice/downloads/jane-austen_pride-and-prejudice.epub"
    gutenberg = [
        _gutenberg("Pride and Prejudice", "Austen, Jane", gutenberg_url),
        _gutenberg("Pride and Prejudice", "Someone Else", gutenberg_url, book_id="999"),
        _gutenberg("Emma", "Austen, Jane", "https://www.gutenberg.org/ebooks/158.epub", book_id="158"),
    ]
    # Two authors share the title, so Gutenberg is not a clear edition.
    assert match_public_domain("Pride and Prejudice", "title", gutenberg=gutenberg, standard_ebooks=[]) == []
    clear_gutenberg = [_gutenberg("Pride and Prejudice", "Austen, Jane", gutenberg_url)]
    standard = [_standard("Pride and Prejudice", "Jane Austen", standard_url)]
    hits = match_public_domain(
        "Pride and Prejudice",
        "title",
        gutenberg=clear_gutenberg,
        standard_ebooks=standard,
    )
    assert [row["source"] for row in hits] == ["gutenberg", "standard_ebooks"]
    assert match_public_domain("Pride", "title", gutenberg=clear_gutenberg, standard_ebooks=standard) == []
    assert match_public_domain("Jane Austen", "author", gutenberg=clear_gutenberg, standard_ebooks=standard) == []
    assert match_public_domain("Pride and Prejudice", "narrator", gutenberg=clear_gutenberg, standard_ebooks=[]) == []
    isbn_row = {**clear_gutenberg[0], "isbn": "9780141439518"}
    assert match_public_domain("9780141439518", "isbn", gutenberg=[isbn_row], standard_ebooks=[])[0]["id"] == "1342"
    assert match_public_domain("9780141439518", "isbn", gutenberg=clear_gutenberg, standard_ebooks=[]) == []


def test_search_public_domain_drops_fuzzy_catalog_hits():
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "gutendex.com":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 1342,
                            "title": "Pride and Prejudice",
                            "authors": [{"name": "Austen, Jane"}],
                            "formats": {
                                "application/epub+zip": "https://www.gutenberg.org/ebooks/1342.epub"
                            },
                        },
                        {
                            "id": 42671,
                            "title": "Pride and Prejudice and Zombies",
                            "authors": [{"name": "Grahame-Smith, Seth"}],
                            "formats": {
                                "application/epub+zip": "https://www.gutenberg.org/ebooks/42671.epub"
                            },
                        },
                    ]
                },
            )
        if host == "standardebooks.org":
            return httpx.Response(
                200,
                json={
                    "publications": [
                        {
                            "metadata": {
                                "identifier": "https://standardebooks.org/ebooks/jane-austen/pride-and-prejudice",
                                "title": "Pride and Prejudice",
                                "author": [{"name": "Jane Austen"}],
                            },
                            "links": [
                                {
                                    "href": "https://standardebooks.org/ebooks/jane-austen/pride-and-prejudice/downloads/jane-austen_pride-and-prejudice.epub",
                                    "type": "application/epub+zip",
                                    "title": "Recommended compatible epub",
                                }
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(404)

    hits = search_public_domain(
        "Pride and Prejudice",
        mode="title",
        transport=httpx.MockTransport(handler),
    )
    assert [row["source"] for row in hits] == ["gutenberg", "standard_ebooks"]
    assert all(row["title"] == "Pride and Prejudice" for row in hits)
    assert search_public_domain("Jane Austen", mode="author", transport=httpx.MockTransport(handler)) == []


def test_shelve_public_domain_writes_epub_without_sab_or_slip(tmp_path):
    db = Database(tmp_path / "librarian.db")
    settings = Settings(books_root=str(tmp_path / "books"))
    called = {"urls": []}

    def handler(request: httpx.Request) -> httpx.Response:
        called["urls"].append(str(request.url))
        if request.url.host == "www.gutenberg.org":
            return httpx.Response(200, content=EPUB)
        return httpx.Response(404)

    result = shelve_edition(
        db,
        settings,
        {
            "source": "gutenberg",
            "id": "1342",
            "title": "Pride and Prejudice",
            "author": "Jane Austen",
            "download_url": "https://www.gutenberg.org/ebooks/1342.epub",
        },
        transport=httpx.MockTransport(handler),
    )
    assert result["jobs_created"] == 0
    assert result["review_state"] == "none"
    assert result["already_on_shelf"] is False
    work = db.get_work(result["work_id"])
    assert work["review_state"] == "none"
    assert work["title"] == "Pride and Prejudice"
    path = tmp_path / "books" / "Jane Austen" / "Pride and Prejudice" / "Pride and Prejudice.epub"
    assert path.read_bytes() == EPUB
    with db._connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"] == 0
        assert (
            conn.execute("SELECT COUNT(*) AS n FROM works WHERE review_state = 'needs_review'").fetchone()["n"]
            == 0
        )
    again = shelve_edition(
        db,
        settings,
        {
            "source": "gutenberg",
            "title": "Pride and Prejudice",
            "author": "Jane Austen",
            "download_url": "https://www.gutenberg.org/ebooks/1342.epub",
        },
        transport=httpx.MockTransport(handler),
    )
    assert again["already_on_shelf"] is True
    assert called["urls"] == ["https://www.gutenberg.org/ebooks/1342.epub"]

    refused = None
    try:
        shelve_edition(
            db,
            settings,
            {
                "source": "gutenberg",
                "title": "Not Gutenberg",
                "author": "Nobody",
                "download_url": "https://example.com/secret.epub",
            },
            transport=httpx.MockTransport(handler),
        )
    except Exception as error:  # noqa: BLE001 — assert the refusal type via message
        refused = error
    assert refused is not None
    assert "Gutenberg" in str(refused)
