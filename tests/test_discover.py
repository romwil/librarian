import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.indexers.discover import category_feeds, clear_discover_cache, public_discover_hit
from librarian.kinds import kind_from_newznab
from librarian.nzbfinder import NZBFinderError
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app

CAPS = json.loads((Path(__file__).parent / "fixtures" / "nzbfinder" / "capabilities.json").read_text())
COMIC_HIT = {
    "title": "Saga 001",
    "kind": "comic",
    "guid": "g-saga",
    "category": 7030,
    "category_name": "Comics",
    "download_url": "https://nzbfinder.example/api/v2/download?id=g-saga.nzb&api_token=secret",
}
TV_HIT = {
    "title": "Some Show S01E01",
    "guid": "g-tv",
    "category": 5000,
    "download_url": "https://example.test/show.nzb",
}
MOVIE_HIT = {
    "title": "Dune.2021",
    "guid": "g-dune-movie",
    "category": 2040,
    "tmdb_id": 438631,
    "download_url": "https://example.test/dune.nzb",
}


def _client(tmp_path, monkeypatch, **settings_fields):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    if settings_fields:
        save_settings(tmp_path, Settings(**settings_fields))
    clear_session_secret_cache()
    clear_rate_limits()
    clear_discover_cache()
    return TestClient(create_app(tmp_path))


def _login(client, username="owner", password="password123"):
    resp = client.post("/api/auth/local/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp


def _patch_discover_client(monkeypatch, *, latest=None, caps=None):
    monkeypatch.setattr(
        "librarian.nzbfinder.NZBFinderClient.capabilities",
        caps or (lambda self: CAPS),
    )

    def fake_latest(self, cat, *, limit=25, path="search"):
        if latest:
            try:
                return latest(self, cat, limit=limit, path=path)
            except TypeError:
                return latest(self, cat)
        return []

    monkeypatch.setattr("librarian.nzbfinder.NZBFinderClient.latest", fake_latest)
    monkeypatch.setattr(
        "librarian.nzbfinder.NZBFinderClient.fetch_rss_category",
        lambda self, cat, *, limit=25: (_ for _ in ()).throw(NZBFinderError(f"{self.label} HTTP 502")),
    )


def test_discover_requires_auth(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.cookies.clear()
    assert client.get("/api/discover").status_code == 401
    hidden = {row["id"] for row in category_feeds(CAPS, extra=False)}
    assert "7030" in hidden
    assert "7010" in hidden
    assert "7020" in hidden
    assert "7999" in hidden
    assert "3030" in hidden
    assert "3010" in hidden
    assert "2000" not in hidden
    assert "2040" not in hidden
    assert "5000" not in hidden
    assert "5040" not in hidden
    assert "6000" not in hidden
    shown = {row["id"]: row["kind"] for row in category_feeds(CAPS, extra=True)}
    assert "2040" not in shown
    assert "5040" not in shown
    assert "6030" not in shown
    assert shown["7030"] == "comic"


def test_discover_hit_strips_token_and_drops_tv_when_extra_off():
    host = {"id": "nzbfinder", "name": "NZBFinder"}
    feed = {"id": "7030", "name": "Comics", "kind": "comic"}
    comic = public_discover_hit(COMIC_HIT, host=host, feed=feed, extra=False)
    assert comic is not None
    assert comic["kind"] == "comic"
    assert "secret" not in comic["download_url"]
    assert public_discover_hit(TV_HIT, host=host, feed=feed, extra=False) is None
    movie = public_discover_hit(MOVIE_HIT, host=host, feed={"id": "2040", "name": "HD", "kind": "movie"}, extra=True)
    assert movie is None


def test_discover_comic_drops_tv_and_keeps_7030(tmp_path, monkeypatch):
    monkeypatch.setenv("NZBFINDER_API_TOKEN", "tok")
    client = _client(tmp_path, monkeypatch, nzbfinder_api_token="tok")
    _login(client)

    def latest(self, cat):
        assert str(cat) == "7030"
        return [COMIC_HIT, TV_HIT]

    _patch_discover_client(monkeypatch, latest=latest)
    resp = client.get("/api/discover", params={"kind": "comic"})
    assert resp.status_code == 200
    body = resp.json()
    assert [row["guid"] for row in body["items"]] == ["g-saga"]
    assert all(row["kind"] == "comic" for row in body["items"])
    assert "5000" not in {row["id"] for row in body["categories"]}
    assert "secret" not in json.dumps(body)
    assert body["limit"] == 12


def test_discover_category_browse_uses_higher_limit(tmp_path, monkeypatch):
    from librarian.indexers.discover import (
        CATEGORY_BROWSE_LIMIT,
        PER_FEED_LIMIT,
        resolve_feed_limit,
    )

    assert resolve_feed_limit() == PER_FEED_LIMIT
    assert resolve_feed_limit(cat="7030") == CATEGORY_BROWSE_LIMIT
    assert resolve_feed_limit(cat="7030", limit=80) == 80
    assert resolve_feed_limit(limit=999) == 100

    monkeypatch.setenv("NZBFINDER_API_TOKEN", "tok")
    client = _client(tmp_path, monkeypatch, nzbfinder_api_token="tok")
    _login(client)
    seen = []

    def latest(self, cat, *, limit=25, path="search"):
        seen.append((str(cat), limit))
        return [
            {
                **COMIC_HIT,
                "guid": f"g-{i}",
                "title": f"Saga {i:03d}",
                "download_url": f"https://nzbfinder.example/api/v2/download?id=g-{i}.nzb&api_token=secret",
            }
            for i in range(limit)
        ]

    _patch_discover_client(monkeypatch, latest=latest)
    rails = client.get("/api/discover", params={"kind": "comic"})
    assert rails.status_code == 200
    assert rails.json()["limit"] == PER_FEED_LIMIT
    assert all(limit == PER_FEED_LIMIT for _, limit in seen if _ == "7030")

    seen.clear()
    browse = client.get("/api/discover", params={"kind": "comic", "cat": "7030"})
    assert browse.status_code == 200
    body = browse.json()
    assert body["limit"] == CATEGORY_BROWSE_LIMIT
    assert body["cat"] == "7030"
    assert len(body["items"]) == CATEGORY_BROWSE_LIMIT
    assert seen == [("7030", CATEGORY_BROWSE_LIMIT)]
    assert "secret" not in json.dumps(body)

    seen.clear()
    capped = client.get("/api/discover", params={"cat": "7030", "limit": 30})
    assert capped.status_code == 200
    assert capped.json()["limit"] == 30
    assert seen == [("7030", 30)]


def test_discover_rss_category_happy_path_mocked(tmp_path, monkeypatch):
    """Discover fills rails from /rss/category XML when caps are present (no live indexer)."""
    from librarian.indexers.discover import discover_beyond

    monkeypatch.setenv("NZBFINDER_API_TOKEN", "tok")
    clear_discover_cache()
    rss = """<?xml version="1.0"?>
<rss version="2.0" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/">
 <channel>
  <item>
   <title>Saga 001</title>
   <guid>g-saga</guid>
   <link>https://nzbfinder.example/get?id=g-saga.nzb&amp;api_token=secret</link>
   <enclosure url="https://nzbfinder.example/get?id=g-saga.nzb&amp;api_token=secret"/>
   <newznab:attr name="category" value="7030"/>
  </item>
 </channel>
</rss>"""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/capabilities"):
            return httpx.Response(200, json=CAPS)
        if path.endswith("/rss/category"):
            assert "id=" in str(request.url)
            return httpx.Response(200, content=rss, headers={"content-type": "text/xml"})
        if "/api/v2/search" in path or path.endswith("/search"):
            return httpx.Response(400, json={"message": "Validation failed", "errors": {"query": ["required"]}})
        return httpx.Response(
            404,
            content="<!DOCTYPE html><html><body>missing</body></html>",
            headers={"content-type": "text/html"},
        )

    settings = Settings(nzbfinder_api_token="tok", nzbfinder_url="https://nzbfinder.example")
    items, categories, beyond_error = discover_beyond(
        settings,
        kind="comic",
        transport=httpx.MockTransport(handler),
    )
    assert beyond_error is None
    assert any(row["id"] == "7030" for row in categories)
    assert [row["title"] for row in items] == ["Saga 001"]
    assert items[0]["kind"] == "comic"
    assert "secret" not in json.dumps(items)


def test_discover_extra_host_502_keeps_nzbfinder(tmp_path, monkeypatch):
    monkeypatch.setenv("NZBFINDER_API_TOKEN", "tok")
    client = _client(
        tmp_path,
        monkeypatch,
        nzbfinder_api_token="tok",
        extra_indexers=[
            {
                "id": "extra1",
                "name": "Extra",
                "url": "https://extra.example",
                "api_token": "extra-tok",
                "enabled": True,
            }
        ],
    )
    _login(client)

    def latest(self, cat):
        if "extra.example" in self.base_url:
            raise NZBFinderError("Extra HTTP 502 returned non-JSON")
        return [COMIC_HIT]

    _patch_discover_client(monkeypatch, latest=latest)
    resp = client.get("/api/discover", params={"kind": "comic"})
    assert resp.status_code == 200
    body = resp.json()
    assert [row["title"] for row in body["items"]] == ["Saga 001"]
    assert body["items"][0]["host_name"] == "NZBFinder"
    assert "502" in (body["beyond_error"] or "")


def test_discover_omits_movie_feeds(tmp_path, monkeypatch):
    monkeypatch.setenv("NZBFINDER_API_TOKEN", "tok")
    client = _client(tmp_path, monkeypatch, nzbfinder_api_token="tok")
    _login(client)

    def latest(self, cat):
        return [MOVIE_HIT, COMIC_HIT]

    _patch_discover_client(monkeypatch, latest=latest)
    resp = client.get("/api/discover")
    assert resp.status_code == 200
    body = resp.json()
    assert "show_extra_categories" not in body
    kinds = {row["kind"] for row in body["items"]}
    ids = {row["id"] for row in body["categories"]}
    assert "movie" not in kinds
    assert "2040" not in ids
    assert "2000" not in ids


def test_reader_can_view_discover_and_request_is_asked(tmp_path, monkeypatch):
    monkeypatch.setenv("NZBFINDER_API_TOKEN", "tok")
    client = _client(tmp_path, monkeypatch, nzbfinder_api_token="tok")
    _login(client)
    minted = client.post("/api/invites", json={"role": "reader"})
    token = minted.json()["token"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert (
        client.post(
            "/api/invites/redeem/local",
            json={"token": token, "username": "reader1", "password": "password123"},
        ).status_code
        == 200
    )
    _patch_discover_client(monkeypatch, latest=lambda self, cat: [COMIC_HIT])
    listed = client.get("/api/discover", params={"kind": "comic"})
    assert listed.status_code == 200
    asked = client.post(
        "/api/request",
        json={"title": "Saga 001", "guid": "g-saga", "kind": "comic", "download_url": "https://example.test/saga.nzb"},
    )
    assert asked.status_code == 200
    assert asked.json()["job"]["status"] == "asked"


def test_movie_request_is_refused(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, nzbfinder_api_token="tok")
    _login(client)
    resp = client.post(
        "/api/request",
        json={"title": "Dune", "guid": "g-dune-movie", "kind": "movie"},
    )
    assert resp.status_code == 400
    assert "shelves" in resp.json()["detail"]


def test_kind_mapping_refuses_movie_tv_adult():
    assert kind_from_newznab(2040) is None
    assert kind_from_newznab(2040, extra=True) is None
    assert kind_from_newznab(5040, extra=True) is None
    assert kind_from_newznab(6030, extra=True) is None
    assert kind_from_newznab(7030, extra=True) == "comic"


def test_movie_feed_does_not_become_a_book():
    host = {"id": "nzbfinder", "name": "NZBFinder"}
    feed = {"id": "2010", "name": "Foreign", "kind": "movie", "parent_id": "2000", "parent_name": "Movies"}
    hit = {
        "title": "Solo.A.Star.Wars.Story.2018",
        "guid": "g-solo",
        "category": 7060,
        "cats": [7060, 2010],
        "download_url": "https://example.test/solo.nzb",
    }
    assert public_discover_hit(hit, host=host, feed=feed, extra=True) is None


def test_tv_feed_is_not_a_book():
    host = {"id": "nzbfinder", "name": "NZBFinder"}
    feed = {"id": "5020", "name": "Foreign", "kind": "tv"}
    hit = {"title": "Show.S01E01", "guid": "g-show", "category": 7020, "download_url": "https://example.test/s.nzb"}
    assert public_discover_hit(hit, host=host, feed=feed, extra=True) is None


def test_category_feeds_skip_movie_parents():
    rows = category_feeds(CAPS, extra=True)
    by_id = {row["id"]: row for row in rows}
    assert "2010" not in by_id
    assert by_id["7060"]["parent_id"] == "7000"
    assert by_id["7060"]["kind"] == "book"
