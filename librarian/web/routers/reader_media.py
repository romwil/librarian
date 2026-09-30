"""Reading Room and listening media: cover, download, stream, chapters, convert."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from librarian.auth import require_role
from librarian.convert import convert_ebook
from librarian.ingest import PathDenied, confined_serve_path
from librarian.listen import extract_chapters
from librarian.serve import (
    existing_file_paths,
    is_inline_media,
    is_reading_file,
    is_streamable_audio,
    media_type_for,
    primary_reading_path,
    resolve_catalog_file,
    safe_filename,
    zip_files,
)
from librarian.web.deps import WebDeps
from librarian.web.schemas import (
    ConvertPayload,
)


def register_reader_media_routes(app: FastAPI, deps: WebDeps) -> None:
    """Register reader and media routes on the composition-root app."""
    root = deps.root
    db = deps.db

    @app.get("/api/works/{work_id}/cover")
    def work_cover(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        path = _media_file_or_404(str(work.get("cover_path") or ""), detail="Cover not found")
        return FileResponse(path, media_type="image/jpeg")

    def _media_file_or_404(raw: str, *, detail: str = "File not found") -> Path:
        try:
            path = confined_serve_path(raw, data_dir=root, must_exist=True)
        except PathDenied as error:
            raise HTTPException(status_code=404, detail=detail) from error
        if not path.is_file():
            raise HTTPException(status_code=404, detail=detail)
        return path

    def _files_on_disk(work_id: str) -> List[Path]:
        confined: List[Path] = []
        for path in existing_file_paths(db.files_for_work(work_id)):
            try:
                confined.append(confined_serve_path(str(path), data_dir=root, must_exist=True))
            except PathDenied:
                continue
        return confined

    def _canonical_file(work_id: str) -> Path:
        on_disk = _files_on_disk(work_id)
        if not on_disk:
            raise HTTPException(status_code=404, detail="File missing")
        return primary_reading_path(on_disk) or on_disk[0]

    def _unlink(path: str) -> None:
        try:
            os.unlink(path)
        except OSError:
            pass

    def _resolve_work_file(rows: List[Dict[str, Any]], file_id: str) -> Path:
        chosen = resolve_catalog_file(rows, file_id)
        if chosen is None:
            raise HTTPException(status_code=404, detail="File not found")
        return _media_file_or_404(str(chosen), detail="File not found")

    @app.get("/api/works/{work_id}/download")
    def work_download(
        work_id: str,
        request: Request,
        format: str = "",
        inline: int = 0,
        file: str = "",
    ):
        require_role(request.state.user, "owner", "op", "reader")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        rows = db.files_for_work(work_id)
        on_disk = _files_on_disk(work_id)
        if not on_disk:
            raise HTTPException(status_code=404, detail="File missing")
        chosen = None
        if str(file or "").strip():
            chosen = _resolve_work_file(rows, file)
        reading = primary_reading_path(on_disk)
        # Convert / Download may use Kindle; Reading Room never does.
        src = chosen or reading or on_disk[0]
        if format:
            fmt = format.lower()
            if f".{fmt}" != src.suffix.lower():
                cache = Path(root) / "conversions" / work_id
                try:
                    dest = convert_ebook(src, fmt, cache)
                except ValueError as error:
                    raise HTTPException(status_code=400, detail=str(error)) from error
                except FileNotFoundError as error:
                    raise HTTPException(status_code=422, detail=str(error)) from error
                except RuntimeError as error:
                    raise HTTPException(status_code=502, detail=str(error)) from error
                dest = _media_file_or_404(str(dest), detail="File missing")
                return FileResponse(dest, filename=dest.name)
        if inline:
            # Hard rule: Reading Room gets ONLY EPUB/CBZ/PDF — never Kindle, never a zip.
            if chosen is not None:
                if is_reading_file(chosen):
                    return FileResponse(
                        chosen,
                        filename=chosen.name,
                        media_type=media_type_for(chosen),
                        content_disposition_type="inline",
                    )
                if is_inline_media(chosen):
                    return FileResponse(
                        chosen,
                        filename=chosen.name,
                        media_type=media_type_for(chosen),
                        content_disposition_type="inline",
                    )
                raise HTTPException(
                    status_code=422,
                    detail="This volume isn’t a readable EPUB, CBZ, or PDF.",
                )
            if reading is not None:
                return FileResponse(
                    reading,
                    filename=reading.name,
                    media_type=media_type_for(reading),
                    content_disposition_type="inline",
                )
            inline_src = next((path for path in on_disk if is_inline_media(path)), None)
            if inline_src is not None:
                return FileResponse(
                    inline_src,
                    filename=inline_src.name,
                    media_type=media_type_for(inline_src),
                    content_disposition_type="inline",
                )
            raise HTTPException(
                status_code=422,
                detail="This volume isn’t a readable EPUB, CBZ, or PDF.",
            )
        if chosen is not None or len(on_disk) == 1:
            return FileResponse(
                src,
                filename=src.name,
                media_type=media_type_for(src),
                content_disposition_type="attachment",
            )
        zip_path = zip_files(on_disk)
        zip_name = f"{safe_filename(str(work.get('title') or 'volume'))}.zip"
        return FileResponse(
            zip_path,
            filename=zip_name,
            media_type="application/zip",
            background=BackgroundTask(_unlink, str(zip_path)),
        )

    @app.get("/api/works/{work_id}/stream")
    def work_stream(work_id: str, request: Request, file: str = ""):
        """Single-file audio stream for on-page album playback (household auth)."""
        require_role(request.state.user, "owner", "op", "reader")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        rows = db.files_for_work(work_id)
        chosen = _resolve_work_file(rows, file)
        if not is_streamable_audio(chosen):
            raise HTTPException(status_code=422, detail="Not a streamable audio file")
        return FileResponse(
            chosen,
            filename=chosen.name,
            media_type=media_type_for(chosen),
            content_disposition_type="inline",
        )

    @app.get("/api/works/{work_id}/chapters")
    def work_chapters(work_id: str, request: Request, file: str = ""):
        """Mutagen chapter markers for an audiobook file (empty list when none)."""
        require_role(request.state.user, "owner", "op", "reader")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        rows = db.files_for_work(work_id)
        wanted = str(file or "").strip()
        if wanted:
            chosen = _resolve_work_file(rows, wanted)
        else:
            on_disk = _files_on_disk(work_id)
            streamable = [path for path in on_disk if is_streamable_audio(path)]
            if not streamable:
                raise HTTPException(status_code=404, detail="File not found")
            chosen = streamable[0]
        if not is_streamable_audio(chosen):
            raise HTTPException(status_code=422, detail="Not a streamable audio file")
        return {"chapters": extract_chapters(chosen), "file": wanted or chosen.name}

    @app.post("/api/works/{work_id}/convert")
    def work_convert(work_id: str, payload: ConvertPayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        if db.get_work(work_id) is None:
            raise HTTPException(status_code=404, detail="Work not found")
        src = _canonical_file(work_id)
        cache = Path(root) / "conversions" / work_id
        try:
            dest = convert_ebook(src, payload.format, cache)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except FileNotFoundError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        return {"path": str(dest), "format": payload.format, "filename": dest.name}
