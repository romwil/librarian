import json
import time
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from librarian.config import Settings, mask_settings, save_settings
from librarian.db import Database
from librarian.enrich import (
    Enrichment,
    _still_needs,
    enrich_backlog_batch,
    enrich_library,
    enrich_work,
    is_thin,
)
from librarian.goodreads import import_goodreads_csv, parse_csv_isbn, parse_goodreads_rows
from librarian.identify import isbn10_to_isbn13, isbn13_to_isbn10, isbn_match_keys
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 80
ISBN13 = "9780441478125"
ISBN10 = "0441478123"
BLURB = "A winter planet and the politics of gender."


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    # Block maintainer .env LLM keys (load_dotenv does not override existing env).
    for key in (
        "LLM_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL",
    ):
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    clear_session_secret_cache()
    clear_rate_limits()
    return TestClient(create_app(tmp_path))


def _wait_enrich_status(client, *, timeout=5.0):
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        resp = client.get("/api/settings/enrich/status")
        assert resp.status_code == 200
        last = resp.json()
        if last.get("status") in ("completed", "failed", "idle"):
            return last
        time.sleep(0.05)
    return last


def _hardcover_edition():
    return {
        "isbn_13": ISBN13,
        "isbn_10": ISBN10,
        "release_date": "1969-01-01",
        "cached_image": {"url": "https://covers.hardcover.test/lh.jpg"},
        "book": {
            "title": "The Left Hand of Darkness",
            "description": f"<p>{BLURB}</p>",
            "release_year": 1969,
            "cached_image": {"url": "https://covers.hardcover.test/lh.jpg"},
            "cached_featured_series": {"name": "Hainish Cycle", "position": 4},
            "cached_tags": {"Genre": [{"tag": "Science Fiction"}, {"tag": "Fiction"}]},
        },
    }


def _handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if request.method == "POST" and "hardcover.app" in url:
        body = json.loads(request.content.decode("utf-8"))
        query = str(body.get("query") or "")
        if "EditionByIsbn" in query:
            return httpx.Response(200, json={"data": {"editions": [_hardcover_edition()]}})
        if "BookSearch" in query:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "search": {
                            "results": [
                                {
                                    "title": "Dune",
                                    "description": "Desert planet.",
                                    "release_year": 1965,
                                    "isbns": ["9780441172719"],
                                    "featured_series": {"name": "Dune", "position": 1},
                                    "image": {"url": "https://covers.hardcover.test/dune.jpg"},
                                }
                            ]
                        }
                    }
                },
            )
        return httpx.Response(200, json={"data": {}})
    if "/isbn/" in url:
        return httpx.Response(
            200,
            json={
                "title": "The Left Hand of Darkness",
                "publish_date": "1969",
                "covers": [5546156],
                "series": ["Hainish Cycle"],
                "works": [{"key": "/works/OL59037W"}],
            },
        )
    if "/works/OL59037W" in url:
        return httpx.Response(
            200,
            json={
                "description": {"value": BLURB},
                "title": "The Left Hand of Darkness",
                "subjects": ["Science fiction", "Gender"],
            },
        )
    if "search.json" in url:
        return httpx.Response(
            200,
            json={
                "docs": [
                    {
                        "title": "Dune",
                        "key": "/works/OL893415W",
                        "first_publish_year": 1965,
                        "cover_i": 99,
                        "isbn": ["9780441172719"],
                        "author_name": ["Frank Herbert"],
                        "subject": ["Science fiction"],
                    }
                ]
            },
        )
    if "/works/OL893415W" in url:
        return httpx.Response(
            200,
            json={
                "description": "Desert planet.",
                "title": "Dune",
                "subjects": ["Science fiction", "Planets"],
            },
        )
    if "wikipedia.org" in url or "wikimedia.org" in url:
        return _wiki_handler(request)
    if request.headers.get("accept", "").startswith("image") or url.endswith(".jpg"):
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
    return httpx.Response(404, json={"error": "missing"})


def _wiki_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "upload.wikimedia.org" in url or request.headers.get("accept", "").startswith("image"):
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
    if "commons.wikimedia.org" in url:
        return httpx.Response(
            200,
            json={
                "query": {
                    "pages": {
                        "1": {
                            "title": "File:Example.jpg",
                            "imageinfo": [
                                {
                                    "url": "https://upload.wikimedia.org/example.jpg",
                                    "thumburl": "https://upload.wikimedia.org/example-thumb.jpg",
                                    "extmetadata": {
                                        "Artist": {"value": "Jane Doe"},
                                        "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                    },
                                }
                            ],
                        }
                    }
                }
            },
        )
    return httpx.Response(
        200,
        json={
            "query": {
                "pages": {
                    "1": {
                        "title": "King Tut (novel)",
                        "extract": "A novel about Tutankhamun.",
                        "pageimage": "Example.jpg",
                        "original": {"source": "https://upload.wikimedia.org/example.jpg"},
                    }
                }
            }
        },
    )


def test_isbn10_converts_to_known_isbn13():
    assert isbn10_to_isbn13(ISBN10) == ISBN13
    assert isbn13_to_isbn10(ISBN13) == ISBN10
    assert isbn_match_keys(ISBN10) == [ISBN10, ISBN13]


def test_goodreads_csv_isbn_strips_equals_quotes():
    assert parse_csv_isbn(f'="{ISBN13}"') == ISBN13
    assert parse_csv_isbn('=""') == ""
    assert parse_csv_isbn("") == ""


def test_still_needs_when_series_name_missing_from_work_and_enrichment():
    work = {
        "description": BLURB,
        "year": 1969,
        "cover_path": "",
        "series_name": "",
    }
    found = Enrichment(
        description=BLURB,
        year=1969,
        cover_url="https://covers.hardcover.test/lh.jpg",
        series_name="",
    )
    assert _still_needs(found, work) is True


def test_hardcover_isbn_fills_thin_work_and_keeps_isbn(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": ISBN13,
        }
    )
    assert is_thin(work) is True
    settings = Settings(hardcover_api_token="hardcover-test-token")
    result = enrich_work(
        db,
        settings,
        work["id"],
        data_dir=tmp_path,
        transport=httpx.MockTransport(_handler),
    )
    updated = result["work"]
    assert result["updated"] is True
    assert result["source"] == "hardcover"
    assert updated["isbn"] == ISBN13
    assert updated["description"] == BLURB
    assert updated["series_name"] == "Hainish Cycle"
    assert updated["series_index"] == "4"
    assert updated["year"] == 1969
    assert updated["cover_path"]
    assert Path(updated["cover_path"]).read_bytes() == JPEG
    assert "Science Fiction" in (updated.get("genre") or "")
    assert updated.get("synopsis_source") == "hardcover"


def test_openlibrary_fills_when_hardcover_has_no_token(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": ISBN13,
        }
    )
    result = enrich_work(
        db,
        Settings(hardcover_api_token=""),
        work["id"],
        data_dir=tmp_path,
        transport=httpx.MockTransport(_handler),
    )
    updated = result["work"]
    assert result["source"] == "openlibrary"
    assert updated["isbn"] == ISBN13
    assert updated["description"] == BLURB
    assert updated["series_name"] == "Hainish Cycle"
    assert updated["year"] == 1969


def test_title_lookup_does_not_write_isbn(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work({"kind": "book", "title": "Dune", "author": "Frank Herbert"})
    result = enrich_work(
        db,
        Settings(hardcover_api_token="hardcover-test-token"),
        work["id"],
        data_dir=tmp_path,
        transport=httpx.MockTransport(_handler),
    )
    assert result["work"]["isbn"] in (None, "")
    assert result["work"]["description"] == "Desert planet."
    assert result["work"]["year"] == 1965
    assert result["work"]["series_name"] == "Dune"


def test_enrich_does_not_overwrite_existing_blurb(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": ISBN13,
            "description": "Keep this.",
            "year": 1969,
        }
    )
    result = enrich_work(
        db,
        Settings(hardcover_api_token="hardcover-test-token"),
        work["id"],
        data_dir=tmp_path,
        transport=httpx.MockTransport(_handler),
    )
    assert result["work"]["description"] == "Keep this."
    assert result["work"]["year"] == 1969
    assert result["work"]["series_name"] == "Hainish Cycle"


def test_enrich_skips_comics(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work({"kind": "comic", "title": "Saga #1", "series_name": "Saga", "series_index": "1"})
    try:
        enrich_work(db, Settings(), work["id"], data_dir=tmp_path, transport=httpx.MockTransport(_handler))
        raise AssertionError("comics must not enrich")
    except ValueError as error:
        assert str(error) == "Only books and audiobooks can be enriched"


def test_goodreads_csv_matches_isbn13_and_creates_thin_favorite(tmp_path):
    db = Database(tmp_path / "librarian.db")
    owner = db.create_local_user(
        user_id="local-owner",
        display_name="owner",
        password_hash="x$y",
        role="owner",
    )
    existing = db.upsert_work(
        {
            "kind": "book",
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": ISBN13,
        }
    )
    csv_text = (
        "Book Id,Title,Author,ISBN,ISBN13,Exclusive Shelf,Original Publication Year\n"
        f'1,The Left Hand of Darkness,Ursula K. Le Guin,="{ISBN10}",="{ISBN13}",read,1969\n'
        '2,No ISBN Book,Someone,"",="",to-read,2020\n'
        '3,Dune,Frank Herbert,"",="9780441172719",to-read,1965\n'
    )
    rows = parse_goodreads_rows(csv_text)
    assert rows[0]["isbn"] == ISBN13
    assert rows[1]["isbn"] == ""
    counts = import_goodreads_csv(db, owner["id"], csv_text)
    assert counts == {"rows": 3, "matched": 1, "created": 1, "favorited": 2, "skipped": 1}
    assert db.is_favorite(owner["id"], existing["id"]) is True
    dune = db.get_work_by_isbn("9780441172719")
    assert dune is not None
    assert dune["title"] == "Dune"
    assert dune["author"] == "Frank Herbert"
    assert dune["isbn"] == "9780441172719"
    assert dune["year"] == 1965
    assert db.files_for_work(dune["id"]) == []
    assert db.is_favorite(owner["id"], dune["id"]) is True
    titles = [row["title"] for row in db.favorite_works(owner["id"])]
    assert titles == ["Dune", "The Left Hand of Darkness"]


def test_mask_settings_hides_hardcover_token():
    masked = mask_settings(Settings(hardcover_api_token="hardcover-test-token"))
    assert masked["hardcover_api_token"] == ""
    assert masked["hardcover_api_token_set"] is True
    assert "hardcover-test-token" not in str(masked)


def test_enrich_and_goodreads_are_owner_only(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    op_token = client.post("/api/invites", json={"role": "op"}).json()["token"]
    reader_token = client.post("/api/invites", json={"role": "reader"}).json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert (
        client.post(
            "/api/invites/redeem/local",
            json={"token": op_token, "username": "ops", "password": "password123"},
        ).status_code
        == 200
    )
    assert client.post("/api/settings/enrich").status_code == 403
    assert client.post("/api/settings/goodreads", files={"file": ("shelf.csv", b"Title\nDune\n")}).status_code == 403
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert (
        client.post(
            "/api/invites/redeem/local",
            json={"token": reader_token, "username": "reader1", "password": "password123"},
        ).status_code
        == 200
    )
    assert client.post("/api/settings/enrich").status_code == 403
    assert client.get("/api/settings").status_code == 403


def test_enrich_api_fills_thin_book(tmp_path, monkeypatch):
    save_settings(tmp_path, Settings(hardcover_api_token="hardcover-test-token"))
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": ISBN13,
        }
    )
    monkeypatch.setattr(
        "librarian.enrich._http_client",
        lambda transport=None: httpx.Client(
            timeout=20.0, transport=httpx.MockTransport(_handler), follow_redirects=True
        ),
    )
    client = _client(tmp_path, monkeypatch)
    login = client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    assert login.status_code == 200
    settings = client.get("/api/settings")
    assert settings.status_code == 200
    assert settings.json()["settings"]["hardcover_api_token"] == ""
    assert settings.json()["settings"]["hardcover_api_token_set"] is True
    resp = client.post("/api/settings/enrich")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kicked_off"] is True
    assert body["status"] in ("running", "completed")
    status = _wait_enrich_status(client)
    assert status["status"] == "completed"
    result = status.get("result") or {}
    assert int(result.get("scanned") or status.get("done") or 0) == 1
    assert int(result.get("updated") or status.get("updated") or 0) == 1
    assert status.get("logs")
    detail = client.get(f"/api/works/{work['id']}")
    assert detail.status_code == 200
    assert detail.json()["work"]["description"] == BLURB
    assert detail.json()["work"]["isbn"] == ISBN13
    one = client.post(f"/api/works/{work['id']}/enrich")
    assert one.status_code == 200
    assert one.json()["work"]["description"] == BLURB


def test_enrich_status_idle_then_running(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    idle = client.get("/api/settings/enrich/status")
    assert idle.status_code == 200
    assert idle.json()["status"] == "idle"
    assert idle.json()["logs"] == []

    save_settings(tmp_path, Settings(hardcover_api_token="hardcover-test-token"))
    db = Database(tmp_path / "librarian.db")
    db.upsert_work(
        {
            "kind": "book",
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": ISBN13,
        }
    )
    monkeypatch.setattr(
        "librarian.enrich._http_client",
        lambda transport=None: httpx.Client(
            timeout=20.0, transport=httpx.MockTransport(_handler), follow_redirects=True
        ),
    )
    started = client.post("/api/settings/enrich")
    assert started.status_code == 200
    assert started.json()["kicked_off"] is True
    again = client.post("/api/settings/enrich")
    assert again.status_code == 200
    # Second kick while running (or just finished) must not error.
    assert "status" in again.json()
    status = _wait_enrich_status(client)
    assert status["status"] == "completed"
    assert status["source"] == "manual"


def test_goodreads_api_import(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    csv_text = (
        "Title,Author,ISBN,ISBN13,Original Publication Year\n"
        'Dune,Frank Herbert,"",="9780441172719",1965\n'
    )
    resp = client.post("/api/settings/goodreads", files={"file": ("goodreads.csv", csv_text.encode("utf-8"), "text/csv")})
    assert resp.status_code == 200
    assert resp.json() == {"rows": 1, "matched": 0, "created": 1, "favorited": 1, "skipped": 0}
    hall = client.get("/api/hall")
    assert [row["title"] for row in hall.json()["favorites"]] == ["Dune"]


def test_enrich_library_counts_complete_books_as_skipped(tmp_path):
    db = Database(tmp_path / "librarian.db")
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(JPEG)
    db.upsert_work(
        {
            "kind": "book",
            "title": "Kindred",
            "author": "Butler",
            "isbn": "9780807083697",
            "description": "A homecoming.",
            "genre": "Fiction",
            "year": 1979,
            "cover_path": str(cover),
        }
    )
    counts = enrich_library(db, Settings(), data_dir=tmp_path, transport=httpx.MockTransport(_handler))
    assert counts["scanned"] == 0
    assert counts["updated"] == 0
    assert counts["skipped"] == 1


def test_openlibrary_fills_genre_from_subjects(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": ISBN13,
        }
    )
    result = enrich_work(
        db,
        Settings(hardcover_api_token=""),
        work["id"],
        data_dir=tmp_path,
        transport=httpx.MockTransport(_handler),
    )
    assert "Science fiction" in (result["work"].get("genre") or "")
    assert result["work"].get("synopsis_source") == "openlibrary"


def test_wikipedia_fills_empty_description_and_localizes_art(tmp_path):
    db = Database(tmp_path / "librarian.db")
    folder = tmp_path / "books" / "Author" / "King Tut"
    folder.mkdir(parents=True)
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "King Tut",
            "author": "Someone",
            "folder_path": str(folder),
            "year": 1978,
        }
    )

    def wiki_only(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "hardcover" in url or "openlibrary.org" in url:
            return httpx.Response(404, json={})
        if request.headers.get("accept", "").startswith("image") or "upload.wikimedia.org" in url:
            return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
        if "wikipedia.org" in url or "commons.wikimedia.org" in url:
            return _wiki_handler(request)
        return httpx.Response(404, json={"error": "missing"})

    result = enrich_work(
        db,
        Settings(hardcover_api_token=""),
        work["id"],
        data_dir=tmp_path,
        transport=httpx.MockTransport(wiki_only),
    )
    updated = result["work"]
    assert updated["description"] == "A novel about Tutankhamun."
    assert updated["synopsis_source"] == "wikipedia"
    assert updated.get("art_attribution")
    assert "CC BY-SA" in updated["art_attribution"]
    atmosphere = Path(updated["atmosphere_path"])
    assert atmosphere.name == "atmosphere.jpg"
    assert atmosphere.read_bytes() == JPEG
    assert Path(updated["cover_path"]).read_bytes() == JPEG


def test_llm_polish_fail_closed_without_key(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Dune",
            "author": "Frank Herbert",
            "description": "Desert planet.",
            "year": 1965,
            "genre": "Science fiction",
        }
    )
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(JPEG)
    db.upsert_work({**work, "cover_path": str(cover)})
    result = enrich_work(
        db,
        Settings(hardcover_api_token="", llm_api_key=""),
        work["id"],
        data_dir=tmp_path,
        transport=httpx.MockTransport(_handler),
    )
    assert not result["work"].get("llm_blurb")


def test_llm_polish_writes_blurb_from_existing_text(tmp_path):
    db = Database(tmp_path / "librarian.db")
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(JPEG)
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Dune",
            "author": "Frank Herbert",
            "description": "A desert planet and a messianic prophecy.",
            "year": 1965,
            "genre": "Science fiction",
            "cover_path": str(cover),
        }
    )

    def llm_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "chat/completions" in url:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": "On a desert world, a prophecy reshapes an empire."}}
                    ]
                },
            )
        return _handler(request)

    result = enrich_work(
        db,
        Settings(
            hardcover_api_token="",
            llm_base_url="https://llm.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        ),
        work["id"],
        data_dir=tmp_path,
        transport=httpx.MockTransport(llm_handler),
    )
    assert result["work"]["llm_blurb"] == "On a desert world, a prophecy reshapes an empire."
    assert result["work"]["description"] == "A desert planet and a messianic prophecy."
    assert result["work"]["isbn"] in (None, "")


def test_enrich_backlog_batch_updates_thin_work(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "The Left Hand of Darkness",
            "author": "Le Guin",
            "isbn": ISBN13,
        }
    )
    assert db.count_works_needing_enrichment() == 1
    result = enrich_backlog_batch(
        db,
        Settings(hardcover_api_token="hardcover-test-token"),
        data_dir=tmp_path,
        limit=5,
        transport=httpx.MockTransport(_handler),
        pause_seconds=0,
    )
    assert result["enriched"] == 1
    assert db.get_work(work["id"])["description"] == BLURB


def _born_to_run_docs():
    return [
        {
            "title": "Born to Run",
            "key": "/works/OL1943602W",
            "first_publish_year": 1975,
            "author_name": ["Bruce Springsteen", "Michael Morpurgo"],
            "subject": [],
            "cover_i": 1,
        },
        {
            "title": "Born to Run",
            "key": "/works/OL44173969W",
            "first_publish_year": 2016,
            "author_name": ["Bruce Springsteen"],
            "subject": ["Autobiography", "Rock musicians", "Memoir"],
            "cover_i": 2,
        },
    ]


def _born_to_run_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "search.json" in url:
        return httpx.Response(200, json={"docs": _born_to_run_docs()})
    if "/works/OL44173969W" in url:
        return httpx.Response(
            200,
            json={
                "title": "Born to Run",
                "description": {
                    "value": "Bruce Springsteen's memoir of growing up and making music."
                },
                "first_publish_date": "2016",
                "subjects": ["Autobiography", "Memoir"],
                "covers": [2],
            },
        )
    if "/works/OL1943602W" in url:
        return httpx.Response(
            200,
            json={
                "title": "Born to Run",
                "description": {
                    "value": "There was something inside the bag, squeaking and squealing in terror."
                },
                "first_publish_date": "1975",
                "subjects": ["Dogs", "Greyhounds"],
                "covers": [1],
            },
        )
    if request.headers.get("accept", "").startswith("image") or url.endswith(".jpg"):
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
    return httpx.Response(404, json={"error": "missing"})


def test_openlibrary_rejects_foreign_coauthor_corruption():
    from librarian.openlibrary import (
        MIN_TITLE_MATCH_SCORE,
        pick_openlibrary_doc,
        score_openlibrary_doc,
    )

    bad, good = _born_to_run_docs()
    assert score_openlibrary_doc(bad, title="Born to Run", author="Bruce Springsteen", year=1975) < MIN_TITLE_MATCH_SCORE
    assert score_openlibrary_doc(good, title="Born to Run", author="Bruce Springsteen", year=1975) >= MIN_TITLE_MATCH_SCORE
    picked, score = pick_openlibrary_doc(
        [bad, good],
        title="Born to Run",
        author="Bruce Springsteen",
        year=1975,
    )
    assert picked is not None
    assert picked["key"] == "/works/OL44173969W"
    assert score >= MIN_TITLE_MATCH_SCORE


def test_openlibrary_title_lookup_skips_morpurgo_corruption(tmp_path):
    from librarian.openlibrary import OpenLibraryClient

    client = OpenLibraryClient(transport=httpx.MockTransport(_born_to_run_handler))
    try:
        hit = client.lookup_by_title("Born to Run", "Bruce Springsteen", year=1975)
    finally:
        client.close()
    assert hit.get("match_key") == "/works/OL44173969W"
    assert "greyhound" not in (hit.get("description") or "").lower()
    assert "Springsteen" in (hit.get("description") or "")
    assert hit.get("match_confidence", 0) >= 0.55


def test_enrich_born_to_run_prefers_memoir_not_greyhound(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "audiobook",
            "title": "Born to Run",
            "author": "Bruce Springsteen",
            "year": 1975,
        }
    )
    result = enrich_work(
        db,
        Settings(hardcover_api_token=""),
        work["id"],
        data_dir=tmp_path,
        transport=httpx.MockTransport(_born_to_run_handler),
    )
    assert result["updated"] is True
    assert result["match_key"] == "/works/OL44173969W"
    assert "greyhound" not in (result["work"].get("description") or "").lower()
    assert "Springsteen" in (result["work"].get("description") or "")


def test_metadata_patch_and_clear_enrich_api(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "audiobook",
            "title": "Born to Run",
            "author": "Bruce Springsteen",
            "year": 1975,
            "description": "Wrong greyhound blurb.",
            "synopsis_source": "openlibrary",
            "llm_blurb": "Polished wrong blurb.",
        }
    )
    patched = client.patch(
        f"/api/works/{work['id']}/metadata",
        json={
            "title": "Born to Run",
            "author": "Bruce Springsteen",
            "year": 2016,
            "description": "The Boss tells his own story.",
            "genre": "Memoir",
        },
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()["work"]
    assert body["year"] == 2016
    assert body["description"] == "The Boss tells his own story."
    assert body["genre"] == "Memoir"

    cleared = client.post(f"/api/works/{work['id']}/clear-enrich")
    assert cleared.status_code == 200, cleared.text
    cleared_work = cleared.json()["work"]
    assert cleared_work["description"] in (None, "")
    assert cleared_work["synopsis_source"] in (None, "")
    assert cleared_work["llm_blurb"] in (None, "")
    assert cleared_work["title"] == "Born to Run"
    assert cleared_work["year"] == 2016


def test_fix_match_apply_api(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "audiobook",
            "title": "Born to Run",
            "author": "Bruce Springsteen",
            "year": 1975,
            "description": "There was something inside the bag, squeaking and squealing in terror.",
            "synopsis_source": "openlibrary",
        }
    )
    monkeypatch.setattr(
        "librarian.enrich._http_client",
        lambda transport=None: httpx.Client(
            timeout=20.0, transport=httpx.MockTransport(_born_to_run_handler), follow_redirects=True
        ),
    )
    monkeypatch.setattr(
        "librarian.web.app.list_match_candidates",
        lambda work, **kwargs: __import__("librarian.enrich", fromlist=["list_match_candidates"]).list_match_candidates(
            work, transport=httpx.MockTransport(_born_to_run_handler), **kwargs
        ),
    )
    candidates = client.get(f"/api/works/{work['id']}/match-candidates")
    assert candidates.status_code == 200, candidates.text
    rows = candidates.json()["candidates"]
    assert rows
    assert rows[0]["match_key"] == "/works/OL44173969W"
    assert all(row["match_key"] != "/works/OL1943602W" or row["match_confidence"] < 0.55 for row in rows)

    applied = client.post(
        f"/api/works/{work['id']}/apply-match",
        json={"match_key": "/works/OL44173969W"},
    )
    assert applied.status_code == 200, applied.text
    payload = applied.json()
    assert payload["match_key"] == "/works/OL44173969W"
    assert "Springsteen" in (payload["work"].get("description") or "")
    assert "greyhound" not in (payload["work"].get("description") or "").lower()
    assert payload["work"]["year"] == 2016


def test_metadata_endpoints_forbid_readers(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work({"kind": "book", "title": "Dune", "author": "Frank Herbert"})
    reader_token = client.post("/api/invites", json={"role": "reader"}).json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert (
        client.post(
            "/api/invites/redeem/local",
            json={"token": reader_token, "username": "reader1", "password": "password123"},
        ).status_code
        == 200
    )
    assert client.patch(f"/api/works/{work['id']}/metadata", json={"description": "Nope"}).status_code == 403
    assert client.get(f"/api/works/{work['id']}/match-candidates").status_code == 403
    assert client.post(f"/api/works/{work['id']}/apply-match", json={"match_key": "/works/x"}).status_code == 403
    assert client.post(f"/api/works/{work['id']}/clear-enrich").status_code == 403
    assert client.post(f"/api/works/{work['id']}/enrich").status_code == 403
