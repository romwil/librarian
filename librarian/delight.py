"""Part E blue-sky delight helpers — lean, shippable slices."""

from __future__ import annotations

import re
from datetime import datetime, time, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from librarian.kinds import KIND_AUDIOBOOK, KIND_COMIC, KIND_MUSIC

AMBIENT_CHOICES = ("off", "paper", "lamp")
REVIEW_QUIET_HOURS = "quiet_hours"
WHISPER_MAX_LEN = 280
WHISPER_LIST_LIMIT = 40


def _plain_sentences(text: str, *, max_sentences: int = 2, max_chars: int = 280) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", str(text or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    out: List[str] = []
    for part in parts:
        piece = part.strip()
        if not piece:
            continue
        out.append(piece)
        if len(out) >= max_sentences:
            break
    joined = " ".join(out) if out else cleaned
    if len(joined) > max_chars:
        joined = joined[: max_chars - 1].rstrip() + "…"
    return joined


def cover_story(work: Optional[Mapping[str, Any]]) -> str:
    """Two-sentence Hall/Work wash caption from llm_blurb or description."""
    if not work:
        return ""
    for key in ("llm_blurb", "description"):
        story = _plain_sentences(str(work.get(key) or ""))
        if story:
            return story
    return ""


def pick_fast_gap(gaps: Sequence[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """Prefer a single missing index / multipart hole that looks quick to fill."""
    ranked: List[Dict[str, Any]] = []
    for raw in gaps or []:
        card = dict(raw)
        missing = card.get("series_missing") or card.get("missing") or []
        if isinstance(missing, list):
            miss_n = len(missing)
        else:
            miss_n = 1 if card.get("missing_index") else 0
        if miss_n < 1 and not card.get("missing_index"):
            continue
        score = miss_n if miss_n > 0 else 99
        if card.get("gap_type") == "multipart":
            score = max(1, score)
        ranked.append({**card, "_score": score})
    if not ranked:
        return None
    ranked.sort(key=lambda row: (int(row.get("_score") or 99), str(row.get("title") or "")))
    best = ranked[0]
    best.pop("_score", None)
    return best


def tonight_shelf(
    *,
    continue_items: Sequence[Mapping[str, Any]] = (),
    gaps: Sequence[Mapping[str, Any]] = (),
    surprise: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Hall card: one continue + one fast gap + one Discover surprise."""
    cont = dict(continue_items[0]) if continue_items else None
    gap = pick_fast_gap(gaps)
    disc = dict(surprise) if surprise else None
    return {
        "continue": cont,
        "gap": gap,
        "surprise": disc,
        "empty": not cont and not gap and not disc,
    }


def series_ribbon(
    *,
    owned_indexes: Sequence[object] = (),
    missing_indexes: Sequence[object] = (),
    current: object = None,
    cap: int = 24,
) -> List[Dict[str, str]]:
    """Owned vs hole beads for Work series spine (Gaps taste)."""
    owned = [str(v).strip() for v in owned_indexes if str(v or "").strip()]
    missing = [str(v).strip() for v in missing_indexes if str(v or "").strip()]
    focus = str(current or "").strip()
    if not owned and not missing:
        return []
    order: List[str] = []
    seen = set()
    for value in sorted(set(owned + missing), key=lambda x: (not _numish(x), _num_key(x), x)):
        if value in seen:
            continue
        seen.add(value)
        order.append(value)
    if len(order) > cap:
        idx = order.index(focus) if focus in order else max(0, len(order) - cap)
        start = max(0, idx - cap // 2)
        order = order[start : start + cap]
    owned_set = set(owned)
    out = []
    for value in order:
        if value in owned_set:
            state = "owned"
        elif value == focus:
            state = "current"
        else:
            state = "missing"
        out.append({"value": value, "state": state})
    return out


def _numish(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def _num_key(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0.0


def estimate_finish_eta_minutes(
    *,
    missing_count: int,
    recent_seconds: Sequence[float] = (),
) -> Optional[int]:
    """Cheap ETA from recent SAB/job durations (median), when sample exists."""
    miss = max(0, int(missing_count or 0))
    samples = [float(s) for s in recent_seconds if s is not None and float(s) > 0]
    if miss < 1 or len(samples) < 2:
        return None
    samples.sort()
    mid = samples[len(samples) // 2]
    minutes = int(round((mid * miss) / 60.0))
    return max(1, minutes)


def finish_set_label(*, missing_count: int, eta_minutes: Optional[int] = None) -> str:
    n = max(0, int(missing_count or 0))
    base = f"Request missing ({n})" if n else "Request missing"
    if eta_minutes:
        return f"{base} · ~{eta_minutes} min"
    return base


def regrab_diff(failed: Mapping[str, Any], candidate: Mapping[str, Any]) -> str:
    """Short human diff between failed NZB and next-best alternate."""
    bits: List[str] = []
    ft = str(failed.get("title") or failed.get("name") or "").strip()
    ct = str(candidate.get("title") or candidate.get("name") or "").strip()
    if ct and ct != ft:
        bits.append(ct[:72] + ("…" if len(ct) > 72 else ""))
    fs = _as_int(failed.get("size"))
    cs = _as_int(candidate.get("size"))
    if fs and cs and fs != cs:
        delta = cs - fs
        sign = "+" if delta > 0 else ""
        bits.append(f"{sign}{_fmt_bytes(delta)}")
    host = str(candidate.get("host") or candidate.get("indexer") or "").strip()
    if host:
        bits.append(host)
    return " · ".join(bits) if bits else "Different release"


def rank_regrab_candidates(
    hits: Sequence[Mapping[str, Any]],
    *,
    failed_guid: str = "",
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """Next-best indexer hits with a different guid than the failed repair."""
    failed = str(failed_guid or "").strip()
    out: List[Dict[str, Any]] = []
    seen = set()
    for raw in hits or []:
        guid = str(raw.get("guid") or raw.get("indexer_guid") or "").strip()
        if not guid or guid == failed or guid in seen:
            continue
        seen.add(guid)
        item = dict(raw)
        item["diff"] = regrab_diff({"guid": failed}, item)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def plexamp_handoff(work: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """Toast payload after music Promote — never audiobooks."""
    if not work:
        return None
    kind = str(work.get("kind") or "")
    if kind == KIND_AUDIOBOOK or kind != KIND_MUSIC:
        return None
    title = str(work.get("title") or "Album").strip()
    artist = str(work.get("author") or "").strip()
    return {
        "title": title,
        "artist": artist,
        "kind": KIND_MUSIC,
        "work_id": work.get("id"),
        "has_cover": bool(work.get("cover_path")),
        "href": "plexamp://",
        "message": "On the music shelf for Plexamp",
    }


def parse_hhmm(value: object, default: time) -> time:
    text = str(value or "").strip()
    if not text:
        return default
    match = re.match(r"^(\d{1,2}):(\d{2})$", text)
    if not match:
        return default
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return default
    return time(hour=hour, minute=minute)


def in_quiet_hours(
    settings: Any,
    *,
    now: Optional[datetime] = None,
) -> bool:
    """True when household quiet hours defer unpack/convert."""
    if not bool(getattr(settings, "quiet_hours_enabled", False)):
        return False
    start = parse_hhmm(getattr(settings, "quiet_hours_start", None), time(22, 0))
    end = parse_hhmm(getattr(settings, "quiet_hours_end", None), time(7, 0))
    current = now or datetime.now(timezone.utc).astimezone()
    clock = current.time().replace(second=0, microsecond=0)
    if start == end:
        return False
    if start < end:
        return start <= clock < end
    # Overnight window e.g. 22:00 → 07:00
    return clock >= start or clock < end


def celebration_candidates(
    *,
    kind_counts: Mapping[str, int],
    author_year_counts: Sequence[Mapping[str, Any]] = (),
) -> List[Dict[str, str]]:
    """Quiet Hall celebrations — milestones, not spam."""
    out: List[Dict[str, str]] = []
    comics = int(kind_counts.get(KIND_COMIC) or 0)
    for threshold in (100, 50, 25, 10):
        if comics >= threshold:
            out.append(
                {
                    "key": f"comics-{threshold}",
                    "message": f"Shelved {threshold} comics",
                }
            )
            break
    books = int(kind_counts.get("book") or 0)
    for threshold in (100, 50, 25):
        if books >= threshold:
            out.append(
                {
                    "key": f"books-{threshold}",
                    "message": f"Shelved {threshold} books",
                }
            )
            break
    for row in author_year_counts or []:
        author = str(row.get("author") or "").strip()
        count = int(row.get("count") or 0)
        year = int(row.get("year") or 0)
        if not author or count < 3 or not year:
            continue
        ordinal = {3: "Third", 4: "Fourth", 5: "Fifth"}.get(count)
        if not ordinal:
            if count >= 6:
                ordinal = f"{count}th"
            else:
                continue
        out.append(
            {
                "key": f"author-{author.lower()}-{year}-{count}",
                "message": f"{ordinal} {author} this year",
            }
        )
        break
    return out[:2]


def normalize_ambient(value: object) -> str:
    text = str(value or "off").strip().lower()
    return text if text in AMBIENT_CHOICES else "off"


def sanitize_whisper(body: object) -> str:
    text = re.sub(r"\s+", " ", str(body or "")).strip()
    if len(text) > WHISPER_MAX_LEN:
        text = text[:WHISPER_MAX_LEN].rstrip()
    return text


def _as_int(value: object) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _fmt_bytes(delta: int) -> str:
    n = abs(int(delta))
    for unit, size in (("GB", 1_000_000_000), ("MB", 1_000_000), ("KB", 1000)):
        if n >= size:
            return f"{n / size:.1f}{unit}"
    return f"{n}B"
