"""Hall, search, browse, works, queue, gaps, and reader routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile

from librarian.web.deps import WebDeps
from librarian.web.route_imports import *  # noqa: F403


def register_catalog_routes(app: FastAPI, deps: WebDeps) -> None:
    """Register catalog routes on the composition-root app."""
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

    @app.get("/api/hall")
    def hall(request: Request):
        user = request.state.user
        recent = db.list_works(limit=18, require_files=True)
        favorites = db.favorite_works(user["id"], limit=18)
        areas = {
            "books": db.list_works(kind="book", limit=12, require_files=True),
            "magazines": db.list_works(kind="magazine", limit=12, require_files=True),
            "comics": db.list_works(kind="comic", limit=12, require_files=True),
            "audiobooks": db.list_works(kind="audiobook", limit=12, require_files=True),
            "incoming_music": db.list_works(kind="music", music_state="incoming", limit=12, require_files=True),
        }
        gaps = []
        if user["role"] in ("owner", "op"):
            gaps = gap_cards(catalog_gaps(db, settings()))
        continue_rows = db.continue_works(user["id"], limit=18)
        continue_split = split_continue_rails(continue_rows)
        surprise = None
        if recent:
            surprise = public_work(recent[0])
        elif favorites:
            surprise = public_work(favorites[0])
        counts = db.kind_counts()
        celebrations = db.unseen_celebrations(
            user["id"],
            celebration_candidates(
                kind_counts=counts,
                author_year_counts=db.author_year_counts(year=datetime.now().year),
            ),
        )
        tonight = tonight_shelf(
            continue_items=continue_rows,
            gaps=gaps,
            surprise=surprise,
        )
        return {
            "whats_new": public_works(recent),
            "favorites": public_works(favorites),
            "areas": {key: public_works(value) for key, value in areas.items()},
            "gaps": gaps,
            "continue": continue_split["reading"],
            "continue_listening": continue_split["listening"],
            "tonight": tonight,
            "celebrations": celebrations,
            "kind_counts": counts,
            "owner_ready": True,
            "empty": not recent and not any(areas.values()),
        }

    @app.get("/api/search")
    def search(
        request: Request,
        q: str = "",
        beyond: int = 0,
        kind: str = "",
        title: str = "",
        author: str = "",
        isbn: str = "",
        series: str = "",
        issue: str = "",
        artist: str = "",
        album: str = "",
        year: str = "",
    ):
        user = request.state.user
        local_kind = kind if kind in ALL_KINDS else None
        local_q = q.strip()
        local = public_works(db.search_works(local_q, limit=24, kind=local_kind) if local_q else [])
        indexer = []
        beyond_error = None
        sought = {
            "kind": kind,
            "q": q,
            "title": title,
            "author": author,
            "isbn": isbn,
            "series": series,
            "issue": issue,
            "artist": artist,
            "album": album,
            "year": year,
        }
        has_beyond_query = bool(beyond) and any(
            str(sought[key] or "").strip() for key in sought if key != "kind"
        )
        extra_on = bool(settings().show_extra_categories)
        search_trace = None
        pick = None
        candidates: List[Dict[str, Any]] = []
        rank_method = ""
        rank_reason = ""
        if kind in EXTRA_KINDS and not extra_on:
            indexer, beyond_error = [], None
        elif has_beyond_query:
            ranked = search_and_rank(settings(), **sought)
            indexer = list(ranked.get("hits") or [])
            beyond_error = ranked.get("error")
            if beyond_error:
                from librarian.llm import friendly_llm_error

                beyond_error = friendly_llm_error(RuntimeError(str(beyond_error)))
            pick = ranked.get("pick")
            candidates = list(ranked.get("candidates") or [])
            rank_method = str(ranked.get("rank_method") or "")
            rank_reason = str(ranked.get("rank_reason") or "")
            search_trace = {
                "conversation": list(ranked.get("conversation") or []),
                "steps": list(ranked.get("steps") or []),
                "results": list(ranked.get("results") or []),
                "plan": ranked.get("plan"),
                "raw_count": ranked.get("raw_count"),
                "rejected_count": ranked.get("rejected_count"),
                "rank_method": rank_method,
                "rank_reason": rank_reason,
            }
        return {
            "q": q,
            "local": local,
            "beyond": indexer,
            "beyond_error": beyond_error,
            "pick": pick,
            "candidates": candidates,
            "rank_method": rank_method,
            "rank_reason": rank_reason,
            "search_trace": search_trace,
            "can_request": user["role"] in ("owner", "op", "reader"),
        }

    @app.get("/api/browse")
    def browse(
        request: Request,
        kind: str = "",
        author: str = "",
        letter: str = "",
        series: str = "",
        genre: str = "",
        shelf: str = "",
        sort: str = "author",
        offset: int = 0,
        limit: int = 48,
    ):
        user = request.state.user
        kind_key = kind if kind in ALL_KINDS else None
        shelf_key = "favorites" if str(shelf or "").strip().lower() == "favorites" else None
        page = db.browse_works(
            kind=kind_key,
            author=author.strip() or None,
            letter=letter.strip() or None,
            series=series.strip() or None,
            genre=genre.strip() or None,
            shelf=shelf_key,
            user_id=user["id"] if shelf_key else None,
            sort=sort,
            offset=offset,
            limit=limit,
        )
        return {
            "items": public_works(page["items"]),
            "total": page["total"],
            "offset": page["offset"],
            "limit": page["limit"],
            "sort": page["sort"],
            "filters": {
                "kind": kind_key or "",
                "author": author.strip(),
                "letter": letter.strip().upper(),
                "series": series.strip(),
                "genre": genre.strip(),
                "shelf": shelf_key or "",
            },
        }

    @app.get("/api/browse/facets")
    def browse_facets_endpoint(
        request: Request,
        kind: str = "",
        shelf: str = "",
    ):
        user = request.state.user
        kind_key = kind if kind in ALL_KINDS else None
        shelf_key = "favorites" if str(shelf or "").strip().lower() == "favorites" else None
        facets = db.browse_facets(
            kind=kind_key,
            shelf=shelf_key,
            user_id=user["id"] if shelf_key else None,
        )
        return facets

    @app.get("/api/suggest")
    def suggest(
        request: Request,
        field: str = "",
        kind: str = "",
        q: str = "",
        limit: int = 12,
    ):
        enforce_rate_limit(request, bucket="suggest", limit=120, window_seconds=60)
        key = str(field or "").strip().lower()
        if key not in SUGGEST_FIELDS:
            raise HTTPException(status_code=400, detail="Unknown suggest field")
        items = suggest_items(db, root, field=key, kind=kind, q=q, limit=limit)
        return {"field": key, "kind": kind, "q": q, "items": items}

    @app.get("/api/discover")
    def discover(request: Request, kind: str = "", cat: str = "", limit: int = 0):
        cfg = settings()
        feed_limit = resolve_feed_limit(cat=cat, limit=limit if limit else None)
        items, categories, beyond_error = discover_beyond(cfg, kind=kind, cat=cat, limit=feed_limit)
        return {
            "kind": kind,
            "cat": cat,
            "limit": feed_limit,
            "items": items,
            "categories": categories,
            "beyond_error": beyond_error,
            "show_extra_categories": bool(cfg.show_extra_categories),
            "can_request": request.state.user["role"] in ("owner", "op", "reader"),
        }

    @app.get("/api/lists/presets")
    def curated_list_presets(request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        cfg = settings()
        from librarian.llm_providers import resolve_llm_connection

        llm_ok = bool(resolve_llm_connection(cfg).get("api_key"))
        return {
            "presets": list_presets(),
            "configured": llm_ok,
            "source": "llm",
            "empty_copy": (
                ""
                if llm_ok
                else "Add a BYO LLM in Settings to load curated bestseller lists."
            ),
        }

    @app.post("/api/lists/llm")
    def curated_llm_list(payload: LlmListPayload, request: Request):
        """BYO LLM curated list → match local shelves. Fail closed without LLM."""
        require_role(request.state.user, "owner", "op", "reader")
        when = normalize_list_date(payload.date)
        if not when:
            raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD or current")
        result = curated_list_payload(
            settings(),
            db,
            preset=payload.preset,
            date=when,
            query=payload.query,
            data_dir=root,
        )
        # Enrich shelved stubs with public_work cover flags.
        for entry in result.get("books") or []:
            for key in ("shelved", "shelved_audiobook"):
                stub = entry.get(key)
                if not stub or not stub.get("id"):
                    continue
                work = public_work(db.get_work(str(stub["id"])))
                if work:
                    entry[key] = {
                        "id": work.get("id"),
                        "title": work.get("title"),
                        "author": work.get("author"),
                        "kind": stub.get("kind") or work.get("kind"),
                        "has_cover": bool(work.get("has_cover") or work.get("cover_path")),
                    }
        result["can_request"] = request.state.user["role"] in ("owner", "op", "reader")
        result["can_confirm"] = request.state.user["role"] in ("owner", "op")
        return result

    @app.post("/api/lists/llm/chase")
    def curated_llm_chase(payload: LlmListChasePayload, request: Request):
        """Find beyond for missing list titles (book + audiobook). Never auto-queues."""
        require_role(request.state.user, "owner", "op", "reader")
        items = [row.model_dump() for row in (payload.items or [])]
        results = chase_missing_items(settings(), items)
        return {
            "results": results,
            "can_request": request.state.user["role"] in ("owner", "op", "reader"),
            "can_confirm": request.state.user["role"] in ("owner", "op"),
        }

    @app.get("/api/lists/nyt/names")
    def nyt_list_names(request: Request):
        """Legacy NYT Books API names — prefer POST /api/lists/llm."""
        require_role(request.state.user, "owner", "op", "reader")
        cfg = settings()
        key = str(cfg.nyt_books_api_key or "").strip()
        if not key:
            return {
                "configured": False,
                "names": default_list_names(),
                "empty_reason": "missing_key",
                "empty_copy": "Add a BYO LLM in Settings for curated bestseller lists.",
                "deprecated": True,
            }
        client = NytBooksClient(key, data_dir=root)
        try:
            names = client.list_names()
        except NytBooksError as error:
            return {
                "configured": True,
                "names": default_list_names(),
                "empty_reason": "error",
                "empty_copy": str(error),
                "deprecated": True,
            }
        finally:
            client.close()
        return {
            "configured": True,
            "names": names or default_list_names(),
            "empty_reason": "",
            "empty_copy": "",
            "deprecated": True,
        }

    @app.get("/api/lists/nyt")
    def nyt_bestseller_list(
        request: Request,
        list: str = "hardcover-fiction",  # noqa: A002 — query param name matches NYT docs
        date: str = "current",
    ):
        require_role(request.state.user, "owner", "op", "reader")
        slug = normalize_list_name(list) or "hardcover-fiction"
        when = normalize_list_date(date)
        if not when:
            raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD or current")
        cfg = settings()
        key = str(cfg.nyt_books_api_key or "").strip()
        client = NytBooksClient(key, data_dir=root)
        try:
            payload = client.bestseller_list(slug, date=when)
        except NytBooksError as error:
            client.close()
            return {
                "configured": bool(key),
                "list_name": slug,
                "date": when,
                "published_date": "",
                "display_name": slug,
                "books": [],
                "empty_reason": "error",
                "empty_copy": str(error),
            }
        client.close()
        books = []
        for book in payload.get("books") or []:
            query = " ".join(
                part for part in (str(book.get("author") or "").strip(), str(book.get("title") or "").strip()) if part
            )
            candidates: List[Dict[str, Any]] = []
            isbn = str(book.get("isbn") or "").strip()
            if isbn:
                candidates.extend(db.search_works(isbn, limit=8, kind="book"))
            if query:
                candidates.extend(db.search_works(query, limit=12, kind="book"))
            # Deduplicate by id while preserving order.
            seen: set[str] = set()
            uniq: List[Dict[str, Any]] = []
            for row in candidates:
                wid = str(row.get("id") or "")
                if not wid or wid in seen:
                    continue
                seen.add(wid)
                uniq.append(row)
            local = match_local_work(book, uniq)
            entry = dict(book)
            if local:
                pub = public_work(local)
                entry["shelved"] = {
                    "id": pub.get("id") if pub else local.get("id"),
                    "title": (pub or local).get("title"),
                    "author": (pub or local).get("author"),
                    "has_cover": bool((pub or local).get("has_cover") or (pub or local).get("cover_path")),
                }
            else:
                entry["shelved"] = None
            books.append(entry)
        empty_reason = str(payload.get("empty_reason") or "")
        empty_copy = ""
        if empty_reason == "missing_key":
            empty_copy = "Add a BYO LLM in Settings for curated bestseller lists."
        elif empty_reason == "empty_list":
            empty_copy = "That list came back empty for this date."
        elif not books and not empty_reason:
            empty_copy = "No titles on this list yet."
        return {
            **payload,
            "books": books,
            "empty_copy": empty_copy,
            "deprecated": True,
        }

    @app.get("/api/works/{work_id}")
    def work_detail(work_id: str, request: Request):
        work = public_work(db.get_work(work_id))
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        files = db.files_for_work(work_id)
        on_disk = existing_file_paths(files)
        part_set = build_part_set(work, files)
        if part_set:
            work["part_set"] = part_set
        related = []
        if work.get("author"):
            related = [
                row
                for row in public_works(db.search_works(str(work["author"]), limit=8))
                if row and row.get("id") != work_id
            ]
        progress = db.get_progress(request.state.user["id"], work_id)
        ribbon = []
        series_name = str(work.get("series_name") or "").strip()
        kind = str(work.get("kind") or "")
        if kind == "audiobook" and str(work.get("abs_item_id") or "").strip():
            try:
                from librarian.audiobookshelf import pull_abs_listen_progress

                pulled = pull_abs_listen_progress(
                    db,
                    settings(),
                    user_id=str(request.state.user["id"]),
                    work=work,
                    files=files,
                )
                if pulled:
                    progress = pulled
            except Exception:  # noqa: BLE001 — fail-soft ABS federation
                pass
        if series_name and kind in ALL_KINDS:
            card = gaps_for_series(db, kind=kind, series_name=series_name)
            owned = card.get("owned_indexes") or [
                str(row.get("series_index") or "")
                for row in db.works_for_series(kind=kind, series_name=series_name)
            ]
            missing = card.get("missing") or card.get("series_missing") or []
            ribbon = series_ribbon(
                owned_indexes=owned,
                missing_indexes=missing,
                current=work.get("series_index"),
            )
        whispers = db.list_whispers(work_id, limit=WHISPER_LIST_LIMIT)
        can_download = bool(on_disk)
        audiobook = companion_audiobook_payload(
            work,
            audiobooks=db.list_works(kind="audiobook", limit=500) if kind == "book" else [],
        )
        return {
            "work": work,
            "files": annotate_work_files(files, on_disk),
            "file_count": len(on_disk),
            "can_open": bool(on_disk),
            "can_download": can_download,
            "can_read": can_read_work(str(work.get("kind") or ""), on_disk),
            "listen": listen_payload(work, can_download=can_download, settings=settings()),
            "komga": komga_payload(work, settings()),
            "audiobook": audiobook,
            "favorite": db.is_favorite(request.state.user["id"], work_id),
            "related": related,
            "progress": progress,
            "ebook_convert": bool(which_ebook_convert()),
            "formats": list(ALLOWED_EBOOK_FORMATS),
            "series_ribbon": ribbon,
            "whispers": whispers,
        }

    @app.post("/api/works/{work_id}/favorite")
    def favorite(work_id: str, request: Request):
        if db.get_work(work_id) is None:
            raise HTTPException(status_code=404, detail="Work not found")
        on = db.toggle_favorite(request.state.user["id"], work_id)
        return {"favorite": on}

    @app.get("/api/works/{work_id}/whispers")
    def work_whispers(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        if db.get_work(work_id) is None:
            raise HTTPException(status_code=404, detail="Work not found")
        return {"whispers": db.list_whispers(work_id, limit=WHISPER_LIST_LIMIT)}

    @app.post("/api/works/{work_id}/whispers")
    def add_work_whisper(work_id: str, payload: WhisperPayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        if db.get_work(work_id) is None:
            raise HTTPException(status_code=404, detail="Work not found")
        body = sanitize_whisper(payload.body)
        if not body:
            raise HTTPException(status_code=400, detail="Whisper is empty")
        whisper = db.add_whisper(work_id=work_id, user_id=request.state.user["id"], body=body)
        return {"whisper": whisper, "whispers": db.list_whispers(work_id, limit=WHISPER_LIST_LIMIT)}

    def _public_prefs(row: Dict[str, Any]) -> Dict[str, Any]:
        nested = dict(row.get("prefs") or {})
        return {
            **row,
            "ui_theme": normalize_ui_theme(nested.get("ui_theme")),
            "ui_font_step": normalize_ui_font_step(nested.get("ui_font_step")),
        }

    @app.get("/api/prefs")
    def get_prefs(request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        return _public_prefs(db.get_user_prefs(request.state.user["id"]))

    @app.put("/api/prefs")
    def put_prefs(payload: PrefsPayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        ambient = normalize_ambient(payload.ambient) if payload.ambient is not None else None
        nested: Dict[str, Any] = {}
        if payload.ui_theme is not None:
            nested["ui_theme"] = normalize_ui_theme(payload.ui_theme)
        if payload.ui_font_step is not None:
            nested["ui_font_step"] = normalize_ui_font_step(payload.ui_font_step)
        return _public_prefs(
            db.set_user_prefs(
                request.state.user["id"],
                ambient=ambient,
                prefs=nested or None,
            )
        )

    @app.post("/api/celebrations/seen")
    def celebration_seen(payload: CelebrationSeenPayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        key = str(payload.key or "").strip()
        if not key:
            raise HTTPException(status_code=400, detail="Missing celebration key")
        db.mark_celebration_seen(request.state.user["id"], key)
        return {"ok": True}

    @app.post("/api/find/finish-eta")
    def finish_eta(payload: FinishSetEtaPayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        miss = int(payload.missing_count or 0)
        kind = str(payload.kind or "").strip()
        multipart = bool(payload.multipart)
        kind_samples = (
            db.recent_job_durations(kind=kind, multipart=True if multipart else None)
            if kind
            else []
        )
        pool_approximate = False
        if len(kind_samples) >= 2:
            samples = kind_samples
        else:
            global_samples = db.recent_job_durations(
                multipart=True if multipart else None
            )
            if len(global_samples) >= 2:
                samples = global_samples
                pool_approximate = bool(kind)
            elif kind_samples:
                samples = kind_samples
                pool_approximate = True
            else:
                samples = global_samples
                pool_approximate = True
        eta = estimate_finish_eta_minutes(
            missing_count=miss,
            recent_seconds=samples,
            total_bytes=payload.total_bytes,
        )
        minutes = eta.get("eta_minutes")
        approximate = bool(eta.get("approximate")) or (bool(minutes) and pool_approximate)
        return {
            "eta_minutes": minutes,
            "approximate": approximate if minutes else False,
            "label": finish_set_label(
                missing_count=miss,
                eta_minutes=minutes,
                approximate=approximate if minutes else False,
            ),
            "quiet_hours": in_quiet_hours(settings()),
        }

    @app.post("/api/works/{work_id}/progress")
    def touch_progress(work_id: str, payload: ProgressPayload, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        if db.get_work(work_id) is None:
            raise HTTPException(status_code=404, detail="Work not found")
        existing = db.get_progress(request.state.user["id"], work_id)
        if payload.finished:
            fraction = 1.0
        elif payload.fraction is not None:
            fraction = float(payload.fraction)
        elif existing:
            fraction = float(existing.get("fraction") or 0)
        else:
            fraction = 0.05
        position = payload.position or (existing or {}).get("position") or ""
        row = db.upsert_progress(
            user_id=request.state.user["id"],
            work_id=work_id,
            position=str(position),
            fraction=fraction,
        )
        work = db.get_work(work_id)
        if work and str(work.get("kind") or "") == "audiobook" and str(work.get("abs_item_id") or "").strip():
            try:
                from librarian.audiobookshelf import push_abs_listen_progress

                push_abs_listen_progress(
                    settings(),
                    work,
                    fraction=fraction,
                    position=str(position),
                    finished=bool(payload.finished),
                    force=bool(payload.finished),
                )
            except Exception:  # noqa: BLE001 — fail-soft ABS federation
                pass
        return {"progress": row}

    @app.get("/api/works/{work_id}/cover")
    def work_cover(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op", "reader")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        path = Path(str(work.get("cover_path") or ""))
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Cover not found")
        return FileResponse(path, media_type="image/jpeg")

    def _files_on_disk(work_id: str) -> List[Path]:
        return existing_file_paths(db.files_for_work(work_id))

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
        on_disk = existing_file_paths(rows)
        if not on_disk:
            raise HTTPException(status_code=404, detail="File missing")
        chosen = None
        if str(file or "").strip():
            chosen = resolve_catalog_file(rows, file)
            if chosen is None:
                raise HTTPException(status_code=404, detail="File not found")
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
        chosen = resolve_catalog_file(rows, file)
        if chosen is None:
            raise HTTPException(status_code=404, detail="File not found")
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
            chosen = resolve_catalog_file(rows, wanted)
            if chosen is None:
                raise HTTPException(status_code=404, detail="File not found")
        else:
            on_disk = existing_file_paths(rows)
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

    @app.post("/api/request")
    def request_item(payload: RequestPayload, request: Request):
        user = request.state.user
        require_role(user, "owner", "op", "reader")
        item = payload.model_dump()
        kind = str(item.get("kind") or (item.get("selected") or {}).get("kind") or "")
        if kind in EXTRA_KINDS and not settings().show_extra_categories:
            raise HTTPException(status_code=400, detail="Show categories is off")
        try:
            job = enqueue_indexer_item(
                db, settings(), item=item, requested_by=user["id"], role=user["role"]
            )
        except (SABError, NZBFinderError) as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        return {"job": job}

    @app.get("/api/queue")
    def queue(request: Request):
        require_role(request.state.user, "owner", "op")
        cfg = settings()
        poll_watch_folder(db, cfg)
        try:
            poll_rss_feeds(db, cfg)
        except Exception:
            pass
        try:
            poll_active_jobs(db, cfg)
        except SABError:
            pass
        jobs = db.list_jobs()
        for job in jobs:
            if job.get("status") != "review":
                continue
            work_id = str(job.get("work_id") or "").strip()
            if not work_id:
                continue
            work = db.get_work(work_id)
            if not work:
                continue
            job["review_reason"] = work.get("review_reason")
            job["review_state"] = work.get("review_state")
        return {"jobs": jobs}

    @app.post("/api/queue/{job_id}/poll")
    def queue_poll(job_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            job = poll_job(db, settings(), job_id)
        except (ValueError, SABError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"job": job}

    @app.post("/api/queue/{job_id}/confirm")
    def queue_confirm(job_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            job = confirm_asked_job(db, settings(), job_id)
        except (ValueError, SABError, NZBFinderError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"job": job}

    @app.get("/api/gaps")
    def gaps(request: Request):
        require_role(request.state.user, "owner", "op")
        rows = catalog_gaps(db, settings())
        return {"series": rows, "cards": gap_cards(rows)}

    @app.post("/api/gaps/confirm")
    def gaps_confirm(payload: RequestPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        return request_item(payload, request)

    @app.post("/api/music/{work_id}/promote")
    def music_promote(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            work = promote_music(db, settings(), work_id)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"work": work, "plexamp": plexamp_handoff(work)}

    @app.post("/api/works/{work_id}/enrich")
    def work_enrich(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            result = enrich_work(db, settings(), work_id, data_dir=root)
        except ValueError as error:
            detail = str(error)
            status = 404 if detail == "Work not found" else 400
            raise HTTPException(status_code=status, detail=detail) from error
        return result

    @app.patch("/api/works/{work_id}/metadata")
    def work_metadata(work_id: str, payload: WorkMetadataPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        fields = payload.model_dump(exclude_unset=True)
        if not fields:
            raise HTTPException(status_code=400, detail="No metadata fields to update")
        try:
            work = update_work_metadata(db, work_id, fields, data_dir=root)
        except ValueError as error:
            detail = str(error)
            status = 404 if detail == "Work not found" else 400
            raise HTTPException(status_code=status, detail=detail) from error
        return {"work": public_work(work)}

    @app.get("/api/works/{work_id}/match-candidates")
    def work_match_candidates(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        if str(work.get("kind") or "") not in ("book", "audiobook", "comic"):
            raise HTTPException(status_code=400, detail="Only books, audiobooks, and comics can be matched")
        candidates = list_match_candidates(work, settings=settings())
        return {"candidates": candidates, "title": work.get("title"), "author": work.get("author")}

    @app.post("/api/works/{work_id}/apply-match")
    def work_apply_match(work_id: str, payload: ApplyMatchPayload, request: Request):
        require_role(request.state.user, "owner", "op")
        work = db.get_work(work_id)
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        try:
            kind = str(work.get("kind") or "")
            if kind == "comic":
                result = apply_comicvine_match(
                    db,
                    settings(),
                    work_id,
                    payload.match_key,
                )
            elif kind == "audiobook":
                result = apply_audnexus_match(
                    db,
                    settings(),
                    work_id,
                    payload.match_key,
                    data_dir=root,
                )
            else:
                result = apply_openlibrary_match(
                    db,
                    settings(),
                    work_id,
                    payload.match_key,
                    data_dir=root,
                )
        except ValueError as error:
            detail = str(error)
            status = 404 if detail in (
                "Work not found",
                "Open Library match not found",
                "Comic Vine match not found",
                "Audnexus match not found",
            ) else 400
            raise HTTPException(status_code=status, detail=detail) from error
        result["work"] = public_work(result.get("work"))
        return result

    @app.post("/api/works/{work_id}/clear-enrich")
    def work_clear_enrich(work_id: str, request: Request):
        require_role(request.state.user, "owner", "op")
        try:
            work = clear_enrichment(db, work_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"work": public_work(work)}

