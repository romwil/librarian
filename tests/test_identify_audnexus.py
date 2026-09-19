"""Identify audiobook → Audnexus score bands (HTTP mocked)."""

from __future__ import annotations

from types import SimpleNamespace

import httpx

from librarian.config import Settings
from librarian.identify import identify_completed


def _handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "catalog/products" in url:
        return httpx.Response(
            200,
            json={"products": [{"asin": "B08G9PRS1K", "title": "Project Hail Mary"}]},
        )
    if "/books/B08G9PRS1K" in url and "/chapters" not in url:
        return httpx.Response(
            200,
            json={
                "asin": "B08G9PRS1K",
                "title": "Project Hail Mary",
                "authors": [{"name": "Andy Weir"}],
                "narrators": [{"name": "Ray Porter"}],
                "releaseDate": "2021-05-04",
            },
        )
    return httpx.Response(404, json={})


def test_identify_audiobook_audnexus_auto(tmp_path):
    folder = tmp_path / "Andy Weir - Project Hail Mary Audiobook"
    folder.mkdir()
    (folder / "book.m4b").write_bytes(b"fake")
    base = Settings()
    settings = SimpleNamespace(**{**base.__dict__, "data_dir": str(tmp_path / "config")})
    (tmp_path / "config").mkdir()
    transport = httpx.MockTransport(_handler)
    result = identify_completed(folder, settings=settings, catalog_transport=transport)
    identity = result["identity"]
    assert identity["kind"] == "audiobook"
    assert identity["asin"] == "B08G9PRS1K"
    assert identity["confidence"] == "high"
    assert identity.get("review_reason") in (None, "")
    assert result["auto_organize"] is True
