"""Business logic behind the HTTP routers. Services never import FastAPI."""

from __future__ import annotations

from typing import Optional


class ServiceError(Exception):
    """A request the service refuses. Routers map ``status_code`` onto the HTTP reply."""

    status_code = 400

    def __init__(self, detail: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(detail)
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(ServiceError):
    status_code = 404


__all__ = ["NotFoundError", "ServiceError"]
