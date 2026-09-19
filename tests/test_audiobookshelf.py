"""Audiobookshelf client — mocked HTTP only (scan notify + progress sync)."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from librarian.audiobookshelf import (
    _ABS_DURATION,
    _ABS_PUSH_AT,
    ABS_PUSH_MIN_INTERVAL_S,
    AudiobookshelfClient,
    AudiobookshelfError,
    map_abs_progress_to_local,
    notify_abs_scan,
    pull_abs_listen_progress,
    push_abs_listen_progress,
    should_adopt_abs_progress,
)
from librarian.auth import hash_password
from librarian.config import Settings
from librarian.db import Database
from librarian.listen import decode_listen_position, encode_listen_position


def _settings(**overrides):
    base = {
        "audiobookshelf_url": "http://abs.local",
        "audiobookshelf_api_token": "secret-abs",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _clear_abs_throttle():
    _ABS_PUSH_AT.clear()
    _ABS_DURATION.clear()
    yield
    _ABS_PUSH_AT.clear()
    _ABS_DURATION.clear()


def test_trigger_scan_posts_libraries():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url.path)))
        if request.url.path.endswith("/api/libraries"):
            return httpx.Response(
                200,
                json={
                    "libraries": [
                        {"id": "lib-books", "mediaType": "book"},
                        {"id": "lib-podcasts", "mediaType": "podcast"},
                    ]
                },
            )
        assert request.method == "POST"
        assert request.headers.get("Authorization") == "Bearer secret-abs"
        return httpx.Response(200, json={"success": True})

    client = AudiobookshelfClient(
        "http://abs.local",
        "secret-abs",
        transport=httpx.MockTransport(handler),
    )
    try:
        scanned = client.scan_audiobook_libraries()
    finally:
        client.close()
    assert scanned == ["lib-books"]
    assert ("POST", "/api/libraries/lib-books/scan") in seen
    assert not any("lib-podcasts" in path for _method, path in seen if _method == "POST")


def test_notify_abs_scan_fail_soft_and_skip():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    result = notify_abs_scan(_settings(), transport=httpx.MockTransport(handler))
    assert result["ok"] is False
    assert result["skipped"] is False

    skipped = notify_abs_scan(_settings(audiobookshelf_url="", audiobookshelf_api_token=""))
    assert skipped == {"ok": False, "skipped": True, "reason": "not_configured"}


def test_get_and_update_media_progress():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = str(request.url.path)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "progress": 0.25,
                    "currentTime": 100.0,
                    "duration": 400.0,
                    "isFinished": False,
                },
            )
        seen["body"] = request.read()
        return httpx.Response(200, json={"success": True})

    client = AudiobookshelfClient(
        "http://abs.local",
        "tok",
        transport=httpx.MockTransport(handler),
    )
    try:
        row = client.get_media_progress("li_1")
        assert row["currentTime"] == 100.0
        assert client.update_media_progress("li_1", current_time=120.0, progress=0.3) is True
    finally:
        client.close()
    assert seen["method"] == "PATCH"
    assert seen["path"].endswith("/api/me/progress/li_1")


def test_get_media_progress_404_is_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = AudiobookshelfClient("http://abs.local", "tok", transport=httpx.MockTransport(handler))
    try:
        assert client.get_media_progress("missing") is None
    finally:
        client.close()


def test_should_adopt_and_map_progress():
    assert should_adopt_abs_progress(local_fraction=0, local_seconds=0, abs_fraction=0.2) is True
    assert should_adopt_abs_progress(local_fraction=0.5, local_seconds=100, abs_fraction=0.2) is False
    assert should_adopt_abs_progress(local_fraction=0.2, local_seconds=10, abs_fraction=0.4) is True
    assert should_adopt_abs_progress(
        local_fraction=0.2, local_seconds=10, abs_current_time=50, abs_fraction=0.2
    ) is True

    mapped = map_abs_progress_to_local(
        {"progress": 0.5, "currentTime": 50.0, "duration": 100.0},
        file_ids=["f1"],
    )
    assert mapped["fraction"] == 0.5
    assert decode_listen_position(mapped["position"]) == {
        "file_id": "f1",
        "seconds": 50.0,
        "rate": 0.0,
    }


def test_pull_adopts_abs_ahead_without_wiping_local(tmp_path):
    db = Database(tmp_path / "librarian.db")
    work = db.upsert_work(
        {
            "kind": "audiobook",
            "title": "Dune",
            "author": "Herbert",
            "abs_item_id": "li_dune",
        }
    )
    user = db.create_local_user(
        user_id="local-owner",
        display_name="owner",
        password_hash=hash_password("password123"),
        role="owner",
    )
    db.upsert_progress(
        user_id=user["id"],
        work_id=work["id"],
        position=encode_listen_position(file_id="f1", seconds=200.0),
        fraction=0.5,
    )

    def behind(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"progress": 0.1, "currentTime": 20.0, "duration": 400.0, "isFinished": False},
        )

    assert (
        pull_abs_listen_progress(
            db,
            _settings(),
            user_id=user["id"],
            work=work,
            files=[{"id": "f1"}],
            transport=httpx.MockTransport(behind),
        )
        is None
    )
    kept = db.get_progress(user["id"], work["id"])
    assert float(kept["fraction"]) == 0.5

    def ahead(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"progress": 0.75, "currentTime": 300.0, "duration": 400.0, "isFinished": False},
        )

    updated = pull_abs_listen_progress(
        db,
        _settings(),
        user_id=user["id"],
        work=work,
        files=[{"id": "f1"}],
        transport=httpx.MockTransport(ahead),
    )
    assert updated is not None
    assert float(updated["fraction"]) == 0.75
    assert decode_listen_position(updated["position"])["seconds"] == 300.0


def test_push_throttles_then_force_finished():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(200, json={"success": True})

    work = {"kind": "audiobook", "abs_item_id": "li_1", "title": "Dune"}
    transport = httpx.MockTransport(handler)
    first = push_abs_listen_progress(
        _settings(),
        work,
        fraction=0.2,
        position=encode_listen_position(file_id="f1", seconds=40.0),
        transport=transport,
    )
    second = push_abs_listen_progress(
        _settings(),
        work,
        fraction=0.21,
        position=encode_listen_position(file_id="f1", seconds=42.0),
        transport=transport,
    )
    finished = push_abs_listen_progress(
        _settings(),
        work,
        fraction=1.0,
        finished=True,
        force=True,
        transport=transport,
    )
    assert first["ok"] is True
    assert second == {"ok": False, "skipped": True, "reason": "throttled"}
    assert finished["ok"] is True
    assert calls.count("PATCH") == 2
    assert ABS_PUSH_MIN_INTERVAL_S >= 1.0


def test_update_refuses_bad_token():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    client = AudiobookshelfClient("http://abs.local", "bad", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(AudiobookshelfError, match="refused"):
            client.update_media_progress("li_1", progress=0.1)
    finally:
        client.close()


def test_settings_object_works_for_notify():
    settings = Settings(
        audiobookshelf_url="http://abs.local",
        audiobookshelf_api_token="tok",
    )
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        if request.url.path.endswith("/api/libraries"):
            return httpx.Response(200, json={"libraries": [{"id": "lib-1", "mediaType": "book"}]})
        return httpx.Response(200, json={})

    result = notify_abs_scan(settings, transport=httpx.MockTransport(handler))
    assert result["ok"] is True
    assert result["libraries"] == ["lib-1"]
    assert "POST" in seen
