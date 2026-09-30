"""Ingest job progress blob for UI polling (Add to the shelves)."""

from __future__ import annotations

from librarian.progress_job import make_job

_api = make_job("ingest")

default_progress = _api.default_progress
progress_path = _api.progress_path
read_ingest_progress = _api.read
write_ingest_progress = _api.write
patch_ingest_progress = _api.patch
append_ingest_log = _api.append_log
begin_ingest_run = _api.begin
finish_ingest_run = _api.finish
is_ingest_running = _api.is_running
IngestProgressReporter = _api.reporter
