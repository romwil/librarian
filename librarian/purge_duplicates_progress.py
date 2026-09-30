"""Purge-duplicate Review slips job progress blob for UI polling."""

from __future__ import annotations

from librarian.progress_job import heartbeat_age_seconds, make_job, parse_utc_timestamp

_api = make_job("purge_duplicates")

HEARTBEAT_STALE_S = _api.heartbeat_stale_s
default_progress = _api.default_progress
progress_path = _api.progress_path
read_purge_duplicates_progress = _api.read
write_purge_duplicates_progress = _api.write
patch_purge_duplicates_progress = _api.patch
append_purge_duplicates_log = _api.append_log
begin_purge_duplicates_run = _api.begin
finish_purge_duplicates_run = _api.finish
is_purge_duplicates_running = _api.is_running
is_purge_duplicates_stale = _api.is_stale
PurgeDuplicatesProgressReporter = _api.reporter

__all__ = [
    "HEARTBEAT_STALE_S",
    "PurgeDuplicatesProgressReporter",
    "append_purge_duplicates_log",
    "begin_purge_duplicates_run",
    "default_progress",
    "finish_purge_duplicates_run",
    "heartbeat_age_seconds",
    "is_purge_duplicates_running",
    "is_purge_duplicates_stale",
    "parse_utc_timestamp",
    "patch_purge_duplicates_progress",
    "progress_path",
    "read_purge_duplicates_progress",
    "write_purge_duplicates_progress",
]
