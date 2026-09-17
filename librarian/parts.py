"""Usenet multipart markers — shared with Find collation (frontend findParts.js)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

_EXT_TAIL = re.compile(
    r"\.(mp3|m4b|m4a|flac|ogg|wav|aac|nzb|par2|rar|zip|7z|nfo|sfv)(?:\b|$)",
    re.IGNORECASE,
)
_YENC = re.compile(r"\byenc\b", re.IGNORECASE)
_BRACKET_PART = re.compile(r"\[(\d+)\s*/\s*(\d+)\]")
_PAREN_PART = re.compile(r"\((\d+)\s*/\s*(\d+)\)")
_OF_PART = re.compile(r"\b(\d{1,3})\s*of\s*(\d{1,3})\b", re.IGNORECASE)
_NAMED_PART = re.compile(
    r"\b(?:part|cd|disc|disk)\s*(\d{1,3})(?:\s*(?:/|of)\s*(\d{1,3}))?\b",
    re.IGNORECASE,
)
_BARE_SLASH_PART = re.compile(r"\b\d{1,3}\s*/\s*\d{1,3}\b")
_NOISE_PREFIX = re.compile(
    r"^(?:attn\s+\S+\s+|nmr(?:t)?\s+|\[?[a-z0-9]{6,}\]\s*-?\s*)",
    re.IGNORECASE,
)


def _named_marker_style(raw: str) -> str:
    lower = str(raw or "").lower()
    if lower.startswith("cd"):
        return "cd"
    if lower.startswith("disc") or lower.startswith("disk"):
        return "disc"
    return "part"


def parse_part_marker(title: object = "") -> Optional[Dict[str, Any]]:
    """Parse Part N/M, NofM, CD/Disc, or [N/M] markers from an NZB/filename title."""
    text = str(title or "")
    if not text.strip():
        return None

    bracket = _BRACKET_PART.search(text)
    paren = _PAREN_PART.search(text)
    of_match = _OF_PART.search(text)
    named = _NAMED_PART.search(text)
    named_with_total = bool(named and named.group(2))

    # Prefer Part N/M / N of M over yEnc [N/M] or (N/M) when both present.
    if (bracket or paren) and (of_match or named_with_total):
        if of_match:
            return {
                "part": int(of_match.group(1)),
                "total": int(of_match.group(2)),
                "style": "of",
                "raw": of_match.group(0),
            }
        assert named is not None
        return {
            "part": int(named.group(1)),
            "total": int(named.group(2)),
            "style": _named_marker_style(named.group(0)),
            "raw": named.group(0),
        }

    if bracket:
        return {
            "part": int(bracket.group(1)),
            "total": int(bracket.group(2)),
            "style": "bracket",
            "raw": bracket.group(0),
        }

    if paren:
        return {
            "part": int(paren.group(1)),
            "total": int(paren.group(2)),
            "style": "paren",
            "raw": paren.group(0),
        }

    if of_match:
        return {
            "part": int(of_match.group(1)),
            "total": int(of_match.group(2)),
            "style": "of",
            "raw": of_match.group(0),
        }

    if named:
        total = int(named.group(2)) if named.group(2) else None
        return {
            "part": int(named.group(1)),
            "total": total,
            "style": _named_marker_style(named.group(0)),
            "raw": named.group(0),
        }

    return None


def strip_part_markers(title: object = "") -> str:
    text = str(title or "")
    text = _BRACKET_PART.sub(" ", text)
    text = _PAREN_PART.sub(" ", text)
    text = _OF_PART.sub(" ", text)
    text = _NAMED_PART.sub(" ", text)
    text = _BARE_SLASH_PART.sub(" ", text)
    text = _EXT_TAIL.sub(" ", text)
    text = _YENC.sub(" ", text)
    text = re.sub(r"[._]+", " ", text)
    text = re.sub(r"\s*[-–—|:]\s*$", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def normalize_part_base(title: object = "") -> str:
    text = strip_part_markers(title).lower()
    text = _NOISE_PREFIX.sub("", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def part_index_origin(parts: Sequence[object]) -> int:
    """Return 0 when any owned part is 0 (zero-based sets), else 1."""
    for raw in parts:
        try:
            if int(raw) == 0:
                return 0
        except (TypeError, ValueError):
            continue
    return 1


def missing_parts(
    owned: Sequence[object],
    total: object,
    *,
    origin: Optional[int] = None,
) -> List[int]:
    """Missing part numbers for a known total (vs owned indexes)."""
    try:
        total_n = int(total) if total is not None else 0
    except (TypeError, ValueError):
        return []
    if total_n < 1:
        return []
    have: set[int] = set()
    for raw in owned or []:
        try:
            have.add(int(raw))
        except (TypeError, ValueError):
            continue
    start = origin if origin is not None else part_index_origin(have)
    last = total_n - 1 if start == 0 else total_n
    return [i for i in range(start, last + 1) if i not in have]


def _coerce_int(value: object) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def infer_part_fields(
    *,
    titles: Sequence[object] = (),
    filenames: Sequence[object] = (),
    existing: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Derive part_total / style / base / per-name part indexes from NZB titles + filenames."""
    prior = dict(existing or {})
    total = _coerce_int(prior.get("part_total"))
    style = str(prior.get("part_style") or "").strip() or None
    base = str(prior.get("part_base") or "").strip() or None
    origin = _coerce_int(prior.get("part_origin"))
    file_parts: Dict[str, int] = {}

    for raw in list(titles) + list(filenames):
        text = str(raw or "")
        if not text.strip():
            continue
        marker = parse_part_marker(text)
        if not marker:
            continue
        part = int(marker["part"])
        if marker.get("total") is not None:
            marker_total = int(marker["total"])
            if total is None or marker_total > total:
                total = marker_total
        if not style and marker.get("style"):
            style = str(marker["style"])
        if not base:
            stripped = strip_part_markers(text)
            if stripped:
                base = stripped
        file_parts[text] = part
        if part == 0 and origin is None:
            origin = 0

    if origin is None and file_parts:
        origin = part_index_origin(file_parts.values())

    out: Dict[str, Any] = {}
    if total is not None:
        out["part_total"] = total
    if style:
        out["part_style"] = style
    if base:
        out["part_base"] = base
    if origin is not None:
        out["part_origin"] = origin
    out["file_parts"] = file_parts
    return out


def owned_parts_from_files(files: Sequence[Mapping[str, Any]]) -> List[int]:
    """Prefer files.part; fall back to parsing filenames."""
    owned: List[int] = []
    seen: set[int] = set()
    for row in files or []:
        part = _coerce_int(row.get("part"))
        if part is None:
            marker = parse_part_marker(row.get("filename") or "")
            if marker:
                part = int(marker["part"])
        if part is None or part in seen:
            continue
        seen.add(part)
        owned.append(part)
    return sorted(owned)


def build_part_set(
    work: Optional[Mapping[str, Any]],
    files: Sequence[Mapping[str, Any]] = (),
) -> Optional[Dict[str, Any]]:
    """API/Hall shape: { total, owned[], style, base, origin? } when total is known."""
    if not work:
        return None
    total = _coerce_int(work.get("part_total"))
    style = str(work.get("part_style") or "").strip() or None
    base = str(work.get("part_base") or "").strip() or None
    origin = _coerce_int(work.get("part_origin"))

    if total is None:
        inferred = infer_part_fields(
            titles=[work.get("title")],
            filenames=[row.get("filename") for row in (files or [])],
        )
        total = _coerce_int(inferred.get("part_total"))
        style = style or inferred.get("part_style")
        base = base or inferred.get("part_base")
        if origin is None:
            origin = _coerce_int(inferred.get("part_origin"))

    if total is None or total < 2:
        return None

    owned = owned_parts_from_files(files)
    if origin is None:
        origin = part_index_origin(owned)
    if not base:
        base = strip_part_markers(work.get("title") or "") or str(work.get("title") or "")
    payload: Dict[str, Any] = {
        "total": total,
        "owned": owned,
        "style": style or "part",
        "base": base,
    }
    if origin is not None:
        payload["origin"] = origin
    return payload


def part_set_incomplete(part_set: Optional[Mapping[str, Any]]) -> bool:
    if not part_set:
        return False
    total = _coerce_int(part_set.get("total"))
    if total is None or total < 2:
        return False
    owned = part_set.get("owned") or []
    missing = missing_parts(owned, total, origin=_coerce_int(part_set.get("origin")))
    return bool(missing)


def merge_part_fields_for_work(
    *,
    work: Mapping[str, Any],
    indexer_item: Optional[Mapping[str, Any]] = None,
    filenames: Sequence[object] = (),
) -> Dict[str, Any]:
    """Fields to merge into upsert_work from NZB title + payload filenames."""
    titles: List[object] = []
    if indexer_item:
        titles.append(indexer_item.get("title"))
        titles.append(indexer_item.get("name"))
    titles.append(work.get("title"))
    inferred = infer_part_fields(
        titles=titles,
        filenames=filenames,
        existing=work,
    )
    out: Dict[str, Any] = {}
    for key in ("part_total", "part_style", "part_base", "part_origin"):
        if key in inferred and inferred[key] is not None:
            out[key] = inferred[key]
    return out


def part_for_filename(filename: object, file_parts: Optional[Mapping[str, int]] = None) -> Optional[int]:
    text = str(filename or "")
    if file_parts and text in file_parts:
        return file_parts[text]
    marker = parse_part_marker(text)
    return int(marker["part"]) if marker else None
