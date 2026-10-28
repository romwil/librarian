"""ISBN extraction and ISBN-10/13 conversion. Never invents a number from a title."""

from __future__ import annotations

import re
from typing import List

ISBN_PATTERN = re.compile(r"\b(?:97[89][-\s]?)?(?:\d[-\s]?){9}[\dXx]\b")


def extract_isbn(text: str) -> str:
    match = ISBN_PATTERN.search(text or "")
    if not match:
        return ""
    digits = re.sub(r"[^0-9Xx]", "", match.group(0))
    return digits.upper()


def _isbn13_check_digit(core12: str) -> str:
    total = sum(int(digit) * (1 if index % 2 == 0 else 3) for index, digit in enumerate(core12))
    return str((10 - (total % 10)) % 10)


def _isbn10_check_digit(core9: str) -> str:
    total = sum(int(digit) * (10 - index) for index, digit in enumerate(core9))
    remainder = (11 - (total % 11)) % 11
    return "X" if remainder == 10 else str(remainder)


def isbn10_to_isbn13(isbn: str) -> str:
    digits = re.sub(r"[^0-9Xx]", "", isbn or "").upper()
    if len(digits) == 13 and digits.startswith(("978", "979")):
        return digits
    if len(digits) != 10:
        return ""
    body = "978" + digits[:9]
    return body + _isbn13_check_digit(body)


def isbn13_to_isbn10(isbn: str) -> str:
    digits = re.sub(r"[^0-9Xx]", "", isbn or "").upper()
    if len(digits) != 13 or not digits.startswith("978"):
        return ""
    core = digits[3:12]
    return core + _isbn10_check_digit(core)


def isbn_match_keys(*values: str) -> List[str]:
    """ISBN-10 and ISBN-13 forms for matching. Never invents a number from a title."""
    keys: List[str] = []
    seen: set[str] = set()
    for value in values:
        digits = extract_isbn(str(value or ""))
        for candidate in (digits, isbn10_to_isbn13(digits), isbn13_to_isbn10(digits)):
            if candidate and candidate not in seen:
                seen.add(candidate)
                keys.append(candidate)
    return keys


def validated_isbn(raw: str) -> str:
    """Return a check-digit-valid ISBN-10/13, else empty. Never invents digits."""
    digits = extract_isbn(raw or "")
    if not digits:
        return ""
    if len(digits) == 13 and digits.isdigit():
        if digits[-1] == _isbn13_check_digit(digits[:12]):
            return digits
        return ""
    if len(digits) == 10:
        core = digits[:9]
        if not core.isdigit():
            return ""
        if digits[-1].upper() == _isbn10_check_digit(core):
            return digits.upper()
        return ""
    return ""
