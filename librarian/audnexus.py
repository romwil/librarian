"""Audnexus / Audible catalog client for audiobook ASIN authority."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.parse import urlencode

import httpx

from librarian.covers import DEFAULT_USER_AGENT

logger = logging.getLogger(__name__)

AUDNEXUS_BASE = "https://api.audnex.us"
AUDIBLE_CATALOG = "https://api.audible.com/1.0/catalog/products"

REVIEW_AUDNEXUS_AMBIGUOUS = "audnexus_ambiguous"
REVIEW_AUDNEXUS_UNMATCHED = "audnexus_unmatched"

SCORE_AUTO = 0.85
SCORE_REVIEW = 0.65

_CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS audnexus_cache (
    cache_key TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
"""


class AudnexusError(RuntimeError):
    """Audnexus / Audible HTTP failure. Messages must never include tokens."""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _tokens(value: Any) -> set[str]:
    return {tok for tok in re.findall(r"[a-z0-9]+", str(value or "").lower()) if len(tok) > 1}


def _authors_match_exact(query: Any, candidate: Any) -> bool:
    """True when authors match as a whole — not a substring of another name.

    Rejects false friends like ``Le``⊂``Le Guin`` and ``Smith``⊂``Smithson``
    that raw ``_norm(a) in _norm(b)`` would accept. Token-set equality also
    treats ``Andy Weir`` and ``Weir, Andy`` as the same author.
    """
    q_tokens, c_tokens = _tokens(query), _tokens(candidate)
    if q_tokens and c_tokens and q_tokens == c_tokens:
        return True
    qn, cn = _norm(query), _norm(candidate)
    return bool(qn and qn == cn)


def jaccard(a: Any, b: Any) -> float:
    left, right = _tokens(a), _tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def is_valid_asin(value: str) -> bool:
    text = _text(value).upper()
    return bool(re.fullmatch(r"B0[A-Z0-9]{8}", text) or re.fullmatch(r"[A-Z0-9]{10}", text))


class AudnexusCache:
    """SQLite response cache under DATA_DIR. Never mock — real sqlite3."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_CACHE_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def get(self, key: str, *, max_age: float = 86400 * 14) -> Optional[Any]:
        now = time.time()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT payload, fetched_at FROM audnexus_cache WHERE cache_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        if now - float(row["fetched_at"]) > max_age:
            return None
        try:
            return json.loads(row["payload"])
        except json.JSONDecodeError:
            return None

    def set(self, key: str, payload: Any) -> None:
        blob = json.dumps(payload)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audnexus_cache (cache_key, payload, fetched_at)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    payload = excluded.payload,
                    fetched_at = excluded.fetched_at
                """,
                (key, blob, time.time()),
            )
            conn.commit()


class AudnexusClient:
    """Audible catalog search + Audnexus book/chapter detail."""

    def __init__(
        self,
        *,
        cache: Optional[AudnexusCache] = None,
        transport: Optional[httpx.BaseTransport] = None,
        region: str = "us",
        min_interval: float = 0.35,
    ) -> None:
        self.cache = cache
        self.region = region or "us"
        self._min_interval = max(0.0, float(min_interval))
        self._last_call = 0.0
        self._pace_lock = threading.Lock()
        self._client = httpx.Client(timeout=30.0, transport=transport, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def _pace(self) -> None:
        if self._min_interval <= 0:
            return
        with self._pace_lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def _headers(self) -> Dict[str, str]:
        return {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}

    def _get_json(self, url: str, *, cache_key: str = "") -> Any:
        if cache_key and self.cache is not None:
            hit = self.cache.get(cache_key)
            if hit is not None:
                return hit
        self._pace()
        try:
            response = self._client.get(url, headers=self._headers())
        except httpx.HTTPError as error:
            raise AudnexusError("Audnexus could not be reached") from error
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise AudnexusError(f"Audnexus HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as error:
            raise AudnexusError("Audnexus returned non-JSON") from error
        if cache_key and self.cache is not None and payload is not None:
            self.cache.set(cache_key, payload)
        return payload

    def book(self, asin: str) -> Optional[Dict[str, Any]]:
        code = _text(asin).upper()
        if not is_valid_asin(code):
            return None
        url = f"{AUDNEXUS_BASE}/books/{code}?region={self.region}"
        payload = self._get_json(url, cache_key=f"book:{self.region}:{code}")
        return payload if isinstance(payload, dict) else None

    def chapters(self, asin: str) -> List[Dict[str, Any]]:
        code = _text(asin).upper()
        if not is_valid_asin(code):
            return []
        url = f"{AUDNEXUS_BASE}/books/{code}/chapters?region={self.region}"
        payload = self._get_json(url, cache_key=f"chapters:{self.region}:{code}")
        if isinstance(payload, dict) and isinstance(payload.get("chapters"), list):
            return [row for row in payload["chapters"] if isinstance(row, dict)]
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        return []

    def catalog_search(self, title: str, author: str = "", *, limit: int = 8) -> List[Dict[str, Any]]:
        params = {
            "num_results": str(max(1, min(20, limit))),
            "products_sort_by": "Relevance",
            "response_groups": "product_plan_details,media,contributors,product_attrs",
        }
        if _text(title):
            params["title"] = _text(title)
        if _text(author):
            params["author"] = _text(author)
        if not params.get("title") and not params.get("author"):
            return []
        url = f"{AUDIBLE_CATALOG}?{urlencode(params)}"
        cache_key = f"search:{self.region}:{params.get('title','')}:{params.get('author','')}:{limit}"
        payload = self._get_json(url, cache_key=cache_key)
        if not isinstance(payload, dict):
            return []
        products = payload.get("products")
        if not isinstance(products, list):
            return []
        return [row for row in products if isinstance(row, dict) and _text(row.get("asin"))]

    def search(
        self,
        *,
        title: str = "",
        author: str = "",
        asin: str = "",
        narrator: str = "",
        series_name: str = "",
        series_index: str = "",
        year: Optional[int] = None,
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        """Return scored candidate dicts (highest first)."""
        results: List[Dict[str, Any]] = []
        seen: set[str] = set()

        def add_book(raw: Mapping[str, Any], *, stub_score: float = 0.0) -> None:
            candidate = book_to_candidate(raw)
            code = _text(candidate.get("asin")).upper()
            if not code or code in seen:
                return
            seen.add(code)
            score = score_candidate(
                candidate,
                title=title,
                author=author,
                narrator=narrator,
                series_name=series_name,
                series_index=series_index,
                year=year,
                asin_hint=asin,
            )
            candidate["score"] = max(score, stub_score)
            results.append(candidate)

        if is_valid_asin(asin):
            detail = self.book(asin)
            if detail:
                add_book(detail, stub_score=1.0)

        if is_valid_asin(title) and _text(title).upper() not in seen:
            detail = self.book(title)
            if detail:
                add_book(detail, stub_score=1.0)

        if _text(title) or _text(author):
            for stub in self.catalog_search(title, author, limit=limit):
                code = _text(stub.get("asin")).upper()
                if not code or code in seen:
                    continue
                try:
                    detail = self.book(code)
                except AudnexusError:
                    detail = None
                if detail:
                    add_book(detail)
                else:
                    add_book(stub)

        results.sort(key=lambda row: float(row.get("score") or 0), reverse=True)
        return results[:limit]


def book_to_candidate(raw: Mapping[str, Any]) -> Dict[str, Any]:
    authors = raw.get("authors") or raw.get("authors") or []
    author_names: List[str] = []
    if isinstance(authors, list):
        for row in authors:
            if isinstance(row, dict):
                name = _text(row.get("name"))
            else:
                name = _text(row)
            if name:
                author_names.append(name)
    narrators = raw.get("narrators") or []
    narrator_names: List[str] = []
    if isinstance(narrators, list):
        for row in narrators:
            if isinstance(row, dict):
                name = _text(row.get("name"))
            else:
                name = _text(row)
            if name:
                narrator_names.append(name)
    series_name = ""
    series_index = ""
    series = raw.get("series") or raw.get("seriesPrimary")
    if isinstance(series, list) and series:
        series = series[0]
    if isinstance(series, dict):
        series_name = _text(series.get("name") or series.get("title"))
        series_index = _text(series.get("position") or series.get("index"))
    year = None
    for key in ("releaseDate", "publishDate", "copyright"):
        value = raw.get(key)
        if isinstance(value, int) and 1900 <= value <= 2100:
            year = value
            break
        text = _text(value)
        match = re.search(r"(19\d{2}|20\d{2})", text)
        if match:
            year = int(match.group(1))
            break
    title = _text(raw.get("title") or raw.get("name"))
    cover = _text(raw.get("image") or raw.get("cover"))
    product_images = raw.get("product_images")
    if not cover and isinstance(product_images, dict):
        cover = _text(product_images.get("500") or product_images.get("300"))
    return {
        "asin": _text(raw.get("asin")).upper(),
        "title": title,
        "author": ", ".join(author_names),
        "narrator": ", ".join(narrator_names),
        "series_name": series_name,
        "series_index": series_index,
        "year": year,
        "description": _text(raw.get("description") or raw.get("summary")),
        "cover": cover,
        "match_key": f"asin:{_text(raw.get('asin')).upper()}",
        "source": "audnexus",
        "kind": "audiobook",
    }


def score_candidate(
    candidate: Mapping[str, Any],
    *,
    title: str = "",
    author: str = "",
    narrator: str = "",
    series_name: str = "",
    series_index: str = "",
    year: Optional[int] = None,
    asin_hint: str = "",
) -> float:
    if is_valid_asin(asin_hint) and _text(asin_hint).upper() == _text(candidate.get("asin")).upper():
        return 1.0
    title_score = jaccard(title, candidate.get("title"))
    author_score = jaccard(author, candidate.get("author"))
    score = 0.45 * title_score + 0.35 * author_score
    if narrator and candidate.get("narrator"):
        score += 0.1 * jaccard(narrator, candidate.get("narrator"))
    if series_name and candidate.get("series_name"):
        score += 0.06 * jaccard(series_name, candidate.get("series_name"))
        if series_index and _text(series_index) == _text(candidate.get("series_index")):
            score += 0.04
    if year and candidate.get("year"):
        try:
            delta = abs(int(year) - int(candidate["year"]))
        except (TypeError, ValueError):
            delta = 99
        if delta == 0:
            score += 0.05
        elif delta == 1:
            score += 0.02
    # Exact normalized title+author boost (full-string / token-set equality — not substring)
    if _norm(title) and _norm(title) == _norm(candidate.get("title")):
        score += 0.08
    if _authors_match_exact(author, candidate.get("author")):
        score += 0.05
    return max(0.0, min(1.0, score))


def band_for_score(score: float) -> str:
    if score >= SCORE_AUTO:
        return "auto"
    if score >= SCORE_REVIEW:
        return "ambiguous"
    return "unmatched"


def review_reason_for_score(score: float) -> Optional[str]:
    band = band_for_score(score)
    if band == "auto":
        return None
    if band == "ambiguous":
        return REVIEW_AUDNEXUS_AMBIGUOUS
    return REVIEW_AUDNEXUS_UNMATCHED


def identity_from_candidate(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "kind": "audiobook",
        "title": _text(candidate.get("title")),
        "author": _text(candidate.get("author")),
        "series_name": _text(candidate.get("series_name")),
        "series_index": _text(candidate.get("series_index")),
        "year": candidate.get("year") if isinstance(candidate.get("year"), int) else None,
        "asin": _text(candidate.get("asin")).upper(),
        "isbn": _text(candidate.get("asin")).upper(),  # shelf key compat
        "description": _text(candidate.get("description")),
        "narrator": _text(candidate.get("narrator")),
        "match_key": _text(candidate.get("match_key")),
        "match_confidence": float(candidate.get("score") or 0),
        "source": "audnexus",
    }


def match_audiobook_tokens(
    tokens: Mapping[str, Any],
    *,
    client: AudnexusClient,
    limit: int = 8,
) -> Dict[str, Any]:
    """Score Audnexus candidates for normalized tokens."""
    candidates = client.search(
        title=_text(tokens.get("title")),
        author=_text(tokens.get("author")),
        asin=_text(tokens.get("asin")),
        narrator=_text(tokens.get("narrator")),
        series_name=_text(tokens.get("series_name")),
        series_index=_text(tokens.get("series_index")),
        year=tokens.get("year") if isinstance(tokens.get("year"), int) else None,
        limit=limit,
    )
    best = candidates[0] if candidates else None
    score = float(best.get("score") or 0) if best else 0.0
    reason = review_reason_for_score(score) if best else REVIEW_AUDNEXUS_UNMATCHED
    return {
        "candidates": candidates,
        "best": best,
        "score": score,
        "band": band_for_score(score) if best else "unmatched",
        "review_reason": reason,
        "identity": identity_from_candidate(best) if best and reason is None else None,
    }


def cache_path_for_settings(settings: Any) -> Path:
    data_dir = Path(getattr(settings, "data_dir", None) or getattr(settings, "DATA_DIR", ".") or ".")
    return Path(data_dir) / "audnexus_cache.sqlite"


def client_from_settings(
    settings: Any,
    *,
    transport: Optional[httpx.BaseTransport] = None,
) -> AudnexusClient:
    return AudnexusClient(
        cache=AudnexusCache(cache_path_for_settings(settings)),
        transport=transport,
        region=str(getattr(settings, "audnexus_region", "us") or "us"),
    )


def list_audnexus_candidates(
    work: Mapping[str, Any],
    *,
    settings: Any = None,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[AudnexusClient] = None,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    own = client is None
    aud = client or client_from_settings(settings or object(), transport=transport)
    try:
        matched = match_audiobook_tokens(work, client=aud, limit=limit)
        return list(matched.get("candidates") or [])
    except AudnexusError as error:
        logger.info("Audnexus search skipped: %s", error)
        return []
    finally:
        if own:
            aud.close()
