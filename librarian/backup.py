"""Nightly SQLite snapshots of the catalog.

One verified copy per day (newest 7 kept) plus one per ISO week (newest 4 kept).
Each snapshot is taken with SQLite's online backup API, so a live WAL database
is copied consistently, then ``PRAGMA integrity_check`` runs on the copy before
it is published. A snapshot that fails the check is thrown away and the earlier
ones stay put.

Only the catalog database is copied. ``session_secret`` and ``settings.json``
(API tokens) are never read here, so a backup file can be handed to someone for
support without handing over the keys to the house. Files are 0600 and the
folder is 0700.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BACKUP_DIRNAME = "backups"
KEEP_DAILY = 7
KEEP_WEEKLY = 4

_DAILY_RE = re.compile(r"^librarian-(\d{4}-\d{2}-\d{2})\.db$")
_WEEKLY_RE = re.compile(r"^librarian-weekly-(\d{4}-W\d{2})\.db$")
_TMP_PREFIX = ".tmp-librarian-"

_FILE_MODE = 0o600
_DIR_MODE = 0o700


class BackupError(RuntimeError):
    """A snapshot could not be taken or did not pass its integrity check."""


@dataclass(frozen=True)
class BackupResult:
    daily: Optional[Path]
    weekly: Optional[Path]
    pruned: List[Path]


def backup_dir_for(data_dir: Path) -> Path:
    return Path(data_dir) / BACKUP_DIRNAME


def daily_name(day: date) -> str:
    return f"librarian-{day.isoformat()}.db"


def weekly_name(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"librarian-weekly-{year:04d}-W{week:02d}.db"


def _chmod(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        logger.debug("Could not chmod %s", path, exc_info=True)


def tighten_database_permissions(db_path: Path) -> None:
    """DB and its WAL/SHM sidecars readable by the service user only (PRIV-017)."""
    base = Path(db_path)
    for candidate in (base, base.with_name(base.name + "-wal"), base.with_name(base.name + "-shm")):
        if candidate.exists():
            _chmod(candidate, _FILE_MODE)


def _ensure_dir(backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    _chmod(backup_dir, _DIR_MODE)


def _integrity_ok(conn: sqlite3.Connection) -> None:
    try:
        rows = conn.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.DatabaseError as error:
        raise BackupError(f"Backup failed: {error}") from error
    verdict = [str(row[0]) for row in rows]
    if verdict != ["ok"]:
        detail = "; ".join(verdict[:3])
        raise BackupError(f"Backup failed integrity_check: {detail}")


def _verify_file(path: Path) -> None:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    try:
        _integrity_ok(conn)
    finally:
        conn.close()


def _unlink_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)


def _snapshot(db_path: Path, destination: Path) -> None:
    """Copy ``db_path`` to ``destination`` (a new 0600 file) and verify the copy."""
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _FILE_MODE)
    os.close(fd)
    source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    target = sqlite3.connect(destination)
    try:
        try:
            source.backup(target)
            # A single self-contained file: no -wal/-shm beside the snapshot.
            target.execute("PRAGMA journal_mode=DELETE")
            _integrity_ok(target)
        except sqlite3.DatabaseError as error:
            raise BackupError(f"Backup failed: {error}") from error
    finally:
        target.close()
        source.close()
        _unlink_sidecars(destination)
    _chmod(destination, _FILE_MODE)


def _copy_private(source: Path, destination: Path) -> None:
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _FILE_MODE)
    try:
        with os.fdopen(fd, "wb") as out, open(source, "rb") as src:
            while chunk := src.read(1024 * 1024):
                out.write(chunk)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    _chmod(destination, _FILE_MODE)


def _matching(backup_dir: Path, pattern: re.Pattern[str]) -> List[Path]:
    if not backup_dir.is_dir():
        return []
    found = [p for p in backup_dir.iterdir() if p.is_file() and pattern.match(p.name)]
    return sorted(found, key=lambda p: p.name)


def _prune(backup_dir: Path) -> List[Path]:
    removed: List[Path] = []
    for pattern, keep in ((_DAILY_RE, KEEP_DAILY), (_WEEKLY_RE, KEEP_WEEKLY)):
        files = _matching(backup_dir, pattern)
        for stale in files[: max(0, len(files) - keep)]:
            stale.unlink(missing_ok=True)
            removed.append(stale)
    return removed


def _clear_partials(backup_dir: Path) -> None:
    if not backup_dir.is_dir():
        return
    for leftover in backup_dir.glob(f"{_TMP_PREFIX}*"):
        leftover.unlink(missing_ok=True)


def snapshot_named(db_path: Path, backup_dir: Path, stem: str) -> Path:
    """Write ``backup_dir/{stem}.db`` (0600, integrity-checked). Not rotated with dailies."""
    cleaned = str(stem or "").strip()
    if not cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        raise BackupError("Backup name is not usable")
    db_path = Path(db_path)
    backup_dir = Path(backup_dir)
    _ensure_dir(backup_dir)
    destination = backup_dir / f"{cleaned}.db"
    temp = backup_dir / f"{_TMP_PREFIX}{uuid.uuid4().hex}.db"
    try:
        _snapshot(db_path, temp)
        os.replace(temp, destination)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    _chmod(destination, _FILE_MODE)
    return destination


def run_backup(db_path: Path, backup_dir: Path, *, now: Optional[datetime] = None) -> BackupResult:
    """Take today's snapshot (and this week's, if missing), then prune.

    Re-running on the same day replaces nothing: an existing verified daily is kept.
    """
    db_path = Path(db_path)
    backup_dir = Path(backup_dir)
    day = (now or datetime.now().astimezone()).date()
    _ensure_dir(backup_dir)
    _clear_partials(backup_dir)
    tighten_database_permissions(db_path)

    daily_path = backup_dir / daily_name(day)
    made_daily: Optional[Path] = None
    if not daily_path.exists():
        temp = backup_dir / f"{_TMP_PREFIX}{uuid.uuid4().hex}.db"
        try:
            _snapshot(db_path, temp)
            os.replace(temp, daily_path)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        made_daily = daily_path

    made_weekly: Optional[Path] = None
    weekly_path = backup_dir / weekly_name(day)
    if not weekly_path.exists():
        temp = backup_dir / f"{_TMP_PREFIX}{uuid.uuid4().hex}.db"
        try:
            _copy_private(daily_path, temp)
            _verify_file(temp)
            os.replace(temp, weekly_path)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        made_weekly = weekly_path

    return BackupResult(daily=made_daily, weekly=made_weekly, pruned=_prune(backup_dir))


def backup_due(backup_dir: Path, *, now: Optional[datetime] = None) -> bool:
    day = (now or datetime.now().astimezone()).date()
    folder = Path(backup_dir)
    return not (folder / daily_name(day)).exists() or not (folder / weekly_name(day)).exists()


def backup_status(backup_dir: Path) -> Dict[str, Any]:
    """What Maintain shows: newest snapshot time and how many are on the shelf."""
    daily = _matching(Path(backup_dir), _DAILY_RE)
    weekly = _matching(Path(backup_dir), _WEEKLY_RE)
    newest: Optional[Path] = daily[-1] if daily else None
    last_backup = None
    if newest is not None:
        stamp = datetime.fromtimestamp(newest.stat().st_mtime).astimezone()
        last_backup = stamp.isoformat(timespec="seconds")
    return {
        "last_backup": last_backup,
        "last_backup_file": newest.name if newest else None,
        "daily_count": len(daily),
        "weekly_count": len(weekly),
    }
