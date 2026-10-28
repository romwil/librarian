"""Shared release-name token rules: tidy, basename/stem, counters, dump detection."""

from __future__ import annotations

import re

from librarian.naming.extensions import STEM_EXTENSIONS

DOT_GROUP = re.compile(r"[\.\-_]+")
AUDIOBOOK_HINT = re.compile(r"(?i)\baudio[\.\s_\-]*book\b|\bunabridged\b|\bm4b\b")
DUMP_RELEASE_TOKEN = re.compile(
    r"(?i)\b("
    r"audio[\.\s_\-]*book|ebook|epub|mobi|azw3|hybrid|retail|proper|repack|"
    r"bitbook|comic|cbr|cbz|mp3|flac|m4b|unabridged|abridged|web[\.\-]?rip"
    r")\b"
)
EBOOK_GROUP = re.compile(r"[\.\s]eBook(?:-|\.)(?P<group>[A-Za-z0-9]+)", re.IGNORECASE)
YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")
AUDIO_PART = re.compile(r"\b(?:part|cd|disc)\s*(\d+)\b", re.IGNORECASE)
# yEnc / article counters — never feed these through pathlib ( '/' is a separator ).
PART_COUNTER = re.compile(r"[\[(]\s*\d{1,3}\s*/\s*\d{1,3}\s*[\])]")
BARE_PART_COUNTER = re.compile(r"\b\d{1,3}\s*/\s*\d{1,3}\b")
MUSIC_TRACK = re.compile(
    r"^(?:(?:cd|disc|disk)\s*(?P<disc>\d+)[\.\s-]+)?(?P<num>\d{1,3})[\.\s-]+(?P<title>.+)$",
    re.IGNORECASE,
)
MBID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def tidy_title(value: str) -> str:
    text = DOT_GROUP.sub(" ", value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def looks_like_dump_title(value: str) -> bool:
    """True for dotted Usenet dumps / release tokens that should not stay as shelf titles."""
    text = str(value or "").strip()
    if not text:
        return True
    if text.count(".") >= 3:
        return True
    if DUMP_RELEASE_TOKEN.search(text):
        return True
    # Humanized dump: many Title Case tokens, no Author - Title separator.
    if " - " not in text and len(text) >= 48 and text.count(" ") >= 6:
        words = [w for w in text.split() if w]
        titled = sum(1 for w in words if w[:1].isupper())
        if titled >= 6 and titled >= len(words) * 0.6:
            return True
    return False


def usenet_basename(name: str) -> str:
    """Basename for Usenet subjects or real paths without splitting on [N/M] slashes."""
    text = str(name or "").strip()
    if not text:
        return ""
    normalized = text.replace("\\", "/")
    looks_like_path = (
        normalized.startswith("/")
        or bool(re.match(r"^[A-Za-z]:/", normalized))
        or "/mnt/" in normalized
        or "/data/" in normalized
        or "/downloads/" in normalized
        or "/config/" in normalized
    )
    if not looks_like_path:
        return text
    # Split on the last path slash that is not inside [] or ().
    depth = 0
    for index in range(len(normalized) - 1, -1, -1):
        char = normalized[index]
        if char in "])":
            depth += 1
        elif char in "[(":
            depth = max(0, depth - 1)
        elif char == "/" and depth == 0:
            return normalized[index + 1 :]
    return normalized


def filename_stem(name: str) -> str:
    """Strip a known extension without pathlib — Path.stem treats '/' in [6/8] as a parent path."""
    base = usenet_basename(name)
    lower = base.lower()
    for ext in sorted(STEM_EXTENSIONS, key=len, reverse=True):
        if lower.endswith(ext):
            return base[: -len(ext)]
    if "." in base:
        head, ext = base.rsplit(".", 1)
        if ext.isalnum() and 1 <= len(ext) <= 5:
            return head
    return base
