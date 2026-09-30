"""Enrich job progress blob for UI polling (Settings + trickle)."""

from __future__ import annotations

from librarian.progress_job import make_job

_api = make_job("enrich")

default_progress = _api.default_progress
progress_path = _api.progress_path
read_enrich_progress = _api.read
write_enrich_progress = _api.write
patch_enrich_progress = _api.patch
append_enrich_log = _api.append_log
begin_enrich_run = _api.begin
finish_enrich_run = _api.finish
is_enrich_running = _api.is_running
EnrichProgressReporter = _api.reporter
