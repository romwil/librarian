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


def encode_listen_position(*, file_id: str = "", seconds: float = 0.0) -> str:
    """Compact bookmark stored in progress.position."""
    fid = _text(file_id)
    secs = max(0.0, float(seconds or 0.0))
    if not fid and secs <= 0:
        return ""
    return json.dumps({"file": fid, "t": round(secs, 3)}, separators=(",", ":"))


def decode_listen_position(raw: Any) -> Dict[str, Any]:
    text = _text(raw)
    if not text:
        return {"file_id": "", "seconds": 0.0}
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {"file_id": "", "seconds": 0.0}
        if isinstance(data, dict):
            return {
                "file_id": _text(data.get("file") or data.get("file_id")),
                "seconds": max(0.0, float(data.get("t") or data.get("seconds") or 0.0)),
            }
    # Legacy "fileId:seconds"
    if ":" in text:
        left, right = text.rsplit(":", 1)
        try:
            return {"file_id": _text(left), "seconds": max(0.0, float(right))}
        except ValueError:
            return {"file_id": _text(text), "seconds": 0.0}
    return {"file_id": text, "seconds": 0.0}


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
    """Deep-link to ABS item when matched; soft Plex handoff when that is the target."""
    if not work or _text(work.get("kind")) != KIND_AUDIOBOOK:
        return None
    abs_url = _text(getattr(settings, "audiobookshelf_url", ""))
    item_id = _text(work.get("abs_item_id"))
    href = abs_item_href(abs_url, item_id)
    if href:
        return {"href": href, "label": "Open in player", "provider": "audiobookshelf"}
    target = _text(getattr(settings, "audiobook_target", "plex")).lower() or "plex"
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
