"""Compatibility shim — audiobook token rules live in ``librarian.naming.audiobook``."""

from __future__ import annotations

from librarian.naming.audiobook import (
    AudiobookTokens,
    extract_asin,
    normalize_audiobook_name,
    tokens_for_identity,
)

__all__ = ["AudiobookTokens", "extract_asin", "normalize_audiobook_name", "tokens_for_identity"]
