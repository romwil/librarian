"""Perimeter headers, CSP, and same-origin checks for unsafe /api methods."""

from __future__ import annotations

from typing import Optional, Tuple
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from librarian.proxy import trust_proxy_headers

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
HOUSEHOLD_REQUEST_HEADER = "x-librarian"
HOUSEHOLD_REQUEST_VALUE = "1"

APP_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
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
    """This request's origin. Trusted X-Forwarded-* only when proxy trust is on."""
    if trust_proxy_headers():
        proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
        host = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
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


def origin_allowed(request: Request) -> bool:
    expected = expected_origin(request)
    got = request_origin(request)
    if expected is None or got is None:
        return False
    return expected == got


def household_header_ok(request: Request) -> bool:
    value = (request.headers.get(HOUSEHOLD_REQUEST_HEADER) or "").strip()
    return value == HOUSEHOLD_REQUEST_VALUE


def is_file_content_path(path: str) -> bool:
    """Direct file bytes: a book opened in a tab must not run script."""
    text = str(path or "")
    if not text.startswith("/api/works/"):
        return False
    return text.endswith("/download") or text.endswith("/stream")


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
