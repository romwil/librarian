"""Shelf health: library-root writability report + PUID ownership guidance."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from librarian.config import Settings

# Match Maintain / HELP / AUTOMAT copy for Calibre-migrated uid-1000 trees.
CHOWN_TIP = (
    "If Review Apply says a folder is locked for the lamp, author trees under the "
    "books root were often migrated as the wrong PUID (uid 1000 with mode 755). "
    "On the host, run: chown -R 99:100 /mnt/user/data/media/library/books "
    "(match the container PUID/PGID), then Apply again. Do not chmod 777."
)

CHOWN_COMMAND = "chown -R 99:100 /mnt/user/data/media/library/books"

_ROOT_FIELDS = (
    ("books_root", "Books"),
    ("magazines_root", "Magazines"),
    ("comics_root", "Comics"),
    ("audiobooks_root", "Audiobooks"),
    ("music_root", "Music"),
)


def _probe_writable(root: Path) -> Dict[str, Any]:
    """Best-effort writability probe without creating lasting clutter."""
    exists = root.exists()
    is_dir = root.is_dir() if exists else False
    writable = False
    detail = ""
    if not exists:
        detail = "missing"
    elif not is_dir:
        detail = "not a directory"
    else:
        probe = root / ".librarian-write-probe"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            writable = True
            detail = "writable"
        except PermissionError:
            detail = "permission denied"
        except OSError as error:
            detail = str(error) or "not writable"
    uid = os.environ.get("PUID") or ""
    return {
        "path": str(root),
        "exists": exists,
        "is_dir": is_dir,
        "writable": writable,
        "detail": detail,
        "puid": uid,
    }


def shelf_permission_report(settings: Settings) -> Dict[str, Any]:
    """Report writability of configured library roots for Maintain Shelf health."""
    roots: List[Dict[str, Any]] = []
    locked = 0
    for field, label in _ROOT_FIELDS:
        raw = str(getattr(settings, field, "") or "").strip()
        if not raw:
            continue
        entry = _probe_writable(Path(raw))
        entry["field"] = field
        entry["label"] = label
        if entry["exists"] and entry["is_dir"] and not entry["writable"]:
            locked += 1
        roots.append(entry)
    return {
        "roots": roots,
        "locked_count": locked,
        "ok": locked == 0,
        "chown_tip": CHOWN_TIP,
        "chown_command": CHOWN_COMMAND,
        "puid": os.environ.get("PUID") or "",
        "pgid": os.environ.get("PGID") or "",
    }


__all__ = [
    "CHOWN_COMMAND",
    "CHOWN_TIP",
    "shelf_permission_report",
]
