"""OPDS 1.2 catalog tokens and jailed acquisition downloads."""

import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from librarian.db import Database
from librarian.opds_tokens import create_catalog_token, create_file_token
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app

ATOM = "{http://www.w3.org/2005/Atom}"
ACQUISITION_REL = "http://opds-spec.org/acquisition"


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    clear_rate_limits()
    return TestClient(create_app(tmp_path))


def _login(client):
    resp = client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    assert resp.status_code == 200
    return resp


def _feed(text: str) -> ET.Element:
    return ET.fromstring(text)


def _hrefs(feed: ET.Element, rel: str) -> list[str]:
    return [el.get("href") or "" for el in feed.iter(f"{ATOM}link") if el.get("rel") == rel]


def _query_token(url: str) -> str:
    values = parse_qs(urlparse(url).query).get("token") or []
    assert values, url
    return values[0]


def _titles(feed: ET.Element) -> list[str]:
    # Direct entry titles only — skip nested author names.
    titles = []
    for entry in feed.findall(f"{ATOM}entry"):
        title = entry.find(f"{ATOM}title")
        titles.append(title.text or "" if title is not None else "")
    return titles


def _shelve(db: Database, tmp_path: Path, *, kind: str, title: str, author: str, filename: str, body: bytes):
    folder = tmp_path / "media" / kind / title
    folder.mkdir(parents=True)
    path = folder / filename
    path.write_bytes(body)
    work = db.upsert_work(
        {
            "kind": kind,
            "title": title,
            "author": author,
            "folder_path": str(folder),
            "review_state": "none",
        }
    )
    row = db.add_file(
        {"work_id": work["id"], "path": str(path), "filename": filename, "kind": kind, "size": len(body)}
    )
    return work, row


def test_opds_root_and_entry_require_a_token(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    # A browser session must not open the catalog.
    assert client.get("/opds").status_code == 401
    assert client.get("/opds/kind/book").status_code == 401
    assert client.get("/opds/authors").status_code == 401
    assert client.get("/opds/search", params={"q": "Dune"}).status_code == 401
    minted = client.get("/api/opds")
    assert minted.status_code == 200
    catalog_url = minted.json()["catalog_url"]
    assert "token=" in catalog_url
    client.cookies.clear()
    root = client.get(catalog_url)
    assert root.status_code == 200
    assert "opds-catalog" in (root.headers.get("content-type") or "")
    feed = _feed(root.text)
    assert _titles(feed) == ["Books", "Magazines", "Comics", "Authors"]
    assert all("token=" in href for href in _hrefs(feed, "subsection"))
    books = next(href for href in _hrefs(feed, "subsection") if "/opds/kind/book" in href)
    entry = client.get(books)
    assert entry.status_code == 200
    # A file token is not a catalog token.
    db = Database(tmp_path / "librarian.db")
    work, row = _shelve(
        db, tmp_path, kind="book", title="Dune", author="Herbert", filename="Dune.epub", body=b"epub-bytes"
    )
    file_token = create_file_token(work["id"], row["id"], data_dir=tmp_path)
    assert client.get("/opds", params={"token": file_token}).status_code == 401
    # Authorization bearer is accepted for navigation.
    catalog_token = _query_token(catalog_url)
    bearer = client.get("/opds/kind/book", headers={"Authorization": f"Bearer {catalog_token}"})
    assert bearer.status_code == 200
    assert "Dune" in _titles(_feed(bearer.text))


def test_acquisition_token_downloads_that_file_and_rejects_another(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    dune, dune_file = _shelve(
        db, tmp_path, kind="book", title="Dune", author="Herbert", filename="Dune.epub", body=b"dune-epub"
    )
    messiah, messiah_file = _shelve(
        db,
        tmp_path,
        kind="book",
        title="Dune Messiah",
        author="Herbert",
        filename="Messiah.epub",
        body=b"messiah-epub",
    )
    _shelve(
        db,
        tmp_path,
        kind="magazine",
        title="Linux Magazine",
        author="Linux",
        filename="issue.pdf",
        body=b"%PDF-mag",
    )
    _shelve(
        db, tmp_path, kind="comic", title="Saga", author="Vaughan", filename="saga.cbz", body=b"cbz-bytes"
    )
    _shelve(
        db,
        tmp_path,
        kind="audiobook",
        title="Dune Audio",
        author="Herbert",
        filename="dune.m4b",
        body=b"audio-bytes",
    )
    catalog = client.get("/api/opds").json()["catalog_url"]
    client.cookies.clear()
    books_href = next(
        href for href in _hrefs(_feed(client.get(catalog).text), "subsection") if href.endswith("/opds/kind/book") or "/opds/kind/book?" in href
    )
    books = _feed(client.get(books_href).text)
    titles = _titles(books)
    assert "Dune" in titles
    assert "Dune Messiah" in titles
    assert "Dune Audio" not in titles
    assert "Linux Magazine" not in titles
    dune_entry = next(entry for entry in books.findall(f"{ATOM}entry") if (entry.find(f"{ATOM}title").text == "Dune"))
    href = dune_entry.find(f"{ATOM}link").get("href")
    assert "token=" in href
    assert f"file={dune_file['id']}" in href
    downloaded = client.get(href)
    assert downloaded.status_code == 200
    assert downloaded.content == b"dune-epub"
    assert "dune" in (downloaded.headers.get("content-disposition") or "").lower() or downloaded.content == b"dune-epub"

    assert client.get(f"/api/works/{dune['id']}/download", params={"file": dune_file["id"]}).status_code == 401
    other = create_file_token(messiah["id"], messiah_file["id"], data_dir=tmp_path)
    stolen = client.get(
        f"/api/works/{dune['id']}/download",
        params={"file": dune_file["id"], "token": other},
    )
    assert stolen.status_code == 401
    swapped = client.get(
        f"/api/works/{dune['id']}/download",
        params={"file": messiah_file["id"], "token": _query_token(href)},
    )
    assert swapped.status_code == 401
    catalog_token = _query_token(catalog)
    assert (
        client.get(
            f"/api/works/{dune['id']}/download",
            params={"file": dune_file["id"], "token": catalog_token},
        ).status_code
        == 401
    )

    magazines = next(
        href
        for href in _hrefs(_feed(client.get(catalog).text), "subsection")
        if "/opds/kind/magazine" in href
    )
    assert "Linux Magazine" in _titles(_feed(client.get(magazines).text))
    comics = next(
        href for href in _hrefs(_feed(client.get(catalog).text), "subsection") if "/opds/kind/comic" in href
    )
    assert "Saga" in _titles(_feed(client.get(comics).text))

    authors = next(href for href in _hrefs(_feed(client.get(catalog).text), "subsection") if "/opds/authors" in href)
    author_names = _titles(_feed(client.get(authors).text))
    assert "Herbert" in author_names
    herbert = next(href for href in _hrefs(_feed(client.get(authors).text), "subsection") if "Herbert" in href or "herbert" in href.lower())
    herbert_titles = _titles(_feed(client.get(herbert).text))
    assert "Dune" in herbert_titles
    assert "Dune Audio" not in herbert_titles

    search_desc = next(href for href in _hrefs(_feed(client.get(catalog).text), "search"))
    description = client.get(search_desc)
    assert description.status_code == 200
    assert "{searchTerms}" in description.text
    found = client.get("/opds/search", params={"q": "Dune", "token": catalog_token})
    assert found.status_code == 200
    assert "Dune" in _titles(_feed(found.text))
    assert "Dune Audio" not in _titles(_feed(found.text))


def test_acquisition_token_cannot_read_outside_the_data_dir(tmp_path, monkeypatch):
    jail = tmp_path / "data"
    jail.mkdir()
    monkeypatch.setenv("LIBRARIAN_FS_ROOT", str(jail))
    client = _client(tmp_path, monkeypatch)
    db = Database(tmp_path / "librarian.db")
    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"SECRET-BYTES")
    work = db.upsert_work({"kind": "book", "title": "Poisoned", "author": "Nobody", "review_state": "none"})
    row = db.add_file(
        {
            "work_id": work["id"],
            "path": str(secret),
            "filename": "secret.txt",
            "kind": "book",
            "size": secret.stat().st_size,
        }
    )
    token = create_file_token(work["id"], row["id"], data_dir=tmp_path)
    leaked = client.get(f"/api/works/{work['id']}/download", params={"file": row["id"], "token": token})
    assert leaked.status_code == 404
    assert b"SECRET-BYTES" not in leaked.content

    inside = jail / "Dune.epub"
    inside.write_bytes(b"jailed-epub")
    owned = db.upsert_work({"kind": "book", "title": "Dune", "author": "Herbert", "review_state": "none"})
    owned_file = db.add_file(
        {
            "work_id": owned["id"],
            "path": str(inside),
            "filename": inside.name,
            "kind": "book",
            "size": len(b"jailed-epub"),
        }
    )
    good = create_file_token(owned["id"], owned_file["id"], data_dir=tmp_path)
    served = client.get(
        f"/api/works/{owned['id']}/download",
        params={"file": owned_file["id"], "token": good},
    )
    assert served.status_code == 200
    assert served.content == b"jailed-epub"


def test_catalog_link_is_per_user_and_stops_after_delete(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    minted = client.get("/api/opds")
    assert minted.status_code == 200
    assert minted.json()["ttl_days"] == 180
    owner_url = minted.json()["catalog_url"]
    invite = client.post("/api/invites", json={"role": "reader"})
    token = invite.json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    redeemed = client.post(
        "/api/invites/redeem/local",
        json={"token": token, "username": "reader1", "password": "password123"},
    )
    assert redeemed.status_code == 200
    reader_id = redeemed.json()["user"]["id"]
    reader_url = client.get("/api/opds").json()["catalog_url"]
    assert "token=" in reader_url
    assert client.get(reader_url).status_code == 200
    client.post("/api/auth/logout")
    client.cookies.clear()
    _login(client)
    assert client.delete(f"/api/people/{reader_id}").status_code == 200
    client.cookies.clear()
    assert client.get(reader_url).status_code == 401
    assert client.get(owner_url).status_code == 200


def test_cookie_download_still_works_without_a_token(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    work, _row = _shelve(
        db, tmp_path, kind="book", title="Dune", author="Herbert", filename="Dune.epub", body=b"cookie-epub"
    )
    resp = client.get(f"/api/works/{work['id']}/download")
    assert resp.status_code == 200
    assert resp.content == b"cookie-epub"
