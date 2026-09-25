"""Download job status machine: asked → queued → downloading → organized|review|failed."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from librarian.arr import ArrError, expect_on_arr, notify_arr_downloaded, sab_category_for_kind
from librarian.config import Settings
from librarian.db import Database
from librarian.identify import inspect_complete_folder, resolve_storage_path
from librarian.indexers.hosts import client_for_host
from librarian.indexers.query import build_job_payload, catalog_author, catalog_title
from librarian.kinds import EXTRA_KINDS, KIND_MOVIE, KIND_TV, KIND_XXX
from librarian.nzbfinder import NZBFinderClient, NZBFinderError
from librarian.organize import organize_identified
from librarian.sabnzbd import SABClient

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("asked", "queued", "downloading", "extracting", "identifying")

UNPACK_STUCK_ERROR = "Unpack did not finish; archives remain in the complete folder"
MISSING_FOLDER_ERROR = "Complete folder not found after remapping SAB storage"
NO_PAYLOAD_ERROR = "No usable files in the complete folder (only par2/nfo/nzb or empty)"


def _fetch_details(finder: NZBFinderClient, guid: str) -> Dict[str, Any]:
    if not guid:
        return {}
    try:
        return finder.details(guid)
    except NZBFinderError:
        return {}


def _job_payload(item: Dict[str, Any], *, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    sought = item.get("sought") if isinstance(item.get("sought"), dict) else item
    selected = item.get("selected") if isinstance(item.get("selected"), dict) else item
    retrieved = item.get("retrieved") if isinstance(item.get("retrieved"), dict) else {}
    candidates = item.get("candidates") if isinstance(item.get("candidates"), list) else []
    payload = build_job_payload(
        sought=sought,
        selected=selected,
        retrieved=retrieved,
        details=details,
        candidates=candidates,
        rank_method=str(item.get("rank_method") or ""),
        rank_reason=str(item.get("rank_reason") or ""),
    )
    return payload


def _queue_download(
    db: Database,
    settings: Settings,
    *,
    item: Dict[str, Any],
    requested_by: str,
    payload: Dict[str, Any],
    sab: Optional[SABClient] = None,
    nzb: Optional[NZBFinderClient] = None,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    finder = nzb or client_for_host(
        settings,
        str((item.get("selected") or {}).get("host_id") or item.get("host_id") or ""),
    )
    guid = str(payload.get("guid") or (item.get("selected") or {}).get("guid") or item.get("guid") or "")
    selected = payload.get("selected") or {}
    title = payload.get("title") or item.get("title")
    kind = str(payload.get("kind") or item.get("kind") or "")
    client = sab or SABClient(settings.sabnzbd_url, settings.sabnzbd_api_key)
    # Push NZB bytes (addfile) with Librarian's indexer credentials. Never hand SAB a
    # stripped download_url (public hits drop api_token → Unauthorized / WAIT).
    # SAB nzbname is the release title, not the Find query (sought.q → title).
    nzo_id = _submit_nzb_to_sab(
        client,
        finder,
        guid=guid,
        nzbname=_sab_nzbname(selected=selected, item=item, catalog_title=str(title or "")),
        cat=sab_category_for_kind(settings, kind),
    )
    status = "queued"
    error = None
    if kind in {KIND_MOVIE, KIND_TV}:
        try:
            payload["arr"] = expect_on_arr(settings, kind, {**item, **payload, "selected": selected})
        except ArrError as err:
            status = "review"
            error = str(err)
            payload["arr_error"] = str(err)
    if kind == KIND_XXX:
        payload["arr"] = {"service": None}
    fields = {
        "status": status,
        "nzo_id": nzo_id,
        "indexer_guid": payload.get("guid") or guid,
        "title": title,
        "kind": kind,
        "requested_by": requested_by,
        "payload": payload,
        "error": error,
    }
    if job_id:
        updated = db.update_job(job_id, **fields)
        assert updated is not None
        return updated
    return db.create_job(fields)


def _sab_nzbname(
    *,
    selected: Dict[str, Any],
    item: Dict[str, Any],
    catalog_title: str,
) -> str:
    """Name SAB sees in history — release/dump title, never the Find query string."""
    _ = item  # top-level title may be sought.q; payload.selected is authoritative
    release = str(selected.get("title") or "").strip()
    catalog = str(catalog_title or "").strip()
    if release:
        return release
    return catalog or "librarian"


def _submit_nzb_to_sab(
    client: SABClient,
    finder: NZBFinderClient,
    *,
    guid: str,
    nzbname: str,
    cat: str,
) -> str:
    """Fetch NZB with Librarian credentials, then SAB addfile. Fail closed — no addurl."""
    if not guid:
        raise NZBFinderError(f"{finder.label} download needs a guid")
    nzb_bytes = finder.fetch_nzb(guid)
    filename = guid if str(guid).endswith(".nzb") else f"{guid}.nzb"
    return client.addfile(nzb_bytes, filename=filename, nzbname=nzbname, cat=cat)


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
    finder = nzb or client_for_host(
        settings,
        str((item.get("selected") or {}).get("host_id") or item.get("host_id") or ""),
    )
    guid = str((item.get("selected") or {}).get("guid") or item.get("guid") or "")
    payload = _job_payload(item, details=_fetch_details(finder, guid))
    title = payload.get("title") or item.get("title")
    kind = payload.get("kind") or item.get("kind")
    if role == "reader":
        return db.create_job(
            {
                "status": "asked",
                "indexer_guid": payload.get("guid") or guid,
                "title": title,
                "kind": kind,
                "requested_by": requested_by,
                "payload": payload,
            }
        )
    return _queue_download(
        db,
        settings,
        item=item,
        requested_by=requested_by,
        payload=payload,
        sab=sab,
        nzb=finder,
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
    payload = dict(item) if isinstance(item, dict) else {}
    return _queue_download(
        db,
        settings,
        item=item if isinstance(item, dict) else {"title": job.get("title")},
        requested_by=str(job.get("requested_by") or ""),
        payload=payload,
        sab=sab,
        nzb=nzb,
        job_id=job_id,
    )


def find_identity_item(job: Dict[str, Any]) -> Dict[str, Any]:
    """Catalog identity from the Find request — never SAB's nzo filename."""
    payload = dict(job.get("payload") or {})
    payload.pop("name", None)
    sought = payload.get("sought") if isinstance(payload.get("sought"), dict) else {}
    retrieved = payload.get("retrieved") if isinstance(payload.get("retrieved"), dict) else {}
    selected = payload.get("selected") if isinstance(payload.get("selected"), dict) else {}
    kind = job.get("kind") or payload.get("kind") or sought.get("kind") or selected.get("kind") or ""
    title = (
        job.get("title")
        or payload.get("title")
        or catalog_title(sought, selected, retrieved)
        or payload.get("book_title")
        or ""
    )
    author = payload.get("author") or catalog_author(sought, selected, retrieved)
    isbn = payload.get("isbn") or sought.get("isbn") or retrieved.get("isbn") or ""
    if kind == "music":
        isbn = ""
    payload["title"] = title
    payload["author"] = author
    payload["isbn"] = isbn
    payload["kind"] = kind
    payload["guid"] = job.get("indexer_guid") or payload.get("guid") or selected.get("guid") or ""
    payload["category"] = payload.get("category") or selected.get("category")
    payload["book_title"] = payload.get("book_title") or retrieved.get("book_title") or ""
    payload["series"] = sought.get("series") or payload.get("series") or ""
    payload["issue"] = sought.get("issue") or payload.get("issue") or ""
    payload["sought"] = sought
    payload["selected"] = selected
    payload["retrieved"] = retrieved
    return payload


def _snapshot_job_fields(snapshot: Dict[str, Any], *, storage_path: Optional[str] = None) -> Dict[str, Any]:
    fields: Dict[str, Any] = {
        "sab_status": snapshot.get("sab_status") or "",
        "nzo_name": snapshot.get("name") or "",
        "percent": snapshot.get("percentage"),
        "bytes": snapshot.get("bytes"),
    }
    path = storage_path if storage_path is not None else str(snapshot.get("storage") or "")
    if path:
        fields["storage_path"] = path
    return fields


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
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    if str(payload.get("source") or "") in {"ingest", "watch"}:
        from librarian.ingest import progress_ingest_job

        return progress_ingest_job(db, settings, job_id)
    if not job.get("nzo_id"):
        return job
    client = sab or SABClient(settings.sabnzbd_url, settings.sabnzbd_api_key)
    snapshot = client.job_status(str(job["nzo_id"]))
    status = snapshot["status"]
    sab_fields = _snapshot_job_fields(
        snapshot, storage_path=str(snapshot.get("storage") or job.get("storage_path") or "") or None
    )
    if status in {"queued", "downloading", "extracting"}:
        updated = db.update_job(job_id, status=status, **sab_fields)
        return updated or job
    if status == "failed":
        reason = str(snapshot.get("fail_message") or snapshot.get("sab_status") or "Failed")
        updated = db.update_job(job_id, status="failed", error=reason, **sab_fields)
        return updated or job
    if status == "completed":
        raw = Path(str(snapshot.get("storage") or job.get("storage_path") or ""))
        storage = resolve_storage_path(raw, settings.complete_root)
        sab_fields = _snapshot_job_fields(snapshot, storage_path=str(storage))
        kind = str(job.get("kind") or (job.get("payload") or {}).get("kind") or "")
        if kind in EXTRA_KINDS:
            if kind == KIND_XXX:
                updated = db.update_job(job_id, status="organized", error=None, **sab_fields)
                return updated or job
            try:
                notify_arr_downloaded(settings, kind, str(storage))
            except ArrError as error:
                updated = db.update_job(job_id, status="review", error=str(error), **sab_fields)
                return updated or job
            updated = db.update_job(job_id, status="organized", error=None, **sab_fields)
            return updated or job
        # Missing folder is a hard fail (nothing to unpack). Archives-only /
        # empty dumps go through organize_identified — it runs par2+unar and
        # parks a Review slip when still stuck. Never mark failed with no work_id
        # for unpack_stuck: that hid audiobooks from Review/Queue recovery.
        inspection = inspect_complete_folder(storage)
        problem = inspection.get("problem")
        if problem == "missing_folder":
            updated = db.update_job(
                job_id,
                status="failed",
                error=MISSING_FOLDER_ERROR + f" ({storage})",
                **sab_fields,
            )
            return updated or job
        db.update_job(job_id, status="identifying", error=None, **sab_fields)
        item = find_identity_item(job)
        organized = organize_identified(
            db,
            settings,
            folder=storage,
            indexer_item=item,
            move_source=True,
        )
        if organized.get("skipped_duplicate"):
            final = "skipped"
        elif organized["organized"] or organized.get("expanded"):
            final = "organized"
        else:
            final = "review"
        updated = db.update_job(
            job_id,
            status=final,
            work_id=organized["work"]["id"],
            error=None,
            **sab_fields,
        )
        return updated or job
    return job


def poll_active_jobs(db: Database, settings: Settings, *, sab: Optional[SABClient] = None) -> int:
    count = 0
    have_sab = sab is not None or bool(str(settings.sabnzbd_api_key or "").strip())
    for job in db.list_jobs(statuses=ACTIVE_STATUSES):
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        if str(payload.get("source") or "") in {"ingest", "watch"}:
            from librarian.ingest import progress_ingest_job

            try:
                progress_ingest_job(db, settings, job["id"])
            except Exception:
                logger.exception("Ingest/watch poll failed for job %s", job.get("id"))
            count += 1
            continue
        if not job.get("nzo_id") or not have_sab:
            continue
        try:
            poll_job(db, settings, job["id"], sab=sab)
        except Exception:
            logger.exception("Job poll failed for %s", job.get("id"))
        count += 1
    return count
