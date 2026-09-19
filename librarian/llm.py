"""BYO OpenAI-compatible identify. Structured JSON only. Never invents an ISBN."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any, Dict, Mapping, Optional

import httpx

from librarian.config import Settings
from librarian.identify import Identity, extract_isbn, looks_like_dump_title, tidy_title
from librarian.kinds import ALL_KINDS, KIND_AUDIOBOOK, KIND_BOOK, KIND_COMIC, KIND_MAGAZINE

logger = logging.getLogger(__name__)

IDENTIFY_PROMPT = """You identify library media from Usenet names, folder names, and indexer fields.
Return ONLY JSON with keys:
kind (book|magazine|comic|audiobook|music|unknown),
title, series (string or null), author_or_artist (string or null),
year (number or null), isbn (string or null), album (string or null),
issue (string or null), confidence (0-1), rationale (short string),
query_terms (array of strings).
Usenet dumps often use dots instead of spaces
(e.g. 102.Minutes.The.Untold.Story...Audio.book.MP3). Turn those into a human title
and author when the evidence supports them. Prefer audiobook when the name says
Audio book / Audiobook / M4B.
Never invent an ISBN. Only copy an ISBN that appears in the evidence.
Only set series/issue when confident. If you are unsure of kind, use unknown.
"""

POLISH_PROMPT = """Rewrite the provided book description into a short readable blurb (2-3 sentences).
Use ONLY facts present in the source text. Never invent an ISBN, series index, year, or genre.
Do not add plot points that are not in the source. Reply with the blurb only.
"""

_MAX_BLURB_CHARS = 480

LLM_UNSET_COPY = "Add a BYO LLM in Settings to suggest a title and author from this dump name."
LLM_FAIL_COPY = "The LLM did not return a usable identity. Keep the fields as they are, or edit by hand."
LLM_RATE_LIMIT_COPY = (
    "The reading room’s language model is rate-limited right now. "
    "Wait a minute, then try again — shelves and Find still work without it."
)

# Serialize all BYO LLM HTTP across the process so list load + chase + enrich
# cannot fan out and amplify provider 429s.
_LLM_GATE = threading.Lock()
_RATE_LIMIT_UNTIL = 0.0
_MAX_RETRIES = 4
_BASE_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 20.0


class LLMError(RuntimeError):
    """LLM HTTP or payload failure."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, retry_after: Optional[float] = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after

    @property
    def rate_limited(self) -> bool:
        return self.status_code == 429 or "rate-limited" in str(self).lower()


def friendly_llm_error(error: BaseException) -> str:
    """Household copy for UI empty states — never dump raw 'LLM HTTP 429'."""
    if isinstance(error, LLMError) and error.rate_limited:
        return LLM_RATE_LIMIT_COPY
    text = str(error or "").strip()
    if re.search(r"\b429\b|rate.?limit", text, re.I):
        return LLM_RATE_LIMIT_COPY
    if re.search(r"\b503\b|overloaded|temporarily unavailable", text, re.I):
        return "The language model is busy. Try again in a moment."
    return text or "The reading room could not reach the LLM."


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


def suggestion_fields(identity: Identity) -> Dict[str, Any]:
    """Review form shape. ISBN omitted unless validated onto the identity."""
    out: Dict[str, Any] = {
        "title": identity.title or "",
        "author": identity.author or "",
        "kind": identity.kind if identity.kind in ALL_KINDS else "",
        "confidence": identity.confidence,
        "rationale": identity.rationale or "",
        "source": identity.source or "llm",
    }
    if identity.series_name:
        out["series_name"] = identity.series_name
    if identity.series_index:
        out["series_index"] = identity.series_index
    if identity.year is not None:
        out["year"] = identity.year
    isbn = extract_isbn(identity.isbn)
    if isbn:
        out["isbn"] = isbn
    return out


def merge_llm_identity(identity: Identity, payload: Mapping[str, Any], evidence: str) -> Identity:
    """Fill empty or dump fields from the model. Drop any ISBN that is not in evidence."""
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
    dump_title = looks_like_dump_title(identity.title)
    if title and (not identity.title or dump_title or identity.confidence != "high"):
        identity.title = title
    author = tidy_title(
        str(payload.get("author_or_artist") or payload.get("author") or payload.get("artist") or "")
    )
    if author and (not identity.author or dump_title):
        identity.author = author
    series = tidy_title(str(payload.get("series") or payload.get("series_name") or ""))
    # Same gate as title: weak / dump filename series (e.g. Mystery Release) must yield to LLM.
    if series and (not identity.series_name or dump_title or identity.confidence != "high"):
        identity.series_name = series
    issue = str(
        payload.get("issue") or payload.get("series_index") or payload.get("album") or ""
    ).strip()
    if issue and (not identity.series_index or dump_title or identity.confidence != "high"):
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
    elif conf >= 0.8 and identity.kind == KIND_AUDIOBOOK and identity.author and identity.title:
        identity.confidence = "high"
        identity.review_reason = None
    elif conf >= 0.55 and identity.title and not looks_like_dump_title(identity.title):
        # Partial win for Review pre-fill — still needs Apply unless stack rules say high.
        identity.confidence = "low" if identity.confidence != "high" else identity.confidence
        if identity.kind in (KIND_BOOK, KIND_AUDIOBOOK) and not identity.author:
            identity.review_reason = identity.review_reason or "unknown_identity"
        elif not identity.review_reason:
            identity.review_reason = "low_confidence"
    return identity


class LLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        provider: str = "openai",
        transport: Optional[httpx.BaseTransport] = None,
        timeout: float = 60.0,
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        from librarian.llm_providers import default_base_url, normalize_provider

        self.provider = normalize_provider(provider)
        self.base_url = str(base_url or "").rstrip("/") or default_base_url(self.provider)
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "").strip()
        self.max_retries = max(0, int(max_retries))
        self._client = httpx.Client(timeout=timeout, transport=transport, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def configured(self) -> bool:
        # Gemini needs only a key (native endpoint has a fixed default host).
        if self.provider == "gemini":
            return bool(self.api_key and self.model)
        return bool(self.base_url and self.api_key and self.model)

    def chat_raw(self, *, system: str, user: str, temperature: float = 0.1) -> str:
        """Native chat completion per provider — returns message content text.

        OpenAI → Chat Completions. Anthropic → Messages. Gemini → generateContent.
        Calls are process-serialized. HTTP 429/503 retry with Retry-After or
        exponential backoff. Never logs the API key.
        """
        if not self.configured():
            raise LLMError("LLM is not configured")
        with _LLM_GATE:
            self._wait_global_cooldown()
            attempt = 0
            while True:
                try:
                    if self.provider == "anthropic":
                        response = self._post_anthropic(system=system, user=user, temperature=temperature)
                    elif self.provider == "gemini":
                        response = self._post_gemini(system=system, user=user, temperature=temperature)
                    else:
                        response = self._post_openai(system=system, user=user, temperature=temperature)
                except httpx.HTTPError as error:
                    raise LLMError(str(error)) from error
                if response.status_code in (429, 503):
                    retry_after = _retry_after_seconds(response)
                    if attempt >= self.max_retries:
                        self._mark_rate_limited(retry_after or _MAX_BACKOFF_SECONDS)
                        raise LLMError(
                            LLM_RATE_LIMIT_COPY,
                            status_code=response.status_code,
                            retry_after=retry_after,
                        )
                    delay = retry_after if retry_after is not None else min(
                        _MAX_BACKOFF_SECONDS,
                        _BASE_BACKOFF_SECONDS * (2**attempt),
                    )
                    logger.info(
                        "LLM %s HTTP %s — backing off %.1fs (attempt %s)",
                        self.provider,
                        response.status_code,
                        delay,
                        attempt + 1,
                    )
                    time.sleep(max(0.05, delay))
                    attempt += 1
                    continue
                if response.status_code >= 400:
                    raise LLMError(
                        friendly_llm_error(
                            LLMError(f"LLM HTTP {response.status_code}", status_code=response.status_code)
                        )
                        if response.status_code == 429
                        else f"LLM HTTP {response.status_code}",
                        status_code=response.status_code,
                    )
                try:
                    payload = response.json()
                except ValueError as error:
                    raise LLMError("LLM returned non-JSON") from error
                text = self._extract_text(payload)
                return text

    def _post_openai(self, *, system: str, user: str, temperature: float) -> httpx.Response:
        url = f"{self.base_url}/chat/completions"
        body = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        return self._client.post(url, headers=headers, json=body)

    def _post_anthropic(self, *, system: str, user: str, temperature: float) -> httpx.Response:
        # Native Messages API — not OpenAI chat/completions.
        base = self.base_url.rstrip("/")
        if base.endswith("/v1"):
            url = f"{base}/messages"
        else:
            url = f"{base}/v1/messages"
        body = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        return self._client.post(url, headers=headers, json=body)

    def _post_gemini(self, *, system: str, user: str, temperature: float) -> httpx.Response:
        # Native Generative Language API generateContent — key via query param only.
        base = self.base_url.rstrip("/")
        model = self.model
        # Allow model ids with or without models/ prefix.
        if model.startswith("models/"):
            model = model[len("models/") :]
        url = f"{base}/models/{model}:generateContent"
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": temperature},
        }
        # Never log params — api key lives here.
        return self._client.post(url, params={"key": self.api_key}, json=body)

    def _extract_text(self, payload: Any) -> str:
        if self.provider == "anthropic":
            blocks = (payload or {}).get("content") or []
            parts = []
            for block in blocks:
                if isinstance(block, Mapping) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
                elif isinstance(block, Mapping) and block.get("text"):
                    parts.append(str(block.get("text") or ""))
            return "".join(parts)
        if self.provider == "gemini":
            candidates = (payload or {}).get("candidates") or []
            if not candidates:
                # Soft block / empty — surface briefly without dumping key material.
                feedback = (payload or {}).get("promptFeedback") or {}
                if feedback:
                    raise LLMError("Gemini refused or blocked the prompt")
                return ""
            content = (candidates[0] or {}).get("content") or {}
            parts = content.get("parts") or []
            texts = []
            for part in parts:
                if isinstance(part, Mapping):
                    texts.append(str(part.get("text") or ""))
            return "".join(texts)
        message = ((payload or {}).get("choices") or [{}])[0].get("message") or {}
        return str(message.get("content") or "")

    def _wait_global_cooldown(self) -> None:
        global _RATE_LIMIT_UNTIL
        now = time.monotonic()
        if _RATE_LIMIT_UNTIL > now:
            delay = _RATE_LIMIT_UNTIL - now
            logger.info("LLM cooling down %.1fs after prior rate limit", delay)
            time.sleep(delay)

    def _mark_rate_limited(self, seconds: float) -> None:
        global _RATE_LIMIT_UNTIL
        _RATE_LIMIT_UNTIL = max(_RATE_LIMIT_UNTIL, time.monotonic() + max(1.0, float(seconds)))

    def chat_json(self, *, system: str, user: str, temperature: float = 0.1) -> Dict[str, Any]:
        """Chat completion parsed as a JSON object (empty dict on soft parse failure)."""
        return parse_json_object(self.chat_raw(system=system, user=user, temperature=temperature))

    def identify(self, evidence: str) -> Dict[str, Any]:
        return self.chat_json(system=IDENTIFY_PROMPT, user=evidence, temperature=0.1)

    def polish_blurb(self, *, title: str, author: str, source_text: str) -> str:
        """Short blurb from existing catalog text only. Fail closed; never invents ISBN."""
        text = re.sub(r"\s+", " ", str(source_text or "")).strip()
        if not text or not self.configured():
            return ""
        user = (
            f"Title: {str(title or '').strip()}\n"
            f"Author: {str(author or '').strip()}\n\n"
            f"Source description:\n{text}"
        )
        try:
            return _clean_blurb(self.chat_raw(system=POLISH_PROMPT, user=user, temperature=0.2))
        except LLMError as error:
            raise LLMError(str(error), status_code=getattr(error, "status_code", None)) from error


def _retry_after_seconds(response: httpx.Response) -> Optional[float]:
    raw = (response.headers.get("retry-after") or "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def reset_llm_rate_limit_state() -> None:
    """Test helper — clear process cooldown between cases."""
    global _RATE_LIMIT_UNTIL
    _RATE_LIMIT_UNTIL = 0.0


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
    from librarian.llm_providers import recommended_model, resolve_llm_connection

    resolved = resolve_llm_connection(settings)
    if not resolved.get("api_key"):
        return None
    model = resolved.get("model") or recommended_model(resolved["provider"])
    client = LLMClient(
        resolved["base_url"],
        resolved["api_key"],
        model,
        provider=resolved["provider"],
        transport=transport,
    )
    if not client.configured():
        client.close()
        return None
    return client
