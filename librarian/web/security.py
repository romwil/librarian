"""Perimeter headers, CSP, and same-origin checks for unsafe /api methods."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Set, Tuple
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from librarian.proxy import trust_proxy_headers

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
HOUSEHOLD_REQUEST_HEADER = "x-librarian"
HOUSEHOLD_REQUEST_VALUE = "1"
_ENV_PUBLIC_ORIGINS = "LIBRARIAN_PUBLIC_ORIGINS"

APP_CSP = (
    "default-src 'self'; "
    "script-src 'self' blob:; "
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; "
    "img-src 'self' data: blob:; "
    "media-src 'self' blob:; "
    "frame-src 'self' blob:; "
    "connect-src 'self' blob:; "
    "worker-src 'self' blob:; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)
FILE_CSP = "sandbox; default-src 'none'"

PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=()"
CROSS_ORIGIN_REFUSED = "Cross-origin request refused"
MISSING_HOUSEHOLD_HEADER = "Missing household request header"

OriginParts = Tuple[str, str, int]


def origin_parts(value: str) -> Optional[OriginParts]:
    """Scheme, host, and port for an Origin or Referer. None if unusable."""
    text = str(value or "").strip()
    if not text or text.lower() == "null":
        return None
    parsed = urlparse(text)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    if scheme not in {"http", "https"} or not host:
        return None
    port = parsed.port
    if port is None:
        port = 443 if scheme == "https" else 80
    return (scheme, host, port)


def expected_origin(request: Request) -> Optional[OriginParts]:
    """This request's origin. Trusted X-Forwarded-* only when proxy trust is on.

    Cloudflare Tunnel often sets ``X-Forwarded-Proto: https`` while leaving
    ``Host`` as the public hostname and omitting ``X-Forwarded-Host``. When
    trust is on, Proto + Host is enough; do not require both forwarded fields.
    """
    if trust_proxy_headers():
        proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
        host = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
        if not host:
            host = (request.headers.get("host") or "").strip()
        if proto and host:
            parts = origin_parts(f"{proto}://{host}")
            if parts is not None:
                return parts
    return origin_parts(str(request.base_url))


def request_origin(request: Request) -> Optional[OriginParts]:
    """Caller origin from Origin, or Referer if Origin is absent."""
    origin = request.headers.get("origin") or ""
    if origin.strip():
        return origin_parts(origin)
    referer = request.headers.get("referer") or ""
    return origin_parts(referer)


def configured_public_origins(request: Request) -> Set[OriginParts]:
    """Household public landing origins (Settings / env), never foreign sites.

    ``public_base_url`` and ``LIBRARIAN_PUBLIC_ORIGINS`` name the guest-facing
    hostname (e.g. Cloudflare Access vip). They do not disable Origin checks.
    """
    allowed: Set[OriginParts] = set()
    raw = (os.environ.get(_ENV_PUBLIC_ORIGINS) or "").strip()
    for piece in raw.split(","):
        parts = origin_parts(piece.strip())
        if parts is not None:
            allowed.add(parts)
    try:
        data_dir = getattr(request.app.state, "data_dir", None)
        if data_dir is not None:
            from librarian.config import load_merged_settings

            settings = load_merged_settings(Path(data_dir))
            parts = origin_parts(str(getattr(settings, "public_base_url", "") or ""))
            if parts is not None:
                allowed.add(parts)
    except Exception:
        pass
    return allowed


def origin_allowed(request: Request) -> bool:
    got = request_origin(request)
    if got is None:
        return False
    expected = expected_origin(request)
    if expected is not None and expected == got:
        return True
    return got in configured_public_origins(request)


def household_header_ok(request: Request) -> bool:
    value = (request.headers.get(HOUSEHOLD_REQUEST_HEADER) or "").strip()
    return value == HOUSEHOLD_REQUEST_VALUE


def is_file_content_path(path: str) -> bool:
    """Direct file bytes: a book opened in a tab must not run script."""
    text = str(path or "")
    if not text.startswith("/api/works/"):
        return False
    return text.endswith("/download") or text.endswith("/stream")


def should_gzip_path(path: str) -> bool:
    """JSON and hashed assets compress. A volume must not — range reads and RAM."""
    return not is_file_content_path(path)


class FileSkipGZipMiddleware(GZipMiddleware):
    """Gzip JSON/assets. Skip /download and /stream so PDFs can range and not hang."""

    def __init__(self, app: ASGIApp, minimum_size: int = 500, compresslevel: int = 9) -> None:
        super().__init__(app, minimum_size=minimum_size, compresslevel=compresslevel)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") == "http" and not should_gzip_path(str(scope.get("path") or "")):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


def csp_for(request: Request) -> str:
    if is_file_content_path(request.url.path):
        return FILE_CSP
    return APP_CSP


def apply_security_headers(request: Request, response: Response) -> Response:
    """Baseline headers on every response. Hashed /assets are immutable."""
    headers = response.headers
    headers["X-Content-Type-Options"] = "nosniff"
    headers["X-Frame-Options"] = "DENY"
    headers["Referrer-Policy"] = "no-referrer"
    headers["Permissions-Policy"] = PERMISSIONS_POLICY
    headers["Cross-Origin-Opener-Policy"] = "same-origin"
    headers["Content-Security-Policy"] = csp_for(request)
    headers["X-Robots-Tag"] = "noindex, nofollow"
    if request.url.path.startswith("/assets/"):
        headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


def origin_refusal(request: Request, detail: str) -> JSONResponse:
    response = JSONResponse({"detail": detail}, status_code=403)
    apply_security_headers(request, response)
    return response


async def perimeter_middleware(request: Request, call_next):
    """Origin + X-Librarian on unsafe /api; security headers on every response."""
    method = request.method.upper()
    path = request.url.path
    if method in UNSAFE_METHODS and path.startswith("/api/"):
        if not origin_allowed(request):
            return origin_refusal(request, CROSS_ORIGIN_REFUSED)
        if not household_header_ok(request):
            return origin_refusal(request, MISSING_HOUSEHOLD_HEADER)
    response = await call_next(request)
    return apply_security_headers(request, response)
