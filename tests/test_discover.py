import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from librarian.arr import expect_on_arr, sab_category_for_kind
from librarian.config import Settings, mask_settings, save_settings
from librarian.indexers.discover import category_feeds, clear_discover_cache, public_discover_hit
from librarian.jobs import enqueue_indexer_item
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
    assert shown["2040"] == "movie"
    assert shown["5040"] == "tv"
    assert shown["6030"] == "xxx"
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
    assert movie is not None
    assert movie["kind"] == "movie"


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


def test_discover_flag_off_hides_movie_feed(tmp_path, monkeypatch):
    monkeypatch.setenv("NZBFINDER_API_TOKEN", "tok")
    client = _client(tmp_path, monkeypatch, nzbfinder_api_token="tok", show_extra_categories=False)
    _login(client)

    def latest(self, cat):
        return [MOVIE_HIT, COMIC_HIT]

    _patch_discover_client(monkeypatch, latest=latest)
    resp = client.get("/api/discover")
    assert resp.status_code == 200
    body = resp.json()
    assert body["show_extra_categories"] is False
    kinds = {row["kind"] for row in body["items"]}
    ids = {row["id"] for row in body["categories"]}
    assert "movie" not in kinds
    assert "2040" not in ids
    assert "2000" not in ids


def test_discover_flag_on_includes_movie_feed(tmp_path, monkeypatch):
    monkeypatch.setenv("NZBFINDER_API_TOKEN", "tok")
    client = _client(tmp_path, monkeypatch, nzbfinder_api_token="tok", show_extra_categories=True)
    _login(client)

    def latest(self, cat):
        if str(cat) in {"2040", "2000"} or str(cat).startswith("20"):
            return [MOVIE_HIT]
        return []

    _patch_discover_client(monkeypatch, latest=latest)
    resp = client.get("/api/discover", params={"kind": "movie"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["show_extra_categories"] is True
    assert [row["kind"] for row in body["items"]] == ["movie"]
    assert any(row["id"] == "2040" for row in body["categories"])


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


def _quiet_nzb():
    nzb_xml = b'<?xml version="1.0"?><nzb xmlns="http://www.newzbin.com/DTD/2003/nzb"></nzb>'

    def handler(request: httpx.Request) -> httpx.Response:
        if "/api/v2/download" in str(request.url) or "/api/v1/getnzb" in str(request.url):
            return httpx.Response(200, content=nzb_xml, headers={"content-type": "application/x-nzb"})
        return httpx.Response(200, json={})

    return httpx.MockTransport(handler)


def _sab_addfile_handler(nzo_id: str, sab_cats=None):
    def sab_handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if request.method == "POST" or params.get("mode") == "addfile":
            if sab_cats is not None:
                # multipart field cat=
                body = request.content or b""
                if b'name="cat"' in body:
                    start = body.find(b'name="cat"')
                    chunk = body[start : start + 120]
                    parts = chunk.split(b"\r\n\r\n", 1)
                    if len(parts) == 2:
                        sab_cats.append(parts[1].split(b"\r\n")[0].decode())
                    else:
                        sab_cats.append("")
                else:
                    sab_cats.append("")
            return httpx.Response(200, json={"nzo_ids": [nzo_id]})
        if params.get("mode") == "addurl":
            raise AssertionError("addurl must not be used")
        return httpx.Response(200, json={"queue": {"slots": []}})

    return sab_handler


def test_movie_request_queues_sab_and_tells_radarr(tmp_path, monkeypatch):
    from librarian.db import Database
    from librarian.nzbfinder import NZBFinderClient
    from librarian.sabnzbd import SABClient

    sab_cats = []
    arr_calls = []

    def expect(settings, kind, item, **kwargs):
        arr_calls.append((kind, item.get("tmdb_id") or (item.get("selected") or {}).get("tmdb_id")))
        return {"service": "radarr", "arr_id": 9, "tmdb_id": 438631}

    monkeypatch.setattr("librarian.jobs.expect_on_arr", expect)
    db = Database(tmp_path / "librarian.db")
    settings = Settings(
        sabnzbd_api_key="sab",
        nzbfinder_api_token="tok",
        show_extra_categories=True,
        radarr_url="http://radarr.example",
        radarr_api_key="radarr-secret",
    )
    job = enqueue_indexer_item(
        db,
        settings,
        item={
            "title": "Dune",
            "guid": "g-dune-movie",
            "kind": "movie",
            "category": 2040,
            "tmdb_id": 438631,
            "download_url": "https://example.test/dune.nzb",
        },
        requested_by="owner-1",
        role="owner",
        sab=SABClient("http://downloader.sl", "sab", transport=httpx.MockTransport(_sab_addfile_handler("SABnzbd_nzo_movie", sab_cats))),
        nzb=NZBFinderClient("https://nzbfinder.example", "tok", transport=_quiet_nzb()),
    )
    assert job["status"] == "queued"
    assert job["nzo_id"] == "SABnzbd_nzo_movie"
    assert sab_cats == ["movies"]
    assert arr_calls == [("movie", 438631)]
    assert job["payload"]["arr"]["service"] == "radarr"


def test_radarr_expect_adds_without_movies_search():
    commands = []

    def handler(request: httpx.Request) -> httpx.Response:
        commands.append(f"{request.method} {request.url.path}")
        path = request.url.path
        if path.endswith("/qualityprofile"):
            return httpx.Response(200, json=[{"id": 1}])
        if path.endswith("/rootfolder"):
            return httpx.Response(200, json=[{"path": "/media/movies"}])
        if "/movie/lookup/tmdb" in path:
            return httpx.Response(200, json={"tmdbId": 438631, "title": "Dune"})
        if path.endswith("/movie") and request.method == "GET":
            return httpx.Response(200, json=[])
        if path.endswith("/movie") and request.method == "POST":
            body = json.loads(request.content.decode())
            assert body["addOptions"]["searchForMovie"] is False
            assert body["rootFolderPath"] == "/media/movies"
            return httpx.Response(200, json={"id": 9, "tmdbId": 438631, "title": "Dune"})
        if path.endswith("/command"):
            body = json.loads(request.content.decode())
            commands.append(body.get("name"))
            return httpx.Response(200, json={"name": body.get("name")})
        return httpx.Response(404, json={})

    settings = Settings(radarr_url="http://radarr.example", radarr_api_key="radarr-secret")
    result = expect_on_arr(
        settings,
        "movie",
        {"title": "Dune", "tmdb_id": 438631},
        transport=httpx.MockTransport(handler),
    )
    assert result["service"] == "radarr"
    assert result["arr_id"] == 9
    assert "POST /api/v3/command" not in commands
    assert "MoviesSearch" not in commands


def test_xxx_request_is_sab_only_no_arr(tmp_path, monkeypatch):
    from librarian.db import Database
    from librarian.nzbfinder import NZBFinderClient
    from librarian.sabnzbd import SABClient

    arr_hits = []
    sab_cats = []

    def boom(*args, **kwargs):
        arr_hits.append("called")
        raise AssertionError("arr should not be called for XXX")

    monkeypatch.setattr("librarian.jobs.expect_on_arr", boom)
    db = Database(tmp_path / "librarian.db")
    job = enqueue_indexer_item(
        db,
        Settings(sabnzbd_api_key="sab", nzbfinder_api_token="tok", show_extra_categories=True),
        item={
            "title": "Clip",
            "guid": "g-xxx",
            "kind": "xxx",
            "category": 6030,
            "download_url": "https://example.test/x.nzb",
        },
        requested_by="owner-1",
        role="owner",
        sab=SABClient(
            "http://downloader.sl",
            "sab",
            transport=httpx.MockTransport(_sab_addfile_handler("SABnzbd_nzo_xxx", sab_cats)),
        ),
        nzb=NZBFinderClient("https://nzbfinder.example", "tok", transport=_quiet_nzb()),
    )
    assert job["status"] == "queued"
    assert job["nzo_id"] == "SABnzbd_nzo_xxx"
    assert sab_cats == [""]
    assert arr_hits == []
    assert job["payload"].get("arr") == {"service": None}


def test_movie_request_without_arr_token_still_sabs_and_needs_you(tmp_path):
    from librarian.db import Database
    from librarian.nzbfinder import NZBFinderClient
    from librarian.sabnzbd import SABClient

    db = Database(tmp_path / "librarian.db")
    job = enqueue_indexer_item(
        db,
        Settings(sabnzbd_api_key="sab", nzbfinder_api_token="tok", show_extra_categories=True),
        item={
            "title": "Dune",
            "guid": "g-dune-movie",
            "kind": "movie",
            "category": 2040,
            "download_url": "https://example.test/dune.nzb",
        },
        requested_by="owner-1",
        role="owner",
        sab=SABClient(
            "http://downloader.sl",
            "sab",
            transport=httpx.MockTransport(_sab_addfile_handler("SABnzbd_nzo_movie")),
        ),
        nzb=NZBFinderClient("https://nzbfinder.example", "tok", transport=_quiet_nzb()),
    )
    assert job["nzo_id"] == "SABnzbd_nzo_movie"
    assert job["status"] == "review"
    assert "Radarr" in (job.get("error") or "")
    assert job["payload"].get("arr") is None


def test_sab_category_names():
    settings = Settings(sab_movie_category="radarr", sab_tv_category="sonarr")
    assert sab_category_for_kind(settings, "movie") == "radarr"
    assert sab_category_for_kind(settings, "tv") == "sonarr"
    assert sab_category_for_kind(settings, "xxx") == ""
    assert sab_category_for_kind(settings, "book") == ""


def test_kind_extra_mapping_stays_off_identify_path():
    assert kind_from_newznab(2040) is None
    assert kind_from_newznab(2040, extra=True) == "movie"
    assert kind_from_newznab(5040, extra=True) == "tv"
    assert kind_from_newznab(6030, extra=True) == "xxx"
    assert kind_from_newznab(7030, extra=True) == "comic"


def test_mask_settings_hides_arr_keys():
    masked = mask_settings(Settings(radarr_api_key="radarr-secret", sonarr_api_key="sonarr-secret"))
    assert masked["radarr_api_key"] == ""
    assert masked["radarr_api_key_set"] is True
    assert masked["sonarr_api_key"] == ""
    assert "radarr-secret" not in json.dumps(masked)
    assert "sonarr-secret" not in json.dumps(masked)


def test_discover_movie_feed_keeps_movie_kind_despite_book_cat():
    """Extras feed kind wins over a stray library category on the item."""
    host = {"id": "nzbfinder", "name": "NZBFinder"}
    feed = {"id": "2010", "name": "Foreign", "kind": "movie", "parent_id": "2000", "parent_name": "Movies"}
    hit = {
        "title": "Solo.A.Star.Wars.Story.2018",
        "guid": "g-solo",
        "category": 7060,
        "cats": [7060, 2010],
        "download_url": "https://example.test/solo.nzb",
    }
    row = public_discover_hit(hit, host=host, feed=feed, extra=True)
    assert row is not None
    assert row["kind"] == "movie"


def test_discover_tv_feed_kind_not_book():
    host = {"id": "nzbfinder", "name": "NZBFinder"}
    feed = {"id": "5020", "name": "Foreign", "kind": "tv"}
    hit = {"title": "Show.S01E01", "guid": "g-show", "category": 7020, "download_url": "https://example.test/s.nzb"}
    row = public_discover_hit(hit, host=host, feed=feed, extra=True)
    assert row is not None
    assert row["kind"] == "tv"


def test_category_feeds_include_parent_for_grouping():
    rows = category_feeds(CAPS, extra=True)
    foreign = {row["id"]: row for row in rows}
    assert foreign["2010"]["parent_id"] == "2000"
    assert foreign["2010"]["parent_name"] == "Movies"
    assert foreign["7060"]["parent_id"] == "7000"
    assert foreign["7060"]["kind"] == "book"
    assert foreign["2010"]["kind"] == "movie"
