"""Member export and the household privacy notice generated from live config."""

from __future__ import annotations

from typing import Any, Dict, List

from librarian.db import Database
from librarian.mail import mail_configured


def household_privacy_notice(settings: Any) -> Dict[str, Any]:
    """Plain-language notice. No secrets. Derived from the running config."""
    paragraphs: List[str] = [
        "Librarian is a household library on this box. There is no public account, "
        "and nothing here is sold or sent to an advertising company.",
        "Your reading place, favorites, and asks stay on this host. Finished titles "
        "are private unless you choose to tell the house.",
        "Invites last 7 days. A forgotten-password link lasts 24 hours and works once. "
        "Signing out of every device, or changing your password, ends other sessions. "
        "Nightly snapshots of the catalog are kept for 35 days.",
    ]
    llm_on = bool(str(getattr(settings, "llm_api_key", "") or "").strip())
    provider = str(getattr(settings, "llm_provider", "") or "").strip() or "the language model"
    if llm_on:
        paragraphs.append(
            f"When a keeper identifies a title, the cover and filename may be sent to {provider} "
            "so the shelves can be named. Readers' search stays on the shelves unless they ask the house."
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
    if mail_configured(settings):
        paragraphs.append(
            "Mail is on. Arrival notes and digest mail use the address on your notification prefs."
        )
    else:
        paragraphs.append("Mail is off. Notices stay in the Inbox on this box.")
    paragraphs.append("The house does not use a third-party analytics SDK.")
    paragraphs.append(
        "You can export your card, or ask whoever runs the library to disable or delete it. "
        "Delete removes your progress, shelves, whispers, and notices from the live database. "
        "Snapshots already taken may still hold a copy until they age off at 35 days."
    )
    return {"title": "How this household library treats your card", "paragraphs": paragraphs}


def member_export_payload(db: Database, user_id: str) -> Dict[str, Any]:
    bundle = db.export_member_bundle(user_id)
    bundle["exported_from"] = "librarian"
    return bundle
