"""Translate service refusals into HTTP errors at the router edge."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from fastapi import HTTPException

from librarian.services import ServiceError


@contextmanager
def http_errors() -> Iterator[None]:
    try:
        yield
    except ServiceError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
