"""Comic+ebook blend split job progress blob for UI polling."""

from __future__ import annotations

from librarian.progress_job import heartbeat_age_seconds, make_job, parse_utc_timestamp

_api = make_job("split_mixed_kinds")

HEARTBEAT_STALE_S = _api.heartbeat_stale_s
default_progress = _api.default_progress
progress_path = _api.progress_path
read_split_mixed_kinds_progress = _api.read
write_split_mixed_kinds_progress = _api.write
patch_split_mixed_kinds_progress = _api.patch
append_split_mixed_kinds_log = _api.append_log
begin_split_mixed_kinds_run = _api.begin
finish_split_mixed_kinds_run = _api.finish
is_split_mixed_kinds_running = _api.is_running
is_split_mixed_kinds_stale = _api.is_stale
SplitMixedKindsProgressReporter = _api.reporter

__all__ = [
    "HEARTBEAT_STALE_S",
    "SplitMixedKindsProgressReporter",
    "append_split_mixed_kinds_log",
    "begin_split_mixed_kinds_run",
    "default_progress",
    "finish_split_mixed_kinds_run",
    "heartbeat_age_seconds",
    "is_split_mixed_kinds_running",
    "is_split_mixed_kinds_stale",
    "parse_utc_timestamp",
    "patch_split_mixed_kinds_progress",
    "progress_path",
    "read_split_mixed_kinds_progress",
    "write_split_mixed_kinds_progress",
]
