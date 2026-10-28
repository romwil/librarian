"""Server-side model triage for low-confidence hold slips.

One background job sends eligible slips to the BYO LLM one at a time, persists each
answer on the slip before the next is sent, and reports ``eligible``, ``suggested``,
``trusted``, ``ambiguous``, ``failed``, and ``applied`` separately. Restarting skips
slips that already have a trusted or ambiguous answer. Nothing is filed here; Apply
trusted matches files only rows the model was confident about.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from librarian.config import Settings
from librarian.db import Database
from librarian.progress_job import ProgressJob, utc_now

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 60
MAX_BATCH_SIZE = 200
DEFAULT_MIN_INTERVAL_S = 1.0
_SETTLED_OUTCOMES = frozenset({"trusted", "ambiguous"})

_COUNTERS = ("eligible", "suggested", "trusted", "ambiguous", "failed", "applied")

PROGRESS = ProgressJob(
    filename="review_suggest_batch_progress.json",
    defaults=lambda: {
        "status": "idle",
        "phase": "",
        "current_title": "",
        "done": 0,
        "total": 0,
        **{key: 0 for key in _COUNTERS},
        "logs": [],
        "error": "",
        "started_at": "",
        "finished_at": "",
        "heartbeat_at": "",
    },
    heartbeat=True,
    heartbeat_stale_s=180.0,
)


def read_progress(data_dir: Path) -> Dict[str, Any]:
    return PROGRESS.read(data_dir)


def is_running(data_dir: Path) -> bool:
    return PROGRESS.is_running(data_dir)


def is_stale(payload: Dict[str, Any]) -> bool:
    return PROGRESS.is_stale(payload)


def begin(data_dir: Path) -> Dict[str, Any]:
    return PROGRESS.begin(data_dir, start_log="Started checking low-confidence slips with the model.")


def finish(data_dir: Path, *, error: str = "") -> Dict[str, Any]:
    return PROGRESS.finish(data_dir, error=error)


def eligible_slips(db: Database, settings: Settings) -> List[Dict[str, Any]]:
    """Slips the model can help with, minus ones that already have a settled answer.

    The path-clear override stays: a structured Author/Title folder is not a model problem.
    """
    from librarian.identify import diagnose_review_folder
    from librarian.organize import review_slip_actions

    works = db.list_works(review_state="needs_review", limit=20000)
    settled = {
        work_id
        for work_id, row in db.get_review_suggestions().items()
        if str(row.get("outcome") or "") in _SETTLED_OUTCOMES
    }
    out: List[Dict[str, Any]] = []
    for work in works:
        work_id = str(work.get("id") or "")
        if work_id in settled:
            continue
        try:
            diagnosis = diagnose_review_folder(
                Path(str(work.get("folder_path") or "")), settings.complete_root
            )
        except OSError:
            diagnosis = {}
        actions = review_slip_actions(work, diagnosis, llm_configured=True)
        if actions.get("can_suggest_llm") or actions.get("needs_llm_suggest"):
            out.append(work)
    return out


def run_suggest_batch(
    db: Database,
    settings: Settings,
    *,
    data_dir: Path,
    batch_size: int = DEFAULT_BATCH_SIZE,
    min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
    llm_client: Any = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Dict[str, Any]:
    """Suggest identities for up to ``batch_size`` eligible slips, persisting each at once."""
    from librarian.llm import LLM_UNSET_COPY, client_from_settings
    from librarian.organize import suggest_review_identity

    size = max(1, min(int(batch_size or DEFAULT_BATCH_SIZE), MAX_BATCH_SIZE))
    llm = llm_client if llm_client is not None else client_from_settings(settings)
    slips = eligible_slips(db, settings)
    eligible = len(slips)
    chosen = slips[:size]
    counts = {key: 0 for key in _COUNTERS}
    counts["eligible"] = eligible
    PROGRESS.patch(data_dir, phase="suggesting", total=len(chosen), done=0, **counts)
    if llm is None:
        PROGRESS.append_log(data_dir, LLM_UNSET_COPY)
        result = {**counts, "done": 0, "total": len(chosen), "error": LLM_UNSET_COPY}
        PROGRESS.finish(data_dir, error=LLM_UNSET_COPY)
        return result
    last_sent = 0.0
    for index, work in enumerate(chosen, start=1):
        work_id = str(work.get("id") or "")
        title = str(work.get("title") or work_id)
        wait = float(min_interval_s) - (time.monotonic() - last_sent)
        if last_sent and wait > 0:
            sleep(wait)
        last_sent = time.monotonic()
        jobs = db.jobs_for_work(work_id)
        try:
            answer = suggest_review_identity(
                db, settings, work_id=work_id, llm_client=llm, job=jobs[0] if jobs else None
            )
            outcome = str(answer.get("outcome") or "failed")
        except Exception as error:  # noqa: BLE001 — one bad slip must not stop the sweep
            logger.exception("Suggest batch failed for %s", work_id)
            db.set_review_suggestion(work_id, outcome="failed", explanation=str(error)[:300])
            outcome = "failed"
        counts["suggested"] += 1
        counts[outcome if outcome in counts else "failed"] += 1
        PROGRESS.patch(data_dir, done=index, current_title=title, **counts)
    result = {**counts, "done": len(chosen), "total": len(chosen)}
    PROGRESS.finish(data_dir, result=result)
    PROGRESS.patch(data_dir, **counts)
    PROGRESS.append_log(
        data_dir,
        (
            f"Finished — {counts['suggested']} sent: {counts['trusted']} ready to file, "
            f"{counts['ambiguous']} need a decision, {counts['failed']} model unavailable."
        ),
    )
    return result


def apply_trusted_matches(
    db: Database,
    settings: Settings,
    *,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """File only slips whose persisted model answer is trusted, through the normal Apply path."""
    from librarian.organize import apply_review

    rows = db.get_review_suggestions()
    examined = 0
    applied = 0
    failures: List[Dict[str, Any]] = []
    for work_id, row in rows.items():
        if str(row.get("outcome") or "") != "trusted":
            continue
        work = db.get_work(work_id)
        if work is None or str(work.get("review_state") or "") != "needs_review":
            continue
        suggestion = row.get("suggestion") if isinstance(row.get("suggestion"), dict) else {}
        examined += 1
        overrides = {
            key: suggestion[key]
            for key in ("title", "author", "kind", "series_name", "series_index", "isbn", "year")
            if suggestion.get(key) not in (None, "")
        }
        folder = Path(str(work.get("folder_path") or ""))
        try:
            apply_review(db, settings, work_id=work_id, folder=folder, identity_overrides=overrides)
            db.delete_review_suggestion(work_id)
            applied += 1
        except Exception as error:  # noqa: BLE001 — a collision or moved folder stays for a person
            failures.append({"id": work_id, "title": work.get("title"), "error": str(error)})
    if data_dir is not None and applied:
        current = PROGRESS.read(data_dir)
        PROGRESS.patch(data_dir, applied=int(current.get("applied") or 0) + applied)
    return {
        "examined": examined,
        "applied": applied,
        "failed": len(failures),
        "failures": failures[:20],
        "at": utc_now(),
    }


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "MAX_BATCH_SIZE",
    "apply_trusted_matches",
    "begin",
    "eligible_slips",
    "finish",
    "is_running",
    "is_stale",
    "read_progress",
    "run_suggest_batch",
]
