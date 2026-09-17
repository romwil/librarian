"""Value-based tests for newznab_cat_to_kind."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from librarian.indexers.kind_map import newznab_cat_to_kind
from librarian.kinds import kind_from_newznab

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "nzbfinder"

EXACT_KINDS = {
    7030: "comic",
    7010: "magazine",
    7000: "book",
    7020: "book",
    7040: "book",
    7060: "book",
    7099: "book",
    3030: "audiobook",
    3000: "music",
    3010: "music",
    3040: "music",
    3999: "music",
    2000: "movie",
    2010: "movie",
    2040: "movie",
    2999: "movie",
    5000: "tv",
    5010: "tv",
    5040: "tv",
    5999: "tv",
    6000: "xxx",
    6010: "xxx",
    6040: "xxx",
    6999: "xxx",
}

UNKNOWN = (
    1,
    10,
    1000,
    3020,
    3060,
    7999,
    8000,
)


@pytest.mark.parametrize("cat, kind", sorted(EXACT_KINDS.items()))
def test_exact_kinds(cat: int, kind: str) -> None:
    assert newznab_cat_to_kind(cat) == kind


@pytest.mark.parametrize("cat", (2000, 5000, 6000, 2040, 5040, 6030))
def test_hall_identify_refuses_extras_without_flag(cat: int) -> None:
    """Display map has movie/tv/xxx; Hall path keeps extra=False → None."""
    assert kind_from_newznab(cat) is None
    assert kind_from_newznab(cat, extra=False) is None


@pytest.mark.parametrize(
    "cat, kind",
    [(2000, "movie"), (2040, "movie"), (5000, "tv"), (5040, "tv"), (6000, "xxx"), (6030, "xxx")],
)
def test_find_display_maps_extras(cat: int, kind: str) -> None:
    assert kind_from_newznab(cat, extra=True) == kind
    assert newznab_cat_to_kind(cat) == kind


@pytest.mark.parametrize("cat", UNKNOWN)
def test_unknown_categories_are_none(cat: int) -> None:
    assert newznab_cat_to_kind(cat) is None


def test_books_linux_fixture_is_book() -> None:
    payload = json.loads((FIXTURES / "books-linux.json").read_text())
    cats = [item["category"] for item in payload["results"]]
    assert cats == [7040, 7040]
    assert [newznab_cat_to_kind(cat) for cat in cats] == ["book", "book"]


def test_search_magazine_fixture_is_magazine() -> None:
    payload = json.loads((FIXTURES / "search-magazine.json").read_text())
    assert payload["results"][0]["category"] == 7010
    assert newznab_cat_to_kind(7010) == "magazine"


def test_copied_fixtures_have_no_tokens() -> None:
    for path in FIXTURES.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "api_token" not in text
        assert "apikey" not in text
