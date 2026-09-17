"""Serve organized files to the household (open inline or download)."""

from __future__ import annotations

import mimetypes
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable, Sequence

INLINE_TYPES = {
    ".pdf": "application/pdf",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".m4b": "audio/mp4",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
    ".aac": "audio/aac",
    ".wma": "audio/x-ms-wma",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".txt": "text/plain",
}

# Mutagen-known audio containers safe for on-page HTML5 stream (never EPUB/PDF/zip).
STREAMABLE_AUDIO_EXTS = frozenset(
    {".mp3", ".m4a", ".m4b", ".flac", ".ogg", ".opus", ".wav", ".aac", ".wma"}
)

READING_TYPES = {
    ".epub": "application/epub+zip",
    ".cbz": "application/vnd.comicbook+zip",
    ".pdf": "application/pdf",
}

READABLE_KINDS = frozenset({"book", "magazine", "comic"})
_READING_RANK = {".epub": 0, ".cbz": 1, ".pdf": 2}

_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def safe_filename(name: str, fallback: str = "volume") -> str:
    cleaned = _UNSAFE.sub(" ", str(name or "")).strip(" .") or fallback
    return cleaned[:120]


def media_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in READING_TYPES:
        return READING_TYPES[suffix]
    if suffix in INLINE_TYPES:
        return INLINE_TYPES[suffix]
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def is_inline_media(path: Path) -> bool:
    return path.suffix.lower() in INLINE_TYPES


def is_streamable_audio(path: Path) -> bool:
    """True when the path is a single audio file safe for household HTML5 playback."""
    return path.suffix.lower() in STREAMABLE_AUDIO_EXTS


def is_reading_file(path: Path) -> bool:
    return path.suffix.lower() in READING_TYPES


def primary_reading_path(paths: Sequence[Path]) -> Path | None:
    readable = [path for path in paths if is_reading_file(path)]
    if not readable:
        return None
    readable.sort(key=lambda path: (_READING_RANK.get(path.suffix.lower(), 9), path.name.lower()))
    return readable[0]


def can_read_work(kind: str, paths: Sequence[Path]) -> bool:
    return str(kind or "") in READABLE_KINDS and primary_reading_path(paths) is not None


def existing_file_paths(rows: Iterable[dict]) -> list[Path]:
    out: list[Path] = []
    for row in rows:
        path = Path(str((row or {}).get("path") or ""))
        if path.is_file():
            out.append(path)
    return out


def annotate_work_files(rows: Iterable[dict], on_disk: Sequence[Path]) -> list[dict]:
    """Mark which catalog files exist and which are Reading Room sources.

    Every on-disk EPUB/CBZ/PDF is marked ``reading_room`` so multi-file magazines
    can open any volume. ``primary_reading_path`` still picks the default Open.
    """
    reading_keys: set[Path] = set()
    for path in on_disk:
        if not is_reading_file(path):
            continue
        try:
            reading_keys.add(path.resolve())
        except OSError:
            reading_keys.add(path)
    out: list[dict] = []
    for row in rows:
        item = dict(row or {})
        path = Path(str(item.get("path") or ""))
        exists = path.is_file()
        item["on_disk"] = exists
        room = False
        if exists and reading_keys:
            try:
                room = path.resolve() in reading_keys
            except OSError:
                room = path in reading_keys
        item["reading_room"] = room
        out.append(item)
    return out


def resolve_catalog_file(rows: Iterable[dict], file_id: str) -> Path | None:
    """Return the on-disk path for a work file id, or None if missing/wrong work."""
    wanted = str(file_id or "").strip()
    if not wanted:
        return None
    for row in rows:
        if str((row or {}).get("id") or "") != wanted:
            continue
        path = Path(str((row or {}).get("path") or ""))
        return path if path.is_file() else None
    return None


def zip_files(paths: Sequence[Path]) -> Path:
    tmp = tempfile.NamedTemporaryFile(
        prefix="librarian-",
        suffix=".zip",
        delete=False,
    )
    tmp_path = Path(tmp.name)
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED) as archive:
            for path in paths:
                archive.write(path, arcname=path.name)
    finally:
        tmp.close()
    return tmp_path
