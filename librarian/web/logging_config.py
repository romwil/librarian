"""Stdout INFO logging with Privacy constraints (PERF-008).

Access lines use the FastAPI route template only — never the raw URL, query
string, path values, user id, client IP, or API keys. ``httpx`` stays at
WARNING so indexer URLs with ``apikey=`` are not logged.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import time
from typing import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("librarian.web.access")

_UUID_SEGMENT = re.compile(
    r"/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_HEX_SEGMENT = re.compile(r"/[0-9a-fA-F]{16,}")
_DIGIT_SEGMENT = re.compile(r"/\d+")


def configure_logging() -> None:
    """Attach a stdout handler when the process has none; always pin noisy loggers."""
    level_name = (os.environ.get("LIBRARIAN_LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            stream=sys.stdout,
        )
    elif root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
    access.setLevel(logging.WARNING)


def route_template(request: Request) -> str:
    """Prefer the matched route path; collapse identifiers when middleware short-circuits."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    raw = str(request.scope.get("path") or "")
    collapsed = _UUID_SEGMENT.sub("/{id}", raw)
    collapsed = _HEX_SEGMENT.sub("/{id}", collapsed)
    collapsed = _DIGIT_SEGMENT.sub("/{id}", collapsed)
    return collapsed or "unmatched"


async def log_http_request(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "%s %s %s %.1fms",
        request.method,
        route_template(request),
        response.status_code,
        duration_ms,
    )
    return response
