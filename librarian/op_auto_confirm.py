"""BD-6 · Op/owner auto-confirm after Ask (opt-in, default OFF).

Readers never auto-confirm. Discover/Search never silent-grab.
Bulk human confirm on Downloads remains. Kill switch lives in Settings.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional, Sequence

from librarian.indexer_scorecard import (
    LANTERN_BRIGHT,
    assemble_indexer_scorecard,
    host_is_muted,
)

logger = logging.getLogger("librarian.op_auto_confirm")

AUTO_CONFIRM_ROLES = frozenset({"owner", "op"})
SECURITY_KIND = "op_auto_confirm"


def _text(value: Any) -> str:
    return str(value or "").strip()


def normalize_allowlist(raw: Any) -> list[str]:
    """Unique host ids from settings — never empty strings."""
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.replace(";", ",").split(",")]
        items = parts
    elif isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray)):
        items = [_text(row) for row in raw]
    else:
        items = []
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = _text(item).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def op_auto_confirm_enabled(settings: Any) -> bool:
    """Kill switch — default OFF."""
    return bool(getattr(settings, "op_auto_confirm_enabled", False))


def host_on_allowlist(settings: Any, host_id: str) -> bool:
    wanted = _text(host_id).lower()
    if not wanted:
        return False
    return wanted in set(normalize_allowlist(getattr(settings, "op_auto_confirm_hosts", None)))


def host_lantern_weather(settings: Any, host_id: str, *, db: Any = None) -> str:
    """Current lantern weather for a host id (empty when unknown)."""
    hid = _text(host_id)
    if not hid or db is None:
        return ""
    try:
        card = assemble_indexer_scorecard(db, settings)
    except Exception:  # noqa: BLE001 — scorecard must never block Ask
        logger.exception("indexer scorecard failed during auto-confirm check")
        return ""
    for row in card.get("lanterns") or []:
        if _text(row.get("id")).lower() == hid.lower():
            return _text(row.get("weather")).lower()
    return ""


def host_is_healthy_lantern(settings: Any, host_id: str, *, db: Any = None) -> bool:
    """Bright lantern and not muted — known-good weather for BD-6."""
    hid = _text(host_id)
    if not hid:
        return False
    if host_is_muted(settings, hid):
        return False
    return host_lantern_weather(settings, hid, db=db) == LANTERN_BRIGHT


def host_eligible_for_auto_confirm(
    settings: Any,
    host_id: str,
    *,
    db: Any = None,
) -> bool:
    """Allowlisted host OR healthy (bright, unmuted) lantern."""
    if host_on_allowlist(settings, host_id):
        return True
    return host_is_healthy_lantern(settings, host_id, db=db)


def should_auto_confirm(
    settings: Any,
    *,
    role: str,
    host_id: str,
    db: Any = None,
) -> bool:
    """True only for owner/op with kill switch ON and an eligible host."""
    if _text(role).lower() not in AUTO_CONFIRM_ROLES:
        return False
    if not op_auto_confirm_enabled(settings):
        return False
    return host_eligible_for_auto_confirm(settings, host_id, db=db)


def record_auto_confirm_audit(
    db: Any,
    *,
    actor_id: str,
    job_id: str,
    host_id: str,
    kind: str = "",
    reason: str = "",
) -> None:
    """Write a security_events row — never stores titles or query text."""
    try:
        db.add_security_event(
            kind=SECURITY_KIND,
            actor_id=_text(actor_id) or None,
            detail={
                "job_id": _text(job_id),
                "host_id": _text(host_id),
                "kind": _text(kind),
                "reason": _text(reason) or "eligible_host",
            },
        )
    except Exception:  # noqa: BLE001 — audit must not undo a successful confirm
        logger.exception("op_auto_confirm audit failed for job %s", job_id)


def maybe_auto_confirm_asked(
    db: Any,
    settings: Any,
    job: Mapping[str, Any],
    *,
    role: str,
    actor_id: str = "",
    host_id: str = "",
) -> Optional[Dict[str, Any]]:
    """After Ask: confirm to SAB when BD-6 carve-out matches. Else None."""
    if not job or not _text(job.get("id")):
        return None
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    selected = payload.get("selected") if isinstance(payload.get("selected"), dict) else {}
    hid = (
        _text(host_id)
        or _text(selected.get("host_id"))
        or _text(payload.get("host_id"))
        or _text(job.get("host_id"))
    )
    if not should_auto_confirm(settings, role=role, host_id=hid, db=db):
        return None

    from librarian.jobs import confirm_asked_job

    try:
        confirmed = confirm_asked_job(db, settings, str(job["id"]))
    except Exception:  # noqa: BLE001
        logger.exception("op auto-confirm failed for job %s", job.get("id"))
        return None

    kind = _text(confirmed.get("kind") or job.get("kind") or payload.get("kind"))
    reason = "allowlist" if host_on_allowlist(settings, hid) else "healthy_lantern"
    record_auto_confirm_audit(
        db,
        actor_id=actor_id,
        job_id=str(confirmed.get("id") or job.get("id") or ""),
        host_id=hid,
        kind=kind,
        reason=reason,
    )
    return confirmed


__all__ = [
    "AUTO_CONFIRM_ROLES",
    "SECURITY_KIND",
    "host_eligible_for_auto_confirm",
    "host_is_healthy_lantern",
    "host_on_allowlist",
    "maybe_auto_confirm_asked",
    "normalize_allowlist",
    "op_auto_confirm_enabled",
    "record_auto_confirm_audit",
    "should_auto_confirm",
]
