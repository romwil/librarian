from librarian.indexers.query import (
    build_job_payload,
    plan_beyond_search,
    search_ladder,
    strip_secret_query,
)


def _rungs(**fields):
    return [(plan["rung"], plan["query"]) for plan in search_ladder(**fields)]


def test_book_ladder_is_isbn_then_title_then_title_and_author():
    ladder = search_ladder(
        kind="book",
        title="Dune",
        author="Herbert",
        isbn="9780441172719",
        year="1965",
        q="ignored-when-title-set",
    )
    assert [plan["rung"] for plan in ladder] == ["isbn", "title", "title_author"]
    first, second, third = (plan["params"] for plan in ladder)
    assert all(plan["endpoint"] == "books" for plan in ladder)
    assert (first["isbn"], first["title"], first["author"]) == ("9780441172719", "", "")
    assert (second["isbn"], second["title"], second["author"]) == ("", "Dune", "")
    assert (third["isbn"], third["title"], third["author"]) == ("", "Dune", "Herbert")
    assert all(plan["cat"] == "7000" for plan in (first, second, third))
    assert not any("1965" in str(value) for plan in ladder for value in plan["params"].values())


def test_plan_beyond_search_is_the_first_rung_not_every_field():
    plan = plan_beyond_search(kind="book", title="Dune", author="Herbert", isbn="9780441172719")
    assert plan is not None
    assert plan["params"]["isbn"] == "9780441172719"
    assert plan["params"]["title"] == ""
    assert plan["params"]["author"] == ""


def test_fake_isbn_is_skipped_and_title_goes_first():
    assert _rungs(kind="book", title="Dune", author="Herbert", isbn="9780441172710") == [
        ("title", "Dune"),
        ("title_author", "Dune Herbert"),
    ]


def test_magazine_ladder_is_title_then_title_and_issue_date():
    ladder = search_ladder(kind="magazine", q="Linux Magazin", year="2026")
    assert [plan["endpoint"] for plan in ladder] == ["books", "books"]
    assert [plan["params"]["cat"] for plan in ladder] == ["7010", "7010"]
    assert [plan["params"]["title"] for plan in ladder] == ["Linux Magazin", "Linux Magazin 2026"]
    assert all(plan["params"]["isbn"] == "" for plan in ladder)


def test_hero_q_maps_into_book_title():
    plan = plan_beyond_search(kind="book", q="The Left Hand of Darkness")
    assert plan is not None
    assert plan["endpoint"] == "books"
    assert plan["params"]["title"] == "The Left Hand of Darkness"


def test_comic_ladder_is_series_and_issue_then_series():
    ladder = search_ladder(kind="comic", series="Saga", issue="54", isbn="9780441172719", year="2018")
    assert [plan["endpoint"] for plan in ladder] == ["search", "search"]
    assert [plan["params"]["cat"] for plan in ladder] == ["7030", "7030"]
    assert [plan["params"]["query"] for plan in ladder] == ["Saga 54", "Saga"]
    assert all("isbn" not in plan["params"] for plan in ladder)


def test_music_ladder_is_album_then_artist_and_album_never_isbn():
    ladder = search_ladder(
        kind="music",
        artist="Queen",
        album="News of the World",
        year="1977",
        isbn="9780441172719",
        title="Dune",
    )
    assert [plan["params"]["query"] for plan in ladder] == ["News of the World", "Queen News of the World"]
    assert all(plan["params"]["cat"] == "3000" for plan in ladder)
    assert all("isbn" not in plan["params"] for plan in ladder)
    assert ladder[0]["sought"].get("isbn") in ("", None)


def test_audiobook_ladder_uses_search_3030_one_field_at_a_time():
    ladder = search_ladder(
        kind="audiobook", author="Le Guin", title="A Wizard of Earthsea", isbn="9780553383041"
    )
    assert [plan["params"]["query"] for plan in ladder] == [
        "9780553383041",
        "A Wizard of Earthsea",
        "A Wizard of Earthsea Le Guin",
    ]
    assert all(plan["endpoint"] == "search" for plan in ladder)
    assert all(plan["params"]["cat"] == "3030" for plan in ladder)


def test_ladder_never_exceeds_three_calls_and_skips_removed_kinds():
    for kind in ("book", "audiobook", "magazine", "comic", "music", ""):
        assert len(search_ladder(kind=kind, q="x", title="T", author="A", isbn="9780441172719",
                                 series="S", issue="1", artist="R", album="L", year="2020")) <= 3
    assert search_ladder(kind="movie", q="Dune") == []


def test_job_payload_keeps_sought_selected_retrieved_without_tokens():
    payload = build_job_payload(
        sought={"kind": "book", "title": "Dune", "author": "Herbert", "isbn": "9780441172719"},
        selected={
            "guid": "g-dune",
            "title": "Herbert-Dune-1977-ebook-GROUP",
            "download_url": "https://nzbfinder.example/api/v2/download?id=g-dune.nzb&api_token=secret",
            "category": 7020,
            "size": 12,
            "author": "Frank Herbert",
            "isbn": "9780441172719",
            "book_title": "Dune",
        },
    )
    assert payload["sought"]["title"] == "Dune"
    assert payload["selected"]["guid"] == "g-dune"
    assert payload["selected"]["title"] == "Herbert-Dune-1977-ebook-GROUP"
    assert "secret" not in payload["selected"]["download_url"]
    assert payload["retrieved"]["isbn"] == "9780441172719"
    assert payload["retrieved"]["book_title"] == "Dune"
    assert payload["title"] == "Dune"
    assert payload["kind"] == "book"
    assert strip_secret_query("https://x.test/d?api_token=abc&id=1") == "https://x.test/d?id=1"
    assert strip_secret_query("https://drunkenslug.com/rss?t=7020&r=secret&dl=1") == "https://drunkenslug.com/rss?t=7020&dl=1"
