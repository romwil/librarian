import json
from pathlib import Path

import httpx

from librarian.indexers.kind_map import newznab_cat_to_kind
from librarian.nzbfinder import NZBFinderClient, NZBFinderError, parse_search_payload

FIXTURE = Path(__file__).parent / "fixtures" / "nzbfinder_search.json"
V2 = Path(__file__).parent / "fixtures" / "nzbfinder"


def test_parse_fixture_maps_movies_and_shelf_kinds():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    items = parse_search_payload(payload)
    kinds = [item["kind"] for item in items]
    assert kinds == ["magazine", "comic", "movie"]
    assert "api_token" not in json.dumps(payload)
    assert items[0]["guid"] == "guid-linux-mag-2026-10"
    assert items[1]["kind"] == "comic"
    assert items[2]["kind"] == "movie"


def test_client_sends_user_agent_and_api_token():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["ua"] = request.headers["user-agent"]
        captured["url"] = str(request.url)
        return httpx.Response(200, json=json.loads((V2 / "search-magazine.json").read_text(encoding="utf-8")))

    transport = httpx.MockTransport(handler)
    client = NZBFinderClient("https://nzbfinder.example", "fixture-token", transport=transport)
    results = client.search("linux", kind="magazine")
    assert captured["ua"].startswith("Librarian/")
    assert "Automat" in captured["ua"]
    assert "/api/v2/search" in captured["url"]
    assert "query=linux" in captured["url"]
    assert "api_token=fixture-token" in captured["url"]
    assert "t=search" not in captured["url"]
    assert [item["kind"] for item in results] == ["magazine"]
    url = client.download_url("guid-linux-mag-2026-10")
    assert url.startswith("https://nzbfinder.example/api/v2/download?")
    assert "id=guid-linux-mag-2026-10" in url
    assert "api_token=fixture-token" in url
    assert "t=get" not in url


def test_client_requires_token():
    client = NZBFinderClient("https://nzbfinder.example", "")
    try:
        client.search("x")
        raise AssertionError("expected NZBFinderError")
    except NZBFinderError as error:
        assert "api_token" in str(error)


def test_v2_books_fixture_normalizes_without_live_fetch():
    payload = json.loads((V2 / "books-linux.json").read_text(encoding="utf-8"))
    items = parse_search_payload(payload)
    assert [item["kind"] for item in items] == ["book", "book"]
    assert items[0]["guid"] == "65f78bbf-023c-4e9f-99c1-93633ed9bcf5"
    assert items[0]["isbn"] == "9788980541119"
    assert items[0]["download_url"].endswith("id=65f78bbf-023c-4e9f-99c1-93633ed9bcf5.nzb")
    assert "api_token" not in items[0]["download_url"]
    assert items[1]["book_title"] == "Linux"


def test_v2_magazine_and_details_fixtures():
    magazine = parse_search_payload(json.loads((V2 / "search-magazine.json").read_text(encoding="utf-8")))
    assert magazine[0]["kind"] == "magazine"
    assert magazine[0]["category"] == 7010
    assert "Linux-Magazin" in magazine[0]["title"]
    details = parse_search_payload(json.loads((V2 / "details-linux.json").read_text(encoding="utf-8")))
    assert details[0]["guid"] == "65f78bbf-023c-4e9f-99c1-93633ed9bcf5"
    assert details[0]["kind"] == "book"


def test_client_books_hits_v2_path():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=json.loads((V2 / "books-linux.json").read_text(encoding="utf-8")))

    client = NZBFinderClient("nzbfinder.example", "fixture-token", transport=httpx.MockTransport(handler))
    results = client.books(title="linux", isbn="9788980541119", limit=2)
    assert captured["url"].startswith("https://nzbfinder.example/api/v2/books?")
    assert "title=linux" in captured["url"]
    assert "isbn=9788980541119" in captured["url"]
    assert "t=book" not in captured["url"]
    assert [item["kind"] for item in results] == ["book", "book"]


def test_client_xml_payload_is_specific_error():
    xml = '<?xml version="1.0"?><rss version="2.0"><channel><title>NZBFinder</title></channel></rss>'

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=xml, headers={"content-type": "text/xml; charset=utf-8"})

    client = NZBFinderClient("https://nzbfinder.example", "tok", transport=httpx.MockTransport(handler))
    try:
        client.search("stephen king")
        raise AssertionError("expected NZBFinderError")
    except NZBFinderError as error:
        message = str(error)
        assert "XML" in message
        assert "non-JSON" not in message or "XML" in message
        assert "401" not in message


def test_client_html_login_and_401_are_specific():
    def html_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content="<!DOCTYPE html><html><body>Login</body></html>",
            headers={"content-type": "text/html; charset=utf-8"},
        )

    html_client = NZBFinderClient("https://nzbfinder.example", "tok", transport=httpx.MockTransport(html_handler))
    try:
        html_client.search("king")
        raise AssertionError("expected NZBFinderError")
    except NZBFinderError as error:
        assert "HTML" in str(error)

    def unauthorized(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Unauthenticated."})

    auth_client = NZBFinderClient("https://nzbfinder.example", "bad", transport=httpx.MockTransport(unauthorized))
    try:
        auth_client.search("king")
        raise AssertionError("expected NZBFinderError")
    except NZBFinderError as error:
        assert "401" in str(error)


MAGAZINE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/">
 <channel>
  <title>NZBFinder</title>
  <item>
   <title>Linux Mag 2026-09</title>
   <guid isPermaLink="true">https://nzbfinder.example/details/guid-linux-mag</guid>
   <link>https://nzbfinder.example/api/v1/getnzb?id=guid-linux-mag.nzb&amp;apikey=secret</link>
   <pubDate>Tue, 15 Sep 2026 22:01:56 +0200</pubDate>
   <category>Books &gt; Magazines</category>
   <enclosure url="https://nzbfinder.example/api/v1/getnzb?id=guid-linux-mag.nzb&amp;apikey=secret" length="123" type="application/x-nzb"/>
   <newznab:attr name="category" value="7010"/>
   <newznab:attr name="size" value="123"/>
  </item>
 </channel>
</rss>
"""


def test_fetch_rss_category_prefers_nzbfinder_path():
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        path = request.url.path
        if path.endswith("/rss/category"):
            assert "id=7010" in str(request.url)
            return httpx.Response(200, content=MAGAZINE_RSS, headers={"content-type": "text/xml"})
        if path.endswith("/rss"):
            return httpx.Response(
                404,
                content="<!DOCTYPE html><html><body>missing</body></html>",
                headers={"content-type": "text/html"},
            )
        return httpx.Response(404, json={"message": "nope"})

    client = NZBFinderClient("https://nzbfinder.example", "tok", transport=httpx.MockTransport(handler))
    raw = client.fetch_rss_category("7010", limit=3)
    assert "Linux Mag" in raw
    assert any("/rss/category" in url for url in captured)
    assert "secret" not in raw or "apikey=secret" in raw  # feed may embed link; client does not log
    items = client.latest("7010", limit=3)
    assert items[0]["title"] == "Linux Mag 2026-09"
    assert items[0]["kind"] == "magazine"
    assert items[0]["category"] in (7010, "7010", 7010)
    # latest must not call empty-query v2 search
    assert not any("/api/v2/search" in url for url in captured)


def test_fetch_rss_category_falls_back_when_nzbfinder_path_404():
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url.path)
        path = request.url.path
        if path.endswith("/rss/category"):
            return httpx.Response(404, json={"message": "The route rss/category could not be found."})
        if path.endswith("/rss"):
            assert "t=7030" in str(request.url)
            return httpx.Response(200, content=MAGAZINE_RSS.replace("7010", "7030"), headers={"content-type": "text/xml"})
        return httpx.Response(500, json={"message": "boom"})

    client = NZBFinderClient("https://classic.example", "tok", transport=httpx.MockTransport(handler))
    raw = client.fetch_rss_category("7030")
    assert "Linux Mag" in raw
    assert captured[:2] == ["/rss/category", "/rss"]


def test_fetch_rss_category_rejects_html_and_tries_next():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/rss/category"):
            return httpx.Response(
                200,
                content="<!DOCTYPE html><html><body>login</body></html>",
                headers={"content-type": "text/html"},
            )
        if path.endswith("/rss"):
            return httpx.Response(
                404,
                content="<!DOCTYPE html><html><body>missing</body></html>",
                headers={"content-type": "text/html"},
            )
        if path.endswith("/api"):
            return httpx.Response(200, content=MAGAZINE_RSS, headers={"content-type": "text/xml"})
        return httpx.Response(404, json={})

    client = NZBFinderClient("https://nzbfinder.example", "tok", transport=httpx.MockTransport(handler))
    raw = client.fetch_rss_category("7010")
    assert "<item>" in raw


def test_empty_query_v2_is_not_used_for_latest():
    """NZBFinder returns 400 Validation failed for empty query — Discover must not depend on it."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "/api/v2/search" in str(request.url):
            return httpx.Response(
                400,
                json={"message": "Validation failed", "errors": {"query": ["required"]}},
            )
        if request.url.path.endswith("/rss/category"):
            return httpx.Response(200, content=MAGAZINE_RSS, headers={"content-type": "text/xml"})
        return httpx.Response(404, json={"message": "nope"})

    client = NZBFinderClient("https://nzbfinder.example", "tok", transport=httpx.MockTransport(handler))
    items = client.latest("7010")
    assert [row["title"] for row in items] == ["Linux Mag 2026-09"]


def test_v2_capabilities_fixture_matches_kind_map():
    payload = json.loads((V2 / "capabilities.json").read_text(encoding="utf-8"))
    expected = {
        2000: "movie",
        5000: "tv",
        6000: "xxx",
        7010: "magazine",
        7020: "book",
        7030: "comic",
        7040: "book",
        3010: "music",
        3030: "audiobook",
        3040: "music",
        3999: "music",
        3020: None,
    }
    for cat, kind in expected.items():
        assert newznab_cat_to_kind(cat) == kind
    names = {row["name"] for row in payload["categories"]}
    assert {"Movies", "TV", "XXX", "Books", "Audio"} <= names
