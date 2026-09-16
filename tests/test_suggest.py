"""Catalog-backed typeahead suggest API."""

from fastapi.testclient import TestClient

from librarian.db import Database
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.suggest import refresh_suggest_cache
from librarian.web.app import create_app


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


def _seed(tmp_path):
    db = Database(tmp_path / "librarian.db")
    db.upsert_work({"kind": "book", "title": "Dune", "author": "Frank Herbert", "year": 1965})
    db.upsert_work({"kind": "book", "title": "Dune Messiah", "author": "Frank Herbert", "year": 1969})
    db.upsert_work({"kind": "book", "title": "Neuromancer", "author": "William Gibson", "year": 1984})
    db.upsert_work(
        {
            "kind": "comic",
            "title": "Saga #1",
            "author": "Brian K. Vaughan",
            "series_name": "Saga",
            "series_index": "1",
            "year": 2012,
        }
    )
    db.upsert_work(
        {
            "kind": "music",
            "title": "Random Access Memories",
            "author": "Daft Punk",
            "series_name": "Random Access Memories",
            "year": 2013,
            "music_state": "incoming",
        }
    )
    db.upsert_work(
        {
            "kind": "music",
            "title": "Discovery",
            "author": "Daft Punk",
            "series_name": "Discovery",
            "year": 2001,
            "music_state": "incoming",
        }
    )
    return db


def test_suggest_requires_auth(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.cookies.clear()
    assert client.get("/api/suggest", params={"field": "author", "q": "frank"}).status_code == 401


def test_suggest_unknown_field_fail_closed(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    resp = client.get("/api/suggest", params={"field": "isbn", "q": "978"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unknown suggest field"


def test_suggest_authors_from_catalog(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    _seed(tmp_path)
    resp = client.get("/api/suggest", params={"field": "author", "kind": "book", "q": "herb"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["field"] == "author"
    values = [row["value"] for row in body["items"]]
    assert values == ["Frank Herbert"]
    assert body["items"][0]["meta"] == "catalog"


def test_suggest_music_artist_and_album(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    _seed(tmp_path)
    artists = client.get("/api/suggest", params={"field": "artist", "kind": "music", "q": "daft"})
    assert [row["value"] for row in artists.json()["items"]] == ["Daft Punk"]
    albums = client.get("/api/suggest", params={"field": "album", "kind": "music", "q": "random"})
    assert "Random Access Memories" in [row["value"] for row in albums.json()["items"]]


def test_suggest_series_and_years(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    _seed(tmp_path)
    series = client.get("/api/suggest", params={"field": "series", "kind": "comic", "q": "sag"})
    assert [row["value"] for row in series.json()["items"]] == ["Saga"]
    years = client.get("/api/suggest", params={"field": "year", "kind": "book", "q": "196"})
    assert "1965" in [row["value"] for row in years.json()["items"]]
    assert "1969" in [row["value"] for row in years.json()["items"]]


def test_suggest_merges_cache_after_catalog(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    db = _seed(tmp_path)
    refresh_suggest_cache(db, tmp_path, include_external=False)
    cache_path = tmp_path / "suggest-cache" / "author.json"
    cache_path.write_text(
        '{"version":1,"items":["Frank Herbert","Octavia E. Butler"]}',
        encoding="utf-8",
    )
    resp = client.get("/api/suggest", params={"field": "author", "kind": "book", "q": ""})
    values = [row["value"] for row in resp.json()["items"]]
    assert values.index("Frank Herbert") < values.index("Octavia E. Butler")
    assert resp.json()["items"][values.index("Octavia E. Butler")]["meta"] == "cache"


def test_owner_refresh_suggest_cache(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    _seed(tmp_path)
    resp = client.post("/api/settings/suggest-cache")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["external"] is False
    assert body["counts"]["author"] >= 2
    assert (tmp_path / "suggest-cache" / "meta.json").is_file()


def test_reader_cannot_refresh_suggest_cache(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    minted = client.post("/api/invites", json={"role": "reader"})
    token = minted.json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    client.post(
        "/api/invites/redeem/local",
        json={"token": token, "username": "reader1", "password": "password123"},
    )
    assert client.post("/api/settings/suggest-cache").status_code == 403
    # Readers may still typeahead against the catalog.
    _seed(tmp_path)
    assert client.get("/api/suggest", params={"field": "title", "q": "dune"}).status_code == 200


def test_refresh_external_mocks_musicbrainz(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _login(client)
    _seed(tmp_path)

    class FakeMB:
        def artist_albums(self, artist):
            return [{"title": "Homework", "author": artist}]

        def close(self):
            return None

    monkeypatch.setattr("librarian.musicbrainz.MusicBrainzClient", lambda **kwargs: FakeMB())
    resp = client.post("/api/settings/suggest-cache?external=1")
    assert resp.status_code == 200
    assert resp.json()["external"] is True
    assert resp.json()["external_added"]["album"] >= 1
    albums = client.get("/api/suggest", params={"field": "album", "q": "home"})
    assert "Homework" in [row["value"] for row in albums.json()["items"]]
