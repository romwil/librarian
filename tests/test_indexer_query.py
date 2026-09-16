from librarian.indexers.query import build_job_payload, plan_beyond_search, strip_secret_query


def test_books_plan_uses_title_author_isbn_and_cat():
    plan = plan_beyond_search(
        kind="book",
        title="Dune",
        author="Herbert",
        isbn="9780441172719",
        q="ignored-when-title-set",
    )
    assert plan is not None
    assert plan["endpoint"] == "books"
    assert plan["params"]["title"] == "Dune"
    assert plan["params"]["author"] == "Herbert"
    assert plan["params"]["isbn"] == "9780441172719"
    assert plan["params"]["cat"] == "7000"


def test_magazine_plan_uses_books_and_7010():
    plan = plan_beyond_search(kind="magazine", q="Linux Magazin", year="2026")
    assert plan is not None
    assert plan["endpoint"] == "books"
    assert plan["params"]["cat"] == "7010"
    assert plan["params"]["title"] == "Linux Magazin 2026"
    assert plan["params"]["isbn"] == ""


def test_hero_q_maps_into_book_title():
    plan = plan_beyond_search(kind="book", q="The Left Hand of Darkness")
    assert plan is not None
    assert plan["endpoint"] == "books"
    assert plan["params"]["title"] == "The Left Hand of Darkness"


def test_comics_plan_stays_on_search_7030():
    plan = plan_beyond_search(kind="comic", series="Saga", issue="54", isbn="9780441172719")
    assert plan is not None
    assert plan["endpoint"] == "search"
    assert plan["params"]["cat"] == "7030"
    assert plan["params"]["query"] == "Saga 54"
    assert "isbn" not in plan["params"]


def test_music_plan_never_uses_books_or_isbn():
    plan = plan_beyond_search(
        kind="music",
        artist="Queen",
        album="News of the World",
        year="1977",
        isbn="9780441172719",
        title="Dune",
    )
    assert plan is not None
    assert plan["endpoint"] == "search"
    assert plan["params"]["cat"] == "3000"
    assert plan["params"]["query"] == "Queen News of the World 1977"
    assert "isbn" not in plan["params"]
    assert plan["sought"].get("isbn") in ("", None)


def test_audiobook_plan_uses_search_3030():
    plan = plan_beyond_search(kind="audiobook", author="Le Guin", title="A Wizard of Earthsea", isbn="9780553383041")
    assert plan is not None
    assert plan["endpoint"] == "search"
    assert plan["params"]["cat"] == "3030"
    assert plan["params"]["query"] == "Le Guin A Wizard of Earthsea 9780553383041"


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
