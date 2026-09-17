from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.nzbfinder import NZBFinderError
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def _client(tmp_path, monkeypatch, **settings_fields):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    if settings_fields:
        save_settings(tmp_path, Settings(**settings_fields))
    clear_session_secret_cache()
    clear_rate_limits()
    return TestClient(create_app(tmp_path))


def _login(client):
    resp = client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    assert resp.status_code == 200


def test_search_beyond_without_token_surfaces_error(tmp_path, monkeypatch):
    monkeypatch.setenv("NZBFINDER_API_TOKEN", "")
    client = _client(tmp_path, monkeypatch)
    _login(client)
    resp = client.get("/api/search", params={"q": "stephen king", "beyond": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["q"] == "stephen king"
    assert body["local"] == []
    assert body["beyond"] == []
    assert body["beyond_error"] == "NZBFinder api_token is not configured"


def test_search_music_uses_search_not_books(tmp_path, monkeypatch):
    monkeypatch.setenv("NZBFINDER_API_TOKEN", "tok")
    client = _client(tmp_path, monkeypatch)
    _login(client)
    calls = []

    def fake_search(self, query, *, cat=None, kind=None, limit=25, offset=0, keep_untyped=False):
        calls.append(("search", query, kind, cat))
        return [{"title": "Awesome Mix", "kind": "music", "guid": "g-mix", "category": 3010}]

    def fake_books(self, *, query="", title="", author="", isbn="", cat=None, limit=25):
        calls.append(("books", query or title, author, isbn, cat))
        return [{"title": "should-not-run", "kind": "book", "guid": "g-book"}]

    monkeypatch.setattr("librarian.nzbfinder.NZBFinderClient.search", fake_search)
    monkeypatch.setattr("librarian.nzbfinder.NZBFinderClient.books", fake_books)
    resp = client.get("/api/search", params={"q": "guardians mix", "beyond": 1, "kind": "music"})
    assert resp.status_code == 200
    body = resp.json()
    assert calls == [("search", "guardians mix", None, "3000")]
    assert [row["kind"] for row in body["beyond"]] == ["music"]
    assert body["beyond"][0]["title"] == "Awesome Mix"


def test_search_beyond_indexer_error_keeps_local_and_surfaces_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("NZBFINDER_API_TOKEN", "tok")
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    db.upsert_work({"kind": "book", "title": "The Shining", "author": "Stephen King"})

    def fail_get(self, path, extra=None):
        raise NZBFinderError("NZBFinder returned non-JSON")

    monkeypatch.setattr("librarian.nzbfinder.NZBFinderClient._get", fail_get)
    resp = client.get("/api/search", params={"q": "king", "beyond": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert [row["title"] for row in body["local"]] == ["The Shining"]
    assert body["beyond"] == []
    assert body["beyond_error"] == "NZBFinder returned non-JSON"


def test_search_local_kind_chip_filters_stacks(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = Database(tmp_path / "librarian.db")
    db.upsert_work({"kind": "book", "title": "Guardians Novel", "author": "Abnett"})
    db.upsert_work({"kind": "music", "title": "Guardians Mix", "author": "Various Artists", "music_state": "incoming"})
    music = client.get("/api/search", params={"q": "Guardians", "kind": "music"})
    assert music.status_code == 200
    assert [row["title"] for row in music.json()["local"]] == ["Guardians Mix"]
    books = client.get("/api/search", params={"q": "Guardians", "kind": "book"})
    assert [row["title"] for row in books.json()["local"]] == ["Guardians Novel"]


def test_search_books_sends_fielded_title_author_isbn(tmp_path, monkeypatch):
    monkeypatch.setenv("NZBFINDER_API_TOKEN", "tok")
    client = _client(tmp_path, monkeypatch)
    _login(client)
    calls = []

    def fake_books(self, *, query="", title="", author="", isbn="", cat=None, limit=25):
        calls.append(("books", title or query, author, isbn, cat))
        return [{"title": "Dune", "kind": "book", "guid": "g-dune", "isbn": isbn, "author": author}]

    def fake_search(self, query, *, cat=None, kind=None, limit=25, offset=0, keep_untyped=False):
        calls.append(("search", query, kind, cat))
        return []

    monkeypatch.setattr("librarian.nzbfinder.NZBFinderClient.books", fake_books)
    monkeypatch.setattr("librarian.nzbfinder.NZBFinderClient.search", fake_search)
    resp = client.get(
        "/api/search",
        params={
            "beyond": 1,
            "kind": "book",
            "title": "Dune",
            "author": "Herbert",
            "isbn": "9780441172719",
        },
    )
    assert resp.status_code == 200
    assert calls == [("books", "Dune", "Herbert", "9780441172719", "7000")]
    assert resp.json()["beyond"][0]["isbn"] == "9780441172719"


def test_search_comics_use_7030_and_music_ignores_isbn(tmp_path, monkeypatch):
    monkeypatch.setenv("NZBFINDER_API_TOKEN", "tok")
    client = _client(tmp_path, monkeypatch)
    _login(client)
    calls = []

    def fake_search(self, query, *, cat=None, kind=None, limit=25, offset=0, keep_untyped=False):
        calls.append(("search", query, cat))
        return [{"title": query, "kind": "comic" if cat == "7030" else "music", "guid": "g"}]

    def fake_books(self, *, query="", title="", author="", isbn="", cat=None, limit=25):
        calls.append(("books", title, isbn, cat))
        return []

    monkeypatch.setattr("librarian.nzbfinder.NZBFinderClient.search", fake_search)
    monkeypatch.setattr("librarian.nzbfinder.NZBFinderClient.books", fake_books)
    comic = client.get("/api/search", params={"beyond": 1, "kind": "comic", "series": "Saga", "issue": "54"})
    assert comic.status_code == 200
    assert calls == [("search", "Saga 54", "7030")]
    calls.clear()
    music = client.get(
        "/api/search",
        params={"beyond": 1, "kind": "music", "artist": "Queen", "album": "Jazz", "isbn": "9780441172719"},
    )
    assert music.status_code == 200
    assert calls == [("search", "Queen Jazz", "3000")]
    assert music.json()["beyond"][0]["kind"] == "music"


def test_search_movie_maps_kind_from_category(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, nzbfinder_api_token="tok", show_extra_categories=True)
    _login(client)

    def fake_search(self, query, *, cat=None, kind=None, limit=25, offset=0, keep_untyped=False):
        assert keep_untyped is True
        assert cat == "2000"
        return [
            {
                "title": "SUPERCARS.CHAMPIONSHIP.2022.Race.21.OTR",
                "kind": None,
                "guid": "g-otr",
                "category": 2040,
            }
        ]

    monkeypatch.setattr("librarian.nzbfinder.NZBFinderClient.search", fake_search)
    resp = client.get("/api/search", params={"beyond": 1, "kind": "movie", "q": "OTR"})
    assert resp.status_code == 200
    beyond = resp.json()["beyond"]
    assert [row["kind"] for row in beyond] == ["movie"]
    assert beyond[0]["title"].startswith("SUPERCARS")
