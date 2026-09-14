"""Download job status machine: asked → queued → downloading → organized|review|failed."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from librarian.config import Settings
from librarian.db import Database
from librarian.nzbfinder import NZBFinderClient
from librarian.organize import organize_identified
from librarian.sabnzbd import SABClient

ACTIVE_STATUSES = ("asked", "queued", "downloading", "extracting", "identifying")


def enqueue_indexer_item(
    db: Database,
    settings: Settings,
    *,
    item: Dict[str, Any],
    requested_by: str,
    role: str,
    sab: Optional[SABClient] = None,
    nzb: Optional[NZBFinderClient] = None,
) -> Dict[str, Any]:
    if role == "reader":
        return db.create_job(
            {
                "status": "asked",
                "indexer_guid": item.get("guid"),
                "title": item.get("title"),
                "kind": item.get("kind"),
                "requested_by": requested_by,
                "payload": item,
            }
        )
    client = sab or SABClient(settings.sabnzbd_url, settings.sabnzbd_api_key)
    finder = nzb or NZBFinderClient(settings.nzbfinder_url, settings.nzbfinder_api_token)
    url = item.get("download_url") or finder.download_url(str(item.get("guid") or ""))
    nzo_id = client.addurl(url, nzbname=str(item.get("title") or "librarian"))
    return db.create_job(
        {
            "status": "queued",
            "nzo_id": nzo_id,
            "indexer_guid": item.get("guid"),
            "title": item.get("title"),
            "kind": item.get("kind"),
            "requested_by": requested_by,
            "payload": item,
        }
    )


def confirm_asked_job(
    db: Database,
    settings: Settings,
    job_id: str,
    *,
    sab: Optional[SABClient] = None,
    nzb: Optional[NZBFinderClient] = None,
) -> Dict[str, Any]:
    job = db.get_job(job_id)
    if job is None:
        raise ValueError("Job not found")
    if job["status"] != "asked":
        raise ValueError("Job is not an asked slip")
    item = job.get("payload") or {}
    client = sab or SABClient(settings.sabnzbd_url, settings.sabnzbd_api_key)
    finder = nzb or NZBFinderClient(settings.nzbfinder_url, settings.nzbfinder_api_token)
    url = item.get("download_url") or finder.download_url(str(item.get("guid") or job.get("indexer_guid") or ""))
    nzo_id = client.addurl(url, nzbname=str(job.get("title") or "librarian"))
    updated = db.update_job(job_id, status="queued", nzo_id=nzo_id)
    assert updated is not None
    return updated


def poll_job(
    db: Database,
    settings: Settings,
    job_id: str,
    *,
    sab: Optional[SABClient] = None,
) -> Dict[str, Any]:
    job = db.get_job(job_id)
    if job is None:
        raise ValueError("Job not found")
    if not job.get("nzo_id"):
        return job
    client = sab or SABClient(settings.sabnzbd_url, settings.sabnzbd_api_key)
    snapshot = client.job_status(str(job["nzo_id"]))
    status = snapshot["status"]
    if status in {"queued", "downloading", "extracting"}:
        updated = db.update_job(job_id, status=status, storage_path=snapshot.get("storage") or job.get("storage_path"))
        return updated or job
    if status == "failed":
        updated = db.update_job(job_id, status="failed", error=str(snapshot.get("sab_status") or "Failed"))
        return updated or job
    if status == "completed":
        storage = Path(str(snapshot.get("storage") or job.get("storage_path") or ""))
        db.update_job(job_id, status="identifying", storage_path=str(storage))
        organized = organize_identified(
            db,
            settings,
            folder=storage,
            indexer_item=job.get("payload") or {"title": job.get("title"), "guid": job.get("indexer_guid")},
        )
        final = "organized" if organized["organized"] else "review"
        updated = db.update_job(
            job_id,
            status=final,
            work_id=organized["work"]["id"],
            storage_path=str(storage),
        )
        return updated or job
    return job


def poll_active_jobs(db: Database, settings: Settings, *, sab: Optional[SABClient] = None) -> int:
    count = 0
    for job in db.list_jobs(statuses=ACTIVE_STATUSES):
        if not job.get("nzo_id"):
            continue
        poll_job(db, settings, job["id"], sab=sab)
        count += 1
    return count
