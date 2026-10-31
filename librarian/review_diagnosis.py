"""Cached folder diagnosis for the Sorting desk.

The poller fills ``review_diagnosis`` so ``GET /api/review`` never walks the
complete folder. Unraid FUSE ``rglob`` stays off the request path.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from librarian.config import Settings
from librarian.db import Database
from librarian.identify import diagnose_review_folder
from librarian.repositories._base import _loads
from librarian.review_bulk import READY_TO_FILE
from librarian.review_reasons import REVIEW_MISSING_FOLDER

logger = logging.getLogger(__name__)

DEFAULT_FILL_LIMIT = 200
PAGE_LIMIT_DEFAULT = 25
PAGE_LIMIT_MAX = 50

EFFECTIVE_REASON_SQL = """
CASE
  WHEN d.problem = 'unpack_stuck' THEN 'unpack_stuck'
  WHEN d.problem = 'missing_folder'
       AND (w.review_reason IS NULL OR w.review_reason IN ('', 'no_payload'))
       THEN 'missing_folder'
  WHEN d.problem = 'no_payload'
       AND (w.review_reason IS NULL OR w.review_reason IN ('', 'no_payload'))
       THEN 'no_payload'
  WHEN (w.review_reason IS NULL OR w.review_reason = '')
       AND (d.problem IS NULL OR d.problem = '')
       AND s.outcome = 'trusted'
       THEN 'ready_to_file'
  ELSE coalesce(nullif(w.review_reason, ''), d.problem, '')
END
"""


def diagnosis_from_live(live: Mapping[str, Any]) -> Dict[str, Any]:
    """Allowlisted diagnosis fields for the desk payload (no file lists)."""
    return {
        "path": str(live.get("path") or ""),
        "resolved_path": str(live.get("resolved_path") or ""),
        "problem": str(live.get("problem") or ""),
        "payload_count": int(live.get("payload_count") or 0),
        "archive_count": int(live.get("archive_count") or 0),
        "junk_count": int(live.get("junk_count") or 0),
        "par2_count": int(live.get("par2_count") or 0),
        "looked_for": str(live.get("looked_for") or ""),
        "tried": str(live.get("tried") or ""),
        "path_note": str(live.get("path_note") or ""),
        "suggested_folder": live.get("suggested_folder"),
        "collection_dump": bool(live.get("collection_dump")),
        "distinct_title_count": int(live.get("distinct_title_count") or 0),
        "path_clear": bool(live.get("path_clear")),
    }


def fill_review_diagnosis(
    db: Database,
    settings: Settings,
    *,
    limit: int = DEFAULT_FILL_LIMIT,
    work_ids: Optional[Sequence[str]] = None,
) -> int:
    """Diagnose open slips and persist the result. Returns rows written."""
    chosen = [str(w).strip() for w in (work_ids or []) if str(w or "").strip()]
    if chosen:
        works = [row for row in (db.get_work(work_id) for work_id in dict.fromkeys(chosen)) if row]
        works = [row for row in works if str(row.get("review_state") or "") == "needs_review"]
    else:
        works = db.list_works(review_state="needs_review", limit=max(1, int(limit)))
    if not works:
        return 0
    existing = db.get_review_diagnoses([str(row.get("id") or "") for row in works])
    written = 0
    now = time.time()
    for work in works:
        work_id = str(work.get("id") or "")
        if not work_id:
            continue
        folder_raw = str(work.get("folder_path") or "")
        prior = existing.get(work_id) or {}
        if (
            prior
            and str(prior.get("folder_path") or "") == folder_raw
            and float(prior.get("updated_at") or 0) >= float(work.get("updated_at") or 0)
        ):
            continue
        try:
            live = diagnose_review_folder(Path(folder_raw), settings.complete_root) if folder_raw else {}
        except OSError:
            live = {"problem": REVIEW_MISSING_FOLDER, "path": folder_raw, "path_clear": False}
        shaped = diagnosis_from_live(live if isinstance(live, dict) else {})
        db.upsert_review_diagnosis(
            work_id,
            folder_path=folder_raw,
            diagnosis=shaped,
            now=now,
        )
        written += 1
    return written


def counts_by_effective_reason(db: Database) -> Dict[str, int]:
    """One counts object for badge, header, and reason chips."""
    sql = f"""
        SELECT {EFFECTIVE_REASON_SQL} AS reason, COUNT(*) AS cnt
        FROM works w
        LEFT JOIN review_diagnosis d ON d.work_id = w.id
        LEFT JOIN review_suggestions s ON s.work_id = w.id
        WHERE w.review_state = 'needs_review'
        GROUP BY reason
    """
    with db._connect() as conn:
        rows = conn.execute(sql).fetchall()
    out: Dict[str, int] = {}
    for row in rows:
        key = str(row["reason"] or "")
        out[key] = int(row["cnt"] or 0)
    return out


def encode_cursor(updated_at: Any, work_id: str) -> str:
    import base64

    raw = f"{float(updated_at or 0):.6f}\t{work_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> Optional[tuple[float, str]]:
    import base64

    text = str(cursor or "").strip()
    if not text:
        return None
    pad = "=" * ((4 - len(text) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(text + pad).decode("utf-8")
        stamp, work_id = raw.split("\t", 1)
        return float(stamp), work_id
    except (ValueError, TypeError, OSError):
        return None


def list_review_page(
    db: Database,
    *,
    reason: str = "",
    cursor: str = "",
    limit: int = PAGE_LIMIT_DEFAULT,
) -> Dict[str, Any]:
    """Cursor page of open slips. Diagnosis is read from the table, never live rglob."""
    size = min(PAGE_LIMIT_MAX, max(1, int(limit or PAGE_LIMIT_DEFAULT)))
    key = str(reason or "").strip()
    decoded = decode_cursor(cursor)
    args: List[Any] = []
    where = ["w.review_state = 'needs_review'"]
    if key:
        where.append(f"({EFFECTIVE_REASON_SQL}) = ?")
        args.append(key)
    if decoded is not None:
        where.append("(w.updated_at < ? OR (w.updated_at = ? AND w.id < ?))")
        args.extend([decoded[0], decoded[0], decoded[1]])
    sql = f"""
        SELECT w.*,
               d.diagnosis_json AS _diagnosis_json,
               d.problem AS _diagnosis_problem,
               d.path_clear AS _diagnosis_path_clear,
               s.outcome AS _suggestion_outcome,
               s.suggestion_json AS _suggestion_json,
               s.explanation AS _suggestion_explanation,
               s.updated_at AS _suggestion_updated_at,
               {EFFECTIVE_REASON_SQL} AS effective_reason
        FROM works w
        LEFT JOIN review_diagnosis d ON d.work_id = w.id
        LEFT JOIN review_suggestions s ON s.work_id = w.id
        WHERE {' AND '.join(where)}
        ORDER BY w.updated_at DESC, w.id DESC
        LIMIT ?
    """
    args.append(size + 1)
    from librarian.repositories._base import _row_dict

    with db._connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    fetched = [_row_dict(row) or {} for row in rows]
    extra = fetched[size:]
    page = fetched[:size]
    next_cursor = None
    if extra and page:
        tail = page[-1]
        next_cursor = encode_cursor(tail.get("updated_at"), str(tail.get("id") or ""))
    return {"rows": page, "next_cursor": next_cursor}


def diagnosis_from_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    stored = _loads(row.get("_diagnosis_json"), None)
    if isinstance(stored, dict) and stored:
        return diagnosis_from_live(stored)
    return {}


__all__ = [
    "DEFAULT_FILL_LIMIT",
    "EFFECTIVE_REASON_SQL",
    "PAGE_LIMIT_DEFAULT",
    "PAGE_LIMIT_MAX",
    "READY_TO_FILE",
    "counts_by_effective_reason",
    "decode_cursor",
    "diagnosis_from_live",
    "diagnosis_from_row",
    "encode_cursor",
    "fill_review_diagnosis",
    "list_review_page",
]
