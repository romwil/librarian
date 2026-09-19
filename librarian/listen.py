"""Audiobook Listen helpers — in-app player handoff + chapter bookmarks."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from librarian.audiobookshelf import normalize_abs_url
from librarian.config import Settings
from librarian.kinds import KIND_AUDIOBOOK
from librarian.serve import is_streamable_audio

logger = logging.getLogger(__name__)


def _text(value: Any) -> str:
    return str(value or "").strip()


def abs_item_href(base_url: str, item_id: str) -> str:
    """Audiobookshelf item deep-link. Empty when either half is missing."""
    base = normalize_abs_url(base_url)
    item = _text(item_id)
    if not base or not item:
        return ""
    return f"{base}/item/{item}"


def encode_listen_position(
    *,
    file_id: str = "",
    seconds: float = 0.0,
    rate: float = 0.0,
) -> str:
    """Compact bookmark stored in progress.position."""
    fid = _text(file_id)
    secs = max(0.0, float(seconds or 0.0))
    if not fid and secs <= 0:
        return ""
    payload: Dict[str, Any] = {"file": fid, "t": round(secs, 3)}
    try:
        playback = float(rate or 0.0)
    except (TypeError, ValueError):
        playback = 0.0
    if playback > 0 and abs(playback - 1.0) > 0.001:
        payload["rate"] = round(playback, 2)
    return json.dumps(payload, separators=(",", ":"))


def decode_listen_position(raw: Any) -> Dict[str, Any]:
    text = _text(raw)
    empty = {"file_id": "", "seconds": 0.0, "rate": 0.0}
    if not text:
        return empty
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return empty
        if isinstance(data, dict):
            try:
                rate = float(data.get("rate") or 0.0)
            except (TypeError, ValueError):
                rate = 0.0
            return {
                "file_id": _text(data.get("file") or data.get("file_id")),
                "seconds": max(0.0, float(data.get("t") or data.get("seconds") or 0.0)),
                "rate": rate if rate > 0 else 0.0,
            }
    # Legacy "fileId:seconds"
    if ":" in text:
        left, right = text.rsplit(":", 1)
        try:
            return {"file_id": _text(left), "seconds": max(0.0, float(right)), "rate": 0.0}
        except ValueError:
            return {"file_id": _text(text), "seconds": 0.0, "rate": 0.0}
    return {"file_id": text, "seconds": 0.0, "rate": 0.0}


def should_write_listen_progress(
    *,
    ready: bool = False,
    seconds: float = 0.0,
    resume_seconds: float = 0.0,
    force: bool = False,
) -> bool:
    """Refuse pre-seek / remount zeros that would wipe a stored bookmark."""
    if not ready and not force:
        return False
    now = max(0.0, float(seconds or 0.0))
    resume = max(0.0, float(resume_seconds or 0.0))
    if resume >= 2.0 and now < 1.0:
        return False
    return True


def split_continue_rails(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Hall Continue vs Continue listening."""
    reading: List[Dict[str, Any]] = []
    listening: List[Dict[str, Any]] = []
    for row in rows or []:
        if _text(row.get("kind")) == KIND_AUDIOBOOK:
            listening.append(row)
        else:
            reading.append(row)
    return {"reading": reading, "listening": listening}


def listen_fraction(*, file_index: int, file_count: int, local_fraction: float) -> float:
    """Overall 0..1 progress across ordered audio files."""
    count = max(1, int(file_count or 1))
    index = max(0, min(count - 1, int(file_index or 0)))
    local = max(0.0, min(1.0, float(local_fraction or 0.0)))
    return max(0.0, min(0.999, (index + local) / count))


def extract_chapters(path: Path) -> List[Dict[str, Any]]:
    """Chapter list from mutagen (m4b/mp4 + ID3 CHAP). Empty when unknown."""
    target = Path(path)
    if not target.is_file() or not is_streamable_audio(target):
        return []
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        return []
    try:
        audio = MutagenFile(str(target), easy=False)
    except Exception as error:  # noqa: BLE001 — tag parse must never break Listen
        logger.debug("chapter read skipped for %s: %s", target.name, error)
        return []
    if audio is None:
        return []

    chapters: List[Dict[str, Any]] = []
    mp4_chapters = getattr(audio, "chapters", None)
    if mp4_chapters:
        for index, row in enumerate(list(mp4_chapters)):
            start = float(getattr(row, "start", 0) or 0)
            title = _text(getattr(row, "title", "") or f"Chapter {index + 1}")
            chapters.append({"index": index, "title": title, "start": start})

    if not chapters:
        try:
            from mutagen.id3 import CHAP, ID3
        except ImportError:
            CHAP = None  # type: ignore[misc, assignment]
            ID3 = None  # type: ignore[misc, assignment]
        if ID3 is not None and CHAP is not None:
            try:
                tags = ID3(str(target))
            except Exception:  # noqa: BLE001
                tags = None
            if tags is not None:
                chap_frames = [frame for frame in tags.values() if isinstance(frame, CHAP)]
                chap_frames.sort(key=lambda frame: float(getattr(frame, "start_time", 0) or 0) / 1000.0)
                for index, frame in enumerate(chap_frames):
                    start_ms = float(getattr(frame, "start_time", 0) or 0)
                    title = ""
                    sub = getattr(frame, "sub_frames", None) or {}
                    for key, value in dict(sub).items():
                        if str(key).startswith("TIT"):
                            title = _text(getattr(value, "text", [""])[0] if getattr(value, "text", None) else value)
                            break
                    chapters.append(
                        {
                            "index": index,
                            "title": title or f"Chapter {index + 1}",
                            "start": start_ms / 1000.0,
                        }
                    )

    return chapters


def audiobook_player_link(
    work: Optional[Mapping[str, Any]],
    settings: Settings,
) -> Optional[Dict[str, Any]]:
    """Deep-link to ABS when matched; soft Plex handoff when that is the target."""
    if not work or _text(work.get("kind")) != KIND_AUDIOBOOK:
        return None
    abs_url = _text(getattr(settings, "audiobookshelf_url", ""))
    item_id = _text(work.get("abs_item_id"))
    target = _text(getattr(settings, "audiobook_target", "plex")).lower() or "plex"
    href = abs_item_href(abs_url, item_id)
    # Prefer ABS when target is Audiobookshelf, or whenever the title is already matched.
    if href and (target == "audiobookshelf" or item_id):
        return {"href": href, "label": "Open in player", "provider": "audiobookshelf"}
    if target == "plex":
        return {"href": "plex://", "label": "Open in Plex", "provider": "plex"}
    if target == "audiobookshelf" and abs_url and not item_id:
        return None
    return None


def player_empty_note(work: Optional[Mapping[str, Any]], settings: Settings) -> str:
    """Honest empty when neither ABS match nor Plex target applies."""
    if not work or _text(work.get("kind")) != KIND_AUDIOBOOK:
        return ""
    if audiobook_player_link(work, settings):
        return ""
    target = _text(getattr(settings, "audiobook_target", "plex")).lower() or "plex"
    abs_url = _text(getattr(settings, "audiobookshelf_url", ""))
    if target == "audiobookshelf" and abs_url and not _text(work.get("abs_item_id")):
        return "Not matched to Audiobookshelf yet — run Match from Settings."
    if target == "librarian_only":
        return "Listening stays in Librarian for this household."
    return ""


def listen_payload(
    work: Optional[Mapping[str, Any]],
    *,
    can_download: bool,
    settings: Settings,
) -> Dict[str, Any]:
    kind = _text((work or {}).get("kind"))
    can_listen = kind == KIND_AUDIOBOOK and bool(can_download)
    player = audiobook_player_link(work, settings) if can_listen else None
    note = player_empty_note(work, settings) if can_listen else ""
    return {
        "can_listen": can_listen,
        "player": player,
        "player_note": note,
    }
