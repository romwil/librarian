"""Shared imports for route registrars (keeps routers thin on boilerplate)."""

from __future__ import annotations

# Re-export the same symbols app.py historically imported for handlers.
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from librarian import __version__
from librarian.audiobook_match import companion_audiobook_payload
from librarian.audiobookshelf import abs_match_counts, match_audiobooks
from librarian.auth import (
    clear_session_cookie,
    has_real_owner,
    public_user,
    require_role,
    set_session_cookie,
    verify_password,
)
from librarian.config import load_merged_settings, mask_settings, merge_secret_fields, save_settings
from librarian.convert import ALLOWED_EBOOK_FORMATS, convert_ebook, which_ebook_convert
from librarian.delight import (
    WHISPER_LIST_LIMIT,
    celebration_candidates,
    estimate_finish_eta_minutes,
    finish_set_label,
    in_quiet_hours,
    normalize_ambient,
    normalize_ui_font_step,
    normalize_ui_theme,
    plexamp_handoff,
    rank_regrab_candidates,
    sanitize_whisper,
    series_ribbon,
    tonight_shelf,
)
from librarian.enrich import (
    apply_audnexus_match,
    apply_comicvine_match,
    apply_openlibrary_match,
    clear_enrichment,
    enrich_library,
    enrich_work,
    friendly_enrich_error,
    list_match_candidates,
    update_work_metadata,
)
from librarian.enrich_progress import (
    EnrichProgressReporter,
    begin_enrich_run,
    finish_enrich_run,
    is_enrich_running,
    read_enrich_progress,
)
from librarian.extra_files_reprocess_progress import (
    ExtraFilesReprocessProgressReporter,
    begin_extra_files_reprocess_run,
    finish_extra_files_reprocess_run,
    is_extra_files_reprocess_running,
    is_extra_files_reprocess_stale,
    read_extra_files_reprocess_progress,
)
from librarian.gaps import catalog_gaps, gap_cards, gaps_for_series
from librarian.goodreads import MAX_GOODREADS_BYTES, import_goodreads_csv
from librarian.identify import diagnose_review_folder
from librarian.indexers.discover import discover_beyond, resolve_feed_limit
from librarian.indexers.rank import remember_candidates, search_and_rank
from librarian.indexers.sync import ping_nzbfinder, sync_nzbfinder
from librarian.ingest import (
    PathDenied,
    confined_path,
    list_dir,
    poll_watch_folder,
    protected_path_refusal,
    run_ingest_paths,
    validate_watch_root,
)
from librarian.ingest_progress import (
    IngestProgressReporter,
    begin_ingest_run,
    finish_ingest_run,
    is_ingest_running,
    read_ingest_progress,
)
from librarian.invites import (
    create_household_invite,
    lookup_pending_invite,
    public_invite_view,
    redeem_local_invite,
)
from librarian.jobs import confirm_asked_job, enqueue_indexer_item, poll_active_jobs, poll_job
from librarian.kinds import ALL_KINDS, EXTRA_KINDS
from librarian.komga import komga_payload
from librarian.listen import extract_chapters, listen_payload, split_continue_rails
from librarian.lists import (
    chase_missing_items,
    curated_list_payload,
    list_presets,
)
from librarian.nyt_books import (
    NytBooksClient,
    NytBooksError,
    default_list_names,
    match_local_work,
    normalize_list_date,
    normalize_list_name,
)
from librarian.nzbfinder import NZBFinderError
from librarian.organize import (
    apply_review,
    organize_identified,
    promote_music,
    repair_review,
    reprocess_extra_files_reviews,
    reprocess_extra_files_work,
    retry_review,
    review_slip_actions,
    shelf_work_for_collision,
    suggest_review_identity,
)
from librarian.parts import build_part_set
from librarian.purge_duplicates import purge_duplicate_reviews
from librarian.purge_duplicates_progress import (
    PurgeDuplicatesProgressReporter,
    begin_purge_duplicates_run,
    finish_purge_duplicates_run,
    is_purge_duplicates_running,
    is_purge_duplicates_stale,
    read_purge_duplicates_progress,
)
from librarian.purge_shells import purge_shell_works
from librarian.purge_shells_progress import (
    PurgeShellsProgressReporter,
    begin_purge_shells_run,
    finish_purge_shells_run,
    is_purge_shells_running,
    is_purge_shells_stale,
    read_purge_shells_progress,
)
from librarian.rate_limit import enforce_rate_limit
from librarian.review_reasons import (
    REVIEW_COMICVINE_AMBIGUOUS,
    REVIEW_COMICVINE_UNMATCHED,
    REVIEW_EXTRA,
    REVIEW_LOW,
    REVIEW_NO_PAYLOAD,
    REVIEW_UNKNOWN,
    REVIEW_UNPACK_STUCK,
)
from librarian.rss import create_rss_feed, poll_rss_feeds, public_rss_feed, update_rss_feed
from librarian.sabnzbd import SABError
from librarian.scan import scan_library
from librarian.scan_progress import (
    ScanProgressReporter,
    begin_scan_run,
    finish_scan_run,
    is_scan_running,
    read_scan_progress,
)
from librarian.serve import (
    annotate_work_files,
    can_read_work,
    existing_file_paths,
    is_inline_media,
    is_reading_file,
    is_streamable_audio,
    media_type_for,
    primary_reading_path,
    resolve_catalog_file,
    safe_filename,
    zip_files,
)
from librarian.sessions import has_usable_session_secret
from librarian.shelf_health import shelf_permission_report
from librarian.split_mixed_kinds import count_mixed_kind_works, split_mixed_kind_works
from librarian.split_mixed_kinds_progress import (
    SplitMixedKindsProgressReporter,
    begin_split_mixed_kinds_run,
    finish_split_mixed_kinds_run,
    is_split_mixed_kinds_running,
    is_split_mixed_kinds_stale,
    read_split_mixed_kinds_progress,
)
from librarian.suggest import SUGGEST_FIELDS, refresh_suggest_cache, suggest_items
from librarian.web.build_info import frontend_public_file, read_build_info
from librarian.web.schemas import (
    ApplyMatchPayload,
    CelebrationSeenPayload,
    ConvertPayload,
    ExtraIndexerPayload,
    FinishSetEtaPayload,
    IngestPayload,
    InvitePayload,
    LlmListChasePayload,
    LlmListPayload,
    LoginPayload,
    MailTestPayload,
    PrefsPayload,
    ProgressPayload,
    RedeemPayload,
    RequestPayload,
    ReviewApplyPayload,
    RssFeedPayload,
    SettingsPayload,
    WhisperPayload,
    WorkMetadataPayload,
)
from librarian.web.serializers import public_work, public_works

logger = logging.getLogger("librarian.web")

_read_build_info = read_build_info
_frontend_public_file = frontend_public_file

__all__ = [
    "os",
    'annotations',
    'logging',
    'datetime',
    'Path',
    'Any',
    'Dict',
    'List',
    'Optional',
    'File',
    'HTTPException',
    'Request',
    'UploadFile',
    'FileResponse',
    'JSONResponse',
    'BackgroundTask',
    '__version__',
    'companion_audiobook_payload',
    'abs_match_counts',
    'match_audiobooks',
    'clear_session_cookie',
    'has_real_owner',
    'public_user',
    'require_role',
    'set_session_cookie',
    'verify_password',
    'load_merged_settings',
    'mask_settings',
    'merge_secret_fields',
    'save_settings',
    'ALLOWED_EBOOK_FORMATS',
    'convert_ebook',
    'which_ebook_convert',
    'WHISPER_LIST_LIMIT',
    'celebration_candidates',
    'estimate_finish_eta_minutes',
    'finish_set_label',
    'in_quiet_hours',
    'normalize_ambient',
    'normalize_ui_font_step',
    'normalize_ui_theme',
    'plexamp_handoff',
    'rank_regrab_candidates',
    'sanitize_whisper',
    'series_ribbon',
    'tonight_shelf',
    'apply_audnexus_match',
    'apply_comicvine_match',
    'apply_openlibrary_match',
    'clear_enrichment',
    'enrich_library',
    'enrich_work',
    'friendly_enrich_error',
    'list_match_candidates',
    'update_work_metadata',
    'EnrichProgressReporter',
    'begin_enrich_run',
    'finish_enrich_run',
    'is_enrich_running',
    'read_enrich_progress',
    'ExtraFilesReprocessProgressReporter',
    'begin_extra_files_reprocess_run',
    'finish_extra_files_reprocess_run',
    'is_extra_files_reprocess_running',
    'is_extra_files_reprocess_stale',
    'read_extra_files_reprocess_progress',
    'catalog_gaps',
    'gap_cards',
    'gaps_for_series',
    'MAX_GOODREADS_BYTES',
    'import_goodreads_csv',
    'diagnose_review_folder',
    'discover_beyond',
    'resolve_feed_limit',
    'remember_candidates',
    'search_and_rank',
    'ping_nzbfinder',
    'sync_nzbfinder',
    'PathDenied',
    'confined_path',
    'list_dir',
    'poll_watch_folder',
    'protected_path_refusal',
    'run_ingest_paths',
    'validate_watch_root',
    'IngestProgressReporter',
    'begin_ingest_run',
    'finish_ingest_run',
    'is_ingest_running',
    'read_ingest_progress',
    'create_household_invite',
    'lookup_pending_invite',
    'public_invite_view',
    'redeem_local_invite',
    'confirm_asked_job',
    'enqueue_indexer_item',
    'poll_active_jobs',
    'poll_job',
    'ALL_KINDS',
    'EXTRA_KINDS',
    'komga_payload',
    'extract_chapters',
    'listen_payload',
    'split_continue_rails',
    'chase_missing_items',
    'curated_list_payload',
    'list_presets',
    'NytBooksClient',
    'NytBooksError',
    'default_list_names',
    'match_local_work',
    'normalize_list_date',
    'normalize_list_name',
    'NZBFinderError',
    'apply_review',
    'organize_identified',
    'promote_music',
    'repair_review',
    'reprocess_extra_files_reviews',
    'reprocess_extra_files_work',
    'retry_review',
    'review_slip_actions',
    'shelf_work_for_collision',
    'suggest_review_identity',
    'build_part_set',
    'purge_duplicate_reviews',
    'PurgeDuplicatesProgressReporter',
    'begin_purge_duplicates_run',
    'finish_purge_duplicates_run',
    'is_purge_duplicates_running',
    'is_purge_duplicates_stale',
    'read_purge_duplicates_progress',
    'purge_shell_works',
    'PurgeShellsProgressReporter',
    'begin_purge_shells_run',
    'finish_purge_shells_run',
    'is_purge_shells_running',
    'is_purge_shells_stale',
    'read_purge_shells_progress',
    'enforce_rate_limit',
    'REVIEW_COMICVINE_AMBIGUOUS',
    'REVIEW_COMICVINE_UNMATCHED',
    'REVIEW_EXTRA',
    'REVIEW_LOW',
    'REVIEW_NO_PAYLOAD',
    'REVIEW_UNKNOWN',
    'REVIEW_UNPACK_STUCK',
    'create_rss_feed',
    'poll_rss_feeds',
    'public_rss_feed',
    'update_rss_feed',
    'SABError',
    'scan_library',
    'ScanProgressReporter',
    'begin_scan_run',
    'finish_scan_run',
    'is_scan_running',
    'read_scan_progress',
    'annotate_work_files',
    'can_read_work',
    'existing_file_paths',
    'is_inline_media',
    'is_reading_file',
    'is_streamable_audio',
    'media_type_for',
    'primary_reading_path',
    'resolve_catalog_file',
    'safe_filename',
    'zip_files',
    'has_usable_session_secret',
    'shelf_permission_report',
    'count_mixed_kind_works',
    'split_mixed_kind_works',
    'SplitMixedKindsProgressReporter',
    'begin_split_mixed_kinds_run',
    'finish_split_mixed_kinds_run',
    'is_split_mixed_kinds_running',
    'is_split_mixed_kinds_stale',
    'read_split_mixed_kinds_progress',
    'SUGGEST_FIELDS',
    'refresh_suggest_cache',
    'suggest_items',
    'frontend_public_file',
    'read_build_info',
    '_read_build_info',
    '_frontend_public_file',
    'ApplyMatchPayload',
    'CelebrationSeenPayload',
    'ConvertPayload',
    'ExtraIndexerPayload',
    'FinishSetEtaPayload',
    'IngestPayload',
    'InvitePayload',
    'LlmListChasePayload',
    'LlmListPayload',
    'LoginPayload',
    'MailTestPayload',
    'PrefsPayload',
    'ProgressPayload',
    'RedeemPayload',
    'RequestPayload',
    'ReviewApplyPayload',
    'RssFeedPayload',
    'SettingsPayload',
    'WhisperPayload',
    'WorkMetadataPayload',
    'public_work',
    'public_works',
    'logger',
]
