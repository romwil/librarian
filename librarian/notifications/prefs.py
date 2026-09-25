"""Per-user notification preference helpers (stored in user_prefs.prefs_json)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from librarian.notifications.kinds import (
    KIND_CATALOG,
    NOTIFICATION_KINDS,
    normalize_kind,
    normalize_kind_pref,
)


def _nested_from_row(user_prefs: Dict[str, Any]) -> Dict[str, Any]:
    """Accept get_user_prefs row or a bare nested prefs dict."""
    if not isinstance(user_prefs, dict):
        return {}
    if isinstance(user_prefs.get("prefs"), dict):
        return dict(user_prefs["prefs"])
    # Bare nested already (or empty).
    skip = {"user_id", "ambient", "updated_at", "prefs", "ui_theme", "ui_font_step"}
    if any(key in user_prefs for key in ("notifications", "notification_email")):
        return {k: v for k, v in user_prefs.items() if k not in skip}
    return {}


def resolve_notification_email(
    user_prefs: Dict[str, Any],
    user: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Prefer prefs notification_email; fall back to user dict if present."""
    nested = _nested_from_row(user_prefs)
    for key in ("notification_email", "email"):
        value = str(nested.get(key) or "").strip()
        if value and "@" in value:
            return value
    if user:
        for key in ("notification_email", "email"):
            value = str(user.get(key) or "").strip()
            if value and "@" in value:
                return value
    return None


def kind_prefs_map(user_prefs: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    nested = _nested_from_row(user_prefs)
    raw_map = nested.get("notifications")
    if not isinstance(raw_map, dict):
        raw_map = {}
    return {kind: normalize_kind_pref(kind, raw_map.get(kind)) for kind in NOTIFICATION_KINDS}


def get_kind_pref(user_prefs: Dict[str, Any], kind: str) -> Dict[str, Any]:
    cleaned = normalize_kind(kind)
    nested = _nested_from_row(user_prefs)
    raw_map = nested.get("notifications") if isinstance(nested.get("notifications"), dict) else {}
    return normalize_kind_pref(cleaned, raw_map.get(cleaned))


def public_notification_prefs(user_prefs: Dict[str, Any]) -> Dict[str, Any]:
    """Shape returned by GET /api/notifications/prefs."""
    return {
        "notification_email": resolve_notification_email(user_prefs) or "",
        "kinds": kind_prefs_map(user_prefs),
        "catalog": KIND_CATALOG,
    }


def merge_notification_prefs(
    existing_row: Dict[str, Any],
    *,
    notification_email: Any = ...,
    kinds: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return updated nested prefs dict ready for Database.set_user_prefs(prefs=...)."""
    nested = _nested_from_row(existing_row)

    if notification_email is not ...:
        if notification_email is None or str(notification_email).strip() == "":
            nested.pop("notification_email", None)
        else:
            cleaned = str(notification_email).strip()
            if "@" not in cleaned:
                raise ValueError("notification_email must look like an email address")
            nested["notification_email"] = cleaned

    if kinds is not None:
        if not isinstance(kinds, dict):
            raise ValueError("kinds must be an object keyed by notification kind")
        current = kind_prefs_map({"prefs": nested})
        for kind, value in kinds.items():
            try:
                cleaned = normalize_kind(kind)
            except ValueError:
                continue
            current[cleaned] = normalize_kind_pref(cleaned, value)
        nested["notifications"] = current

    return nested
