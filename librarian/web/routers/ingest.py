"""Filesystem browse, ingest kickoff, and organize preview."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile

from librarian.auth import require_role
from librarian.ingest import (
    PathDenied,
    confined_path,
    list_dir,
    protected_path_refusal,
    run_ingest_paths,
)
from librarian.ingest_progress import (
    IngestProgressReporter,
    begin_ingest_run,
    finish_ingest_run,
    is_ingest_running,
    read_ingest_progress,
)
from librarian.organize import organize_identified
from librarian.web.deps import WebDeps
from librarian.web.schemas import IngestPayload

logger = logging.getLogger("librarian.web")


def register_ingest_routes(app: FastAPI, deps: WebDeps) -> None:
    """Register ingest routes on the composition-root app."""
    root = deps.root
    db = deps.db
    settings = deps.settings
    enrich_job = deps.enrich_job
    scan_job = deps.scan_job
    ingest_job = deps.ingest_job
    extra_files_reprocess_job = deps.extra_files_reprocess_job
    purge_duplicates_job = deps.purge_duplicates_job
    purge_shells_job = deps.purge_shells_job
    split_mixed_kinds_job = deps.split_mixed_kinds_job

    def current_user(request: Request) -> Optional[Dict[str, Any]]:
        return deps.current_user(request)

    @app.get("/api/fs")
    def fs_list(request: Request, path: str = ""):
        require_role(request.state.user, "owner", "op")
        try:
            return list_dir(path)
        except PathDenied as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/ingest")
    def ingest_path(payload: IngestPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            target = confined_path(payload.path, must_exist=True)
        except PathDenied as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        refusal = protected_path_refusal(target, settings())
        if refusal:
            raise HTTPException(status_code=400, detail=refusal)
        user_id = request.state.user["id"]
        source_path = str(target)

        def run_ingest() -> None:
            reporter = IngestProgressReporter(root, source_path=source_path)
            try:
                run_ingest_paths(
                    db,
                    settings(),
                    paths=[target],
                    requested_by=user_id,
                    source="ingest",
                    progress=reporter,
                )
            except Exception as error:
                logger.exception("Add to the shelves failed")
                reporter.fail(str(error) or "Ingest failed")

        # Expand recursively in the worker so the meter denominator is real.
        kicked = ingest_job.start_if_idle(
            is_running=lambda: is_ingest_running(root),
            begin=lambda: begin_ingest_run(
                root, source_path=source_path, total=0, phase="scanning"
            ),
            target=run_ingest,
            name="librarian-ingest",
        )
        progress = read_ingest_progress(root)
        return {**progress, "kicked_off": kicked}

    @app.get("/api/ingest/status")
    def ingest_status(request: Request):
        require_role(request.state.user, "owner", "op")
        progress = read_ingest_progress(root)
        if str(progress.get("status") or "") != "running":
            return progress
        if ingest_job.alive():
            return progress
        # Rebuild / process restart left a stale "running" blob with no worker.
        return finish_ingest_run(
            root,
            error="Shelving stopped — the lamp was restarted. Try Add again.",
        )

    @app.post("/api/organize/preview")
    def organize_preview(folder: str, request: Request, guid: str = "", title: str = ""):
        require_role(request.state.user, "owner", "op")
        try:
            target = confined_path(folder, must_exist=True)
        except PathDenied as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        refusal = protected_path_refusal(target, settings())
        if refusal:
            raise HTTPException(status_code=400, detail=refusal)
        result = organize_identified(
            db,
            settings(),
            folder=target,
            indexer_item={"guid": guid, "title": title} if title or guid else None,
            apply=False,
        )
        return result
