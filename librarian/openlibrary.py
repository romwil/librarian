"""Open Library ISBN and title lookup. Never invents an ISBN."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlencode

import httpx

from librarian.covers import DEFAULT_USER_AGENT, OPENLIB_ISBN_COVER
from librarian.descriptions import normalize_description
from librarian.identify import extract_isbn

OPENLIB_ISBN = "https://openlibrary.org/isbn/{isbn}.json"
OPENLIB_SEARCH = "https://openlibrary.org/search.json"
OPENLIB_COVER_ID = "https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
_SERIES_POS = re.compile(
    r"(?:#\s*|,\s*#\s*|,\s*book\s+|,\s*vol(?:ume)?\.?\s+|\s+\()\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _year_from(value: Any) -> Optional[int]:
    if isinstance(value, int) and 1000 <= value <= 2100:
        return value
    match = re.search(r"(19\d{2}|20\d{2})", str(value or ""))
    if match:
        return int(match.group(1))
    return None


def _description(value: Any) -> str:
    if isinstance(value, dict):
        raw = str(value.get("value") or value.get("text") or "").strip()
    else:
        raw = str(value or "").strip()
    return normalize_description(raw)


def _series_name(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        for item in value:
            name = _series_name(item)
            if name:
                return name
    if isinstance(value, dict):
        return str(value.get("name") or value.get("title") or "").strip()
    return ""


def _title_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


_NAME_STOP = frozenset({"the", "a", "an", "and", "of", "jr", "sr"})
_MEMOIR_HINTS = ("memoir", "autobiograph", "biograph")
# Below this, title+author search returns no enrichment (reject low-confidence hits).
MIN_TITLE_MATCH_SCORE = 0.55
_SEARCH_CANDIDATE_LIMIT = 12


def _name_tokens(value: Any) -> frozenset[str]:
    tokens = re.findall(r"[a-z0-9]+", str(value or "").lower())
    return frozenset(token for token in tokens if token and token not in _NAME_STOP)


def _author_overlap(want: str, candidate: str) -> float:
    left = _name_tokens(want)
    right = _name_tokens(candidate)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left.issubset(right) or right.issubset(left):
        return 0.9
    shared = len(left & right)
    if shared == 0:
        return 0.0
    return shared / max(len(left), len(right))


def _doc_authors(doc: Mapping[str, Any]) -> List[str]:
    raw = doc.get("author_name") or []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item or "").strip()]
    text = str(raw or "").strip()
    return [text] if text else []


def _doc_subjects(doc: Mapping[str, Any]) -> List[str]:
    raw = doc.get("subject") or []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item or "").strip()]
    text = str(raw or "").strip()
    return [text] if text else []


def _has_memoir_subject(subjects: List[str]) -> bool:
    for subject in subjects:
        key = _title_key(subject)
        if any(hint in key for hint in _MEMOIR_HINTS):
            return True
    return False


def score_openlibrary_doc(
    doc: Mapping[str, Any],
    *,
    title: str,
    author: str = "",
    year: Optional[int] = None,
) -> float:
    """Score an Open Library search doc for title+author enrich matching.

    Hard-rejects wrong titles and authors that don't overlap. Caps scores when the
    hit lists foreign co-authors (e.g. Springsteen+Morpurgo corruption for
    *Born to Run*) so sole-author memoir hits can win.
    """
    want_title = _title_key(title)
    got_title = _title_key(doc.get("title"))
    if not want_title or not got_title:
        return 0.0
    if want_title == got_title:
        title_score = 1.0
    elif want_title in got_title or got_title in want_title:
        title_score = 0.72
    else:
        return 0.0

    authors = _doc_authors(doc)
    want_author = str(author or "").strip()
    author_score = 0.5
    if want_author:
        overlaps = [_author_overlap(want_author, name) for name in authors]
        best = max(overlaps) if overlaps else 0.0
        if best < 0.5:
            return 0.0
        author_score = best
        if len(authors) == 1 and best >= 0.85:
            author_score = min(1.0, best + 0.05)
        elif len(authors) > 1:
            foreign = any(overlap < 0.4 for overlap in overlaps)
            if foreign:
                # Corrupted multi-author OL records must not beat a clean hit.
                return min(0.4, title_score * 0.35 + best * 0.4)

    subjects = _doc_subjects(doc)
    memoir_bonus = 0.0
    if want_author and _has_memoir_subject(subjects):
        memoir_bonus = 0.15

    year_bonus = 0.0
    if year is not None:
        doc_year = _year_from(doc.get("first_publish_year"))
        if doc_year is not None:
            delta = abs(int(doc_year) - int(year))
            if delta == 0:
                year_bonus = 0.1
            elif delta <= 2:
                year_bonus = 0.05
            elif delta >= 30:
                # Album-year shelving (1975) vs memoir (2016) — soft preference only.
                year_bonus = -0.02

    score = title_score * 0.35 + author_score * 0.5 + memoir_bonus + year_bonus
    return min(1.0, max(0.0, score))


def pick_openlibrary_doc(
    docs: List[Mapping[str, Any]],
    *,
    title: str,
    author: str = "",
    year: Optional[int] = None,
    min_score: float = MIN_TITLE_MATCH_SCORE,
) -> Tuple[Optional[Dict[str, Any]], float]:
    best_doc: Optional[Dict[str, Any]] = None
    best_score = 0.0
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        score = score_openlibrary_doc(doc, title=title, author=author, year=year)
        if score > best_score:
            best_score = score
            best_doc = doc
    if best_doc is None or best_score < min_score:
        return None, best_score
    return best_doc, best_score


def _sort_index(value: str) -> Tuple[int, str]:
    if re.fullmatch(r"\d+", value):
        return (int(value), "")
    match = re.fullmatch(r"(\d+)\.(\d+)", value)
    if match:
        return (int(match.group(1)), match.group(2))
    return (10**9, value)


def _series_index_from_label(label: str, series_name: str) -> str:
    text = str(label or "").strip()
    if not text:
        return ""
    match = _SERIES_POS.search(text)
    if match:
        index = match.group(1)
        if index.endswith(".0"):
            index = index[:-2]
        return index
    return ""


def _doc_in_series(doc: Mapping[str, Any], series_name: str) -> bool:
    want = _title_key(series_name)
    if not want:
        return False
    raw = doc.get("series")
    labels: List[str] = []
    if isinstance(raw, list):
        labels = [str(item) for item in raw]
    elif raw:
        labels = [str(raw)]
    if not labels:
        title = _title_key(doc.get("title"))
        return bool(title) and want in title
    for label in labels:
        key = _title_key(_SERIES_POS.sub("", label))
        if want == key or want in key or key in want:
            return True
    return False


def _volume_from_search_doc(doc: Mapping[str, Any], series_name: str) -> Dict[str, Any]:
    labels = doc.get("series") if isinstance(doc.get("series"), list) else [doc.get("series")]
    index = ""
    for label in labels:
        index = _series_index_from_label(str(label or ""), series_name)
        if index:
            break
    title = str(doc.get("title") or "").strip()
    authors = doc.get("author_name") or []
    author = authors[0] if isinstance(authors, list) and authors else ""
    year = _year_from(doc.get("first_publish_year"))
    isbn = ""
    raw_isbn = doc.get("isbn")
    if isinstance(raw_isbn, list) and raw_isbn:
        isbn = extract_isbn(str(raw_isbn[0]))
    elif raw_isbn:
        isbn = extract_isbn(str(raw_isbn))
    out: Dict[str, Any] = {
        "title": title or f"{series_name} {index}".strip(),
        "series_name": series_name,
        "series_index": index,
        "author": str(author or "").strip(),
        "source": "openlibrary",
    }
    if year:
        out["year"] = year
    if isbn:
        out["isbn"] = isbn
    return out


def _cover_url(edition: Mapping[str, Any], isbn: str = "") -> str:
    covers = edition.get("covers")
    if isinstance(covers, list) and covers:
        cover_id = covers[0]
        if isinstance(cover_id, int) or str(cover_id).isdigit():
            return OPENLIB_COVER_ID.format(cover_id=cover_id)
    cover = edition.get("cover")
    if isinstance(cover, dict):
        for key in ("large", "medium", "small"):
            url = str(cover.get(key) or "").strip()
            if url.startswith("http"):
                return url
    digits = extract_isbn(isbn) or extract_isbn(str((edition.get("isbn_13") or [""])[0] if isinstance(edition.get("isbn_13"), list) else edition.get("isbn_13") or ""))
    if digits:
        return OPENLIB_ISBN_COVER.format(isbn=digits)
    return ""


class OpenLibraryClient:
    def __init__(
        self,
        *,
        transport: Optional[httpx.BaseTransport] = None,
        client: Optional[httpx.Client] = None,
        timeout: float = 20.0,
    ) -> None:
        self._own = client is None
        self._client = client or httpx.Client(
            timeout=timeout, transport=transport, follow_redirects=True
        )

    def close(self) -> None:
        if self._own:
            self._client.close()

    def _get_json(self, url: str) -> Dict[str, Any]:
        try:
            response = self._client.get(
                url,
                headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"},
            )
        except httpx.HTTPError:
            return {}
        if response.status_code >= 400:
            return {}
        try:
            payload = response.json()
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _work_payload(self, work_key: str) -> Dict[str, Any]:
        key = str(work_key or "").strip()
        if not key:
            return {}
        if not key.startswith("/"):
            key = f"/works/{key}"
        return self._get_json(f"https://openlibrary.org{key}.json")

    def lookup_by_isbn(self, isbn: str) -> Dict[str, Any]:
        digits = extract_isbn(isbn)
        if not digits:
            return {}
        edition = self._get_json(OPENLIB_ISBN.format(isbn=digits))
        if not edition:
            return {}
        work: Dict[str, Any] = {}
        works = edition.get("works")
        if isinstance(works, list) and works and isinstance(works[0], dict):
            work = self._work_payload(str(works[0].get("key") or ""))
        description = _description(work.get("description") or edition.get("description"))
        year = _year_from(edition.get("publish_date") or work.get("first_publish_date"))
        series = _series_name(edition.get("series") or work.get("series"))
        authors = edition.get("authors") or work.get("authors") or []
        author = ""
        if isinstance(authors, list) and authors:
            first = authors[0]
            if isinstance(first, dict):
                author = str(first.get("name") or "").strip()
        genre = _subjects_to_genre(work.get("subjects") or edition.get("subjects"))
        out: Dict[str, Any] = {
            "title": str(edition.get("title") or work.get("title") or "").strip(),
            "author": author,
            "description": description,
            "cover_url": _cover_url(edition, digits),
            "source": "openlibrary",
        }
        if year:
            out["year"] = year
        if series:
            out["series_name"] = series
        if genre:
            out["genre"] = genre
        return out

    def _enrichment_from_doc(
        self,
        doc: Mapping[str, Any],
        *,
        fallback_title: str = "",
        fallback_author: str = "",
        match_confidence: Optional[float] = None,
        work: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        work_payload = work if isinstance(work, Mapping) else self._work_payload(str(doc.get("key") or ""))
        description = _description(work_payload.get("description"))
        year = _year_from(doc.get("first_publish_year") or work_payload.get("first_publish_date"))
        cover_id = doc.get("cover_i")
        cover = ""
        if isinstance(cover_id, int) or str(cover_id or "").isdigit():
            cover = OPENLIB_COVER_ID.format(cover_id=cover_id)
        authors = _doc_authors(doc)
        author_name = authors[0] if authors else str(fallback_author or "")
        series = ""
        series_raw = doc.get("series")
        if isinstance(series_raw, list) and series_raw:
            series = str(series_raw[0]).strip()
        series = series or _series_name(work_payload.get("series"))
        genre = _subjects_to_genre(work_payload.get("subjects") or doc.get("subject"))
        key = str(doc.get("key") or work_payload.get("key") or "").strip()
        out: Dict[str, Any] = {
            "title": str(doc.get("title") or work_payload.get("title") or fallback_title).strip(),
            "author": str(author_name or "").strip(),
            "description": description,
            "cover_url": cover,
            "source": "openlibrary",
            "match_key": key,
        }
        if match_confidence is not None:
            out["match_confidence"] = round(float(match_confidence), 3)
        if year:
            out["year"] = year
        if series:
            out["series_name"] = series
        if genre:
            out["genre"] = genre
        # Title search may include ISBNs on the hit — we deliberately do not copy them.
        return out

    def lookup_by_key(self, work_key: str) -> Dict[str, Any]:
        key = str(work_key or "").strip()
        if not key:
            return {}
        if not key.startswith("/"):
            key = f"/works/{key}"
        work = self._work_payload(key)
        if not work:
            return {}
        authors: List[str] = []
        raw_authors = work.get("authors") or []
        if isinstance(raw_authors, list):
            for item in raw_authors:
                if isinstance(item, dict):
                    # Work payloads often nest {"author": {"key": "..."}} without names.
                    name = str(item.get("name") or "").strip()
                    if name:
                        authors.append(name)
        doc = {
            "key": key,
            "title": work.get("title"),
            "author_name": authors,
            "first_publish_year": _year_from(
                work.get("first_publish_date") or work.get("first_publish_year")
            ),
            "subject": work.get("subjects") or [],
            "cover_i": (work.get("covers") or [None])[0] if isinstance(work.get("covers"), list) else None,
            "series": work.get("series"),
        }
        return self._enrichment_from_doc(doc, work=work, match_confidence=1.0)

    def lookup_by_title(
        self,
        title: str,
        author: str = "",
        *,
        year: Optional[int] = None,
    ) -> Dict[str, Any]:
        name = str(title or "").strip()
        if not name:
            return {}
        params = {"title": name, "limit": str(_SEARCH_CANDIDATE_LIMIT)}
        if str(author or "").strip():
            params["author"] = str(author).strip()
        payload = self._get_json(f"{OPENLIB_SEARCH}?{urlencode(params)}")
        docs = payload.get("docs") if isinstance(payload.get("docs"), list) else []
        doc, score = pick_openlibrary_doc(
            [row for row in docs if isinstance(row, dict)],
            title=name,
            author=author,
            year=year,
        )
        if doc is None:
            return {}
        return self._enrichment_from_doc(
            doc,
            fallback_title=name,
            fallback_author=author,
            match_confidence=score,
        )

    def search_title_candidates(
        self,
        title: str,
        author: str = "",
        *,
        year: Optional[int] = None,
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        """Ranked alternate Open Library hits for Fix match UI (no description fetch)."""
        name = str(title or "").strip()
        if not name:
            return []
        params = {"title": name, "limit": str(max(_SEARCH_CANDIDATE_LIMIT, int(limit)))}
        if str(author or "").strip():
            params["author"] = str(author).strip()
        payload = self._get_json(f"{OPENLIB_SEARCH}?{urlencode(params)}")
        docs = payload.get("docs") if isinstance(payload.get("docs"), list) else []
        ranked: List[Tuple[float, Dict[str, Any]]] = []
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            score = score_openlibrary_doc(doc, title=name, author=author, year=year)
            if score <= 0:
                continue
            authors = _doc_authors(doc)
            cover_id = doc.get("cover_i")
            cover = ""
            if isinstance(cover_id, int) or str(cover_id or "").isdigit():
                cover = OPENLIB_COVER_ID.format(cover_id=cover_id)
            ranked.append(
                (
                    score,
                    {
                        "match_key": str(doc.get("key") or "").strip(),
                        "title": str(doc.get("title") or "").strip(),
                        "author": ", ".join(authors),
                        "year": _year_from(doc.get("first_publish_year")),
                        "cover_url": cover,
                        "match_confidence": round(float(score), 3),
                        "subjects": _doc_subjects(doc)[:6],
                        "source": "openlibrary",
                    },
                )
            )
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [row for _, row in ranked[: max(1, int(limit))]]

    def series_volumes(self, series_name: str) -> List[Dict[str, Any]]:
        """Expected volumes for a series. No invented ISBNs; only catalog digits if present."""
        name = str(series_name or "").strip()
        if not name:
            return []
        payload = self._get_json(
            f"{OPENLIB_SEARCH}?{urlencode({'q': f'series:\"{name}\"', 'limit': '50'})}"
        )
        docs = payload.get("docs") if isinstance(payload.get("docs"), list) else []
        if not docs:
            payload = self._get_json(
                f"{OPENLIB_SEARCH}?{urlencode({'q': name, 'limit': '50'})}"
            )
            docs = payload.get("docs") if isinstance(payload.get("docs"), list) else []
        volumes: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            if not _doc_in_series(doc, name):
                continue
            volume = _volume_from_search_doc(doc, name)
            key = volume.get("series_index") or _title_key(volume.get("title"))
            if not key or key in seen:
                continue
            seen.add(str(key))
            volumes.append(volume)
        volumes.sort(key=lambda row: _sort_index(str(row.get("series_index") or "")))
        return volumes


def _subjects_to_genre(raw: Any) -> str:
    from librarian.metadata import join_subjects

    return join_subjects(raw)
