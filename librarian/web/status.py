"""Owner /api/status payload and public readiness checks (BD-5, PERF-016)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from librarian import __version__
from librarian.web.build_info import frontend_public_file, parse_build_info, read_build_info
from librarian.whats_new_truth import notes_match_runtime, release_notes_tip


def notes_tip_from_image() -> str:
    """Release-notes tip from the image / package tree, never DATA_DIR (OPS-016)."""
    path = frontend_public_file("release-notes.json")
    if path is None:
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return release_notes_tip(payload)


def last_backup_at(data_dir: Path) -> Optional[str]:
    """Newest snapshot mtime under DATA_DIR/backups, or None when sprint 0.1 has not run."""
    folder = Path(data_dir) / "backups"
    if not folder.is_dir():
        return None
    newest_mtime = 0.0
    found = False
    try:
        entries = list(folder.iterdir())
    except OSError:
        return None
    for path in entries:
        if not path.is_file() or path.suffix != ".db" or path.name.endswith(".tmp"):
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime >= newest_mtime:
            newest_mtime = mtime
            found = True
    if not found:
        return None
    return datetime.fromtimestamp(newest_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def owner_status(*, db: Any, poller: Any, data_dir: Path) -> Dict[str, Any]:
    stamp = parse_build_info(read_build_info())
    notes_version = notes_tip_from_image()
    return {
        "version": __version__,
        "rev": stamp["rev"],
        "built_at": stamp["built_at"],
        "notes_version": notes_version,
        "notes_match": notes_match_runtime(runtime=__version__, notes_version=notes_version),
        "last_backup": last_backup_at(data_dir),
        "poller_alive": bool(poller is not None and getattr(poller, "is_running", False)),
    }


def is_ready(*, db: Any, poller: Optional[Any]) -> bool:
    """True when SQLite answers SELECT 1 and the poller thread is alive."""
    try:
        with db._connect() as conn:
            row = conn.execute("SELECT 1").fetchone()
        if row is None or int(row[0]) != 1:
            return False
    except Exception:
        return False
    return bool(poller is not None and getattr(poller, "is_running", False))
