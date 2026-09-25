"""Canonical Review slip reason codes.

Single source of truth for SQLite ``works.review_reason`` values and live
``folder_diagnosis.problem`` codes. Import from here (or re-exported from
``librarian.identify``) — do not invent parallel string literals.
"""

from __future__ import annotations

REVIEW_UNKNOWN = "unknown_identity"
REVIEW_LOW = "low_confidence"
REVIEW_UNEXPECTED = "unexpected_kind"
REVIEW_NO_PAYLOAD = "no_payload"
REVIEW_UNPACK_STUCK = "unpack_stuck"
REVIEW_EXTRA = "extra_files"
REVIEW_CONVERT = "convert_failed"
REVIEW_COLLISION = "collision"
REVIEW_MISSING_FOLDER = "missing_folder"
REVIEW_COMICVINE_AMBIGUOUS = "comicvine_ambiguous"
REVIEW_COMICVINE_UNMATCHED = "comicvine_unmatched"
REVIEW_AUDNEXUS_AMBIGUOUS = "audnexus_ambiguous"
REVIEW_AUDNEXUS_UNMATCHED = "audnexus_unmatched"
REVIEW_QUIET_HOURS = "quiet_hours"

# Alias kept for jobs / ingest comparisons that historically used this name.
UNPACK_STUCK = REVIEW_UNPACK_STUCK

ALL_REVIEW_REASONS = frozenset(
    {
        REVIEW_UNKNOWN,
        REVIEW_LOW,
        REVIEW_UNEXPECTED,
        REVIEW_NO_PAYLOAD,
        REVIEW_UNPACK_STUCK,
        REVIEW_EXTRA,
        REVIEW_CONVERT,
        REVIEW_COLLISION,
        REVIEW_MISSING_FOLDER,
        REVIEW_COMICVINE_AMBIGUOUS,
        REVIEW_COMICVINE_UNMATCHED,
        REVIEW_AUDNEXUS_AMBIGUOUS,
        REVIEW_AUDNEXUS_UNMATCHED,
        REVIEW_QUIET_HOURS,
    }
)

__all__ = [
    "ALL_REVIEW_REASONS",
    "REVIEW_AUDNEXUS_AMBIGUOUS",
    "REVIEW_AUDNEXUS_UNMATCHED",
    "REVIEW_COLLISION",
    "REVIEW_COMICVINE_AMBIGUOUS",
    "REVIEW_COMICVINE_UNMATCHED",
    "REVIEW_CONVERT",
    "REVIEW_EXTRA",
    "REVIEW_LOW",
    "REVIEW_MISSING_FOLDER",
    "REVIEW_NO_PAYLOAD",
    "REVIEW_QUIET_HOURS",
    "REVIEW_UNEXPECTED",
    "REVIEW_UNKNOWN",
    "REVIEW_UNPACK_STUCK",
    "UNPACK_STUCK",
]
