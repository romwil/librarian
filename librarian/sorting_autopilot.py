"""High-confidence Sorting autopilot. Files path-clear books. Never talks to SABnzbd."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from librarian.config import Settings
from librarian.db import Database
from librarian.review_diagnosis import fill_review_diagnosis
from librarian.slip_gate import accept_path_clear_slips, folder_is_path_clear
from librarian.sorting_undo import record_sorting_undo

logger = logging.getLogger(__name__)

AUTOPILOT_TICK_LIMIT = 25


def run_sorting_autopilot(db: Database, settings: Settings) -> Dict[str, Any]:
    """File high-confidence Author/Title slips. Undo is 24h. Never enqueues SAB."""
    fill_review_diagnosis(db, settings, limit=AUTOPILOT_TICK_LIMIT)
    candidates: List[Dict[str, Any]] = []
    for work in db.list_works(review_state="needs_review", limit=200):
        if str(work.get("kind") or "") != "book":
            continue
        folder = str(work.get("folder_path") or "")
        if not folder:
            continue
        try:
            if folder_is_path_clear(folder):
                candidates.append(work)
        except OSError:
            continue
        if len(candidates) >= AUTOPILOT_TICK_LIMIT:
            break
    if not candidates:
        return {"changed": 0, "examined": 0, "undo_recorded": False}
    before = {str(row.get("id") or "") for row in candidates}
    accepted = accept_path_clear_slips(db, reason="", works=candidates)
    filed = []
    for work in candidates:
        work_id = str(work.get("id") or "")
        fresh = db.get_work(work_id) if work_id else None
        if fresh is None:
            continue
        if str(fresh.get("review_state") or "") != "needs_review":
            filed.append(work)
    undo = False
    if filed:
        undo = bool(record_sorting_undo(db, action="autopilot", works=filed, reason="path_clear"))
    logger.info(
        "Sorting autopilot examined %s, filed %s (undo=%s)",
        len(before),
        int(accepted.get("accepted") or 0),
        undo,
    )
    return {
        "changed": int(accepted.get("accepted") or 0),
        "examined": len(candidates),
        "kept": int(accepted.get("kept") or 0),
        "undo_recorded": undo,
    }


__all__ = ["AUTOPILOT_TICK_LIMIT", "run_sorting_autopilot"]
