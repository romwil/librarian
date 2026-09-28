"""Gaps as gifts — holes framed as the next chapter of a run."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, MutableMapping, Sequence


def _text(value: Any) -> str:
    return str(value or "").strip()


def gift_invitation(card: Mapping[str, Any]) -> str:
    """Warm invitation — never admin debt."""
    series = _text(card.get("series_name")) or "this run"
    index = _text(card.get("series_index") or card.get("missing_index"))
    gap_type = _text(card.get("gap_type"))
    if gap_type == "multipart":
        return f"A few parts remain to finish {series}."
    if gap_type in {"audiobook_parts", "music_tracks"}:
        return f"Next pieces of {series} are waiting to complete the set."
    if index:
        return f"Next to complete the run: {series} {index}."
    return f"Next to complete the run: {series}."


def gift_presence(cards: Sequence[Mapping[str, Any]]) -> str:
    count = len(cards or [])
    if count < 1:
        return "The runs on these shelves feel whole tonight."
    if count == 1:
        return "One gentle hole invites the next chapter."
    return f"{count} gentle holes invite the next chapters of a run."


def frame_gap_as_gift(card: MutableMapping[str, Any] | Dict[str, Any]) -> Dict[str, Any]:
    out = dict(card)
    out["gift"] = True
    out["invitation"] = gift_invitation(out)
    return out


def gift_cards(cards: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return [frame_gap_as_gift(dict(card)) for card in cards or ()]
