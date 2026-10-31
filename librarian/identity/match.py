"""One catalog identity matcher (ARCH-021).

Groups works that are the same title so duplicate-merge and cleanup share a
definition. Evidence order matches ``resolve_work``: identifiers, file hashes,
then normalized title/author (Calibre numeric suffixes already stripped by
``title_match_key``).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, List, Sequence, Tuple

from librarian.identity.authors import author_match_key
from librarian.identity.isbn import canonical_isbn13
from librarian.identity.titles import strip_calibre_suffix, title_match_key

IDENTIFIER_SCHEMES = frozenset({"isbn13", "asin", "ol_work", "hardcover"})


def _rows(db: Any, sql: str, args: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with db._connect() as conn:
        return [dict(row) for row in conn.execute(sql, tuple(args)).fetchall()]


def _coalesce(groups: List[List[str]]) -> List[List[str]]:
    automatic = [sorted(group) for group in groups if len(group) > 1]
    changed = True
    while changed:
        changed = False
        for left in automatic[:]:
            for right in automatic[:]:
                if left is not right and set(left) & set(right):
                    automatic.remove(left)
                    automatic.remove(right)
                    automatic.append(sorted(set(left) | set(right)))
                    changed = True
                    break
            if changed:
                break
    return automatic


def duplicate_groups(db: Any) -> Tuple[List[List[str]], List[List[str]]]:
    """Return ``(automatic_merge_groups, possible_duplicate_groups)``.

    Automatic groups share an identifier or file hash, or share a normalized
    title/author with more than one distinct ISBN (editions of one work).
    Title-and-author-only clusters stay in ``possible`` so an owner can look.
    """
    works = _rows(
        db,
        "SELECT id, kind, title, author, isbn, publisher FROM works ORDER BY created_at, id",
    )
    links: dict[str, set[str]] = defaultdict(set)
    for row in _rows(db, "SELECT scheme, value, work_id FROM work_identifiers"):
        if row["scheme"] in IDENTIFIER_SCHEMES:
            links[f"id:{row['scheme']}:{row['value']}"].add(row["work_id"])
    for work in works:
        isbn13 = canonical_isbn13(work.get("isbn"))
        if isbn13:
            links[f"id:isbn13:{isbn13}"].add(work["id"])
    for row in _rows(
        db, "SELECT work_id, sha256 FROM files WHERE sha256 IS NOT NULL AND sha256 != ''"
    ):
        links[f"hash:{row['sha256']}"].add(row["work_id"])
    automatic = _coalesce([sorted(value) for value in links.values() if len(value) > 1])
    auto_ids = {item for group in automatic for item in group}
    normalized: dict[tuple[str, str], list[str]] = defaultdict(list)
    for work in works:
        key = (title_match_key(work["title"]), author_match_key(work["author"], db))
        if all(key):
            normalized[key].append(work["id"])
    possible: list[list[str]] = []
    for ids in normalized.values():
        if len(ids) <= 1 or set(ids) <= auto_ids:
            continue
        matched = [work for work in works if work["id"] in ids]
        known = [work["id"] for work in matched if canonical_isbn13(work.get("isbn"))]
        isbns = {
            canonical_isbn13(work.get("isbn"))
            for work in matched
            if canonical_isbn13(work.get("isbn"))
        }
        if len(known) > 1 and len(isbns) > 1:
            automatic.append(sorted(known))
            auto_ids.update(known)
        if len(known) != len(ids):
            possible.append(ids)
        elif len(known) <= 1:
            possible.append(ids)
    return automatic, possible


def calibre_suffixed_titles(db: Any) -> list[dict[str, str]]:
    """Works whose stored title still carries a ``(11630)``-style Calibre id."""
    rows = []
    for work in _rows(db, "SELECT id, title FROM works ORDER BY title, id"):
        title = str(work.get("title") or "")
        stripped = strip_calibre_suffix(title)
        if stripped and stripped != title.strip():
            rows.append(
                {
                    "id": str(work["id"]),
                    "title": title,
                    "stripped": stripped,
                }
            )
    return rows


def sample_groups(groups: Sequence[Sequence[str]], *, limit: int = 5) -> list[list[str]]:
    return [list(group) for group in list(groups)[: max(0, int(limit))]]
