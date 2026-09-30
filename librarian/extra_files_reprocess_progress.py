"""Clear extra-files slips job progress blob for Review UI polling."""

from __future__ import annotations

from librarian.progress_job import heartbeat_age_seconds, make_job, parse_utc_timestamp

_api = make_job("extra_files_reprocess")

HEARTBEAT_STALE_S = _api.heartbeat_stale_s
default_progress = _api.default_progress
progress_path = _api.progress_path
read_extra_files_reprocess_progress = _api.read
write_extra_files_reprocess_progress = _api.write
patch_extra_files_reprocess_progress = _api.patch
append_extra_files_reprocess_log = _api.append_log
begin_extra_files_reprocess_run = _api.begin
finish_extra_files_reprocess_run = _api.finish
is_extra_files_reprocess_running = _api.is_running
is_extra_files_reprocess_stale = _api.is_stale
ExtraFilesReprocessProgressReporter = _api.reporter

__all__ = [
    "HEARTBEAT_STALE_S",
    "ExtraFilesReprocessProgressReporter",
    "append_extra_files_reprocess_log",
    "begin_extra_files_reprocess_run",
    "default_progress",
    "finish_extra_files_reprocess_run",
    "heartbeat_age_seconds",
    "is_extra_files_reprocess_running",
    "is_extra_files_reprocess_stale",
    "parse_utc_timestamp",
    "patch_extra_files_reprocess_progress",
    "progress_path",
    "read_extra_files_reprocess_progress",
    "write_extra_files_reprocess_progress",
]
