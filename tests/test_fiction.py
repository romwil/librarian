"""Genre classifier for automatic audiobook wants. No database."""

from __future__ import annotations

from librarian.fiction import classify_genre


def test_classify_fiction_subjects():
    assert classify_genre("Fiction") == "fiction"
    assert classify_genre("Science Fiction, Fantasy") == "fiction"
    assert classify_genre("science-fiction") == "fiction"
    assert classify_genre("Juvenile fiction") == "fiction"
    assert classify_genre("Literary fiction") == "fiction"
    assert classify_genre("Short stories") == "fiction"
    assert classify_genre("Mystery, Thriller, Horror, Romance") == "fiction"
    assert classify_genre("A novel") == "fiction"


def test_classify_nonfiction_wins_over_fiction():
    assert classify_genre("Biography") == "nonfiction"
    assert classify_genre("non-fiction") == "nonfiction"
    assert classify_genre("Nonfiction") == "nonfiction"
    assert classify_genre("non fiction") == "nonfiction"
    assert classify_genre("History, Fiction") == "nonfiction"
    assert classify_genre("Science Fiction, True Crime") == "nonfiction"
    assert classify_genre("Science") == "nonfiction"
    assert classify_genre("Popular Science") == "nonfiction"
    assert classify_genre("Self-help") == "nonfiction"
    assert classify_genre("Cooking, Mystery") == "nonfiction"
    assert classify_genre("Reference") == "nonfiction"
    assert classify_genre("Business") == "nonfiction"
    assert classify_genre("Religion") == "nonfiction"


def test_classify_science_fiction_is_not_science():
    assert classify_genre("Science Fiction") == "fiction"
    assert classify_genre("Science Fiction, Science") == "nonfiction"


def test_classify_empty_and_ambiguous_are_unknown():
    assert classify_genre(None) == "unknown"
    assert classify_genre("") == "unknown"
    assert classify_genre("   ") == "unknown"
    assert classify_genre("Poetry") == "unknown"
    assert classify_genre("Computing") == "unknown"
    assert classify_genre("-genre") == "unknown"
