"""Reader asks shown on the Library card. Never queues SABnzbd."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

_ON_THE_WAY = frozenset({"queued", "downloading", "extracting", "identifying", "processing"})
_ARRIVED = frozenset({"organized", "completed"})


def ask_state(job: Mapping[str, Any]) -> tuple[str, str]:
    """Map a job onto a calm Library-card label."""
    status = str(job.get("status") or "").strip().lower()
    work_id = str(job.get("work_id") or "").strip()
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    guid = str(job.get("indexer_guid") or payload.get("guid") or "").strip()
    if work_id and status in _ARRIVED | {"skipped"}:
        return "arrived", "On the shelf"
    if status == "review":
        return "sorting", "Needs Sorting"
    if status == "failed":
        return "failed", "Needs another look"
    if status in _ON_THE_WAY:
        return "on_the_way", "On the way"
    if status == "asked" and not guid:
        return "looking", "Looking"
    if status == "asked":
        return "waiting", "Waiting for the owner"
    if work_id:
        return "arrived", "On the shelf"
    return "looking", "Looking"


def public_asks(jobs: Sequence[Mapping[str, Any]], *, limit: int = 20) -> List[Dict[str, Any]]:
    """Deduped Your-asks rows for the Library card."""
    items: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for job in jobs or []:
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        wanted_id = str(payload.get("wanted_id") or "").strip()
        title = str(job.get("title") or payload.get("title") or "").strip()
        kind = str(job.get("kind") or payload.get("kind") or "").strip()
        key = f"wanted:{wanted_id}" if wanted_id else f"{title.lower()}|{kind}|{job.get('id')}"
        if key in seen:
            continue
        seen.add(key)
        state, label = ask_state(job)
        work_id = str(job.get("work_id") or "").strip()
        items.append(
            {
                "id": str(job.get("id") or ""),
                "title": title or "A title",
                "kind": kind,
                "status": str(job.get("status") or ""),
                "state": state,
                "label": label,
                "work_id": work_id or None,
                "href": f"/works/{work_id}" if work_id and state == "arrived" else None,
            }
        )
        if len(items) >= limit:
            break
    return items
