import json
from pathlib import Path

import httpx

from librarian.nzbfinder import NZBFinderClient, NZBFinderError, parse_search_payload

FIXTURE = Path(__file__).parent / "fixtures" / "nzbfinder_search.json"


def test_parse_fixture_strips_movies_and_maps_kinds():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    items = parse_search_payload(payload)
    kinds = [item["kind"] for item in items]
    assert kinds == ["magazine", "comic", None]
    assert "api_token" not in json.dumps(payload)
    assert items[0]["guid"] == "guid-linux-mag-2026-10"
    assert items[1]["kind"] == "comic"


def test_client_sends_user_agent_and_api_token():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["ua"] = request.headers["user-agent"]
        captured["url"] = str(request.url)
        return httpx.Response(200, json=json.loads(FIXTURE.read_text(encoding="utf-8")))

    transport = httpx.MockTransport(handler)
    client = NZBFinderClient("https://nzbfinder.example", "fixture-token", transport=transport)
    results = client.search("linux", kind="magazine")
    assert captured["ua"].startswith("Librarian/")
    assert "api_token=fixture-token" in captured["url"]
    assert "t=search" in captured["url"]
    assert [item["kind"] for item in results] == ["magazine", "comic"]
    url = client.download_url("guid-linux-mag-2026-10")
    assert url.startswith("https://nzbfinder.example/api?")
    assert "t=get" in url
    assert "api_token=fixture-token" in url


def test_client_requires_token():
    client = NZBFinderClient("https://nzbfinder.example", "")
    try:
        client.search("x")
        raise AssertionError("expected NZBFinderError")
    except NZBFinderError as error:
        assert "api_token" in str(error)
