"""Phase 2 Sorting desk: pagination, diagnosis cache, undo, autopilot, identify inflow.

SQLite stays real. NZBFinder / SAB / LLM HTTP are not used here.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.jobs import dismiss_queue_job, retry_failed_job
from librarian.review_diagnosis import fill_review_diagnosis
from librarian.sessions import clear_session_secret_cache
from librarian.sorting_autopilot import run_sorting_autopilot
from librarian.sorting_undo import public_undo, record_sorting_undo, restore_sorting_undo
from librarian.web.app import create_app


def _client(tmp_path, monkeypatch, settings=None):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    if settings is not None:
        save_settings(tmp_path, settings)
    app = create_app(tmp_path)
    client = TestClient(app)
    assert client.post(
        "/api/auth/local/login", json={"username": "owner", "password": "password123"}
    ).status_code == 200
    return client, app


def _slip(db: Database, *, title: str, reason: str = "low_confidence", folder: str = "") -> dict:
    return db.upsert_work(
        {
            "kind": "book",
            "title": title,
            "author": "Ann Author",
            "review_state": "needs_review",
            "review_reason": reason,
            "folder_path": folder,
        }
    )


def test_parse_book_scene_and_calibre_suffix():
    from librarian.naming.book import parse_book_scene, strip_calibre_suffix

    assert strip_calibre_suffix("The Left Hand of Darkness (11630)") == "The Left Hand of Darkness"
    assert strip_calibre_suffix("Plain Title") == "Plain Title"
    scene = parse_book_scene("Le.Guin-The.Left.Hand.of.Darkness.2024.EPUB-GROUP")
    assert scene is not None
    author, title = scene
    assert "Guin" in author
    assert "Left Hand of Darkness" in title
    byline = parse_book_scene("The Left Hand of Darkness by Le Guin")
    assert byline == ("Le Guin", "The Left Hand of Darkness")
    assert parse_book_scene("hobbit-rip") is None
    assert parse_book_scene("Fourth Wing - Rebecca Yarros.epub") is None


def test_identify_scene_release_is_high_confidence(tmp_path):
    from librarian.identify import identify_completed

    class _RaiseLLM:
        def identify(self, evidence: str):
            raise RuntimeError("llm unavailable")

    folder = tmp_path / "Le.Guin-The.Left.Hand.of.Darkness.2024.EPUB-GROUP"
    folder.mkdir()
    (folder / "book.epub").write_bytes(b"epub")
    result = identify_completed(
        folder,
        indexer_item={"kind": "book", "title": folder.name, "category": 7020},
        llm_client=_RaiseLLM(),
    )
    identity = result["identity"]
    assert identity["kind"] == "book"
    assert "Guin" in str(identity.get("author") or "")
    assert "Left Hand" in str(identity.get("title") or "")
    assert identity["confidence"] == "high"
    assert not identity.get("review_reason")
    assert result["auto_organize"] is True


def test_identify_strips_calibre_suffix_from_title(tmp_path):
    from librarian.identify import identify_completed

    class _RaiseLLM:
        def identify(self, evidence: str):
            raise RuntimeError("llm unavailable")

    folder = tmp_path / "Le Guin - The Left Hand of Darkness (11630)"
    folder.mkdir()
    (folder / "book.epub").write_bytes(b"epub")
    result = identify_completed(folder, indexer_item={"kind": "book"}, llm_client=_RaiseLLM())
    title = str(result["identity"].get("title") or "")
    assert "(11630)" not in title
    assert "Left Hand" in title


def test_convert_failed_is_still_a_sorting_slip(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "comic",
            "title": "Vampirella #6",
            "review_state": "needs_review",
            "review_reason": "convert_failed",
            "folder_path": str(tmp_path / "Vampirella.No.06"),
        }
    )
    listed = db.list_works(review_state="needs_review", review_reason="convert_failed")
    assert work["id"] in {row["id"] for row in listed}


def test_review_get_does_not_rglob(tmp_path, monkeypatch):
    called: list[str] = []

    def boom(*_args, **_kwargs):
        called.append("diagnose")
        raise AssertionError("GET /api/review must not walk the folder")

    monkeypatch.setattr("librarian.identify.diagnose_review_folder", boom)
    monkeypatch.setattr("librarian.services.review.diagnose_review_folder", boom)
    settings = Settings(books_root=str(tmp_path / "books"), complete_root=str(tmp_path / "complete"))
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    _slip(db, title="Odd One", reason="low_confidence", folder=str(tmp_path / "complete" / "odd"))
    listed = client.get("/api/review")
    assert listed.status_code == 200
    body = listed.json()
    assert "works" in body and "items" in body
    assert body["works"] == body["items"]
    assert called == []
    assert body["counts_by_reason"]["low_confidence"] == 1
    assert body["total"] == 1
    assert "undo" in body


def test_review_list_pages_with_cursor(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    db = app.state.db
    for index in range(30):
        _slip(db, title=f"Slip {index:02d}", reason="low_confidence")
    first = client.get("/api/review?limit=25")
    assert first.status_code == 200
    body = first.json()
    assert len(body["works"]) == 25
    assert body["next_cursor"]
    assert body["total"] == 30
    second = client.get(f"/api/review?limit=25&cursor={body['next_cursor']}")
    assert second.status_code == 200
    page = second.json()
    assert len(page["works"]) == 5
    assert page["next_cursor"] in (None, "")
    ids = {row["id"] for row in body["works"]} | {row["id"] for row in page["works"]}
    assert len(ids) == 30


def test_review_reason_filter_and_counts(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    db = app.state.db
    _slip(db, title="Low", reason="low_confidence")
    _slip(db, title="Twin", reason="collision")
    _slip(db, title="Fail", reason="convert_failed")
    listed = client.get("/api/review?reason=convert_failed")
    assert listed.status_code == 200
    body = listed.json()
    assert {row["review_reason"] for row in body["works"]} == {"convert_failed"}
    assert body["counts_by_reason"]["low_confidence"] == 1
    assert body["counts_by_reason"]["collision"] == 1
    assert body["counts_by_reason"]["convert_failed"] == 1


def test_unpack_stuck_overlay_comes_from_diagnosis_table(tmp_path, monkeypatch):
    stuck = tmp_path / "usenet" / "complete" / "downloads" / "VA-Guardians.Mix"
    stuck.mkdir(parents=True)
    (stuck / "mix.rar").write_bytes(b"Rar!")
    (stuck / "mix.par2").write_bytes(b"par2")
    settings = Settings(
        books_root=str(tmp_path / "books"),
        complete_root=str(tmp_path / "usenet" / "complete"),
    )
    client, app = _client(tmp_path, monkeypatch, settings=settings)
    db = app.state.db
    work = db.upsert_work(
        {
            "kind": "music",
            "title": "Guardians Mix",
            "author": "Various Artists",
            "review_state": "needs_review",
            "review_reason": "no_payload",
            "folder_path": str(stuck),
        }
    )
    written = fill_review_diagnosis(db, settings, work_ids=[work["id"]])
    assert written == 1
    listed = client.get("/api/review")
    assert listed.status_code == 200
    row = listed.json()["works"][0]
    assert row["id"] == work["id"]
    assert row["review_reason"] == "unpack_stuck"
    assert row["folder_diagnosis"]["problem"] == "unpack_stuck"
    refreshed = db.get_work(work["id"])
    assert refreshed["review_reason"] == "no_payload"


def test_sorting_undo_restores_deleted_slips(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = _slip(db, title="Tossed")
    snapshot = dict(work)
    db.discard_review_slip(work["id"])
    assert db.get_work(work["id"]) is None
    recorded = record_sorting_undo(db, action="delete", works=[snapshot], reason="low_confidence")
    assert recorded and recorded["available"] is True
    restored = restore_sorting_undo(db)
    assert restored["ok"] is True
    assert restored["restored"] == 1
    back = db.get_work(work["id"])
    assert back is not None
    assert back["review_state"] == "needs_review"
    assert public_undo(db)["available"] is False


def test_bulk_delete_preview_and_undo_via_api(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    db = app.state.db
    one = _slip(db, title="One")
    two = _slip(db, title="Two")
    preview = client.post(
        "/api/review/bulk-by-reason",
        json={"reason": "low_confidence", "action": "delete", "dry_run": True},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["dry_run"] is True
    assert body["would_change"] == 2
    assert db.get_work(one["id"]) is not None
    gone = client.post(
        "/api/review/bulk-by-reason",
        json={"reason": "low_confidence", "action": "delete", "dry_run": False},
    )
    assert gone.status_code == 200
    assert gone.json()["changed"] == 2
    assert db.get_work(one["id"]) is None
    undo = client.get("/api/review/undo")
    assert undo.status_code == 200
    assert undo.json()["available"] is True
    restored = client.post("/api/review/undo")
    assert restored.status_code == 200
    assert restored.json()["restored"] == 2
    assert db.get_work(one["id"])["review_state"] == "needs_review"
    assert db.get_work(two["id"])["review_state"] == "needs_review"


def test_autopilot_files_path_clear_books_never_sab(tmp_path, monkeypatch):
    called: list[str] = []

    def boom(*_args, **_kwargs):
        called.append("sab")
        raise AssertionError("autopilot must never talk to SABnzbd")

    monkeypatch.setattr("librarian.sabnzbd.SABClient.addfile", boom)
    monkeypatch.setattr("librarian.jobs._queue_download", boom)
    settings = Settings(books_root=str(tmp_path / "books"), complete_root=str(tmp_path / "complete"))
    db = Database(tmp_path / "librarian.db")
    folder = tmp_path / "books" / "Le Guin" / "The Left Hand of Darkness"
    folder.mkdir(parents=True)
    (folder / "book.epub").write_bytes(b"epub")
    work = db.upsert_work(
        {
            "kind": "book",
            "title": "Mystery",
            "author": "Unknown",
            "review_state": "needs_review",
            "review_reason": "low_confidence",
            "folder_path": str(folder),
        }
    )
    result = run_sorting_autopilot(db, settings)
    assert result["changed"] >= 1
    assert result["undo_recorded"] is True
    fresh = db.get_work(work["id"])
    assert fresh is not None
    assert fresh["review_state"] != "needs_review"
    assert called == []
    assert public_undo(db)["available"] is True


def test_retry_failed_job_returns_to_asked_not_sab(tmp_path, monkeypatch):
    called: list[str] = []

    def boom(*_args, **_kwargs):
        called.append("sab")
        raise AssertionError("retry must not send SABnzbd")

    monkeypatch.setattr("librarian.jobs._queue_download", boom)
    db = Database(tmp_path / "librarian.db")
    job = db.create_job({"status": "failed", "title": "A miss", "kind": "book", "error": "nzb gone"})
    updated = retry_failed_job(db, job["id"])
    assert updated["status"] == "asked"
    skipped = db.create_job({"status": "skipped", "title": "Skip me", "kind": "book"})
    again = retry_failed_job(db, skipped["id"])
    assert again["status"] == "asked"
    dismissed = dismiss_queue_job(db, again["id"])
    assert dismissed["status"] == "skipped"
    assert called == []


def test_queue_lists_needs_you_first_and_retry_route(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    db = app.state.db
    db.create_job({"status": "asked", "title": "Waiting", "kind": "book"})
    failed = db.create_job({"status": "failed", "title": "Broke", "kind": "book", "error": "nzb gone"})
    db.create_job({"status": "review", "title": "Needs you", "kind": "book"})
    listed = client.get("/api/queue")
    assert listed.status_code == 200
    statuses = [row["status"] for row in listed.json()["jobs"]]
    assert statuses[0] == "review"
    retried = client.post(f"/api/queue/{failed['id']}/retry")
    assert retried.status_code == 200
    assert retried.json()["job"]["status"] == "asked"
    gone = client.post(f"/api/queue/{failed['id']}/dismiss")
    assert gone.status_code == 200
    assert gone.json()["job"]["status"] == "skipped"


def test_sorting_autopilot_source_never_imports_sab():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "librarian"
    for name in ("sorting_autopilot.py", "sorting_undo.py", "review_diagnosis.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        assert all("sabnzbd" not in item and item != "librarian.jobs" for item in imported)
