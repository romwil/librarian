"""Canonical work identity helpers.

This package is deliberately small: callers supply their candidate metadata and
the catalog database, and the resolver returns an existing canonical work id
only when the evidence is strong enough.
"""

from librarian.identity.resolve import resolve_work

__all__ = ["resolve_work"]
