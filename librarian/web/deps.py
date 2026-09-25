"""Shared create_app dependencies passed into route registrars."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from librarian.db import Database
from librarian.progress_job import BackgroundJobSlot


@dataclass
class WebDeps:
    """Composition-root handles for route modules."""

    root: Path
    db: Database
    settings: Callable[[], Any]
    enrich_job: BackgroundJobSlot
    scan_job: BackgroundJobSlot
    ingest_job: BackgroundJobSlot
    extra_files_reprocess_job: BackgroundJobSlot
    purge_duplicates_job: BackgroundJobSlot
    purge_shells_job: BackgroundJobSlot
    split_mixed_kinds_job: BackgroundJobSlot

    def current_user(self, request) -> Optional[Dict[str, Any]]:
        from librarian.auth import user_from_request

        return user_from_request(request, self.db)
