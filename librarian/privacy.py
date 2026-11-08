"""Member export, personal-data registry, and household privacy notice."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Literal, TypedDict

from librarian.db import Database
from librarian.mail import mail_configured

ExportTreatment = Literal["include", "exclude", "summarize"]
DeleteTreatment = Literal["delete", "anonymize", "detach", "revoke", "age_out", "n/a"]

EXPORT_SCHEMA_VERSION = 1


class PersonalDataCategory(TypedDict):
    """One person-linked store. Drives export checklist + deletion cascade tests."""

    key: str
    table: str
    subject_column: str
    export: ExportTreatment
    delete: DeleteTreatment
    export_fields: List[str]
    summary: str
    reason: str


# Contract for PRIV-002 / PRIV-009. When adding a user-id column, register it here
# and extend export_member_bundle / delete_user_cascade (or document exclusion).
PERSONAL_DATA_REGISTRY: List[PersonalDataCategory] = [
    {
        "key": "user",
        "table": "users",
        "subject_column": "id",
        "export": "include",
        "delete": "delete",
        "export_fields": [
            "id",
            "display_name",
            "role",
            "created_at",
            "last_login_at",
            "disabled",
        ],
        "summary": "Library card identity (no password hash).",
        "reason": "Member portability of their own card metadata.",
    },
    {
        "key": "prefs",
        "table": "user_prefs",
        "subject_column": "user_id",
        "export": "include",
        "delete": "delete",
        "export_fields": ["ambient", "prefs"],
        "summary": "Theme, ambient, notification nested prefs.",
        "reason": "Personal UI and inbox choices.",
    },
    {
        "key": "progress",
        "table": "progress",
        "subject_column": "user_id",
        "export": "include",
        "delete": "delete",
        "export_fields": ["work_id", "position", "fraction", "updated_at"],
        "summary": "Continue / Finished place per volume.",
        "reason": "Reading place is personal; never shared via shelf visibility.",
    },
    {
        "key": "shelves",
        "table": "shelves",
        "subject_column": "owner_user_id",
        "export": "include",
        "delete": "delete",
        "export_fields": ["id", "name", "created_at", "shared"],
        "summary": "Named shelves this member owns.",
        "reason": "Owned collections travel with the card.",
    },
    {
        "key": "shelf_items",
        "table": "shelf_items",
        "subject_column": "shelf_id",
        "export": "include",
        "delete": "delete",
        "export_fields": ["shelf_id", "work_id", "added_at"],
        "summary": "Volumes on owned shelves.",
        "reason": "Shelf membership is part of the owned collection.",
    },
    {
        "key": "whispers",
        "table": "whispers",
        "subject_column": "user_id",
        "export": "include",
        "delete": "delete",
        "export_fields": ["id", "work_id", "body", "created_at"],
        "summary": "Notes the member left on volumes.",
        "reason": "Authored notes belong to the card; work pages may still show display name while live.",
    },
    {
        "key": "notifications",
        "table": "user_notifications",
        "subject_column": "user_id",
        "export": "include",
        "delete": "delete",
        "export_fields": [
            "id",
            "kind",
            "title",
            "body",
            "related_id",
            "created_at",
            "seen_at",
        ],
        "summary": "Inbox rows for this card.",
        "reason": "Arrival / ask notices are personal.",
    },
    {
        "key": "password_hash",
        "table": "users",
        "subject_column": "id",
        "export": "exclude",
        "delete": "delete",
        "export_fields": [],
        "summary": "Password hash.",
        "reason": "Secrets never leave the box via export.",
    },
    {
        "key": "sessions",
        "table": "sessions",
        "subject_column": "user_id",
        "export": "exclude",
        "delete": "delete",
        "export_fields": [],
        "summary": "Signed-in device sessions (IP / UA).",
        "reason": "Operational security state; revoke on disable/delete, not portable.",
    },
    {
        "key": "password_resets",
        "table": "password_resets",
        "subject_column": "user_id",
        "export": "exclude",
        "delete": "delete",
        "export_fields": [],
        "summary": "Pending reset tokens.",
        "reason": "One-time security artifacts.",
    },
    {
        "key": "celebrations_seen",
        "table": "celebrations_seen",
        "subject_column": "user_id",
        "export": "exclude",
        "delete": "delete",
        "export_fields": [],
        "summary": "Which delight toasts this card has already seen.",
        "reason": "Ephemeral UI state; not needed for portability.",
    },
    {
        "key": "notification_digest_queue",
        "table": "notification_digest_queue",
        "subject_column": "user_id",
        "export": "exclude",
        "delete": "delete",
        "export_fields": [],
        "summary": "Pending digest mail queue.",
        "reason": "Transient delivery queue; Inbox export covers delivered copy.",
    },
    {
        "key": "invites_created",
        "table": "invites",
        "subject_column": "created_by",
        "export": "exclude",
        "delete": "revoke",
        "export_fields": [],
        "summary": "Pending invites this member minted.",
        "reason": "Household ops artifact; pending invites are revoked on delete.",
    },
    {
        "key": "invites_redeemed",
        "table": "invites",
        "subject_column": "redeemed_user_id",
        "export": "exclude",
        "delete": "detach",
        "export_fields": [],
        "summary": "Invite row that created this card.",
        "reason": "Keep invite history; clear the subject pointer on delete.",
    },
    {
        "key": "jobs_requested",
        "table": "jobs",
        "subject_column": "requested_by",
        "export": "exclude",
        "delete": "detach",
        "export_fields": [],
        "summary": "Downloads / asks attributed to this card.",
        "reason": "Queue history stays for house ops; requester identity is cleared.",
    },
    {
        "key": "notifications_from",
        "table": "user_notifications",
        "subject_column": "from_user_id",
        "export": "exclude",
        "delete": "detach",
        "export_fields": [],
        "summary": "Notices another member received from this card.",
        "reason": "Recipient keeps their Inbox; sender pointer is nulled.",
    },
    {
        "key": "security_events_subject",
        "table": "security_events",
        "subject_column": "user_id",
        "export": "exclude",
        "delete": "anonymize",
        "export_fields": [],
        "summary": "Security log rows naming this member as subject.",
        "reason": "Audit trail survives; direct identity is nulled.",
    },
    {
        "key": "security_events_actor",
        "table": "security_events",
        "subject_column": "actor_id",
        "export": "exclude",
        "delete": "anonymize",
        "export_fields": [],
        "summary": "Security log rows naming this member as actor.",
        "reason": "Audit trail survives; direct identity is nulled.",
    },
    {
        "key": "catalog_snapshots",
        "table": "backups",
        "subject_column": "n/a",
        "export": "exclude",
        "delete": "age_out",
        "export_fields": [],
        "summary": "Nightly SQLite snapshots under /config/backups.",
        "reason": "Recovery copies may hold deleted rows until the 35-day window ages out.",
    },
    {
        "key": "integration_secrets",
        "table": "settings",
        "subject_column": "n/a",
        "export": "exclude",
        "delete": "n/a",
        "export_fields": [],
        "summary": "Indexer / SAB / LLM / session secrets.",
        "reason": "Host secrets; never member-portable and omitted from snapshots.",
    },
]


def export_field_checklist() -> List[Dict[str, str]]:
    """Human + test-facing include/exclude table for /api/auth/export (PRIV-002)."""
    return [
        {
            "key": row["key"],
            "export": row["export"],
            "summary": row["summary"],
            "reason": row["reason"],
        }
        for row in PERSONAL_DATA_REGISTRY
    ]


def deletion_cascade_checklist() -> List[Dict[str, str]]:
    """Disable / delete / anonymize / age-out outcomes (PRIV-009)."""
    return [
        {
            "key": row["key"],
            "delete": row["delete"],
            "summary": row["summary"],
            "reason": row["reason"],
        }
        for row in PERSONAL_DATA_REGISTRY
        if row["delete"] != "n/a"
    ]


def included_export_keys() -> List[str]:
    return [row["key"] for row in PERSONAL_DATA_REGISTRY if row["export"] == "include"]


def household_privacy_notice(settings: Any) -> Dict[str, Any]:
    """Plain-language notice. No secrets. Derived from the running config."""
    paragraphs: List[str] = [
        "Librarian is a household library on this box. There is no public account, "
        "and nothing here is sold or sent to an advertising company.",
        "Your reading place, favorites, and asks stay on this host. Finished titles "
        "are private unless you choose to tell the house. Another card never sees "
        "your Continue place — even on a shared shelf.",
        "Invites last 7 days. A forgotten-password link lasts 24 hours and works once. "
        "Signing out of every device, or changing your password, ends other sessions. "
        "Nightly snapshots of the catalog are kept for 35 days.",
    ]
    llm_on = bool(str(getattr(settings, "llm_api_key", "") or "").strip())
    provider = str(getattr(settings, "llm_provider", "") or "").strip() or "the language model"
    if llm_on:
        paragraphs.append(
            f"When a keeper identifies a title, suggests a Sorting name, names a Bestsellers list, "
            f"or ranks Find hits, cover, filename, and title metadata may be sent to {provider}. "
            "The model never invents an ISBN. Readers' search stays on the shelves unless they ask the house."
        )
    else:
        paragraphs.append(
            "No language-model key is configured on this box right now, so titles are not sent out for identify."
        )
    indexer = bool(str(getattr(settings, "nzbfinder_api_token", "") or "").strip())
    extras = [
        row
        for row in (getattr(settings, "extra_indexers", None) or [])
        if isinstance(row, dict) and str(row.get("api_token") or "").strip()
    ]
    if indexer or extras:
        paragraphs.append(
            "Search beyond the shelves queries the household indexer (and any extra Newznab hosts). "
            "Those hosts see the title you typed, not your name."
        )
    hardcover = bool(str(getattr(settings, "hardcover_api_token", "") or "").strip())
    if hardcover:
        paragraphs.append(
            "Enrich may send ISBN or title and author to Hardcover (and Open Library as fallback) "
            "to fill covers and series — never an invented ISBN."
        )
    if mail_configured(settings):
        paragraphs.append(
            "Mail is on. Arrival notes and digest mail use the address on your notification prefs."
        )
    else:
        paragraphs.append("Mail is off. Notices stay in the Inbox on this box.")
    paragraphs.append(
        "The house does not use a third-party analytics SDK. House pulse on Maintain "
        "is on-box household totals — never a per-reader funnel."
    )
    paragraphs.append(
        "An OPDS catalog link on your Library card lasts 180 days. Anyone with that "
        "link can browse the shelves; copy it only into your own reader app."
    )
    paragraphs.append(
        "You can export your card (identity, prefs, progress, owned shelves, whispers, "
        "and Inbox — never passwords, sessions, or other members). Ask whoever runs the "
        "library to pause or delete a card: pause revokes sessions; delete removes live "
        "personal rows and anonymizes audit/job pointers. Snapshots already taken may "
        "still hold a copy until they age off at 35 days."
    )
    return {"title": "How this household library treats your card", "paragraphs": paragraphs}


def member_export_payload(db: Database, user_id: str) -> Dict[str, Any]:
    """Self-export bundle plus schema version, timestamp, and field checklist (PRIV-002)."""
    bundle = db.export_member_bundle(user_id)
    bundle["exported_from"] = "librarian"
    bundle["export_version"] = EXPORT_SCHEMA_VERSION
    bundle["generated_at"] = time.time()
    bundle["checklist"] = export_field_checklist()
    return bundle
