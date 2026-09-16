import json

import httpx
from fastapi.testclient import TestClient

from librarian.audiobookshelf import AudiobookshelfClient, match_audiobooks
from librarian.config import Settings, mask_settings, save_settings
from librarian.db import Database
from librarian.nzbfinder import NZBFinderError
from librarian.rate_limit import clear_rate_limits
from librarian.rss import poll_feed, poll_rss_feeds
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app

RSS_XML = """<?xml version="1.0"?>
<rss version="2.0" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/">
  <channel>
    <item>
      <title>A Wizard of Earthsea</title>
      <guid>guid-earthsea</guid>
      <enclosure url="https://example.test/earthsea.nzb"/>
      <newznab:attr name="category" value="7020"/>
    </item>
    <item>
      <title>Some Show S01E01</title>
      <guid>guid-tv</guid>
      <enclosure url="https://example.test/show.nzb"/>
      <newznab:attr name="category" value="5000"/>
    </item>
  </channel>
</rss>
"""


def _client(tmp_path, monkeypatch, **settings_fields):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    if settings_fields:
        save_settings(tmp_path, Settings(**settings_fields))
    clear_session_secret_cache()
    clear_rate_limits()
    return TestClient(create_app(tmp_path))


def _login(client, username="owner", password="password123"):
    resp = client.post("/api/auth/local/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp


def test_extra_host_502_keeps_nzbfinder_hits(tmp_path, monkeypatch):
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

    def fake_books(self, *, query="", title="", author="", isbn="", cat=None, limit=25):
        if "extra.example" in self.base_url:
            raise NZBFinderError("Extra HTTP 502 returned non-JSON")
        return [{"title": "Dune", "kind": "book", "guid": "g-dune", "host_name": self.label}]

    monkeypatch.setattr("librarian.nzbfinder.NZBFinderClient.books", fake_books)
    resp = client.get("/api/search", params={"beyond": 1, "kind": "book", "title": "Dune"})
    assert resp.status_code == 200
    body = resp.json()
    assert [row["title"] for row in body["beyond"]] == ["Dune"]
    assert body["beyond"][0]["host_id"] == "nzbfinder"
    assert body["beyond"][0]["host_name"] == "NZBFinder"
    assert body["beyond_error"] == "Extra HTTP 502 returned non-JSON"


def test_extra_host_is_queried_and_deduped(tmp_path, monkeypatch):
    monkeypatch.setenv("NZBFINDER_API_TOKEN", "tok")
    client = _client(
        tmp_path,
        monkeypatch,
        nzbfinder_api_token="tok",
        extra_indexers=[
            {
                "id": "extra1",
                "name": "Books.nzb",
                "url": "https://extra.example",
                "api_token": "extra-tok",
                "enabled": True,
            }
        ],
    )
    _login(client)
    hosts = []

    def fake_books(self, *, query="", title="", author="", isbn="", cat=None, limit=25):
        hosts.append(self.label)
        return [{"title": "Dune", "kind": "book", "guid": "g-dune"}]

    monkeypatch.setattr("librarian.nzbfinder.NZBFinderClient.books", fake_books)
    resp = client.get("/api/search", params={"beyond": 1, "kind": "book", "title": "Dune"})
    assert resp.status_code == 200
    assert hosts == ["NZBFinder", "Books.nzb"]
    assert [row["guid"] for row in resp.json()["beyond"]] == ["g-dune"]
    assert resp.json()["beyond"][0]["host_name"] == "NZBFinder"
    assert resp.json()["beyond_error"] is None


def test_search_without_beyond_does_not_query_indexers(tmp_path, monkeypatch):
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
    calls = []

    def fake_books(self, **kwargs):
        calls.append("books")
        return []

    monkeypatch.setattr("librarian.nzbfinder.NZBFinderClient.books", fake_books)
    resp = client.get("/api/search", params={"q": "Dune", "kind": "book"})
    assert resp.status_code == 200
    assert calls == []
    assert resp.json()["beyond"] == []


def test_rss_poll_inserts_new_guid_once_and_refuses_tv(tmp_path):
    db = Database(tmp_path / "librarian.db")
    feed = db.upsert_rss_feed(
        {"id": "feed-books", "name": "Books", "url": "https://example.test/rss?apikey=secret", "kind": "book"}
    )
    created = poll_feed(db, feed, fetch=lambda _url: RSS_XML)
    assert created == 1
    jobs = db.list_jobs()
    assert [job["indexer_guid"] for job in jobs] == ["guid-earthsea"]
    assert jobs[0]["status"] == "asked"
    assert jobs[0]["kind"] == "book"
    assert jobs[0]["payload"]["source"] == "rss"
    assert "secret" not in json.dumps(jobs[0]["payload"])
    stored = db.get_rss_feed("feed-books")
    assert stored["last_guid"] == "guid-earthsea"
    created_again = poll_feed(db, stored, fetch=lambda _url: RSS_XML)
    assert created_again == 0
    assert len(db.list_jobs()) == 1


def test_rss_poller_skips_disabled(tmp_path):
    db = Database(tmp_path / "librarian.db")
    db.upsert_rss_feed(
        {
            "id": "off",
            "name": "Off",
            "url": "https://example.test/rss",
            "kind": "book",
            "enabled": 0,
        }
    )
    assert poll_rss_feeds(db, Settings(), fetch=lambda _url: RSS_XML) == 0
    assert db.list_jobs() == []


def test_abs_match_by_isbn_and_no_token_makes_no_calls(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {"kind": "audiobook", "title": "Dune", "author": "Herbert", "isbn": "9780441172719"}
    )
    quiet = match_audiobooks(db, Settings())
    assert quiet["called"] is False
    assert quiet["updated"] == 0
    assert db.get_work(work["id"])["abs_item_id"] in (None, "")

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url.path))
        if request.url.path.endswith("/api/libraries"):
            return httpx.Response(200, json={"libraries": [{"id": "lib-1", "mediaType": "book"}]})
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "abs-dune",
                        "media": {
                            "metadata": {
                                "title": "Dune",
                                "isbn": "9780441172719",
                                "authors": [{"name": "Herbert"}],
                            }
                        },
                    }
                ]
            },
        )

    abs_client = AudiobookshelfClient(
        "http://abs.example",
        "tok",
        transport=httpx.MockTransport(handler),
    )
    result = match_audiobooks(
        db,
        Settings(audiobookshelf_url="http://abs.example", audiobookshelf_api_token="tok"),
        client=abs_client,
    )
    assert "/api/libraries" in calls[0]
    assert result["called"] is True
    assert result["updated"] == 1
    assert result["matched"] == 1
    assert db.get_work(work["id"])["abs_item_id"] == "abs-dune"
    abs_client.close()


def test_abs_title_only_does_not_match(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work({"kind": "audiobook", "title": "Dune", "author": ""})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/libraries"):
            return httpx.Response(200, json={"libraries": [{"id": "lib-1", "mediaType": "book"}]})
        return httpx.Response(
            200,
            json={"results": [{"id": "abs-dune", "media": {"metadata": {"title": "Dune", "authors": []}}}]},
        )

    abs_client = AudiobookshelfClient("http://abs.example", "tok", transport=httpx.MockTransport(handler))
    match_audiobooks(
        db,
        Settings(audiobookshelf_url="http://abs.example", audiobookshelf_api_token="tok"),
        client=abs_client,
    )
    assert db.get_work(work["id"])["abs_item_id"] in (None, "")
    abs_client.close()


def test_reader_forbidden_on_rss_and_abs_match(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
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
    assert client.put("/api/settings", json={"household_name": "Nope"}).status_code == 403
    assert client.post("/api/rss", json={"url": "https://example.test/rss", "kind": "book"}).status_code == 403
    assert client.post("/api/settings/abs-match").status_code == 403
    assert client.get("/api/rss").status_code == 403


def test_owner_settings_mask_extra_and_abs_tokens(tmp_path, monkeypatch):
    client = _client(
        tmp_path,
        monkeypatch,
        nzbfinder_api_token="nzb-secret",
        audiobookshelf_url="http://abs.example",
        audiobookshelf_api_token="abs-secret",
        extra_indexers=[
            {
                "id": "extra1",
                "name": "Books.nzb",
                "url": "https://extra.example",
                "api_token": "extra-secret",
                "enabled": True,
            }
        ],
    )
    _login(client)
    listed = client.get("/api/settings")
    assert listed.status_code == 200
    body = listed.json()
    settings = body["settings"]
    assert settings["audiobookshelf_api_token"] == ""
    assert settings["audiobookshelf_api_token_set"] is True
    assert settings["audiobookshelf_url"] == "http://abs.example"
    assert settings["extra_indexers"][0]["api_token"] == ""
    assert settings["extra_indexers"][0]["api_token_set"] is True
    assert "extra-secret" not in json.dumps(body)
    assert "abs-secret" not in json.dumps(body)
    assert body["abs_match"]["audiobooks"] == 0

    rss = client.post(
        "/api/rss",
        json={"url": "https://example.test/rss?apikey=rss-secret", "kind": "comic", "name": "Comics"},
    )
    assert rss.status_code == 200
    assert rss.json()["feed"]["kind"] == "comic"
    assert "rss-secret" not in json.dumps(rss.json())
    assert "apikey" not in rss.json()["feed"]["url"]


def test_mask_settings_extra_indexers_never_returns_token():
    masked = mask_settings(
        Settings(
            audiobookshelf_api_token="abs-secret",
            extra_indexers=[
                {"name": "X", "url": "https://x.example", "api_token": "extra-secret", "enabled": True}
            ],
        )
    )
    assert masked["audiobookshelf_api_token"] == ""
    assert masked["audiobookshelf_api_token_set"] is True
    assert masked["extra_indexers"][0]["api_token"] == ""
    assert masked["extra_indexers"][0]["api_token_set"] is True
    assert "extra-secret" not in json.dumps(masked)
    assert "abs-secret" not in json.dumps(masked)


def test_extra_indexer_blank_token_keeps_saved(tmp_path, monkeypatch):
    client = _client(
        tmp_path,
        monkeypatch,
        extra_indexers=[
            {
                "id": "extra1",
                "name": "Books.nzb",
                "url": "https://extra.example",
                "api_token": "extra-secret",
                "enabled": True,
            }
        ],
    )
    _login(client)
    saved = client.put(
        "/api/settings",
        json={
            "extra_indexers": [
                {
                    "id": "extra1",
                    "name": "Books.nzb",
                    "url": "https://extra.example",
                    "api_token": "",
                    "enabled": True,
                }
            ]
        },
    )
    assert saved.status_code == 200
    assert saved.json()["settings"]["extra_indexers"][0]["api_token_set"] is True
    from librarian.config import load_merged_settings

    stored = load_merged_settings(tmp_path)
    assert stored.extra_indexers[0]["api_token"] == "extra-secret"


def test_rss_update_and_fetch(tmp_path):
    from librarian.rss import create_rss_feed, fetch_rss, parse_rss_xml, update_rss_feed

    db = Database(tmp_path / "librarian.db")
    feed = create_rss_feed(db, {"url": "https://example.test/rss", "kind": "book", "name": "Books"})
    updated = update_rss_feed(db, feed["id"], {"name": "Magazines", "kind": "magazine"})
    assert updated["name"] == "Magazines"
    assert updated["kind"] == "magazine"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=RSS_XML)

    raw = fetch_rss("https://example.test/rss", transport=httpx.MockTransport(handler))
    items = parse_rss_xml(raw)
    assert items[0]["guid"] == "guid-earthsea"
    assert items[0]["kind"] == "book"
    assert items[1]["kind"] is None


def test_abs_match_by_author_and_title(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {"kind": "audiobook", "title": "The Left Hand of Darkness", "author": "Ursula K. Le Guin"}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/libraries"):
            return httpx.Response(200, json={"libraries": [{"id": "lib-1", "mediaType": "book"}]})
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "abs-lhod",
                        "media": {
                            "metadata": {
                                "title": "The Left Hand of Darkness",
                                "authors": [{"name": "Ursula K. Le Guin"}],
                            }
                        },
                    }
                ]
            },
        )

    abs_client = AudiobookshelfClient("http://abs.example", "tok", transport=httpx.MockTransport(handler))
    result = match_audiobooks(
        db,
        Settings(audiobookshelf_url="http://abs.example", audiobookshelf_api_token="tok"),
        client=abs_client,
    )
    assert result["updated"] == 1
    assert db.get_work(work["id"])["abs_item_id"] == "abs-lhod"
    abs_client.close()

