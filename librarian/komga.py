"""Komga federation — scan webhook + deep-links. Fail-soft; never invent book ids."""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional
from urllib.parse import quote

import httpx

from librarian.covers import DEFAULT_USER_AGENT
from librarian.kinds import KIND_COMIC

logger = logging.getLogger(__name__)


class KomgaError(RuntimeError):
    """Komga HTTP failure. Messages must never include the API key."""


def _text(value: Any) -> str:
    return str(value or "").strip()


class KomgaClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        library_id: str = "",
        transport: Optional[httpx.BaseTransport] = None,
        client: Optional[httpx.Client] = None,
        timeout: float = 12.0,
    ) -> None:
        self.base_url = _text(base_url).rstrip("/")
        self.api_key = _text(api_key)
        self.library_id = _text(library_id)
        self._own = client is None
        self._client = client or httpx.Client(
            timeout=timeout, transport=transport, follow_redirects=True
        )

    def close(self) -> None:
        if self._own:
            self._client.close()

    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.library_id)

    def _headers(self) -> Dict[str, str]:
        return {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json",
            "X-API-Key": self.api_key,
        }

    def trigger_scan(self) -> bool:
        """POST library scan. Returns True on success; raises KomgaError on hard failure."""
        if not self.configured():
            return False
        url = f"{self.base_url}/api/v1/libraries/{quote(self.library_id, safe='')}/scan"
        try:
            response = self._client.post(url, headers=self._headers())
        except httpx.HTTPError as error:
            raise KomgaError("Komga could not be reached") from error
        if response.status_code in (200, 202, 204):
            return True
        if response.status_code == 401:
            raise KomgaError("Komga key was refused")
        if response.status_code == 404:
            raise KomgaError("Komga library was not found")
        raise KomgaError(f"Komga HTTP {response.status_code}")


def komga_web_href(settings: Any, work: Optional[Mapping[str, Any]] = None) -> Optional[str]:
    """Deep-link into Komga web UI (library or series search)."""
    base = _text(getattr(settings, "komga_url", ""))
    library_id = _text(getattr(settings, "komga_library_id", ""))
    if not base:
        return None
    if library_id:
        series = _text((work or {}).get("series_name") or (work or {}).get("title"))
        if series:
            return (
                f"{base.rstrip('/')}/#/libraries/{quote(library_id, safe='')}"
                f"/series?search={quote(series)}"
            )
        return f"{base.rstrip('/')}/#/libraries/{quote(library_id, safe='')}"
    return base.rstrip("/") + "/"


def komga_reader_link(
    work: Optional[Mapping[str, Any]],
    settings: Any,
) -> Optional[Dict[str, Any]]:
    if not work or _text(work.get("kind")) != KIND_COMIC:
        return None
    if not _text(getattr(settings, "komga_url", "")):
        return None
    href = komga_web_href(settings, work)
    if not href:
        return None
    return {"href": href, "label": "Open in Komga", "provider": "komga"}


def komga_payload(work: Optional[Mapping[str, Any]], settings: Any) -> Dict[str, Any]:
    link = komga_reader_link(work, settings)
    return {
        "configured": bool(
            _text(getattr(settings, "komga_url", ""))
            and _text(getattr(settings, "komga_api_key", ""))
            and _text(getattr(settings, "komga_library_id", ""))
        ),
        "reader": link,
    }


def notify_komga_scan(settings: Any, *, transport: Optional[httpx.BaseTransport] = None) -> Dict[str, Any]:
    """Non-blocking intent: attempt scan, swallow errors into a small status dict."""
    url = _text(getattr(settings, "komga_url", ""))
    key = _text(getattr(settings, "komga_api_key", ""))
    library_id = _text(getattr(settings, "komga_library_id", ""))
    if not (url and key and library_id):
        return {"ok": False, "skipped": True, "reason": "not_configured"}
    client = KomgaClient(url, key, library_id=library_id, transport=transport)
    try:
        client.trigger_scan()
        return {"ok": True, "skipped": False}
    except KomgaError as error:
        logger.warning("Komga scan failed: %s", error)
        return {"ok": False, "skipped": False, "error": str(error)}
    except Exception as error:  # noqa: BLE001 — fail-soft federation
        logger.warning("Komga scan unexpected failure: %s", error)
        return {"ok": False, "skipped": False, "error": "unexpected"}
    finally:
        client.close()
