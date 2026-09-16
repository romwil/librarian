from librarian.db import Database


def test_wal_pragmas(tmp_path):
    db = Database(tmp_path / "librarian.db")
    pragmas = db.pragmas()
    assert pragmas["journal_mode"] == "wal"
    assert pragmas["busy_timeout"] == 30000
    assert pragmas["synchronous"] == 1


def test_fts_exact_titles(tmp_path):
    db = Database(tmp_path / "librarian.db")
    db.upsert_work({"kind": "book", "title": "Dune", "author": "Herbert", "genre": "sf"})
    db.upsert_work({"kind": "book", "title": "Kindred", "author": "Butler", "genre": "sf"})
    hits = db.search_works("Dune")
    assert [row["title"] for row in hits] == ["Dune"]
    empty = db.search_works("zzz-no-such")
    assert empty == []
    db.upsert_work({"kind": "music", "title": "Dune Soundtrack", "author": "Zimmer", "music_state": "incoming"})
    assert [row["kind"] for row in db.search_works("Dune", kind="music")] == ["music"]
    assert [row["title"] for row in db.search_works("Dune", kind="book")] == ["Dune"]


def test_favorites_are_user_scoped(tmp_path):
    db = Database(tmp_path / "librarian.db")
    owner = db.create_local_user(
        user_id="local-owner",
        display_name="owner",
        password_hash="x$y",
        role="owner",
    )
    reader = db.create_local_user(
        user_id="local-reader",
        display_name="reader",
        password_hash="x$y",
        role="reader",
    )
    work = db.upsert_work({"kind": "comic", "title": "Saga #1", "series_name": "Saga", "series_index": "1"})
    assert db.toggle_favorite(owner["id"], work["id"]) is True
    assert db.is_favorite(owner["id"], work["id"]) is True
    assert db.add_favorite(owner["id"], work["id"]) is False
    assert db.is_favorite(reader["id"], work["id"]) is False
    assert [row["title"] for row in db.favorite_works(owner["id"])] == ["Saga #1"]
    assert db.favorite_works(reader["id"]) == []
