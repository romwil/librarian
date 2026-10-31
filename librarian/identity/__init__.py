"""Canonical work identity helpers.

This package is deliberately small: callers supply their candidate metadata and
the catalog database, and the resolver returns an existing canonical work id
only when the evidence is strong enough.
"""

from librarian.identity.match import duplicate_groups
from librarian.identity.resolve import resolve_work
from librarian.identity.titles import strip_calibre_suffix

__all__ = ["duplicate_groups", "resolve_work", "strip_calibre_suffix"]
