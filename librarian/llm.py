"""BYO OpenAI-compatible identify. Structured JSON only. Never invents an ISBN."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Mapping, Optional

import httpx

from librarian.config import Settings
from librarian.identify import Identity, extract_isbn, tidy_title
from librarian.kinds import ALL_KINDS, KIND_BOOK, KIND_COMIC, KIND_MAGAZINE

IDENTIFY_PROMPT = """You identify library media from Usenet names, folder names, and indexer fields.
Return ONLY JSON with keys:
kind (book|magazine|comic|audiobook|music|unknown),
title, series (string or null), author_or_artist (string or null),
year (number or null), isbn (string or null), album (string or null),
issue (string or null), confidence (0-1), rationale (short string),
query_terms (array of strings).
Never invent an ISBN. Only copy an ISBN that appears in the evidence.
If you are unsure of kind, use unknown.
"""

POLISH_PROMPT = """Rewrite the provided book description into a short readable blurb (2-3 sentences).
Use ONLY facts present in the source text. Never invent an ISBN, series index, year, or genre.
Do not add plot points that are not in the source. Reply with the blurb only.
"""

_MAX_BLURB_CHARS = 480


class LLMError(RuntimeError):
    """LLM HTTP or payload failure."""


def parse_json_object(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}


def evidence_isbn(text: str) -> str:
    return extract_isbn(text or "")


def merge_llm_identity(identity: Identity, payload: Mapping[str, Any], evidence: str) -> Identity:
    """Fill empty fields from the model. Drop any ISBN that is not in evidence."""
    if not payload:
        return identity
    kind = str(payload.get("kind") or "").strip().lower()
    if kind == "unknown":
        identity.review_reason = "unknown_identity"
        identity.confidence = "low"
        identity.source = "llm"
        identity.rationale = str(payload.get("rationale") or identity.rationale)
        return identity
    if kind in ALL_KINDS and identity.confidence != "high":
        identity.kind = kind

    title = tidy_title(str(payload.get("title") or ""))
    if title and (not identity.title or identity.confidence != "high"):
        identity.title = title
    author = tidy_title(str(payload.get("author_or_artist") or payload.get("author") or ""))
    if author and not identity.author:
        identity.author = author
    series = tidy_title(str(payload.get("series") or ""))
    if series and not identity.series_name:
        identity.series_name = series
    issue = str(payload.get("issue") or payload.get("album") or "").strip()
    if issue and not identity.series_index:
        identity.series_index = issue
    year = payload.get("year")
    if identity.year is None and str(year or "").isdigit():
        identity.year = int(year)

    claimed = extract_isbn(str(payload.get("isbn") or ""))
    allowed = evidence_isbn(evidence)
    if claimed and claimed == allowed:
        identity.isbn = claimed
    # Invented ISBN is discarded even when the model is confident.

    terms = payload.get("query_terms") or []
    if isinstance(terms, list):
        extra = [str(term) for term in terms if str(term).strip()]
        identity.query_terms = list(dict.fromkeys([*identity.query_terms, *extra]))

    identity.rationale = str(payload.get("rationale") or identity.rationale)
    identity.source = "llm"

    try:
        conf = float(payload.get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    if conf >= 0.8 and identity.kind == KIND_BOOK and identity.isbn and identity.author and identity.title:
        identity.confidence = "high"
        identity.review_reason = None
    elif conf >= 0.8 and identity.kind in (KIND_COMIC, KIND_MAGAZINE) and identity.series_name and identity.series_index:
        identity.confidence = "high"
        identity.review_reason = None
    return identity


class LLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        transport: Optional[httpx.BaseTransport] = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = str(base_url or "").rstrip("/")
        self.api_key = str(api_key or "").strip()
        self.model = model
        self._client = httpx.Client(timeout=timeout, transport=transport, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def identify(self, evidence: str) -> Dict[str, Any]:
        if not self.base_url or not self.api_key:
            raise LLMError("LLM is not configured")
        url = f"{self.base_url}/chat/completions"
        try:
            response = self._client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "temperature": 0.1,
                    "messages": [
                        {"role": "system", "content": IDENTIFY_PROMPT},
                        {"role": "user", "content": evidence},
                    ],
                },
            )
        except httpx.HTTPError as error:
            raise LLMError(str(error)) from error
        if response.status_code >= 400:
            raise LLMError(f"LLM HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as error:
            raise LLMError("LLM returned non-JSON") from error
        message = ((payload or {}).get("choices") or [{}])[0].get("message") or {}
        return parse_json_object(str(message.get("content") or ""))

    def polish_blurb(self, *, title: str, author: str, source_text: str) -> str:
        """Short blurb from existing catalog text only. Fail closed; never invents ISBN."""
        text = re.sub(r"\s+", " ", str(source_text or "")).strip()
        if not text or not self.base_url or not self.api_key:
            return ""
        url = f"{self.base_url}/chat/completions"
        user = (
            f"Title: {str(title or '').strip()}\n"
            f"Author: {str(author or '').strip()}\n\n"
            f"Source description:\n{text}"
        )
        try:
            response = self._client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "temperature": 0.2,
                    "messages": [
                        {"role": "system", "content": POLISH_PROMPT},
                        {"role": "user", "content": user},
                    ],
                },
            )
        except httpx.HTTPError as error:
            raise LLMError(str(error)) from error
        if response.status_code >= 400:
            raise LLMError(f"LLM HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as error:
            raise LLMError("LLM returned non-JSON") from error
        message = ((payload or {}).get("choices") or [{}])[0].get("message") or {}
        return _clean_blurb(str(message.get("content") or ""))


def _clean_blurb(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip().strip('"').strip("'")
    if not cleaned:
        return ""
    cleaned = re.sub(r"^(blurb|summary|description)\s*:\s*", "", cleaned, flags=re.I).strip()
    if len(cleaned) > _MAX_BLURB_CHARS:
        cleaned = cleaned[: _MAX_BLURB_CHARS - 1].rstrip() + "…"
    return cleaned


def client_from_settings(
    settings: Settings,
    *,
    transport: Optional[httpx.BaseTransport] = None,
) -> Optional[LLMClient]:
    if not str(settings.llm_base_url or "").strip() or not str(settings.llm_api_key or "").strip():
        return None
    return LLMClient(
        settings.llm_base_url,
        settings.llm_api_key,
        settings.llm_model or "gpt-4o-mini",
        transport=transport,
    )
