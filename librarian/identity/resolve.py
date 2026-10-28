"""Single canonical-work resolver used before creating catalog rows."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any, Optional

from librarian.identity.authors import author_match_key
from librarian.identity.isbn import canonical_isbn13
from librarian.identity.titles import title_match_key

_IDENTIFIER_FIELDS = {
    "isbn13": ("isbn13", "isbn"),
    "asin": ("asin",),
    "ol_work": ("ol_work", "openlibrary_work", "open_library_work"),
    "hardcover": ("hardcover", "hardcover_id"),
}


def kind_family(value: object) -> str:
    """Books and audiobooks have one work family; other kinds remain distinct."""
    kind = str(value or "").strip().lower()
    return "book" if kind in {"book", "audiobook"} else kind


def _identifier_values(candidate: Mapping[str, Any]) -> Sequence[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    identifiers = candidate.get("identifiers")
    extra = identifiers if isinstance(identifiers, Mapping) else {}
    for scheme, fields in _IDENTIFIER_FIELDS.items():
        value = next(
            (
                candidate.get(field) or extra.get(field)
                for field in fields
                if candidate.get(field) or extra.get(field)
            ),
            "",
        )
        if scheme == "isbn13":
            value = canonical_isbn13(value)
        else:
            value = str(value or "").strip()
        if value:
            values.append((scheme, value))
    return values


def _sha256_values(candidate: Mapping[str, Any]) -> Sequence[str]:
    values: list[str] = []
    for key in ("sha256", "file_sha256"):
        value = str(candidate.get(key) or "").strip().lower()
        if value:
            values.append(value)
    raw_many = candidate.get("sha256s") or candidate.get("file_sha256s") or ()
    if isinstance(raw_many, str):
        raw_many = (raw_many,)
    if isinstance(raw_many, Sequence):
        values.extend(str(value or "").strip().lower() for value in raw_many)
    return tuple(dict.fromkeys(value for value in values if value))


def _normalized_matches(db: Any, candidate: Mapping[str, Any]) -> list[str]:
    title = title_match_key(candidate.get("title"))
    author = author_match_key(candidate.get("author"), db)
    family = kind_family(candidate.get("kind"))
    if not title or not author or not family:
        return []
    with db._connect() as conn:
        if family == "book":
            rows = conn.execute(
                "SELECT id, kind, title, author FROM works WHERE kind IN (?, ?)",
                ("book", "audiobook"),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, kind, title, author FROM works WHERE kind = ?",
                (family,),
            ).fetchall()
    matches = []
    for row in rows:
        row_family = kind_family(row["kind"])
        if row_family != family or title_match_key(row["title"]) != title:
            continue
        row_author = str(row["author"] or "")
        if author_match_key(row_author, db) == author:
            matches.append(str(row["id"]))
    return list(dict.fromkeys(matches))


def resolve_work(db: Any, candidate: MutableMapping[str, Any]) -> Optional[str]:
    """Resolve an existing canonical work in evidence order.

    1. Canonical identifiers, 2. file hashes, 3. normalized title/author/kind.
    Only a unique step-three result is returned, and it annotates the mutable
    candidate with ``match_confidence='normalized'``.
    """
    for scheme, value in _identifier_values(candidate):
        work = db.get_work_by_identifier(scheme=scheme, value=value)
        if work:
            return str(work["id"])

    for digest in _sha256_values(candidate):
        file_row = db.get_file_by_sha256(digest)
        if file_row and file_row.get("work_id"):
            return str(file_row["work_id"])

    matches = _normalized_matches(db, candidate)
    if len(matches) == 1:
        candidate["match_confidence"] = "normalized"
        return matches[0]
    return None


__all__ = ["kind_family", "resolve_work"]
