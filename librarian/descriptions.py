"""Catalog description helpers — detect HTML and sanitize for household display."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import List

_HTMLISH = re.compile(r"<[a-z][\s\S]*>", re.IGNORECASE)
ALLOWED_TAGS = frozenset({"p", "br", "em", "strong", "i", "b", "ul", "ol", "li", "h3", "h4"})
_VOID = frozenset({"br"})


def looks_like_html(text: str) -> bool:
    return bool(_HTMLISH.search(str(text or "")))


class _AllowlistSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: List[str] = []
        self._stack: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name in {"script", "style", "iframe", "object", "embed"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if name not in ALLOWED_TAGS:
            return
        if name in _VOID:
            self._parts.append(f"<{name}>")
            return
        self._stack.append(name)
        self._parts.append(f"<{name}>")

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in {"script", "style", "iframe", "object", "embed"}:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if name not in ALLOWED_TAGS or name in _VOID:
            return
        if name in self._stack:
            while self._stack:
                current = self._stack.pop()
                self._parts.append(f"</{current}>")
                if current == name:
                    break

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._skip_depth:
            return
        self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._skip_depth:
            return
        self._parts.append(f"&#{name};")

    def result(self) -> str:
        while self._stack:
            self._parts.append(f"</{self._stack.pop()}>")
        return "".join(self._parts).strip()


def sanitize_description(text: str) -> str:
    """Keep allowlisted markup; drop scripts, attributes, and unknown tags."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    if not looks_like_html(raw):
        return raw
    parser = _AllowlistSanitizer()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:
        cleaned = re.sub(r"<[^>]+>", " ", raw)
        return re.sub(r"\s+", " ", cleaned).strip()
    return parser.result()


def normalize_description(text: str) -> str:
    """Enrich write-path: sanitize HTML blurbs (or leave plain text alone)."""
    return sanitize_description(text)
