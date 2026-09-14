"""SABnzbd client for http://downloader.sl — addurl, queue, history."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

QUEUE_STATUSES = {
    "Queued": "queued",
    "Downloading": "downloading",
    "Paused": "queued",
    "Fetching": "downloading",
    "QuickCheck": "extracting",
    "Verifying": "extracting",
    "Repairing": "extracting",
    "Extracting": "extracting",
    "Moving": "extracting",
    "Running": "downloading",
}

HISTORY_STATUSES = {
    "Completed": "completed",
    "Failed": "failed",
}


class SABError(RuntimeError):
    """SABnzbd HTTP or payload failure."""


def map_sab_status(status: str, *, history: bool = False) -> str:
    raw = str(status or "").strip()
    table = HISTORY_STATUSES if history else QUEUE_STATUSES
    if raw in table:
        return table[raw]
    lowered = raw.lower()
    if lowered in {"completed", "finished"}:
        return "completed"
    if lowered in {"failed", "failure"}:
        return "failed"
    if lowered in {"extracting", "verifying", "repairing", "moving"}:
        return "extracting"
    if lowered in {"downloading", "fetching", "running"}:
        return "downloading"
    if lowered in {"queued", "paused", "idle"}:
        return "queued"
    return "queued" if not history else "failed"


class SABClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.base_url = str(base_url or "").rstrip("/")
        self.api_key = str(api_key or "").strip()
        self._client = httpx.Client(timeout=30.0, transport=transport, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def _call(self, mode: str, **params: Any) -> Dict[str, Any]:
        if not self.api_key:
            raise SABError("SABnzbd API key is not configured")
        query = {"mode": mode, "output": "json", "apikey": self.api_key}
        query.update({key: value for key, value in params.items() if value not in (None, "")})
        url = f"{self.base_url}/api"
        try:
            response = self._client.get(url, params=query)
        except httpx.HTTPError as error:
            raise SABError(str(error)) from error
        if response.status_code >= 400:
            raise SABError(f"SABnzbd HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as error:
            raise SABError("SABnzbd returned non-JSON") from error
        if not isinstance(payload, dict):
            raise SABError("SABnzbd returned an unexpected payload")
        return payload

    def addurl(self, nzb_url: str, *, nzbname: str = "", cat: str = "") -> str:
        payload = self._call("addurl", name=nzb_url, nzbname=nzbname, cat=cat)
        ids = payload.get("nzo_ids") or []
        if not ids:
            raise SABError("SABnzbd addurl did not return nzo_id")
        return str(ids[0])

    def queue(self, nzo_id: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if nzo_id:
            params["nzo_ids"] = nzo_id
        payload = self._call("queue", **params)
        queue = payload.get("queue") or payload
        slots = queue.get("slots") if isinstance(queue, dict) else []
        return list(slots or [])

    def history(self, nzo_id: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"limit": 50}
        if nzo_id:
            params["nzo_ids"] = nzo_id
        payload = self._call("history", **params)
        history = payload.get("history") or payload
        slots = history.get("slots") if isinstance(history, dict) else []
        return list(slots or [])

    def job_status(self, nzo_id: str) -> Dict[str, Any]:
        for slot in self.queue(nzo_id):
            if str(slot.get("nzo_id") or "") == nzo_id:
                return {
                    "nzo_id": nzo_id,
                    "status": map_sab_status(str(slot.get("status") or ""), history=False),
                    "sab_status": slot.get("status"),
                    "storage": slot.get("storage") or slot.get("path") or "",
                    "name": slot.get("filename") or slot.get("name") or "",
                    "where": "queue",
                    "raw": slot,
                }
        for slot in self.history(nzo_id):
            if str(slot.get("nzo_id") or "") == nzo_id:
                return {
                    "nzo_id": nzo_id,
                    "status": map_sab_status(str(slot.get("status") or ""), history=True),
                    "sab_status": slot.get("status"),
                    "storage": slot.get("storage") or slot.get("path") or "",
                    "name": slot.get("name") or slot.get("nzb_name") or "",
                    "where": "history",
                    "raw": slot,
                }
        return {
            "nzo_id": nzo_id,
            "status": "queued",
            "sab_status": "Unknown",
            "storage": "",
            "name": "",
            "where": "missing",
            "raw": {},
        }
