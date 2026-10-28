"""Holds desk automation: group actions, duplicate gate, server model triage. SQLite stays real."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.db import Database
from librarian.duplicate_gate import (
    duplicate_gate,
    normalize_author,
    normalize_title,
    slip_cooldown_active,
    start_slip_cooldown,
)
from librarian.llm import LLMClient
from librarian.review_bulk import BulkError, bulk_by_reason
from librarian.review_suggest_batch import (
    apply_trusted_matches,
    eligible_slips,
    read_progress,
    run_suggest_batch,
)
from librarian.sessions import clear_session_secret_cache
from librarian.wanted import dedupe_key
from librarian.web.app import create_app

NOW = 1_700_000_000.0


def _settings(tmp_path: Path, **extra) -> Settings:
    return Settings(
        books_root=str(tmp_path / "books"),
        magazines_root=str(tmp_path / "magazines"),
        comics_root=str(tmp_path / "comics"),
        audiobooks_root=str(tmp_path / "audiobooks"),
        incoming_music_root=str(tmp_path / "incoming"),
        music_root=str(tmp_path / "music"),
        complete_root=str(tmp_path / "complete"),
        **extra,
    )


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "librarian.db")
    try:
        yield database
    finally:
        database.close()


def _client(tmp_path, monkeypatch, settings):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    clear_session_secret_cache()
    save_settings(tmp_path, settings)
    app = create_app(tmp_path)
    client = TestClient(app)
    assert client.post(
        "/api/auth/local/login", json={"username": "owner", "password": "password123"}
    ).status_code == 200
    return client, app


def _slip(db: Database, folder: Path, *, reason: str, title: str, author: str = "Ann Author",
          kind: str = "book", blob: bytes | None = b"slip-bytes", name: str = "book.epub") -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    if blob is not None:
        (folder / name).write_bytes(blob)
    return db.upsert_work(
        {
            "kind": kind,
            "title": title,
            "author": author,
            "review_state": "needs_review",
            "review_reason": reason,
            "folder_path": str(folder),
        }
    )


def _shelf(db: Database, folder: Path, *, title: str, author: str, blob: bytes, kind: str = "book") -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    payload = folder / "book.epub"
    payload.write_bytes(blob)
    row = db.upsert_work(
        {"kind": kind, "title": title, "author": author, "review_state": "none", "folder_path": str(folder)}
    )
    db.upsert_file(
        {
            "work_id": row["id"],
            "path": str(payload),
            "filename": payload.name,
            "kind": kind,
            "size": len(blob),
        }
    )
    return row


# --- group actions ------------------------------------------------------------


def test_delete_group_removes_slips_jobs_and_wanted_but_keeps_folders(db, tmp_path):
    settings = _settings(tmp_path)
    folder = tmp_path / "complete" / "Odd Name 1"
    slip = _slip(db, folder, reason="low_confidence", title="Odd Name 1")
    other = _slip(db, tmp_path / "complete" / "Odd Name 2", reason="low_confidence", title="Odd Name 2")
    keep = _slip(db, tmp_path / "complete" / "Other", reason="collision", title="Other")
    wanted = db.insert_wanted(
        {
            "dedupe_key": dedupe_key(kind="book", title="Odd Name 1", author="Ann Author"),
            "title": "Odd Name 1",
            "author": "Ann Author",
            "kind": "book",
            "status": "wanted",
            "next_search_at": NOW,
            "source": "manual",
        }
    )
    job = db.claim_and_create_wanted_job(
        wanted["id"],
        {"indexer_guid": "g1", "title": "Odd Name 1", "kind": "book", "payload": {"wanted_id": wanted["id"]}},
        now=NOW,
    )
    db.update_job(job["id"], work_id=slip["id"], status="review")

    result = bulk_by_reason(db, settings, reason="low_confidence", action="delete", data_dir=tmp_path)

    assert result["examined"] == 2
    assert result["changed"] == 2
    assert result["failed"] == 0
    assert result["wanted_dismissed"] == 1
    assert result["undo_recorded"] is True
    assert db.get_work(slip["id"]) is None
    assert db.get_work(other["id"]) is None
    assert db.get_job(job["id"]) is None
    assert db.get_wanted(wanted["id"])["status"] == "dismissed"
    assert db.get_work(keep["id"])["review_state"] == "needs_review"
    assert (folder / "book.epub").read_bytes() == b"slip-bytes"
    assert [row["work_id"] for row in db.list_review_audit(action="delete_slip")].count(slip["id"]) == 1
    assert slip_cooldown_active(db, folder)


def test_selected_ids_outside_the_group_are_skipped_not_deleted(db, tmp_path):
    settings = _settings(tmp_path)
    inside = _slip(db, tmp_path / "complete" / "In", reason="low_confidence", title="In")
    outside = _slip(db, tmp_path / "complete" / "Out", reason="collision", title="Out")

    result = bulk_by_reason(
        db,
        settings,
        reason="low_confidence",
        action="delete",
        work_ids=[inside["id"], outside["id"], "gone-id"],
    )

    assert result["examined"] == 3
    assert result["changed"] == 1
    assert result["skipped"] == 2
    assert result["reasons"] == {"not_in_group": 1, "not_found": 1}
    assert db.get_work(outside["id"]) is not None


def test_delete_group_reports_partial_failure(db, tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    first = _slip(db, tmp_path / "complete" / "A", reason="low_confidence", title="A")
    second = _slip(db, tmp_path / "complete" / "B", reason="low_confidence", title="B")
    real = db.discard_review_slip

    def flaky(work_id, **kwargs):
        if work_id == second["id"]:
            raise RuntimeError("disk said no")
        return real(work_id, **kwargs)

    monkeypatch.setattr(db, "discard_review_slip", flaky)
    result = bulk_by_reason(db, settings, reason="low_confidence", action="delete")

    assert result["changed"] == 1
    assert result["failed"] == 1
    assert result["reasons"]["failed"] == 1
    assert result["failures"][0]["id"] == second["id"]
    assert "disk said no" in result["failures"][0]["error"]
    assert db.get_work(first["id"]) is None
    assert db.get_work(second["id"]) is not None


def test_accept_clear_files_only_path_clear_rows(db, tmp_path):
    settings = _settings(tmp_path)
    clear = _slip(
        db,
        tmp_path / "William W. Johnstone" / "Fire in the Ashes",
        reason="low_confidence",
        title="Fire in the Ashes",
        author="William W. Johnstone",
    )
    muddy = _slip(db, tmp_path / "inbox" / "rel-x9", reason="low_confidence", title="rel-x9", name="rel.epub")

    result = bulk_by_reason(db, settings, reason="low_confidence", action="accept_clear")

    assert result["changed"] == 1
    assert result["reasons"] == {"not_path_clear": 1}
    assert db.get_work(clear["id"])["review_state"] != "needs_review"
    assert db.get_work(muddy["id"])["review_state"] == "needs_review"


def test_purge_duplicates_preview_then_purges_exact_only(db, tmp_path):
    settings = _settings(tmp_path)
    _shelf(db, tmp_path / "books" / "Ann Author" / "Twin", title="Twin", author="Ann Author", blob=b"same")
    _shelf(db, tmp_path / "books" / "Ann Author" / "Fuzzy", title="Fuzzy", author="Ann Author", blob=b"orig")
    exact = _slip(db, tmp_path / "complete" / "Twin", reason="collision", title="Twin", blob=b"same")
    fuzzy = _slip(db, tmp_path / "complete" / "Fuzzy", reason="possible_duplicate", title="Fuzzy", blob=b"other")
    empty = _slip(db, tmp_path / "complete" / "Empty", reason="collision", title="Empty", blob=None)

    preview = bulk_by_reason(db, settings, reason="collision", action="purge_duplicates", dry_run=True)
    assert preview["dry_run"] is True
    assert preview["changed"] == 0
    assert preview["purgeable"] == 1
    assert preview["unassessable"] == 1
    assert preview["works_evidence"][exact["id"]]["evidence"] == "exact_fingerprint"
    assert preview["works_evidence"][empty["id"]]["evidence"] == "unassessable"
    assert db.get_work(exact["id"]) is not None

    real = bulk_by_reason(db, settings, reason="collision", action="purge_duplicates", data_dir=tmp_path)
    assert real["changed"] == 1
    assert real["reasons"]["unassessable"] == 1
    assert db.get_work(exact["id"]) is None
    assert db.get_work(empty["id"]) is not None
    assert db.get_work(fuzzy["id"]) is not None
    assert (tmp_path / "complete" / "Twin" / "book.epub").read_bytes() == b"same"


def test_purge_refuses_non_duplicate_group_and_preview_on_delete(db, tmp_path):
    settings = _settings(tmp_path)
    with pytest.raises(BulkError):
        bulk_by_reason(db, settings, reason="low_confidence", action="purge_duplicates")
    with pytest.raises(BulkError):
        bulk_by_reason(db, settings, reason="low_confidence", action="delete", dry_run=True)
    with pytest.raises(BulkError):
        bulk_by_reason(db, settings, reason="low_confidence", action="rewant")


def test_bulk_by_reason_api(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    client, app = _client(tmp_path, monkeypatch, settings)
    db = app.state.db
    slip = _slip(db, tmp_path / "complete" / "X", reason="low_confidence", title="X")

    bad = client.post("/api/review/bulk-by-reason", json={"reason": "low_confidence", "action": "nuke"})
    assert bad.status_code == 400
    resp = client.post(
        "/api/review/bulk-by-reason",
        json={"reason": "low_confidence", "action": "delete", "work_ids": [slip["id"]]},
    )
    assert resp.status_code == 200
    assert resp.json()["changed"] == 1
    assert db.get_work(slip["id"]) is None


# --- duplicate gate -------------------------------------------------------------


def test_normalizers_fold_articles_punctuation_and_last_first():
    assert normalize_title("The Hobbit (Unabridged)") == "hobbit"
    assert normalize_title("Hobbit!") == "hobbit"
    assert normalize_author("Tolkien, J.R.R.") == normalize_author("J. R. R. Tolkien")


def test_gate_resolves_exact_fingerprint_and_holds_fuzzy(db, tmp_path):
    shelved = _shelf(db, tmp_path / "books" / "Tolkien" / "Hobbit", title="The Hobbit",
                     author="J.R.R. Tolkien", blob=b"hobbit-bytes")
    twin = tmp_path / "complete" / "Hobbit.Twin"
    twin.mkdir(parents=True)
    (twin / "book.epub").write_bytes(b"hobbit-bytes")
    other = tmp_path / "complete" / "Hobbit.Other"
    other.mkdir(parents=True)
    (other / "book.epub").write_bytes(b"different-bytes")
    identity = {"kind": "book", "title": "Hobbit", "author": "Tolkien, J.R.R."}

    resolved = duplicate_gate(db, identity, twin)
    assert resolved["action"] == "resolve"
    assert resolved["evidence"] == "exact_fingerprint"
    assert resolved["work"]["id"] == shelved["id"]

    held = duplicate_gate(db, identity, other)
    assert held["action"] == "hold"
    assert held["evidence"] == "same_normalized_identity"
    assert (other / "book.epub").read_bytes() == b"different-bytes"

    assert duplicate_gate(db, {"kind": "book", "title": "Silmarillion", "author": "Tolkien"}, other)[
        "action"
    ] == "pass"


def test_organize_holds_possible_duplicate_with_one_motion(db, tmp_path):
    from librarian.organize import organize_identified, review_slip_actions

    settings = _settings(tmp_path)
    _shelf(db, tmp_path / "books" / "Tolkien" / "Hobbit", title="The Hobbit",
           author="J.R.R. Tolkien", blob=b"hobbit-bytes")
    folder = tmp_path / "complete" / "hobbit-rip"
    folder.mkdir(parents=True)
    (folder / "hobbit.epub").write_bytes(b"different-bytes")

    result = organize_identified(
        db,
        settings,
        folder=folder,
        indexer_item={"kind": "book", "title": "Hobbit", "author": "Tolkien, J.R.R."},
        move_source=True,
    )
    work = result["work"]
    assert work["review_state"] == "needs_review"
    assert work["review_reason"] == "possible_duplicate"
    actions = review_slip_actions(work, {"path": str(folder)}, llm_configured=False)
    assert actions["recommended_motion"] == "skip"
    assert (folder / "hobbit.epub").read_bytes() == b"different-bytes"


def test_cooldown_blocks_same_folder_until_it_changes(db, tmp_path):
    folder = tmp_path / "complete" / "Again"
    folder.mkdir(parents=True)
    (folder / "book.epub").write_bytes(b"x")
    start_slip_cooldown(db, folder, reason="purge", now=time.time())
    assert slip_cooldown_active(db, folder)
    (folder / "extra.epub").write_bytes(b"new file")
    assert not slip_cooldown_active(db, folder)
    start_slip_cooldown(db, folder, reason="purge", seconds=1, now=time.time() - 10)
    assert not slip_cooldown_active(db, folder)


def test_organize_skips_slip_while_cooldown_is_active(db, tmp_path):
    from librarian.organize import organize_identified

    settings = _settings(tmp_path)
    folder = tmp_path / "complete" / "x9-dump"
    folder.mkdir(parents=True)
    (folder / "x9.epub").write_bytes(b"dump")
    start_slip_cooldown(db, folder, reason="purge_duplicates")

    result = organize_identified(
        db, settings, folder=folder, indexer_item={"kind": "book", "title": "x9-dump"}, move_source=True
    )
    assert result.get("skipped_cooldown") is True
    assert db.count_works(review_state="needs_review") == 0


# --- server model triage ----------------------------------------------------------


def _llm(answers: dict, calls: list, db: Database | None = None, seen: list | None = None) -> LLMClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        text = json.dumps(body)
        if db is not None and seen is not None:
            seen.append(set(db.get_review_suggestions().keys()))
        for marker, answer in answers.items():
            if marker in text:
                calls.append(marker)
                if answer is None:
                    return httpx.Response(500, json={"error": "down"})
                return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})
        calls.append("?")
        return httpx.Response(500, json={"error": "no marker"})

    return LLMClient("http://llm.example/v1", "k", "gpt-test", transport=httpx.MockTransport(handler))


def _triage_slips(db: Database, tmp_path: Path) -> dict:
    out = {}
    for marker in ("alpha", "bravo", "charlie"):
        folder = tmp_path / "complete" / f"{marker}.Audio.book.MP3.x264"
        folder.mkdir(parents=True)
        (folder / "01.mp3").write_bytes(b"ID3")
        out[marker] = db.upsert_work(
            {
                "kind": "audiobook",
                "title": f"{marker}.Audio.book.MP3.x264",
                "author": "",
                "review_state": "needs_review",
                "review_reason": "low_confidence",
                "folder_path": str(folder),
            }
        )
    return out


ANSWERS = {
    "alpha": {"kind": "audiobook", "title": "Alpha Story", "author_or_artist": "Al Writer",
              "confidence": 0.93, "rationale": "clear"},
    "bravo": {"kind": "audiobook", "title": "Bravo Tale", "author_or_artist": "",
              "confidence": 0.6, "rationale": "no author"},
    "charlie": None,
}


def test_suggest_batch_persists_each_slip_before_the_next(db, tmp_path):
    settings = _settings(tmp_path, llm_base_url="http://llm.example/v1", llm_api_key="k", llm_model="gpt-test")
    slips = _triage_slips(db, tmp_path)
    calls: list = []
    seen: list = []
    result = run_suggest_batch(
        db, settings, data_dir=tmp_path, llm_client=_llm(ANSWERS, calls, db, seen), sleep=lambda _s: None
    )

    assert sorted(calls) == ["alpha", "bravo", "charlie"]
    assert [len(prior) for prior in seen] == [0, 1, 2]
    assert result["eligible"] == 3
    assert result["suggested"] == 3
    assert result["trusted"] == 1
    assert result["ambiguous"] == 1
    assert result["failed"] == 1
    stored = db.get_review_suggestions()
    assert stored[slips["alpha"]["id"]]["outcome"] == "trusted"
    assert stored[slips["alpha"]["id"]]["suggestion"]["author"] == "Al Writer"
    assert stored[slips["bravo"]["id"]]["outcome"] == "ambiguous"
    assert "author" in stored[slips["bravo"]["id"]]["explanation"].lower()
    assert stored[slips["charlie"]["id"]]["outcome"] == "failed"
    assert db.get_work(slips["alpha"]["id"])["review_reason"] is None
    assert db.get_work(slips["bravo"]["id"])["review_reason"] == "low_confidence"
    assert db.get_work(slips["bravo"]["id"])["review_state"] == "needs_review"
    progress = read_progress(tmp_path)
    assert progress["trusted"] == 1 and progress["ambiguous"] == 1 and progress["failed"] == 1

    again_calls: list = []
    rerun = run_suggest_batch(
        db, settings, data_dir=tmp_path, llm_client=_llm(ANSWERS, again_calls), sleep=lambda _s: None
    )
    assert again_calls == ["charlie"]
    assert rerun["eligible"] == 1


def test_apply_trusted_uses_persisted_answers_only(db, tmp_path):
    settings = _settings(tmp_path, llm_base_url="http://llm.example/v1", llm_api_key="k", llm_model="gpt-test")
    slips = _triage_slips(db, tmp_path)
    run_suggest_batch(db, settings, data_dir=tmp_path, llm_client=_llm(ANSWERS, []), sleep=lambda _s: None)

    result = apply_trusted_matches(db, settings, data_dir=tmp_path)

    assert result["examined"] == 1
    assert result["applied"] == 1
    filed = db.get_work(slips["alpha"]["id"])
    assert filed["review_state"] != "needs_review"
    assert filed["title"] == "Alpha Story"
    assert db.get_work(slips["bravo"]["id"])["review_state"] == "needs_review"
    assert read_progress(tmp_path)["applied"] == 1
    assert read_progress(tmp_path)["trusted"] == 1


def test_path_clear_folder_is_not_sent_to_the_model(db, tmp_path):
    settings = _settings(tmp_path)
    _slip(
        db,
        tmp_path / "Box, C.J_" / "Three Weeks to Say Goodbye (9989)",
        reason="low_confidence",
        title="Three Weeks to Say Goodbye",
        author="Box, C.J.",
    )
    assert eligible_slips(db, settings) == []


def test_suggest_batch_api_polls_to_completion_and_lists_triage(tmp_path, monkeypatch):
    settings = _settings(tmp_path, llm_base_url="http://llm.example/v1", llm_api_key="k", llm_model="gpt-test")
    client, app = _client(tmp_path, monkeypatch, settings)
    db = app.state.db
    slips = _triage_slips(db, tmp_path)
    llm = _llm(ANSWERS, [])
    monkeypatch.setattr("librarian.llm.client_from_settings", lambda _s: llm)
    monkeypatch.setattr("librarian.review_suggest_batch.DEFAULT_MIN_INTERVAL_S", 0.0)

    started = client.post("/api/review/suggest-batch")
    assert started.status_code == 200
    deadline = time.time() + 10
    status = {}
    while time.time() < deadline:
        status = client.get("/api/review/suggest-batch/status").json()
        if status.get("status") in ("completed", "failed"):
            break
        time.sleep(0.05)
    assert status["status"] == "completed"
    assert status["trusted"] == 1 and status["ambiguous"] == 1 and status["failed"] == 1

    works = {row["id"]: row for row in client.get("/api/review").json()["works"]}
    assert works[slips["alpha"]["id"]]["llm_triage"]["outcome"] == "trusted"
    assert works[slips["alpha"]["id"]]["effective_reason"] == "ready_to_file"
    assert works[slips["bravo"]["id"]]["llm_triage"]["outcome"] == "ambiguous"
    assert works[slips["charlie"]["id"]]["llm_triage"]["outcome"] == "failed"

    applied = client.post("/api/review/apply-trusted")
    assert applied.status_code == 200
    assert applied.json()["applied"] == 1
