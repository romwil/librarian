"""Goodreads CSV / shelf export. Match by ISBN onto Favorites. No OAuth."""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Mapping, Optional

from librarian.db import Database
from librarian.identify import extract_isbn, isbn_match_keys, tidy_title

MAX_GOODREADS_BYTES = 5 * 1024 * 1024


def parse_csv_isbn(raw: str) -> str:
    """Goodreads wraps ISBNs as =\"978...\". Empty quotes are not an ISBN."""
    text = str(raw or "").strip()
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    if text.startswith("="):
        text = text[1:].strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    if text in {"", '""', "=''"}:
        return ""
    return extract_isbn(text)


def _cell(row: Mapping[str, Any], *names: str) -> str:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        if name.lower() in lowered:
            return str(lowered[name.lower()] or "").strip()
    return ""


def parse_goodreads_rows(text: str) -> List[Dict[str, Any]]:
    raw = text.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(raw))
    rows: List[Dict[str, Any]] = []
    for record in reader:
        title = tidy_title(_cell(record, "Title", "Book Title"))
        author = tidy_title(_cell(record, "Author", "Author l-f", "Additional Authors"))
        if author and "," in author and _cell(record, "Author l-f") == author:
            last, first = [part.strip() for part in author.split(",", 1)]
            author = tidy_title(f"{first} {last}")
        isbn13 = parse_csv_isbn(_cell(record, "ISBN13", "ISBN 13"))
        isbn10 = parse_csv_isbn(_cell(record, "ISBN", "ISBN10", "ISBN 10"))
        isbn = isbn13 or isbn10
        year_text = _cell(record, "Original Publication Year", "Year Published")
        year = int(year_text) if year_text.isdigit() else None
        rows.append(
            {
                "title": title,
                "author": author,
                "isbn": isbn,
                "isbn13": isbn13,
                "isbn10": isbn10,
                "year": year,
                "shelf": _cell(record, "Exclusive Shelf", "Bookshelves"),
            }
        )
    return rows


def _match_work(db: Database, row: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    for key in isbn_match_keys(str(row.get("isbn13") or ""), str(row.get("isbn10") or ""), str(row.get("isbn") or "")):
        hit = db.get_work_by_isbn(key)
        if hit:
            return hit
    return None


def import_goodreads_csv(db: Database, user_id: str, text: str) -> Dict[str, int]:
    """Match CSV ISBNs onto existing books, else create thin works that need Find."""
    rows = parse_goodreads_rows(text)
    counts = {"rows": len(rows), "matched": 0, "created": 0, "favorited": 0, "skipped": 0}
    for row in rows:
        isbn = str(row.get("isbn") or "")
        if not isbn:
            counts["skipped"] += 1
            continue
        work = _match_work(db, row)
        if work is None:
            title = str(row.get("title") or "").strip() or f"ISBN {isbn}"
            work = db.upsert_work(
                {
                    "kind": "book",
                    "title": title,
                    "author": row.get("author") or "",
                    "isbn": isbn,
                    "year": row.get("year"),
                    "review_state": "none",
                }
            )
            counts["created"] += 1
        else:
            counts["matched"] += 1
        if db.add_favorite(user_id, str(work["id"])):
            counts["favorited"] += 1
    return counts
