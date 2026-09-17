"""Wikipedia / Wikimedia enrich helpers. Public MediaWiki APIs only. Never invents ISBN."""

from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Optional, Tuple
from urllib.parse import urlencode

import httpx

from librarian.covers import DEFAULT_USER_AGENT

WIKI_API = "https://en.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
_MAX_EXTRACT_CHARS = 4000


def _clean_extract(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return ""
    if len(cleaned) > _MAX_EXTRACT_CHARS:
        cleaned = cleaned[: _MAX_EXTRACT_CHARS - 1].rstrip() + "…"
    return cleaned


def _page_from_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    pages = (payload.get("query") or {}).get("pages") or {}
    if not isinstance(pages, dict):
        return {}
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        if page.get("missing") is not None:
            continue
        return page
    return {}


def book_title_candidates(title: str, author: str = "", year: Optional[int] = None) -> list[str]:
    cleaned = str(title or "").strip()
    if not cleaned:
        return []
    author_name = str(author or "").strip()
    candidates = [cleaned, f"{cleaned} (novel)", f"{cleaned} (book)"]
    if year is not None:
        candidates.append(f"{cleaned} ({int(year)} novel)")
        candidates.append(f"{cleaned} ({int(year)} book)")
    if author_name:
        candidates.append(f"{cleaned} ({author_name} novel)")
        candidates.append(f"{author_name} {cleaned}")
    # Preserve order, drop dupes.
    seen: set[str] = set()
    out: list[str] = []
    for item in candidates:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def fetch_book_page(
    title: str,
    *,
    author: str = "",
    year: Optional[int] = None,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """Return extract + optional page image URL for a book title. Empty dict on miss."""
    own = client is None
    http = client or httpx.Client(timeout=20.0, transport=transport, follow_redirects=True)
    try:
        for candidate in book_title_candidates(title, author=author, year=year):
            params = {
                "action": "query",
                "format": "json",
                "prop": "extracts|pageimages|info",
                "exintro": "1",
                "explaintext": "1",
                "redirects": "1",
                "piprop": "original|thumbnail",
                "pithumbsize": "1000",
                "inprop": "url",
                "titles": candidate,
            }
            try:
                response = http.get(
                    f"{WIKI_API}?{urlencode(params)}",
                    headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"},
                )
            except httpx.HTTPError:
                continue
            if response.status_code >= 400:
                continue
            try:
                payload = response.json()
            except ValueError:
                continue
            if not isinstance(payload, dict):
                continue
            page = _page_from_payload(payload)
            extract = _clean_extract(str(page.get("extract") or ""))
            if not extract:
                continue
            image_url = ""
            original = page.get("original") if isinstance(page.get("original"), dict) else {}
            thumb = page.get("thumbnail") if isinstance(page.get("thumbnail"), dict) else {}
            for bucket in (original, thumb):
                url = str(bucket.get("source") or "").strip()
                if url.startswith("http"):
                    image_url = url
                    break
            image_title = str(page.get("pageimage") or "").strip()
            return {
                "extract": extract,
                "image_url": image_url,
                "image_title": image_title,
                "page_title": str(page.get("title") or candidate).strip(),
                "source": "wikipedia",
            }
        return {}
    finally:
        if own:
            http.close()


def commons_file_attribution(
    file_title: str,
    *,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
) -> Dict[str, str]:
    """Artist + license short name for a Commons file. Fail closed when unclear."""
    name = str(file_title or "").strip()
    if not name:
        return {}
    if not name.startswith("File:"):
        name = f"File:{name}"
    own = client is None
    http = client or httpx.Client(timeout=20.0, transport=transport, follow_redirects=True)
    try:
        params = {
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "titles": name,
            "iiprop": "url|extmetadata",
            "iiurlwidth": "1200",
        }
        try:
            response = http.get(
                f"{COMMONS_API}?{urlencode(params)}",
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
        page = _page_from_payload(payload if isinstance(payload, dict) else {})
        infos = page.get("imageinfo") if isinstance(page.get("imageinfo"), list) else []
        if not infos or not isinstance(infos[0], dict):
            return {}
        info = infos[0]
        meta = info.get("extmetadata") if isinstance(info.get("extmetadata"), dict) else {}
        artist = _meta_value(meta, "Artist")
        license_name = _meta_value(meta, "LicenseShortName") or _meta_value(meta, "License")
        credit = _meta_value(meta, "Credit")
        if not license_name:
            return {}
        url = str(info.get("thumburl") or info.get("url") or "").strip()
        attribution = ", ".join(part for part in (artist or credit, license_name) if part)
        if not attribution:
            return {}
        out = {"attribution": attribution, "license": license_name}
        if url.startswith("http"):
            out["image_url"] = url
        if artist:
            out["artist"] = artist
        return out
    finally:
        if own:
            http.close()


def _meta_value(meta: Mapping[str, Any], key: str) -> str:
    raw = meta.get(key)
    if isinstance(raw, dict):
        text = str(raw.get("value") or "").strip()
    else:
        text = str(raw or "").strip()
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def resolve_wikimedia_art(
    page: Mapping[str, Any],
    *,
    transport: Optional[httpx.BaseTransport] = None,
    client: Optional[httpx.Client] = None,
) -> Tuple[str, str]:
    """Return ``(image_url, attribution)``. Empty when license metadata is missing."""
    image_title = str(page.get("image_title") or "").strip()
    image_url = str(page.get("image_url") or "").strip()
    if image_title:
        meta = commons_file_attribution(image_title, transport=transport, client=client)
        if meta.get("attribution"):
            return str(meta.get("image_url") or image_url), str(meta["attribution"])
        return "", ""
    # Page thumbnail without a Commons title — refuse (no license string).
    return "", ""
