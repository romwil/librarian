"""DrunkenSlug is classic Newznab (XML / o=json), not NZBFinder /api/v2 JSON."""

import json

import httpx

from librarian.config import Settings, mask_settings
from librarian.indexers.discover import category_feeds
from librarian.indexers.hosts import (
    DRUNKENSLUG_ID,
    DRUNKENSLUG_PRESET,
    DRUNKENSLUG_URL,
    enabled_hosts,
    normalize_extra_indexers,
    search_beyond,
)
from librarian.nzbfinder import (
    DIALECT_NEWZNAB,
    NZBFinderClient,
    NZBFinderError,
    infer_newznab_dialect,
    parse_caps_payload,
)

CLASSIC_SEARCH = {
    "channel": {
        "item": [
            {
                "title": "The Art of War",
                "guid": "ds-art-1",
                "link": "https://drunkenslug.com/details/ds-art-1",
                "enclosure": {"@attributes": {"url": "https://drunkenslug.com/getnzb/ds-art-1.nzb"}},
                "attr": [
                    {"@attributes": {"name": "category", "value": "7020"}},
                    {"@attributes": {"name": "size", "value": "12345"}},
                    {"@attributes": {"name": "author", "value": "Sun Tzu"}},
                ],
            },
            {
                "title": "Some Film 2024",
                "guid": "ds-mov-1",
                "attr": [{"@attributes": {"name": "category", "value": "2000"}}],
            },
        ]
    }
}

CLASSIC_CAPS_XML = """<?xml version="1.0"?>
<caps>
  <server title="DrunkenSlug" url="https://drunkenslug.com"/>
  <limits max="100" default="25"/>
  <searching>
    <search available="yes" supportedParams="q,cat,limit,offset"/>
    <book-search available="yes" supportedParams="q"/>
  </searching>
  <categories>
    <category id="7000" name="Books">
      <subcat id="7010" name="Magazines"/>
      <subcat id="7020" name="Ebook"/>
      <subcat id="7030" name="Comics"/>
    </category>
    <category id="2000" name="Movies">
      <subcat id="2040" name="HD"/>
    </category>
  </categories>
</caps>
"""

CLASSIC_RSS = """<?xml version="1.0"?>
<rss version="2.0" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/">
  <channel>
    <item>
      <title>Earthsea ebook</title>
      <guid>ds-earthsea</guid>
      <newznab:attr name="category" value="7020"/>
    </item>
  </channel>
</rss>
"""

NZB_XML = b'<?xml version="1.0"?><nzb xmlns="http://www.newzbin.com/DTD/2003/nzb"></nzb>'


def _ds_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    path = request.url.path
    if path.endswith("/api") and "t=search" in url:
        assert "o=json" in url
        assert "/api/v2/" not in path
        return httpx.Response(200, json=CLASSIC_SEARCH)
    if path.endswith("/api") and "t=get" in url:
        assert "id=ds-art-1" in url
        return httpx.Response(200, content=NZB_XML, headers={"content-type": "application/x-nzb"})
    if path.endswith("/api") and "t=caps" in url:
        return httpx.Response(200, content=CLASSIC_CAPS_XML, headers={"content-type": "text/xml"})
    if path.endswith("/rss"):
        assert "t=7020" in url
        assert "r=fixture-token" in url
        return httpx.Response(200, content=CLASSIC_RSS, headers={"content-type": "text/xml"})
    if "/api/v2/" in path:
        return httpx.Response(
            200,
            content=CLASSIC_RSS,
            headers={"content-type": "application/xml"},
        )
    return httpx.Response(404, json={"message": "nope"})


def test_drunkenslug_hostname_is_classic_newznab():
    assert infer_newznab_dialect("https://drunkenslug.com") == DIALECT_NEWZNAB
    assert infer_newznab_dialect("https://api.drunkenslug.com/api") == DIALECT_NEWZNAB
    assert infer_newznab_dialect("https://nzbfinder.example", label="NZBFinder") == "v2"


def test_preset_normalizes_stable_id_and_empty_token():
    rows = normalize_extra_indexers(
        [{"name": "DrunkenSlug", "url": DRUNKENSLUG_URL, "api_token": "", "enabled": True}]
    )
    assert rows[0]["id"] == DRUNKENSLUG_ID
    assert rows[0]["url"] == DRUNKENSLUG_URL
    assert rows[0]["api_token"] == ""
    assert rows[0]["dialect"] == DIALECT_NEWZNAB
    assert rows[0]["name"] == DRUNKENSLUG_PRESET["name"]
    masked = mask_settings(Settings(extra_indexers=[{"url": DRUNKENSLUG_URL, "api_token": "ds-secret"}]))
    assert masked["extra_indexers"][0]["api_token"] == ""
    assert masked["extra_indexers"][0]["api_token_set"] is True
    assert "ds-secret" not in json.dumps(masked)


def test_classic_search_uses_api_t_search_and_refuses_movies():
    client = NZBFinderClient(
        "https://drunkenslug.com",
        "fixture-token",
        transport=httpx.MockTransport(_ds_handler),
        label="DrunkenSlug",
    )
    assert client.dialect == DIALECT_NEWZNAB
    traced = client.books_traced(title="The Art of War", author="Sun Tzu", cat="7020")
    assert [row["guid"] for row in traced["accepted"]] == ["ds-art-1"]
    assert traced["accepted"][0]["kind"] == "book"
    assert traced["accepted"][0]["author"] == "Sun Tzu"
    assert any(row.get("guid") == "ds-mov-1" for row in traced["rejected"])
    url = client.download_url("ds-art-1")
    assert "t=get" in url
    assert "/api/v2/" not in url
    assert "apikey=fixture-token" in url
    body = client.fetch_nzb("ds-art-1")
    assert b"<nzb" in body


def test_classic_xml_search_parses_rss_items():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api") and "t=search" in str(request.url):
            return httpx.Response(200, content=CLASSIC_RSS, headers={"content-type": "application/rss+xml"})
        return httpx.Response(404, json={})

    client = NZBFinderClient(
        "https://drunkenslug.com",
        "tok",
        transport=httpx.MockTransport(handler),
        label="DrunkenSlug",
    )
    rows = client.search("Earthsea", kind="book")
    assert [row["guid"] for row in rows] == ["ds-earthsea"]
    assert rows[0]["kind"] == "book"


def test_classic_caps_xml_feeds_books_not_movies_by_default():
    caps = parse_caps_payload(None, body=CLASSIC_CAPS_XML)
    library = category_feeds(caps, extra=False)
    extra = category_feeds(caps, extra=True)
    assert {row["id"] for row in library} == {"7010", "7020", "7030"}
    assert "2040" in {row["id"] for row in extra}
    assert "2040" not in {row["id"] for row in library}


def test_classic_error_xml_does_not_look_like_empty_hits():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content='<?xml version="1.0"?><error code="100" description="Incorrect user credentials"/>',
            headers={"content-type": "text/xml"},
        )

    client = NZBFinderClient(
        "https://drunkenslug.com",
        "bad",
        transport=httpx.MockTransport(handler),
        label="DrunkenSlug",
    )
    try:
        client.search("Dune", kind="book")
        raise AssertionError("expected NZBFinderError")
    except NZBFinderError as error:
        assert "credentials" in str(error).lower()
        assert "bad" not in str(error)


def test_search_beyond_includes_drunkenslug_hits():
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "nzbfinder.example":
            return httpx.Response(
                200,
                json={"results": [{"title": "Dune NZBFinder", "guid": "nf-dune", "category": 7020}]},
            )
        if host == "drunkenslug.com" and "t=search" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "channel": {
                        "item": {
                            "title": "Dune DrunkenSlug",
                            "guid": "ds-dune",
                            "attr": [{"@attributes": {"name": "category", "value": "7020"}}],
                        }
                    }
                },
            )
        return httpx.Response(404, json={"message": "nope"})

    settings = Settings(
        nzbfinder_url="https://nzbfinder.example",
        nzbfinder_api_token="nf-tok",
        extra_indexers=[
            {
                "id": DRUNKENSLUG_ID,
                "name": "DrunkenSlug",
                "url": DRUNKENSLUG_URL,
                "api_token": "ds-tok",
                "enabled": True,
                "dialect": DIALECT_NEWZNAB,
            }
        ],
    )
    hosts = enabled_hosts(settings)
    assert [row["id"] for row in hosts] == ["nzbfinder", DRUNKENSLUG_ID]
    hits, error = search_beyond(
        settings,
        transport=httpx.MockTransport(handler),
        kind="book",
        title="Dune",
    )
    assert error is None
    titles = [row["title"] for row in hits]
    assert titles == ["Dune NZBFinder", "Dune DrunkenSlug"]
    assert hits[1]["host_name"] == "DrunkenSlug"
    assert "ds-tok" not in json.dumps(hits)
    assert "r=" not in json.dumps(hits)


def test_v2_host_still_uses_api_v2():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"results": [{"title": "Linux Mag", "guid": "g-mag", "category": 7010}]},
        )

    client = NZBFinderClient("https://nzbfinder.example", "tok", transport=httpx.MockTransport(handler))
    rows = client.search("linux", kind="magazine")
    assert "/api/v2/search" in captured["url"]
    assert "t=search" not in captured["url"]
    assert [row["kind"] for row in rows] == ["magazine"]
