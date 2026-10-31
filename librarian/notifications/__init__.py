"""Notification platform package."""

from __future__ import annotations

from librarian.notifications.kinds import (
    KIND_CATALOG,
    NEWSLETTER_TIMINGS,
    NOTIFICATION_KIND_SET,
    NOTIFICATION_KINDS,
    normalize_kind,
    normalize_kind_pref,
    normalize_newsletter_timing,
    public_kind_catalog,
)
from librarian.notifications.loop import (
    complete_asked_loop,
    flush_notice_scheduler,
    notify_asked_confirm,
    notify_job_arrived,
)
from librarian.notifications.newsletters import (
    build_member_edition,
    deliver_editions,
    edition_due,
    resolve_push_user_ids,
)
from librarian.notifications.prefs import (
    get_kind_pref,
    get_newsletter_last_edition_at,
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
    "NEWSLETTER_TIMINGS",
    "NOTIFICATION_KINDS",
    "NOTIFICATION_KIND_SET",
    "normalize_kind",
    "normalize_kind_pref",
    "normalize_newsletter_timing",
    "public_kind_catalog",
    "get_kind_pref",
    "get_newsletter_last_edition_at",
    "kind_prefs_map",
    "merge_notification_prefs",
    "public_notification_prefs",
    "resolve_notification_email",
    "deliver_notification",
    "fan_out_notifications",
    "flush_email_digests",
    "notification_channel_offerings",
    "user_wants_channel",
    "complete_asked_loop",
    "flush_notice_scheduler",
    "notify_asked_confirm",
    "notify_job_arrived",
    "build_member_edition",
    "deliver_editions",
    "edition_due",
    "resolve_push_user_ids",
]
