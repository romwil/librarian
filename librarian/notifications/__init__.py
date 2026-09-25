"""Notification platform package."""

from __future__ import annotations

from librarian.notifications.kinds import (
    KIND_CATALOG,
    NOTIFICATION_KIND_SET,
    NOTIFICATION_KINDS,
    normalize_kind,
    normalize_kind_pref,
)
from librarian.notifications.prefs import (
    get_kind_pref,
    kind_prefs_map,
    merge_notification_prefs,
    public_notification_prefs,
    resolve_notification_email,
)
from librarian.notifications.service import (
    deliver_notification,
    fan_out_notifications,
    flush_email_digests,
    notification_channel_offerings,
    user_wants_channel,
)

__all__ = [
    "KIND_CATALOG",
    "NOTIFICATION_KINDS",
    "NOTIFICATION_KIND_SET",
    "normalize_kind",
    "normalize_kind_pref",
    "get_kind_pref",
    "kind_prefs_map",
    "merge_notification_prefs",
    "public_notification_prefs",
    "resolve_notification_email",
    "deliver_notification",
    "fan_out_notifications",
    "flush_email_digests",
    "notification_channel_offerings",
    "user_wants_channel",
]
