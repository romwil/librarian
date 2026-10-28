"""ISBN normalization for canonical work identity."""

from __future__ import annotations

from librarian.naming.isbn import isbn10_to_isbn13, validated_isbn


def canonical_isbn13(value: object) -> str:
    """Return a checksum-valid ISBN-13, converting valid ISBN-10 values."""
    isbn = validated_isbn(str(value or ""))
    if len(isbn) == 13:
        return isbn
    if len(isbn) == 10:
        return isbn10_to_isbn13(isbn)
    return ""


def is_valid_isbn13(value: object) -> bool:
    """Whether *value* is already a checksum-valid ISBN-13."""
    isbn = validated_isbn(str(value or ""))
    return len(isbn) == 13 and isbn == str(value or "").replace("-", "").replace(" ", "")


__all__ = ["canonical_isbn13", "is_valid_isbn13"]
