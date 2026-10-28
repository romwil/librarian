"""Usenet release / SAB folder names → Identity, routed through the kind-specific rules."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Sequence

from librarian.kinds import (
    ALL_KINDS,
    KIND_AUDIOBOOK,
    KIND_BOOK,
    KIND_MUSIC,
    kind_from_newznab,
)
from librarian.naming.audiobook import normalize_audiobook_name
from librarian.naming.comic import parse_comic
from librarian.naming.identity import Identity
from librarian.naming.isbn import ISBN_PATTERN, extract_isbn
from librarian.naming.magazine import parse_magazine
from librarian.naming.tokens import (
    AUDIO_PART,
    AUDIOBOOK_HINT,
    BARE_PART_COUNTER,
    EBOOK_GROUP,
    MUSIC_TRACK,
    PART_COUNTER,
    YEAR,
    filename_stem,
    tidy_title,
    usenet_basename,
)


def _clean_piece(value: str) -> str:
    text = EBOOK_GROUP.sub("", value)
    text = AUDIO_PART.sub("", text)
    text = PART_COUNTER.sub(" ", text)
    text = BARE_PART_COUNTER.sub(" ", text)
    text = YEAR.sub("", text)
    text = ISBN_PATTERN.sub("", text)
    return tidy_title(text)


def parse_usenet_name(name: str, *, category: object = None, kind: object = None) -> Identity:
    """Deterministic Usenet / folder parse. Never invents an ISBN. Filename layer is weak."""
    raw = usenet_basename(name)
    stem = filename_stem(raw)
    isbn = extract_isbn(stem)
    hinted = str(kind or "").strip().lower()
    if hinted not in ALL_KINDS:
        hinted = kind_from_newznab(category) or ""

    magazine = parse_magazine(stem, hinted=hinted, isbn=isbn)
    if magazine is not None:
        return magazine
    comic = parse_comic(stem, hinted=hinted, isbn=isbn)
    if comic is not None:
        return comic

    year_match = YEAR.search(stem)
    year = int(year_match.group(1)) if year_match else None

    track = MUSIC_TRACK.search(stem) if hinted in ("", KIND_MUSIC, KIND_AUDIOBOOK) else None
    track_title = ""
    tracknumber = ""
    discnumber = ""
    if track:
        tracknumber = str(int(track.group("num")))
        track_title = tidy_title(track.group("title"))
        if track.groupdict().get("disc"):
            discnumber = str(int(track.group("disc")))

    author = ""
    title = ""
    album = ""
    if hinted == KIND_MUSIC and " - " in stem:
        author, album = [_clean_piece(part) for part in stem.split(" - ", 1)]
        title = album
    elif " - " in stem:
        author, title = [_clean_piece(part) for part in stem.split(" - ", 1)]
    else:
        cleaned = _clean_piece(stem)
        title = cleaned
        if hinted == KIND_BOOK and " by " in cleaned.lower():
            head, tail = re.split(r"\s+by\s+", cleaned, maxsplit=1, flags=re.IGNORECASE)
            title, author = head.strip(), tail.strip()

    inferred = hinted
    if not inferred:
        if AUDIOBOOK_HINT.search(stem):
            inferred = KIND_AUDIOBOOK
        elif any(token in stem.lower() for token in ("flac", "mp3", "vinyl", "album")):
            inferred = KIND_MUSIC
        else:
            inferred = KIND_BOOK

    if inferred == KIND_AUDIOBOOK and title:
        title = tidy_title(AUDIO_PART.sub("", title)) or title
        title = AUDIOBOOK_HINT.sub(" ", title)
        title = re.sub(r"\s+", " ", title).strip() or title
        tokens = normalize_audiobook_name(stem)
        author = tokens.author or author
        title = tokens.title or title
        year = tokens.year if tokens.year is not None else year
        series_name = tokens.series_name
        series_index = tokens.series_index
        asin = tokens.asin
        narrator = tokens.narrator
    else:
        series_name = album
        series_index = ""
        asin = ""
        narrator = ""

    high = bool(isbn and author and title) if inferred == KIND_BOOK else False
    return Identity(
        kind=inferred,
        title=title or track_title or tidy_title(stem),
        author=author,
        series_name=series_name if inferred == KIND_AUDIOBOOK else album,
        series_index=series_index if inferred == KIND_AUDIOBOOK else "",
        album=album,
        track_title=track_title,
        tracknumber=tracknumber,
        discnumber=discnumber,
        year=year,
        isbn=isbn or asin,
        asin=asin,
        narrator=narrator,
        confidence="high" if high else "low",
        rationale="indexer/parse fields" if isbn else "filename parse",
        query_terms=[part for part in (author, title, isbn or asin) if part],
        source="parse",
    )


def release_file_fields(
    folder: Path,
    files: Sequence[Path],
    *,
    kind: str = "",
    category: object = None,
) -> Dict[str, Any]:
    """Identify layer 3: conservative kind-specific folder/filename parse. Weak titles only fill holes."""
    names: List[str] = [Path(folder).name]
    if files:
        names.append(files[0].stem)
        names.append(files[0].name)
        if len(files) == 1 and files[0].parent != Path(folder):
            names.append(files[0].parent.name)
    merged: Dict[str, Any] = {}
    skip = {"confidence", "rationale", "source", "query_terms", "review_reason", "kind"}
    for name in names:
        parsed = parse_usenet_name(name, category=category, kind=kind)
        data = parsed.as_dict()
        if kind == KIND_BOOK and not data.get("isbn"):
            # Author - Title.epub is a weak title only when nothing else exists.
            data = {key: data.get(key) for key in ("title", "author", "year", "isbn") if data.get(key)}
        for key, value in data.items():
            if key in skip or value in (None, "", [], "low"):
                continue
            if merged.get(key) in (None, ""):
                merged[key] = value
    return merged
