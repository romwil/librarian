"""BD-6 · Op auto-confirm after Ask — opt-in, audit, never readers."""

from __future__ import annotations

import httpx

from librarian.auth import hash_password
from librarian.config import Settings
from librarian.db import Database
from librarian.op_auto_confirm import (
    SECURITY_KIND,
    host_on_allowlist,
    normalize_allowlist,
    should_auto_confirm,
)
from librarian.wanted import add_wanted
from librarian.wanted_search import ask_wanted_hit

NZB_XML = b'<?xml version="1.0"?><nzb xmlns="http://www.newzbin.com/DTD/2003/nzb"></nzb>'


def _settings(**kwargs) -> Settings:
    base = dict(
        sabnzbd_url="http://sab.test",
        sabnzbd_api_key="sab",
        nzbfinder_url="https://nzbfinder.test",
        nzbfinder_api_token="tok",
        op_auto_confirm_enabled=False,
        op_auto_confirm_hosts=[],
    )
    base.update(kwargs)
    return Settings(**base)


def test_normalize_allowlist_dedupes_and_lowers():
    assert normalize_allowlist("NZBFinder, nzbfinder; other") == ["nzbfinder", "other"]
    assert normalize_allowlist(["  A ", "", "a"]) == ["a"]


def test_should_auto_confirm_default_off_and_readers_never():
    settings = _settings(op_auto_confirm_enabled=True, op_auto_confirm_hosts=["nzbfinder"])
    assert should_auto_confirm(settings, role="reader", host_id="nzbfinder") is False
    assert should_auto_confirm(settings, role="owner", host_id="nzbfinder") is True
    assert should_auto_confirm(settings, role="op", host_id="nzbfinder") is True
    off = _settings(op_auto_confirm_enabled=False, op_auto_confirm_hosts=["nzbfinder"])
    assert should_auto_confirm(off, role="owner", host_id="nzbfinder") is False
    assert host_on_allowlist(settings, "NZBFinder") is True


def test_ask_wanted_auto_confirms_allowlisted_host(tmp_path, monkeypatch):
    from librarian.nzbfinder import NZBFinderClient
    from librarian.sabnzbd import SABClient

    db = Database(tmp_path / "librarian.db")
    owner = db.create_local_user(
        user_id="u-owner",
        display_name="owner",
        role="owner",
        password_hash=hash_password("password123"),
    )
    row = add_wanted(db, {"title": "Trusted Title", "kind": "book", "author": "Ada"})
    settings = _settings(op_auto_confirm_enabled=True, op_auto_confirm_hosts=["nzbfinder"])

    def sab_handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if request.method == "POST" or params.get("mode") == "addfile":
            return httpx.Response(200, json={"nzo_ids": ["nzo-auto-1"]})
        return httpx.Response(200, json={"queue": {"slots": []}})

    def nzb_handler(request: httpx.Request) -> httpx.Response:
        if "/download" in str(request.url) or "getnzb" in str(request.url):
            return httpx.Response(200, content=NZB_XML)
        return httpx.Response(200, json={})

    sab = SABClient("http://sab.test", "sab", transport=httpx.MockTransport(sab_handler))
    nzb = NZBFinderClient(
        "https://nzbfinder.test", "tok", transport=httpx.MockTransport(nzb_handler)
    )

    # Patch confirm path clients via monkeypatch on confirm_asked_job internals
    import librarian.jobs as jobs_mod

    real_confirm = jobs_mod.confirm_asked_job

    def confirm_with_clients(db_, settings_, job_id, **kwargs):
        kwargs.setdefault("sab", sab)
        kwargs.setdefault("nzb", nzb)
        return real_confirm(db_, settings_, job_id, **kwargs)

    monkeypatch.setattr(jobs_mod, "confirm_asked_job", confirm_with_clients)

    hit = {
        "guid": "g-auto-1",
        "title": "Trusted Title",
        "host_id": "nzbfinder",
        "kind": "book",
    }
    result = ask_wanted_hit(
        db,
        str(row["id"]),
        hit,
        settings=settings,
        role="owner",
        actor_id=owner["id"],
    )
    assert result["outcome"] == "auto_confirmed"
    assert result["auto_confirmed"] is True
    job = db.get_job(str(result["job_id"]))
    assert job is not None
    assert job["status"] == "queued"
    assert job["nzo_id"] == "nzo-auto-1"

    with db._connect() as conn:
        events = conn.execute(
            "SELECT kind, actor_id, detail_json FROM security_events WHERE kind = ?",
            (SECURITY_KIND,),
        ).fetchall()
    assert len(events) == 1
    assert events[0]["actor_id"] == owner["id"]
    assert "nzbfinder" in str(events[0]["detail_json"])


def test_ask_wanted_stays_asked_when_kill_switch_off(tmp_path):
    db = Database(tmp_path / "librarian.db")
    db.create_local_user(
        user_id="u-owner",
        display_name="owner",
        role="owner",
        password_hash=hash_password("password123"),
    )
    row = add_wanted(db, {"title": "Wait for confirm", "kind": "book"})
    settings = _settings(op_auto_confirm_enabled=False, op_auto_confirm_hosts=["nzbfinder"])
    result = ask_wanted_hit(
        db,
        str(row["id"]),
        {"guid": "g-wait", "title": "Wait", "host_id": "nzbfinder", "kind": "book"},
        settings=settings,
        role="owner",
        actor_id="u-owner",
    )
    assert result["outcome"] == "hit"
    assert result.get("auto_confirmed") is False
    job = db.get_job(str(result["job_id"]))
    assert job["status"] == "asked"
    assert job["nzo_id"] is None
