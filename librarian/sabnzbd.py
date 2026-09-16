"""SABnzbd client for http://downloader.sl — addurl, queue, history, get_files."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

QUEUE_STATUSES = {
    "Queued": "queued",
    "Paused": "queued",
    "Propagating": "queued",
    "Downloading": "downloading",
    "Fetching": "downloading",
    "Running": "downloading",
    "QuickCheck": "extracting",
    "Verifying": "extracting",
    "Repairing": "extracting",
    "Extracting": "extracting",
    "Moving": "extracting",
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
    if lowered in {"extracting", "verifying", "repairing", "moving", "quickcheck"}:
        return "extracting"
    if lowered in {"downloading", "fetching", "running"}:
        return "downloading"
    if lowered in {"queued", "paused", "idle", "propagating"}:
        return "queued"
    return "queued" if not history else "failed"


def _intish(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _stage_fail_message(slot: Dict[str, Any]) -> str:
    action = str(slot.get("action_line") or "").strip()
    lowered = action.lower()
    if action and any(token in lowered for token in ("fail", "error", "abort")):
        return action
    for stage in slot.get("stage_log") or []:
        if not isinstance(stage, dict):
            continue
        name = str(stage.get("name") or "")
        for line in stage.get("actions") or []:
            text = str(line or "")
            blob = f"{name} {text}".lower()
            if name.lower() in {"unpack", "repair"} and any(
                token in blob for token in ("fail", "error", "abort", "damaged")
            ):
                return str(text).strip() or f"{name} failed"
    return ""


def _slot_fail_message(slot: Dict[str, Any]) -> str:
    return str(slot.get("fail_message") or "").strip() or _stage_fail_message(slot)


def _slot_bytes(slot: Dict[str, Any]) -> Optional[int]:
    for key in ("bytes", "downloaded", "sizebytes"):
        parsed = _intish(slot.get(key))
        if parsed is not None:
            return parsed
    mb = _intish(slot.get("mb"))
    if mb is not None:
        return mb * 1024 * 1024
    return None


def _slot_percent(slot: Dict[str, Any]) -> Optional[str]:
    raw = slot.get("percentage")
    if raw not in (None, ""):
        return str(raw)
    mb = _intish(slot.get("mb"))
    left = _intish(slot.get("mbleft"))
    if mb and left is not None and mb > 0:
        done = max(0, min(100, int(round(100 * (mb - left) / mb))))
        return str(done)
    return None


def snapshot_from_slot(slot: Dict[str, Any], *, nzo_id: str, history: bool) -> Dict[str, Any]:
    raw_status = str(slot.get("status") or "")
    mapped = map_sab_status(raw_status, history=history)
    explicit_fail = str(slot.get("fail_message") or "").strip()
    fail_message = _slot_fail_message(slot)
    if history and explicit_fail and mapped == "completed":
        mapped = "failed"
    name = slot.get("filename") or slot.get("name") or slot.get("nzb_name") or ""
    storage = slot.get("storage") or slot.get("path") or ""
    return {
        "nzo_id": nzo_id,
        "status": mapped,
        "sab_status": raw_status or ("Failed" if mapped == "failed" else ""),
        "fail_message": fail_message,
        "storage": storage,
        "path": slot.get("path") or "",
        "name": str(name or ""),
        "percentage": _slot_percent(slot),
        "bytes": _slot_bytes(slot),
        "files": [],
        "where": "history" if history else "queue",
        "raw": slot,
    }


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
        error = payload.get("error")
        if error:
            raise SABError(str(error))
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

    def get_files(self, nzo_id: str) -> List[Dict[str, Any]]:
        """Documented `mode=get_files&value=nzo_id` — NZB articles while the job is in queue."""
        payload = self._call("get_files", value=nzo_id)
        files = payload.get("files")
        if isinstance(files, list):
            return list(files)
        return []

    def job_status(self, nzo_id: str) -> Dict[str, Any]:
        for slot in self.queue(nzo_id):
            if str(slot.get("nzo_id") or "") == nzo_id:
                snap = snapshot_from_slot(slot, nzo_id=nzo_id, history=False)
                try:
                    snap["files"] = self.get_files(nzo_id)
                except SABError:
                    snap["files"] = []
                return snap
        for slot in self.history(nzo_id):
            if str(slot.get("nzo_id") or "") == nzo_id:
                return snapshot_from_slot(slot, nzo_id=nzo_id, history=True)
        return {
            "nzo_id": nzo_id,
            "status": "queued",
            "sab_status": "Unknown",
            "fail_message": "",
            "storage": "",
            "path": "",
            "name": "",
            "percentage": None,
            "bytes": None,
            "files": [],
            "where": "missing",
            "raw": {},
        }
