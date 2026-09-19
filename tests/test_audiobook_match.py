"""Book → audiobook companion matching."""

from librarian.audiobook_match import (
    audiobook_find_fields,
    companion_audiobook_payload,
    match_companion_audiobook,
)


def test_match_by_isbn_prefers_audiobook_with_same_isbn():
    book = {"kind": "book", "title": "Dune", "author": "Frank Herbert", "isbn": "9780441172719"}
    audiobooks = [
        {"id": "a1", "kind": "audiobook", "title": "Other", "author": "X", "isbn": "9780316580489"},
        {"id": "a2", "kind": "audiobook", "title": "Dune", "author": "Frank Herbert", "isbn": "0441172717"},
    ]
    hit = match_companion_audiobook(book, audiobooks)
    assert hit and hit["id"] == "a2"


def test_match_by_title_author_when_no_isbn():
    book = {"kind": "book", "title": "Dune", "author": "Frank Herbert", "isbn": ""}
    audiobooks = [
        {"id": "a1", "kind": "audiobook", "title": "Dune", "author": "Someone Else", "isbn": ""},
        {"id": "a2", "kind": "audiobook", "title": "Dune", "author": "Frank Herbert", "isbn": ""},
    ]
    hit = match_companion_audiobook(book, audiobooks)
    assert hit and hit["id"] == "a2"


def test_match_by_series_index():
    book = {
        "kind": "book",
        "title": "Dune Messiah",
        "author": "Frank Herbert",
        "isbn": "",
        "series_name": "Dune",
        "series_index": "2",
    }
    audiobooks = [
        {
            "id": "a1",
            "kind": "audiobook",
            "title": "Dune",
            "author": "Frank Herbert",
            "series_name": "Dune",
            "series_index": "1",
        },
        {
            "id": "a2",
            "kind": "audiobook",
            "title": "Dune Messiah (Unabridged)",
            "author": "Frank Herbert",
            "series_name": "Dune",
            "series_index": "2.0",
        },
    ]
    hit = match_companion_audiobook(book, audiobooks)
    assert hit and hit["id"] == "a2"


def test_title_only_does_not_match():
    book = {"kind": "book", "title": "Dune", "author": "", "isbn": ""}
    audiobooks = [{"id": "a1", "kind": "audiobook", "title": "Dune", "author": "Frank Herbert"}]
    assert match_companion_audiobook(book, audiobooks) is None


def test_non_book_not_applicable():
    payload = companion_audiobook_payload(
        {"kind": "magazine", "title": "Wired"},
        audiobooks=[{"id": "a1", "kind": "audiobook", "title": "Wired"}],
    )
    assert payload["applicable"] is False
    assert payload["shelved"] is None


def test_payload_find_prefill_and_shelved():
    book = {"kind": "book", "title": "Dune", "author": "Frank Herbert", "isbn": "9780441172719"}
    audiobooks = [
        {
            "id": "a2",
            "kind": "audiobook",
            "title": "Dune",
            "author": "Frank Herbert",
            "isbn": "9780441172719",
            "cover_path": "/tmp/cover.jpg",
        }
    ]
    payload = companion_audiobook_payload(book, audiobooks=audiobooks)
    assert payload["applicable"] is True
    assert payload["shelved"]["id"] == "a2"
    assert payload["shelved"]["has_cover"] is True
    assert payload["find"]["kind"] == "audiobook"
    assert payload["find"]["title"] == "Dune"
    assert payload["find"]["isbn"] == "9780441172719"
    fields = audiobook_find_fields(book)
    assert fields["kind"] == "audiobook"
    assert "Dune" in fields["q"]
