"""Scan job progress blob for UI polling (Settings → Scan the shelves)."""

from __future__ import annotations

from librarian.progress_job import make_job

_api = make_job("scan")

default_progress = _api.default_progress
progress_path = _api.progress_path
read_scan_progress = _api.read
write_scan_progress = _api.write
patch_scan_progress = _api.patch
append_scan_log = _api.append_log
begin_scan_run = _api.begin
finish_scan_run = _api.finish
is_scan_running = _api.is_running
ScanProgressReporter = _api.reporter
