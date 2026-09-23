"""Byte-identity helpers for ingest duplicate detection.

Prefer size+inode on the same device (hardlinks / same file), then fall back
to a content SHA-256. Used by Add-to-shelves pre-scan and organize collisions.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from librarian.identify import MEDIA_EXTENSIONS, list_payload_files

_CHUNK = 1024 * 1024


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def files_byte_identical(left: Path, right: Path) -> bool:
    """True when both paths exist and hold the same bytes."""
    try:
        left_stat = left.stat()
        right_stat = right.stat()
    except OSError:
        return False
    if left_stat.st_size != right_stat.st_size:
        return False
    if left_stat.st_dev == right_stat.st_dev and left_stat.st_ino == right_stat.st_ino:
        return True
    try:
        return hash_file(left) == hash_file(right)
    except OSError:
        return False


def payload_media_files(target: Path) -> List[Path]:
    """Media files that define a volume for fingerprinting."""
    if not target.exists():
        return []
    if target.is_file():
        if target.suffix.lower() in MEDIA_EXTENSIONS:
            return [target]
        return []
    return list(list_payload_files(target))


def _stat_key(path: Path) -> Optional[Tuple[int, int, int]]:
    try:
        st = path.stat()
    except OSError:
        return None
    return (int(st.st_dev), int(st.st_ino), int(st.st_size))


def volume_content_fingerprint(target: Path) -> Optional[str]:
    """Stable fingerprint for a volume's media payload (None when empty)."""
    files = payload_media_files(target)
    if not files:
        return None
    parts: List[str] = []
    for path in sorted(files, key=lambda item: item.name.lower()):
        key = _stat_key(path)
        if key is None:
            continue
        # Size+inode is enough when comparing copies on the same volume later;
        # content hash distinguishes equal-size distinct files across trees.
        try:
            content = hash_file(path)
        except OSError:
            continue
        parts.append(f"{path.suffix.lower()}:{key[2]}:{content}")
    if not parts:
        return None
    joined = "|".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def payloads_byte_identical(sources: Sequence[Path], dests: Sequence[Path]) -> bool:
    """True when every source/dest pair is byte-identical (order aligned)."""
    if len(sources) != len(dests) or not sources:
        return False
    for src, dest in zip(sources, dests):
        if not files_byte_identical(src, dest):
            return False
    return True


def count_media_files(targets: Iterable[Path]) -> int:
    total = 0
    for target in targets:
        total += len(payload_media_files(target))
    return total
