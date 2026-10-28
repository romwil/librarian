"""Processed New & noted rows use SQLite, never a test-only cache."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta

import httpx
import pytest

from librarian.config import Settings
from librarian.db import Database
from librarian.lists import clear_lists_memory_cache
from librarian.llm import reset_llm_rate_limit_state
from librarian.noted import (
    HOUSEHOLD_CACHE_SOURCE,
    HOUSEHOLD_ORIGIN_LABEL,
    MISSING_NYT_AND_MODEL,
    NYT_CACHE_SOURCE,
    _cache_rows,
    _cache_upsert,
    _stored_week_dates,
    add_missing_noted_history,
    cached_noted_desk,
    noted_history,
    refresh_nyt_list,
)
from librarian.nyt_books import clear_nyt_memory_cache


def _nyt_transport(calls: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "results": {
                    "published_date": request.url.path.split("/")[-2],
                    "display_name": "Hardcover Fiction",
                    "books": [
                        {
                            "title": "Cached Book",
                            "author": "A. Reader",
                            "primary_isbn13": "9780441172719",
                            "rank": 1,
                        }
                    ],
                }
            },
        )

    return httpx.MockTransport(handler)


def test_dated_nyt_cache_hit_does_not_refetch(tmp_path):
    db = Database(tmp_path / "library.db")
    calls: list[str] = []
    settings = Settings(nyt_books_api_key="test-key")
    try:
        assert refresh_nyt_list(
            db,
            settings,
            list_name="hardcover-fiction",
            published_date="2026-01-04",
            data_dir=tmp_path,
            transport=_nyt_transport(calls),
        ) == 1
        assert refresh_nyt_list(
            db,
            settings,
            list_name="hardcover-fiction",
            published_date="2026-01-04",
            data_dir=tmp_path,
            transport=_nyt_transport(calls),
        ) == 0
    finally:
        db.close()
    assert calls == ["/svc/books/v3/lists/2026-01-04/hardcover-fiction.json"]


def test_cached_noted_desk_returns_latest_nyt_cache_without_refreshing_every_lane(tmp_path, monkeypatch):
    db = Database(tmp_path / "library.db")
    try:
        _cache_upsert(
            db,
            {
                "source": "nyt",
                "source_key": "9780441172719",
                "isbn13": "9780441172719",
                "title": "Current NYT Book",
                "author": "A. Reader",
                "list_name": "hardcover-fiction",
                "published_date": "2026-10-25",
            },
        )
        _cache_upsert(
            db,
            {
                "source": "nyt",
                "source_key": "9780061120084",
                "isbn13": "9780061120084",
                "title": "Older NYT Book",
                "author": "A. Reader",
                "list_name": "hardcover-fiction",
                "published_date": "2026-10-18",
            },
        )
        monkeypatch.setattr(
            "librarian.noted.run_noted_refresh",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cold refresh")),
        )
        desk = cached_noted_desk(db, Settings(nyt_books_api_key="test-key"), data_dir=tmp_path)
    finally:
        db.close()

    lane = next(row for row in desk["lanes"] if row["id"] == "nyt-hardcover-fiction")
    assert [row["title"] for row in lane["items"]] == ["Current NYT Book"]
    assert lane["empty_copy"] == ""


def test_cached_noted_desk_marks_a_shelved_title(tmp_path):
    db = Database(tmp_path / "library.db")
    try:
        work = db.upsert_work(
            {"id": "owned", "kind": "book", "title": "Atomic Habits", "author": "James Clear", "isbn": ""}
        )
        db.add_file(
            {
                "work_id": work["id"],
                "path": str(tmp_path / "owned.epub"),
                "filename": "owned.epub",
                "kind": "book",
                "size": 1,
            }
        )
        _cache_upsert(
            db,
            {
                "source": "open_library",
                "source_key": "OL1W",
                "title": "Atomic Habits",
                "author": "James Clear",
                "list_name": "daily",
                "published_date": "2026-10-28",
            },
        )
        desk = cached_noted_desk(db, Settings(), data_dir=tmp_path)
    finally:
        db.close()

    item = next(row for row in desk["lanes"] if row["id"] == "open-library-daily")["items"][0]
    assert item["shelved"]["id"] == "owned"
    assert item["wanted"]["kinds"] == ["audiobook"]


def test_cached_noted_desk_reports_missing_nyt_key_without_network_work(tmp_path):
    db = Database(tmp_path / "library.db")
    try:
        desk = cached_noted_desk(db, Settings(), data_dir=tmp_path)
    finally:
        db.close()

    lane = next(row for row in desk["lanes"] if row["id"] == "nyt-hardcover-fiction")
    assert lane["items"] == []
    assert lane["empty_copy"] == MISSING_NYT_AND_MODEL
    assert lane["origin_label"] == ""


def test_noted_history_explains_when_nyt_key_is_missing(tmp_path):
    db = Database(tmp_path / "library.db")
    try:
        with pytest.raises(ValueError, match=MISSING_NYT_AND_MODEL):
            noted_history(
                db,
                Settings(),
                list_name="hardcover-fiction",
                start="2026-10-01",
                end="2026-10-28",
                data_dir=tmp_path,
            )
    finally:
        db.close()


def test_noted_history_marks_a_shelved_title_matched(tmp_path, monkeypatch):
    db = Database(tmp_path / "library.db")
    try:
        work = db.upsert_work(
            {"id": "owned", "kind": "book", "title": "Cached Book", "author": "A. Reader", "isbn": "9780441172719"}
        )
        db.add_file(
            {
                "work_id": work["id"],
                "path": str(tmp_path / "owned.epub"),
                "filename": "owned.epub",
                "kind": "book",
                "size": 1,
            }
        )
        _cache_upsert(
            db,
            {
                "source": "nyt",
                "source_key": "9780441172719",
                "isbn13": "9780441172719",
                "title": "Cached Book",
                "author": "A. Reader",
                "list_name": "hardcover-fiction",
                "published_date": "2026-10-25",
            },
        )
        monkeypatch.setattr("librarian.noted.refresh_nyt_list", lambda *args, **kwargs: 0)
        history = noted_history(
            db,
            Settings(nyt_books_api_key="test-key"),
            list_name="hardcover-fiction",
            start="2026-10-01",
            end="2026-10-28",
            data_dir=tmp_path,
        )
    finally:
        db.close()
    assert history["items"][0]["status"] == "matched"
    assert history["counts"]["matched"] == 1


def test_six_month_history_dedupes_by_isbn(tmp_path, monkeypatch):
    db = Database(tmp_path / "library.db")
    try:
        for week in ("2026-01-01", "2026-01-08", "2026-01-15"):
            _cache_upsert(
                db,
                {
                    "source": "nyt",
                    "source_key": "9780441172719",
                    "isbn13": "9780441172719",
                    "title": "Cached Book",
                    "author": "A. Reader",
                    "list_name": "hardcover-fiction",
                    "published_date": week,
                },
            )
        monkeypatch.setattr("librarian.noted.refresh_nyt_list", lambda *args, **kwargs: 0)
        history = noted_history(
            db,
            Settings(nyt_books_api_key="test-key"),
            list_name="hardcover-fiction",
            start="2026-01-01",
            end="2026-06-30",
            data_dir=tmp_path,
        )
    finally:
        db.close()
    assert len(history["items"]) == 1
    assert history["items"][0]["weeks"] == ["2026-01-01", "2026-01-08", "2026-01-15"]
    assert history["items"][0]["status"] == "missing"
    assert history["counts"] == {"matched": 0, "wanted": 0, "missing": 1}


def _llm_settings() -> Settings:
    return Settings(
        llm_provider="openai",
        llm_base_url="http://llm.test/v1",
        llm_api_key="test-llm-key",
        llm_model="gpt-test",
    )


def _llm_list_transport(calls: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        body = json.loads(request.content.decode())
        raw = request.content.decode()
        assert "test-llm-key" not in raw
        assert request.headers.get("authorization", "").startswith("Bearer ")
        user = body["messages"][1]["content"]
        assert "2026-10-18" in user
        assert "Hardcover Fiction" in user
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "display_name": "Hardcover Fiction",
                                    "published_date": "2026-10-18",
                                    "books": [
                                        {
                                            "title": "Model Book",
                                            "author": "A. Writer",
                                            "isbn": "9780441172719",
                                            "rank": 1,
                                        },
                                        {
                                            "title": "No Isbn Yet",
                                            "author": "B. Writer",
                                            "isbn": None,
                                            "rank": 2,
                                        },
                                    ],
                                }
                            )
                        }
                    }
                ]
            },
        )

    return httpx.MockTransport(handler)


def test_history_falls_back_to_household_model_without_nyt_key(tmp_path):
    reset_llm_rate_limit_state()
    clear_lists_memory_cache()
    db = Database(tmp_path / "library.db")
    calls: list[str] = []
    try:
        work = db.upsert_work(
            {
                "id": "owned",
                "kind": "book",
                "title": "Shelf Only Title",
                "author": "Shelf Author",
                "isbn": "9780441172719",
            }
        )
        db.add_file(
            {
                "work_id": work["id"],
                "path": str(tmp_path / "owned.epub"),
                "filename": "owned.epub",
                "kind": "book",
                "size": 1,
            }
        )
        history = noted_history(
            db,
            _llm_settings(),
            list_name="hardcover-fiction",
            start="2026-10-18",
            end="2026-10-18",
            data_dir=tmp_path,
            llm_transport=_llm_list_transport(calls),
        )
        stored = _cache_rows(
            db,
            source=HOUSEHOLD_CACHE_SOURCE,
            list_name="hardcover-fiction",
            published_date="2026-10-18",
        )
        again = noted_history(
            db,
            _llm_settings(),
            list_name="hardcover-fiction",
            start="2026-10-18",
            end="2026-10-18",
            data_dir=tmp_path,
            llm_transport=_llm_list_transport(calls),
        )
        added = add_missing_noted_history(db, history["items"])
        wanted = [row["title"] for row in db.list_wanted()]
    finally:
        db.close()

    assert calls == ["/v1/chat/completions"]
    assert len(stored) == 2
    by_title = {row["title"]: row for row in stored}
    assert by_title["Model Book"]["isbn13"] == "9780441172719"
    assert by_title["No Isbn Yet"]["isbn13"] is None
    matched = next(item for item in history["items"] if item["title"] == "Model Book")
    blank = next(item for item in history["items"] if item["title"] == "No Isbn Yet")
    assert matched["status"] == "matched"
    assert blank["status"] == "missing"
    assert not blank.get("isbn13")
    assert history["origin"] == "household"
    assert history["origin_label"] == HOUSEHOLD_ORIGIN_LABEL
    assert "New York Times API" in history["origin_label"]
    assert again["counts"]["matched"] == 1
    assert added == 1
    assert wanted == ["No Isbn Yet"]


def test_nyt_key_does_not_call_the_household_model(tmp_path, monkeypatch):
    db = Database(tmp_path / "library.db")
    calls: list[str] = []

    def boom(*_args, **_kwargs):
        raise AssertionError("household model was called")

    monkeypatch.setattr("librarian.noted.fetch_llm_list", boom)
    monkeypatch.setattr("librarian.noted.client_from_settings", boom)
    try:
        stored = refresh_nyt_list(
            db,
            Settings(nyt_books_api_key="test-key"),
            list_name="hardcover-fiction",
            published_date="2026-10-18",
            data_dir=tmp_path,
            transport=_nyt_transport(calls),
        )
        desk = cached_noted_desk(db, Settings(nyt_books_api_key="test-key"), data_dir=tmp_path)
    finally:
        db.close()

    assert stored == 1
    assert calls == ["/svc/books/v3/lists/2026-10-18/hardcover-fiction.json"]
    lane = next(row for row in desk["lanes"] if row["id"] == "nyt-hardcover-fiction")
    assert lane["origin"] == "nyt"
    assert lane["origin_label"] == ""
    assert [row["title"] for row in lane["items"]] == ["Cached Book"]


def _week_dates(start: str, count: int) -> list[str]:
    day = date.fromisoformat(start)
    return [(day + timedelta(days=7 * offset)).isoformat() for offset in range(count)]


def _range_transport(
    calls: list[str],
    *,
    empty: set[str] | None = None,
    fail_once: set[str] | None = None,
):
    """One list per requested week. The API's published_date is deliberately not that week."""
    skipped = set(empty or ())
    pending_fail = set(fail_once or ())

    def handler(request: httpx.Request) -> httpx.Response:
        week = request.url.path.split("/")[-2]
        calls.append(week)
        if week in pending_fail:
            pending_fail.remove(week)
            return httpx.Response(503, json={"fault": "unavailable"})
        books = []
        if week not in skipped:
            book = {
                "title": f"Listed {week.replace('-', '')}",
                "author": "A. Reader",
                "rank": 1,
            }
            if week.endswith("01-04"):
                book["primary_isbn13"] = "9780441172719"
            books.append(book)
        return httpx.Response(
            200,
            json={
                "results": {
                    "published_date": "1999-12-31",
                    "display_name": "Hardcover Fiction",
                    "books": books,
                }
            },
        )

    return httpx.MockTransport(handler)


def test_date_range_stores_each_week_and_reuses_overlap(tmp_path):
    clear_nyt_memory_cache()
    db = Database(tmp_path / "library.db")
    calls: list[str] = []
    weeks = _week_dates("2026-01-04", 6)
    settings = Settings(nyt_books_api_key="test-key")
    try:
        history = noted_history(
            db,
            settings,
            list_name="hardcover-fiction",
            start=weeks[0],
            end=weeks[-1],
            data_dir=tmp_path,
            transport=_range_transport(calls),
        )
        stored = _stored_week_dates(db, source=NYT_CACHE_SOURCE, list_name="hardcover-fiction")
        with_isbn = _cache_rows(
            db,
            source=NYT_CACHE_SOURCE,
            list_name="hardcover-fiction",
            published_date=weeks[0],
        )
        without_isbn = _cache_rows(
            db,
            source=NYT_CACHE_SOURCE,
            list_name="hardcover-fiction",
            published_date=weeks[1],
        )
        assert refresh_nyt_list(
            db,
            settings,
            list_name="hardcover-fiction",
            published_date=weeks[0],
            data_dir=tmp_path,
            transport=_range_transport(calls),
        ) == 0
        desk = cached_noted_desk(db, settings, data_dir=tmp_path)
        overlap_end = _week_dates(weeks[3], 4)[-1]
        before = len(calls)
        overlap = noted_history(
            db,
            settings,
            list_name="hardcover-fiction",
            start=weeks[3],
            end=overlap_end,
            data_dir=tmp_path,
            transport=_range_transport(calls),
        )
        edge = calls[before:]
        before = len(calls)
        noted_history(
            db,
            settings,
            list_name="hardcover-fiction",
            start=weeks[3],
            end=overlap_end,
            data_dir=tmp_path,
            transport=_range_transport(calls),
        )
        stored_after = _stored_week_dates(db, source=NYT_CACHE_SOURCE, list_name="hardcover-fiction")
    finally:
        db.close()

    assert calls == [*weeks, overlap_end]
    assert stored == set(weeks)
    assert "1999-12-31" not in stored
    assert with_isbn[0]["isbn13"] == "9780441172719"
    assert with_isbn[0]["source"] == NYT_CACHE_SOURCE
    assert without_isbn[0]["isbn13"] is None
    by_title = {item["title"]: item["weeks"] for item in history["items"]}
    assert set(by_title) == {f"Listed {week.replace('-', '')}" for week in weeks}
    assert by_title[f"Listed {weeks[0].replace('-', '')}"] == [weeks[0]]
    lane = next(row for row in desk["lanes"] if row["id"] == "nyt-hardcover-fiction")
    assert [row["title"] for row in lane["items"]] == [f"Listed {weeks[-1].replace('-', '')}"]
    assert lane["origin"] == "nyt"
    assert lane["origin_label"] == ""
    assert edge == [overlap_end]
    assert calls[before:] == []
    titles = {item["title"] for item in overlap["items"]}
    assert f"Listed {weeks[3].replace('-', '')}" in titles
    assert f"Listed {overlap_end.replace('-', '')}" in titles
    assert f"Listed {weeks[0].replace('-', '')}" not in titles
    assert stored_after == set(weeks) | {overlap_end}


def test_empty_published_week_is_not_fetched_again(tmp_path):
    clear_nyt_memory_cache()
    db = Database(tmp_path / "library.db")
    calls: list[str] = []
    try:
        noted_history(
            db,
            Settings(nyt_books_api_key="test-key"),
            list_name="hardcover-fiction",
            start="2026-04-05",
            end="2026-04-05",
            data_dir=tmp_path,
            transport=_range_transport(calls, empty={"2026-04-05"}),
        )
        again = noted_history(
            db,
            Settings(nyt_books_api_key="test-key"),
            list_name="hardcover-fiction",
            start="2026-04-05",
            end="2026-04-05",
            data_dir=tmp_path,
            transport=_range_transport(calls, empty={"2026-04-05"}),
        )
        stored = _stored_week_dates(db, source=NYT_CACHE_SOURCE, list_name="hardcover-fiction")
        visible = _cache_rows(
            db,
            source=NYT_CACHE_SOURCE,
            list_name="hardcover-fiction",
            published_date="2026-04-05",
        )
    finally:
        db.close()

    assert calls == ["2026-04-05"]
    assert stored == {"2026-04-05"}
    assert visible == []
    assert again["items"] == []


def test_failed_week_can_be_fetched_later(tmp_path):
    clear_nyt_memory_cache()
    db = Database(tmp_path / "library.db")
    calls: list[str] = []
    transport = _range_transport(calls, fail_once={"2026-05-03"})
    settings = Settings(nyt_books_api_key="test-key")
    try:
        first = noted_history(
            db,
            settings,
            list_name="hardcover-fiction",
            start="2026-05-03",
            end="2026-05-03",
            data_dir=tmp_path,
            transport=transport,
        )
        missed = _stored_week_dates(db, source=NYT_CACHE_SOURCE, list_name="hardcover-fiction")
        second = noted_history(
            db,
            settings,
            list_name="hardcover-fiction",
            start="2026-05-03",
            end="2026-05-03",
            data_dir=tmp_path,
            transport=transport,
        )
        stored = _stored_week_dates(db, source=NYT_CACHE_SOURCE, list_name="hardcover-fiction")
        noted_history(
            db,
            settings,
            list_name="hardcover-fiction",
            start="2026-05-03",
            end="2026-05-03",
            data_dir=tmp_path,
            transport=transport,
        )
    finally:
        db.close()

    assert calls == ["2026-05-03", "2026-05-03"]
    assert missed == set()
    assert first["items"] == []
    assert stored == {"2026-05-03"}
    assert [item["title"] for item in second["items"]] == ["Listed 20260503"]


def _household_range_transport(calls: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raw = request.content.decode()
        assert "test-llm-key" not in raw
        body = json.loads(raw)
        user = body["messages"][1]["content"]
        found = re.search(r"published on (\d{4}-\d{2}-\d{2})", user)
        week = found.group(1) if found else ""
        calls.append(week)
        books = []
        if week != "2026-03-08":
            book = {"title": f"Household {week.replace('-', '')}", "author": "A. Writer", "rank": 1, "isbn": None}
            if week == "2026-03-01":
                book["isbn"] = "9780441172719"
            books.append(book)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "display_name": "Hardcover Fiction",
                                    "published_date": "1999-12-31",
                                    "books": books,
                                }
                            )
                        }
                    }
                ]
            },
        )

    return httpx.MockTransport(handler)


def test_household_range_reuses_stored_weeks_including_empty(tmp_path, monkeypatch):
    reset_llm_rate_limit_state()
    clear_lists_memory_cache()
    db = Database(tmp_path / "library.db")
    calls: list[str] = []
    monkeypatch.setattr("librarian.noted._fill_missing_household_lists", lambda *_args, **_kwargs: None)
    try:
        history = noted_history(
            db,
            _llm_settings(),
            list_name="hardcover-fiction",
            start="2026-03-01",
            end="2026-03-08",
            data_dir=tmp_path,
            llm_transport=_household_range_transport(calls),
        )
        desk = cached_noted_desk(db, _llm_settings(), data_dir=tmp_path)
        before = len(calls)
        overlap = noted_history(
            db,
            _llm_settings(),
            list_name="hardcover-fiction",
            start="2026-03-01",
            end="2026-03-15",
            data_dir=tmp_path,
            llm_transport=_household_range_transport(calls),
        )
        edge = calls[before:]
        before = len(calls)
        noted_history(
            db,
            _llm_settings(),
            list_name="hardcover-fiction",
            start="2026-03-01",
            end="2026-03-15",
            data_dir=tmp_path,
            llm_transport=_household_range_transport(calls),
        )
        stored = _stored_week_dates(db, source=HOUSEHOLD_CACHE_SOURCE, list_name="hardcover-fiction")
        first = _cache_rows(
            db,
            source=HOUSEHOLD_CACHE_SOURCE,
            list_name="hardcover-fiction",
            published_date="2026-03-01",
        )
        blank = _cache_rows(
            db,
            source=HOUSEHOLD_CACHE_SOURCE,
            list_name="hardcover-fiction",
            published_date="2026-03-15",
        )
    finally:
        db.close()

    assert calls == ["2026-03-01", "2026-03-08", "2026-03-15"]
    assert edge == ["2026-03-15"]
    assert calls[before:] == []
    assert stored == {"2026-03-01", "2026-03-08", "2026-03-15"}
    assert "1999-12-31" not in stored
    assert first[0]["isbn13"] == "9780441172719"
    assert first[0]["source"] == HOUSEHOLD_CACHE_SOURCE
    assert blank[0]["isbn13"] is None
    assert history["origin"] == "household"
    assert history["origin_label"] == HOUSEHOLD_ORIGIN_LABEL
    assert [item["title"] for item in history["items"]] == ["Household 20260301"]
    titles = {item["title"] for item in overlap["items"]}
    assert titles == {"Household 20260301", "Household 20260315"}
    lane = next(row for row in desk["lanes"] if row["id"] == "nyt-hardcover-fiction")
    assert [row["title"] for row in lane["items"]] == ["Household 20260301"]
    assert lane["origin"] == "household"
    assert lane["origin_label"] == HOUSEHOLD_ORIGIN_LABEL


def test_add_missing_skips_shelved_titles(tmp_path):
    db = Database(tmp_path / "library.db")
    try:
        work = db.upsert_work(
            {"id": "owned", "kind": "book", "title": "Owned", "author": "A. Reader", "isbn": "9780441172719"}
        )
        db.add_file(
            {
                "work_id": work["id"],
                "path": str(tmp_path / "owned.epub"),
                "filename": "owned.epub",
                "kind": "book",
                "size": 1,
            }
        )
        added = add_missing_noted_history(
            db,
            [
                {"title": "Owned", "author": "A. Reader", "isbn13": "9780441172719"},
                {"title": "Missing", "author": "A. Reader", "isbn13": "9780061120084"},
            ],
        )
        assert added == 1
        assert [row["title"] for row in db.list_wanted()] == ["Missing"]
    finally:
        db.close()
