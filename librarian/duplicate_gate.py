"""Duplicate evidence and the pre-slip duplicate gate.

Evidence for one slip against what is already shelved:

- ``exact_fingerprint``: the slip's media bytes match a shelved folder or another slip.
- ``same_shelved_identity``: same kind + title + author (or ISBN / series) as a shelved
  work, but different bytes.
- ``same_normalized_identity``: title and author match a shelved work only after
  normalizing punctuation, articles, and "Last, First" order.
- ``unassessable``: the slip folder has no readable media to fingerprint.

The gate runs before organize opens a new slip. Exact fingerprints resolve to the shelved
work; a confident normalized match is held as ``possible_duplicate``. Files are never
deleted on a fuzzy match.
"""

from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from librarian.db import Database
from librarian.file_identity import volume_content_fingerprint
from librarian.identity import resolve_work

EVIDENCE_EXACT = "exact_fingerprint"
EVIDENCE_SAME_IDENTITY = "same_shelved_identity"
EVIDENCE_NORMALIZED = "same_normalized_identity"
EVIDENCE_UNASSESSABLE = "unassessable"
EVIDENCE_NONE = "no_match"

EVIDENCE_KINDS = (
    EVIDENCE_EXACT,
    EVIDENCE_SAME_IDENTITY,
    EVIDENCE_NORMALIZED,
    EVIDENCE_UNASSESSABLE,
    EVIDENCE_NONE,
)

SLIP_COOLDOWN_SECONDS = 6 * 60 * 60

_ARTICLES = ("the ", "a ", "an ")
_BRACKETS = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
_NON_WORD = re.compile(r"[^a-z0-9]+")


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.casefold().replace("&", " and ")


def normalize_title(value: Any) -> str:
    text = _BRACKETS.sub(" ", _fold(value))
    text = _NON_WORD.sub(" ", text).strip()
    for article in _ARTICLES:
        if text.startswith(article):
            text = text[len(article) :]
            break
    return " ".join(text.split())


def normalize_author(value: Any) -> str:
    text = _fold(value).strip()
    if "," in text:
        last, _, first = text.partition(",")
        if first.strip() and " " not in last.strip():
            text = f"{first} {last}"
    text = _NON_WORD.sub(" ", text)
    return " ".join(part for part in text.split() if len(part) > 1 or part.isdigit())


def identity_key(kind: Any, title: Any, author: Any) -> Optional[tuple]:
    t = normalize_title(title)
    a = normalize_author(author)
    if not t or not a or t == a:
        return None
    return (str(kind or "").strip().lower(), t, a)


def _author_token(author: Any) -> str:
    parts = normalize_author(author).split()
    return max(parts, key=len) if parts else ""


def normalized_shelf_matches(
    db: Database,
    identity: Mapping[str, Any],
    *,
    exclude_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Shelved works with the same normalized kind + title + author."""
    key = identity_key(identity.get("kind"), identity.get("title"), identity.get("author"))
    if key is None:
        return []
    token = _author_token(identity.get("author"))
    out = []
    for row in db.list_shelved_by_author_token(kind=key[0], token=token, limit=60):
        if exclude_id and str(row.get("id") or "") == exclude_id:
            continue
        if identity_key(row.get("kind"), row.get("title"), row.get("author")) == key:
            out.append(row)
    return out


def folder_fingerprint(path: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    try:
        return volume_content_fingerprint(path) if path.exists() else None
    except OSError:
        return None


def duplicate_gate(
    db: Database,
    identity: Mapping[str, Any],
    folder: Path,
) -> Dict[str, Any]:
    """Decide before a slip exists: resolve, hold as possible_duplicate, or pass."""
    if str(identity.get("kind") or "") == "music":
        return {"action": "pass", "evidence": EVIDENCE_NONE, "work": None}
    resolver_candidate = dict(identity)
    resolved_id = resolve_work(db, resolver_candidate)
    if resolved_id:
        work = db.get_work(resolved_id)
        if work:
            if resolver_candidate.get("match_confidence") == "normalized":
                return {"action": "hold", "evidence": EVIDENCE_NORMALIZED, "work": work}
            return {"action": "resolve", "evidence": EVIDENCE_EXACT, "work": work}
    matches = normalized_shelf_matches(db, identity)
    if not matches:
        return {"action": "pass", "evidence": EVIDENCE_NONE, "work": None}
    source_fp = folder_fingerprint(Path(folder))
    if source_fp:
        for row in matches:
            twin = Path(str(row.get("folder_path") or ""))
            if str(twin) and folder_fingerprint(twin) == source_fp:
                return {"action": "resolve", "evidence": EVIDENCE_EXACT, "work": row}
    if len(matches) == 1:
        return {"action": "hold", "evidence": EVIDENCE_NORMALIZED, "work": matches[0]}
    return {"action": "pass", "evidence": EVIDENCE_NORMALIZED, "work": None}


# --- cooldown: a purged folder cannot reopen the same slip right away -----------


def folder_key(folder: Any) -> str:
    text = str(folder or "").strip().rstrip("/")
    return text


def folder_signature(folder: Path) -> str:
    """Names, sizes, and mtimes under the folder. Changes when the download changes."""
    root = Path(folder)
    digest = hashlib.sha256()
    try:
        if root.is_file():
            st = root.stat()
            digest.update(f"{root.name}:{st.st_size}:{int(st.st_mtime)}".encode())
            return digest.hexdigest()
        entries = sorted(path for path in root.rglob("*") if path.is_file())
    except OSError:
        return ""
    for path in entries[:500]:
        try:
            st = path.stat()
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        digest.update(f"{rel}:{st.st_size}:{int(st.st_mtime)}\n".encode())
    return digest.hexdigest()


def start_slip_cooldown(
    db: Database,
    folder: Any,
    *,
    reason: str,
    seconds: float = SLIP_COOLDOWN_SECONDS,
    now: Optional[float] = None,
) -> None:
    key = folder_key(folder)
    if not key:
        return
    path = Path(key)
    if not path.exists():
        return
    moment = time.time() if now is None else float(now)
    db.set_slip_cooldown(
        key,
        signature=folder_signature(path),
        reason=reason,
        until=moment + float(seconds),
        now=moment,
    )


def slip_cooldown_active(db: Database, folder: Any, *, now: Optional[float] = None) -> bool:
    key = folder_key(folder)
    if not key:
        return False
    row = db.get_slip_cooldown(key)
    if row is None:
        return False
    moment = time.time() if now is None else float(now)
    if float(row.get("until_at") or 0) <= moment:
        return False
    return str(row.get("signature") or "") == folder_signature(Path(key))


__all__ = [
    "EVIDENCE_EXACT",
    "EVIDENCE_KINDS",
    "EVIDENCE_NONE",
    "EVIDENCE_NORMALIZED",
    "EVIDENCE_SAME_IDENTITY",
    "EVIDENCE_UNASSESSABLE",
    "SLIP_COOLDOWN_SECONDS",
    "duplicate_gate",
    "folder_fingerprint",
    "folder_signature",
    "identity_key",
    "normalize_author",
    "normalize_title",
    "normalized_shelf_matches",
    "slip_cooldown_active",
    "start_slip_cooldown",
]
