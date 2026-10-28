"""Processed New & noted rows use SQLite, never a test-only cache."""

from __future__ import annotations

import httpx

from librarian.config import Settings
from librarian.db import Database
from librarian.noted import (
    _cache_upsert,
    add_missing_noted_history,
    noted_history,
    refresh_nyt_list,
)


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
