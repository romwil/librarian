"""Komga client — mocked HTTP only."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from librarian.komga import (
    KomgaClient,
    KomgaError,
    komga_payload,
    komga_reader_link,
    notify_komga_scan,
)


def _settings(**overrides):
    base = {
        "komga_url": "http://komga.local:25600",
        "komga_api_key": "secret-komga",
        "komga_library_id": "lib-1",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_trigger_scan_posts_library(tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("X-API-Key")
        assert request.method == "POST"
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    client = KomgaClient(
        "http://komga.local:25600",
        "secret-komga",
        library_id="lib-1",
        transport=transport,
    )
    try:
        assert client.trigger_scan() is True
    finally:
        client.close()
    assert seen["url"].endswith("/api/v1/libraries/lib-1/scan")
    assert seen["key"] == "secret-komga"


def test_trigger_scan_refuses_bad_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    client = KomgaClient(
        "http://komga.local:25600",
        "bad",
        library_id="lib-1",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(KomgaError, match="refused"):
            client.trigger_scan()
    finally:
        client.close()


def test_notify_komga_scan_fail_soft():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    result = notify_komga_scan(
        _settings(),
        transport=httpx.MockTransport(handler),
    )
    assert result["ok"] is False
    assert result["skipped"] is False


def test_notify_skips_when_unconfigured():
    result = notify_komga_scan(_settings(komga_url="", komga_api_key="", komga_library_id=""))
    assert result == {"ok": False, "skipped": True, "reason": "not_configured"}


def test_komga_reader_link_for_comic():
    work = {"kind": "comic", "series_name": "Saga", "title": "Saga #1"}
    link = komga_reader_link(work, _settings())
    assert link is not None
    assert link["label"] == "Open in Komga"
    assert "libraries/lib-1" in link["href"]
    assert "Saga" in link["href"]
    assert komga_reader_link({"kind": "book"}, _settings()) is None
    payload = komga_payload(work, _settings())
    assert payload["configured"] is True
    assert payload["reader"]["href"] == link["href"]
