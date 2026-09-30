"""Shell-works purge job progress blob for UI polling."""

from __future__ import annotations

from librarian.progress_job import heartbeat_age_seconds, make_job, parse_utc_timestamp

_api = make_job("purge_shells")

HEARTBEAT_STALE_S = _api.heartbeat_stale_s
default_progress = _api.default_progress
progress_path = _api.progress_path
read_purge_shells_progress = _api.read
write_purge_shells_progress = _api.write
patch_purge_shells_progress = _api.patch
append_purge_shells_log = _api.append_log
begin_purge_shells_run = _api.begin
finish_purge_shells_run = _api.finish
is_purge_shells_running = _api.is_running
is_purge_shells_stale = _api.is_stale
PurgeShellsProgressReporter = _api.reporter

__all__ = [
    "HEARTBEAT_STALE_S",
    "PurgeShellsProgressReporter",
    "append_purge_shells_log",
    "begin_purge_shells_run",
    "default_progress",
    "finish_purge_shells_run",
    "heartbeat_age_seconds",
    "is_purge_shells_running",
    "is_purge_shells_stale",
    "parse_utc_timestamp",
    "patch_purge_shells_progress",
    "progress_path",
    "read_purge_shells_progress",
    "write_purge_shells_progress",
]
