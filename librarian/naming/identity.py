"""The identity record every naming rule and identify layer fills in."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Identity:
    kind: str
    title: str
    author: str = ""
    series_name: str = ""
    series_index: str = ""
    year: Optional[int] = None
    isbn: str = ""
    asin: str = ""
    mbid: str = ""
    album: str = ""
    track_title: str = ""
    tracknumber: str = ""
    discnumber: str = ""
    recording_mbid: str = ""
    publisher: str = ""
    description: str = ""
    genre: str = ""
    narrator: str = ""
    volume_year: Optional[int] = None
    comic_format: str = ""
    comic_subtitle: str = ""
    comic_variant: str = ""
    comicvine_volume_id: Optional[int] = None
    comicvine_issue_id: Optional[int] = None
    penciller: str = ""
    inker: str = ""
    colorist: str = ""
    cover_artist: str = ""
    letterer: str = ""
    cover: str = ""
    web: str = ""
    month: Optional[int] = None
    day: Optional[int] = None
    confidence: str = "low"
    rationale: str = ""
    query_terms: List[str] = field(default_factory=list)
    review_reason: Optional[str] = None
    source: str = "parse"
    match_candidates: List[Dict[str, Any]] = field(default_factory=list)
    match_confidence: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "author": self.author,
            "series_name": self.series_name,
            "series_index": self.series_index,
            "year": self.year,
            "isbn": self.isbn,
            "asin": self.asin,
            "mbid": self.mbid,
            "album": self.album,
            "track_title": self.track_title,
            "tracknumber": self.tracknumber,
            "discnumber": self.discnumber,
            "recording_mbid": self.recording_mbid,
            "publisher": self.publisher,
            "description": self.description,
            "genre": self.genre,
            "narrator": self.narrator,
            "volume_year": self.volume_year,
            "comic_format": self.comic_format,
            "comic_subtitle": self.comic_subtitle,
            "comic_variant": self.comic_variant,
            "comicvine_volume_id": self.comicvine_volume_id,
            "comicvine_issue_id": self.comicvine_issue_id,
            "penciller": self.penciller,
            "inker": self.inker,
            "colorist": self.colorist,
            "cover_artist": self.cover_artist,
            "letterer": self.letterer,
            "cover": self.cover,
            "web": self.web,
            "month": self.month,
            "day": self.day,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "query_terms": list(self.query_terms),
            "review_reason": self.review_reason,
            "source": self.source,
            "match_candidates": list(self.match_candidates),
            "match_confidence": self.match_confidence,
        }
