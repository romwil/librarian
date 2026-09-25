"""Personalized library newsletter editions (weekly / monthly cadence)."""

from __future__ import annotations

import logging
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence

from librarian.notifications.kinds import normalize_newsletter_timing
from librarian.notifications.prefs import (
    _nested_from_row,
    get_kind_pref,
    get_newsletter_last_edition_at,
    stamp_newsletter_last_edition,
)
from librarian.notifications.service import deliver_notification

logger = logging.getLogger(__name__)

EDITION_PICK_CAP = 8
WEEKLY_SECONDS = 6.5 * 86400
MONTHLY_SECONDS = 28 * 86400
DEFAULT_LOOKBACK_WEEKLY = 7 * 86400
DEFAULT_LOOKBACK_MONTHLY = 31 * 86400

KIND_LABELS = {
    "book": "books",
    "audiobook": "audiobooks",
    "comic": "comics",
    "magazine": "magazines",
    "music": "music",
}


def _display_name(user: Dict[str, Any]) -> str:
    return str(user.get("display_name") or user.get("preferred_name") or "there").strip() or "there"


def _format_title_line(work: Dict[str, Any]) -> str:
    title = str(work.get("title") or "Untitled").strip() or "Untitled"
    author = str(work.get("author") or "").strip()
    year = work.get("year")
    bits = [title]
    if author:
        bits.append(f"by {author}")
    if year not in (None, ""):
        bits.append(f"({year})")
    return "• " + " ".join(bits)


def structured_edition_picks(
    works: Sequence[Dict[str, Any]],
    *,
    limit: int = EDITION_PICK_CAP,
) -> List[Dict[str, Any]]:
    """Normalize works into inbox pick rows (fail-closed without an id)."""
    picks: List[Dict[str, Any]] = []
    cap = max(1, min(int(limit), EDITION_PICK_CAP))
    for work in works or []:
        if not isinstance(work, dict):
            continue
        work_id = str(work.get("id") or "").strip()
        title = str(work.get("title") or "").strip()
        if not work_id or not title:
            continue
        pick: Dict[str, Any] = {
            "id": work_id,
            "title": title,
            "kind": str(work.get("kind") or "book"),
        }
        author = str(work.get("author") or "").strip()
        if author:
            pick["author"] = author
        year = work.get("year")
        if year not in (None, ""):
            try:
                pick["year"] = int(year)
            except (TypeError, ValueError):
                pass
        genre = str(work.get("genre") or "").strip()
        if genre:
            pick["genre"] = genre
        if work.get("cover_path") or work.get("has_cover"):
            pick["has_cover"] = True
        picks.append(pick)
        if len(picks) >= cap:
            break
    return picks


def gather_taste_signals(db: Any, user_id: str) -> Dict[str, Any]:
    """Collect Continue / Favorites / completed Request signals for intro voice."""
    uid = str(user_id or "").strip()
    authors: Counter[str] = Counter()
    genres: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    sample_titles: List[str] = []

    def _note(work: Dict[str, Any], *, weight: int = 1) -> None:
        if not isinstance(work, dict):
            return
        author = str(work.get("author") or "").strip()
        if author:
            authors[author] += weight
        genre = str(work.get("genre") or "").strip()
        if genre:
            # Genre may be comma-separated.
            for part in genre.replace(";", ",").split(","):
                cleaned = part.strip()
                if cleaned:
                    genres[cleaned] += weight
        kind = str(work.get("kind") or "").strip().lower()
        if kind:
            kinds[kind] += weight
        title = str(work.get("title") or "").strip()
        if title and title not in sample_titles and len(sample_titles) < 4:
            sample_titles.append(title)

    if uid:
        try:
            for work in db.continue_works(uid, limit=8) or []:
                _note(work, weight=3)
        except Exception:  # noqa: BLE001
            logger.exception("taste: continue_works failed for %s", uid)
        try:
            for work in db.favorite_works(uid, limit=8) or []:
                _note(work, weight=2)
        except Exception:  # noqa: BLE001
            logger.exception("taste: favorite_works failed for %s", uid)
        try:
            for job in db.list_completed_jobs_for_user(uid, limit=8) or []:
                # Prefer linked work when present; else job title/kind.
                work_id = str(job.get("work_id") or "").strip()
                work = db.get_work(work_id) if work_id and hasattr(db, "get_work") else None
                if work:
                    _note(work, weight=2)
                else:
                    _note(
                        {
                            "title": job.get("title"),
                            "kind": job.get("kind"),
                            "author": "",
                            "genre": "",
                        },
                        weight=1,
                    )
        except Exception:  # noqa: BLE001
            logger.exception("taste: completed jobs failed for %s", uid)

    return {
        "authors": [name for name, _ in authors.most_common(3)],
        "genres": [name for name, _ in genres.most_common(3)],
        "kinds": [name for name, _ in kinds.most_common(3)],
        "sample_titles": sample_titles,
    }


def shape_intro(tastes: Dict[str, Any], *, preferred: str) -> str:
    """Warm one-liner from taste signals — recognition without surveillance."""
    genres = list(tastes.get("genres") or [])
    authors = list(tastes.get("authors") or [])
    kinds = list(tastes.get("kinds") or [])
    kind_phrase = KIND_LABELS.get(kinds[0], kinds[0]) if kinds else ""

    if genres and authors:
        return (
            f"{preferred}, you've been keeping close company with {genres[0]} "
            f"and {authors[0]} — here's what landed since your last letter."
        )
    if genres:
        return (
            f"{preferred}, the house noticed you've been leaning into {genres[0]} — "
            "here are a few that arrived for the shelves."
        )
    if authors:
        return (
            f"{preferred}, with {authors[0]} still on your mind, "
            "here is what has settled on the shelves since last time."
        )
    if kind_phrase:
        return (
            f"{preferred}, a short letter about recent {kind_phrase} "
            "and whatever else found a place this period."
        )
    return (
        f"{preferred}, a quiet letter from the library — "
        "recent arrivals, nothing you didn't ask the house to remember."
    )


def edition_lookback_seconds(cadence: str) -> float:
    cleaned = normalize_newsletter_timing(cadence)
    if cleaned == "monthly":
        return DEFAULT_LOOKBACK_MONTHLY
    return DEFAULT_LOOKBACK_WEEKLY


def edition_due(
    user_prefs: Dict[str, Any],
    *,
    now: Optional[float] = None,
    force: bool = False,
) -> bool:
    """Whether this member is due for an edition (opt-in + cadence)."""
    if force:
        pref = get_kind_pref(user_prefs, "newsletter")
        return bool(pref.get("enabled"))
    pref = get_kind_pref(user_prefs, "newsletter")
    if not pref.get("enabled"):
        return False
    cadence = normalize_newsletter_timing(pref.get("timing"))
    last = get_newsletter_last_edition_at(user_prefs)
    if last is None:
        return True
    ts = time.time() if now is None else float(now)
    gap = WEEKLY_SECONDS if cadence == "weekly" else MONTHLY_SECONDS
    return (ts - float(last)) >= gap


def build_member_edition(
    db: Any,
    *,
    user: Dict[str, Any],
    user_prefs: Optional[Dict[str, Any]] = None,
    now: Optional[float] = None,
    since_ts: Optional[float] = None,
) -> Dict[str, Any]:
    """Build personalized subject + body + picks for one member."""
    prefs = user_prefs if user_prefs is not None else db.get_user_prefs(str(user["id"]))
    pref = get_kind_pref(prefs, "newsletter")
    cadence = normalize_newsletter_timing(pref.get("timing"))
    ts = time.time() if now is None else float(now)
    last = get_newsletter_last_edition_at(prefs)
    if since_ts is not None:
        window_start = float(since_ts)
    elif last is not None:
        window_start = float(last)
    else:
        window_start = ts - edition_lookback_seconds(cadence)

    preferred = _display_name(user)
    tastes = gather_taste_signals(db, str(user["id"]))
    intro = shape_intro(tastes, preferred=preferred)
    try:
        recent = db.list_works_added_since(window_start, limit=EDITION_PICK_CAP, require_files=True)
    except Exception:  # noqa: BLE001
        logger.exception("edition: list_works_added_since failed")
        recent = []
    picks = structured_edition_picks(recent)
    count = len(picks)
    title_lines = "\n".join(_format_title_line(p) for p in picks) or (
        "• Quiet stretch — nothing new settled on the shelves yet."
    )
    period_word = "month" if cadence == "monthly" else "week"
    subject = f"Your library letter, {preferred}"
    body = (
        f"Hi {preferred},\n\n"
        f"{intro}\n\n"
        f"New since your last letter: {count} title{'s' if count != 1 else ''} "
        f"this {period_word}.\n"
        f"{title_lines}\n\n"
        "Open the Hall anytime — the lamp is on.\n"
    )
    return {
        "subject": subject,
        "body": body,
        "title": subject,
        "blurb": intro,
        "picks": picks,
        "cadence": cadence,
        "since_ts": window_start,
        "tastes": tastes,
    }


def deliver_editions(
    db: Any,
    settings: Any,
    *,
    now: Optional[float] = None,
    user_ids: Optional[Sequence[str]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Fan out opt-in newsletter editions (inbox + email prefs). Never force-email."""
    ts = time.time() if now is None else float(now)
    skipped_disabled = 0
    skipped_opt_out = 0
    skipped_not_due = 0
    skipped_missing = 0
    candidates: List[Dict[str, Any]] = []

    if user_ids is None:
        candidates = list(db.list_users() if hasattr(db, "list_users") else [])
    else:
        seen: set[str] = set()
        for raw_id in user_ids:
            uid = str(raw_id or "").strip()
            if not uid or uid in seen:
                continue
            seen.add(uid)
            row = db.get_user(uid)
            if row is None:
                skipped_missing += 1
                continue
            candidates.append(row)

    delivered = 0
    emailed = 0
    targeted = 0
    results: List[Dict[str, Any]] = []

    for user in candidates:
        if user.get("disabled"):
            skipped_disabled += 1
            continue
        targeted += 1
        uid = str(user["id"])
        prefs = db.get_user_prefs(uid)
        if not get_kind_pref(prefs, "newsletter").get("enabled"):
            skipped_opt_out += 1
            continue
        if not edition_due(prefs, now=ts, force=force):
            skipped_not_due += 1
            continue

        content = build_member_edition(db, user=user, user_prefs=prefs, now=ts)
        related = f"newsletter-{content['cadence']}-{int(ts // 86400)}"
        result = deliver_notification(
            db,
            settings,
            user_id=uid,
            kind="newsletter",
            title=content["title"],
            body=content["body"],
            payload={
                "newsletter": content["cadence"],
                "picks": content.get("picks") or [],
                "blurb": content.get("blurb") or "",
                "path": "/inbox",
            },
            related_id=related,
            email_subject=content["subject"],
        )
        # Stamp last edition only when something actually landed.
        if result.get("notification") or result.get("emailed"):
            nested = stamp_newsletter_last_edition(_nested_from_row(prefs), when=ts)
            db.set_user_prefs(uid, prefs=nested)
            if result.get("notification"):
                delivered += 1
            if result.get("emailed"):
                emailed += 1
        results.append(
            {
                "user_id": uid,
                "notification": result.get("notification"),
                "emailed": result.get("emailed"),
                "skipped": result.get("skipped"),
            }
        )

    return {
        "delivered": delivered,
        "emailed": emailed,
        "targeted": targeted,
        "skipped_opt_out": skipped_opt_out,
        "skipped_not_due": skipped_not_due,
        "skipped_disabled": skipped_disabled,
        "skipped_missing": skipped_missing,
        "force": bool(force),
        "results": results,
    }


def resolve_push_user_ids(
    db: Any,
    *,
    scope: str,
    actor_id: str,
    user_ids: Optional[Sequence[str]] = None,
) -> List[str]:
    """Map owner push scope → concrete user ids (opt-in still enforced at deliver)."""
    cleaned = str(scope or "self").strip().lower()
    if cleaned in {"self", "me"}:
        return [str(actor_id)]
    if cleaned in {"users", "selected"}:
        out: List[str] = []
        seen: set[str] = set()
        for raw in user_ids or []:
            uid = str(raw or "").strip()
            if not uid or uid in seen:
                continue
            seen.add(uid)
            out.append(uid)
        return out
    # all / opted_in
    users = list(db.list_users() if hasattr(db, "list_users") else [])
    return [str(u["id"]) for u in users if u and not u.get("disabled")]
