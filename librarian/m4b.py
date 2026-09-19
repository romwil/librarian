"""Multipart audio → single M4B via ffmpeg (chapters, tags, cover, faststart)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from librarian.convert import RunTool, run_tool

logger = logging.getLogger(__name__)

AUDIO_SUFFIXES = {".mp3", ".m4a", ".m4b", ".flac", ".ogg", ".opus", ".aac", ".wav"}
_remux_lock = threading.Lock()

RunProbe = Callable[..., subprocess.CompletedProcess]


def which_ffmpeg() -> Optional[str]:
    return shutil.which("ffmpeg")


def which_ffprobe() -> Optional[str]:
    return shutil.which("ffprobe")


def list_audio_sources(folder: Path) -> List[Path]:
    if not folder.is_dir():
        return []
    found = [
        path
        for path in sorted(folder.rglob("*"))
        if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES
    ]
    return found


def needs_m4b_remux(sources: Sequence[Path]) -> bool:
    """Remux when multipart or non-m4b spoken-word payload."""
    if not sources:
        return False
    if len(sources) > 1:
        return True
    return sources[0].suffix.lower() != ".m4b"


def probe_duration_seconds(path: Path, *, runner: RunTool = run_tool) -> float:
    ffprobe = which_ffprobe()
    if not ffprobe:
        return 0.0
    result = runner(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout=60,
    )
    if result.returncode != 0:
        return 0.0
    try:
        return max(0.0, float((result.stdout or b"").decode("utf-8", errors="ignore").strip() or 0))
    except ValueError:
        return 0.0


def chapters_from_boundaries(
    sources: Sequence[Path],
    *,
    runner: RunTool = run_tool,
    titles: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Build chapter markers from per-file durations (track boundaries)."""
    chapters: List[Dict[str, Any]] = []
    cursor = 0.0
    for index, path in enumerate(sources):
        title = ""
        if titles and index < len(titles):
            title = str(titles[index] or "").strip()
        if not title:
            title = path.stem
        chapters.append({"index": index, "title": title, "start": cursor})
        cursor += probe_duration_seconds(path, runner=runner)
    return chapters


def chapters_from_audnexus(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize Audnexus chapter payloads to {index,title,start}."""
    out: List[Dict[str, Any]] = []
    for index, row in enumerate(rows or []):
        start = row.get("startOffsetMs")
        if start is None:
            start = row.get("start")
        try:
            if start is not None and float(start) > 1000:
                start_s = float(start) / 1000.0
            else:
                start_s = float(start or 0)
        except (TypeError, ValueError):
            start_s = 0.0
        title = str(row.get("title") or row.get("name") or f"Chapter {index + 1}").strip()
        out.append({"index": index, "title": title, "start": max(0.0, start_s)})
    return out


def _write_ffmetadata(chapters: Sequence[Mapping[str, Any]], dest: Path, *, total_ms: int = 0) -> Path:
    lines = [";FFMETADATA1"]
    for index, row in enumerate(chapters):
        start_ms = int(float(row.get("start") or 0) * 1000)
        if index + 1 < len(chapters):
            end_ms = int(float(chapters[index + 1].get("start") or 0) * 1000)
        else:
            end_ms = total_ms if total_ms > start_ms else start_ms + 1000
        title = str(row.get("title") or f"Chapter {index + 1}").replace("=", "\\=").replace(";", "\\;")
        lines.extend(
            [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={start_ms}",
                f"END={end_ms}",
                f"title={title}",
            ]
        )
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest


def _write_concat_list(sources: Sequence[Path], dest: Path) -> Path:
    lines = []
    for path in sources:
        # ffmpeg concat demuxer needs escaped single quotes
        escaped = str(path.resolve()).replace("'", r"'\''")
        lines.append(f"file '{escaped}'")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest


def validate_m4b(path: Path, *, runner: RunTool = run_tool) -> bool:
    if not path.is_file() or path.stat().st_size < 64:
        return False
    if path.suffix.lower() != ".m4b" and path.suffix.lower() != ".m4a":
        return False
    duration = probe_duration_seconds(path, runner=runner)
    return duration > 0 or which_ffprobe() is None


def build_m4b(
    sources: Sequence[Path],
    dest: Path,
    *,
    chapters: Optional[Sequence[Mapping[str, Any]]] = None,
    tags: Optional[Mapping[str, Any]] = None,
    cover: Optional[Path] = None,
    runner: RunTool = run_tool,
    work_dir: Optional[Path] = None,
) -> Path:
    """Concat sources into dest (.m4b). Raises RuntimeError on failure."""
    ffmpeg = which_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is not installed")
    sources = [Path(path) for path in sources if Path(path).is_file()]
    if not sources:
        raise RuntimeError("no audio sources for M4B remux")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(work_dir) if work_dir else dest.parent / f".m4b-staging-{dest.stem}"
    scratch.mkdir(parents=True, exist_ok=True)
    concat_list = _write_concat_list(sources, scratch / "concat.txt")
    staging = scratch / "output.m4b"
    meta_path = scratch / "ffmetadata.txt"

    chapter_rows = list(chapters or [])
    if not chapter_rows and len(sources) > 1:
        chapter_rows = chapters_from_boundaries(sources, runner=runner)

    total_ms = 0
    if chapter_rows:
        last_start = float(chapter_rows[-1].get("start") or 0)
        # Approximate end from sum of source durations when available.
        total = sum(probe_duration_seconds(path, runner=runner) for path in sources)
        total_ms = int(max(total, last_start + 1) * 1000)
        _write_ffmetadata(chapter_rows, meta_path, total_ms=total_ms)

    argv = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list)]
    if chapter_rows and meta_path.is_file():
        argv.extend(["-i", str(meta_path), "-map_metadata", "1"])
    if cover and Path(cover).is_file():
        argv.extend(["-i", str(cover), "-map", "0", "-map", f"{2 if chapter_rows else 1}", "-c:v", "copy", "-disposition:v:0", "attached_pic"])
    else:
        argv.extend(["-map", "0"])
    tag_map = dict(tags or {})
    for key, flag in (
        ("title", "title"),
        ("author", "artist"),
        ("album", "album"),
        ("narrator", "composer"),
        ("year", "date"),
        ("asin", "comment"),
        ("genre", "genre"),
    ):
        value = tag_map.get(key)
        if value not in (None, ""):
            argv.extend(["-metadata", f"{flag}={value}"])
    if tag_map.get("author"):
        argv.extend(["-metadata", f"album_artist={tag_map['author']}"])
    argv.extend(["-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(staging)])

    result = runner(argv, timeout=3600)
    if result.returncode != 0 or not staging.is_file():
        err = (result.stderr or b"").decode("utf-8", errors="ignore")[-400:]
        raise RuntimeError(f"ffmpeg M4B remux failed: {err or result.returncode}")
    if not validate_m4b(staging, runner=runner):
        raise RuntimeError("M4B validation failed after remux")
    if dest.exists():
        dest.unlink()
    shutil.move(str(staging), str(dest))
    return dest


def maybe_remux_audiobook_folder(
    folder: Path,
    identity: Mapping[str, Any],
    *,
    runner: Optional[RunTool] = None,
    chapters: Optional[Sequence[Mapping[str, Any]]] = None,
    cover: Optional[Path] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Remux audio under folder into a single Title.m4b when eligible.

    Concurrency-1. Leaves folder untouched on skip/failure (caller decides Review).
    """
    run = runner or run_tool
    sources = list_audio_sources(folder)
    if not force and not needs_m4b_remux(sources):
        return {"remuxed": False, "path": str(sources[0]) if sources else "", "reason": "already_m4b"}
    if not which_ffmpeg():
        return {"remuxed": False, "path": "", "reason": "ffmpeg_missing"}
    # Only remux when ASIN-resolved (or force from Review Apply).
    asin = str(identity.get("asin") or "").strip()
    if not force and not asin:
        return {"remuxed": False, "path": "", "reason": "identity_unresolved"}

    title = str(identity.get("title") or "Audiobook").strip() or "Audiobook"
    dest = Path(folder) / f"{title}.m4b"
    tags = {
        "title": title,
        "author": identity.get("author") or "",
        "album": identity.get("series_name") or title,
        "narrator": identity.get("narrator") or "",
        "year": identity.get("year") or "",
        "asin": asin,
        "genre": identity.get("genre") or "Audiobook",
    }
    with _remux_lock:
        try:
            built = build_m4b(
                sources,
                dest,
                chapters=chapters,
                tags=tags,
                cover=cover,
                runner=run,
                work_dir=Path(folder) / ".m4b-work",
            )
        except RuntimeError as error:
            logger.info("M4B remux skipped: %s", error)
            return {"remuxed": False, "path": "", "reason": str(error)}
        # Purge staging sources only after validate — keep dest.
        for path in sources:
            if path.resolve() != built.resolve():
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        work = Path(folder) / ".m4b-work"
        if work.is_dir():
            shutil.rmtree(work, ignore_errors=True)
        return {"remuxed": True, "path": str(built), "reason": "ok"}
