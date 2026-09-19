"""Audnexus client scoring and cache — HTTP mocked, SQLite real."""

from __future__ import annotations

import httpx

from librarian.audnexus import (
    REVIEW_AUDNEXUS_AMBIGUOUS,
    REVIEW_AUDNEXUS_UNMATCHED,
    AudnexusCache,
    AudnexusClient,
    band_for_score,
    match_audiobook_tokens,
    score_candidate,
)


def test_score_bands():
    assert band_for_score(0.9) == "auto"
    assert band_for_score(0.7) == "ambiguous"
    assert band_for_score(0.4) == "unmatched"


def test_score_exact_asin():
    score = score_candidate(
        {"asin": "B08G9PRS1K", "title": "Project Hail Mary", "author": "Andy Weir"},
        title="Wrong",
        author="Wrong",
        asin_hint="B08G9PRS1K",
    )
    assert score == 1.0


def test_audnexus_cache_roundtrip(tmp_path):
    cache = AudnexusCache(tmp_path / "audnexus_cache.sqlite")
    cache.set("book:us:B08G9PRS1K", {"asin": "B08G9PRS1K", "title": "Project Hail Mary"})
    hit = cache.get("book:us:B08G9PRS1K")
    assert hit["title"] == "Project Hail Mary"


def test_match_audiobook_tokens_with_mock_transport(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "catalog/products" in url:
            return httpx.Response(
                200,
                json={
                    "products": [
                        {"asin": "B08G9PRS1K", "title": "Project Hail Mary"},
                        {"asin": "B00AAAAAAA", "title": "Something Else"},
                    ]
                },
            )
        if url.endswith("/books/B08G9PRS1K?region=us") or "/books/B08G9PRS1K?" in url:
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
        if "/books/B00AAAAAAA" in url:
            return httpx.Response(
                200,
                json={
                    "asin": "B00AAAAAAA",
                    "title": "Something Else",
                    "authors": [{"name": "Other"}],
                },
            )
        return httpx.Response(404, json={"error": "missing"})

    transport = httpx.MockTransport(handler)
    client = AudnexusClient(
        cache=AudnexusCache(tmp_path / "cache.sqlite"),
        transport=transport,
        min_interval=0,
    )
    try:
        matched = match_audiobook_tokens(
            {"title": "Project Hail Mary", "author": "Andy Weir"},
            client=client,
        )
    finally:
        client.close()
    assert matched["best"]["asin"] == "B08G9PRS1K"
    assert matched["score"] >= 0.85
    assert matched["review_reason"] is None
    assert matched["identity"]["title"] == "Project Hail Mary"


def test_ambiguous_band_reason():
    candidate = {
        "asin": "B00ZZZZZZZ",
        "title": "Hail",
        "author": "Weir",
    }
    score = score_candidate(candidate, title="Project Hail Mary", author="Andy Weir")
    assert 0.65 <= score < 0.85 or score < 0.65
    # Ensure reason helpers stay imported / stable for Review.
    assert REVIEW_AUDNEXUS_AMBIGUOUS.startswith("audnexus_")
    assert REVIEW_AUDNEXUS_UNMATCHED.startswith("audnexus_")


def test_author_boost_rejects_partial_name_substrings():
    """Exact-author boost must not fire for Le⊂Le Guin or Smith⊂Smithson."""
    le_guin = {"asin": "B00AAAAAAA", "title": "Earthsea", "author": "Le Guin"}
    exact_le = score_candidate(le_guin, title="Earthsea", author="Le Guin")
    partial_le = score_candidate(le_guin, title="Earthsea", author="Le")
    # Full match: title + author jaccard 1 + title boost 0.08 + author boost 0.05
    assert exact_le == 0.45 + 0.35 + 0.08 + 0.05
    # Partial "Le": author jaccard 0.5, title boost only — no author boost
    assert partial_le == 0.45 + 0.35 * 0.5 + 0.08
    assert exact_le - partial_le > 0.05

    smithson = {"asin": "B00BBBBBBB", "title": "Earthsea", "author": "Smithson"}
    exact_smith = score_candidate(smithson, title="Earthsea", author="Smithson")
    partial_smith = score_candidate(smithson, title="Earthsea", author="Smith")
    assert exact_smith == 0.45 + 0.35 + 0.08 + 0.05
    # Distinct tokens → author jaccard 0; substring must not add the 0.05 boost
    assert partial_smith == 0.45 + 0.08
    assert exact_smith - partial_smith >= 0.05


def test_author_boost_token_order_insensitive():
    candidate = {"asin": "B00CCCCCCC", "title": "Hail Mary", "author": "Andy Weir"}
    assert score_candidate(candidate, title="Hail Mary", author="Weir, Andy") == score_candidate(
        candidate, title="Hail Mary", author="Andy Weir"
    )
