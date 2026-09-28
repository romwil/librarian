"""Calibre re-normalize — one-button Look first / shelve."""

from fastapi.testclient import TestClient

from librarian.calibre_renormalize import assemble_calibre_renormalize, renormalize_presence
from librarian.config import Settings
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def test_presence_quiet_without_dump():
    assert "No Calibre" in renormalize_presence(None)


def test_assemble_without_calibre(tmp_path):
    settings = Settings.from_mapping(
        {
            "books_root": str(tmp_path / "library" / "books"),
            "magazines_root": str(tmp_path / "library" / "magazines"),
            "comics_root": str(tmp_path / "library" / "comics"),
            "audiobooks_root": str(tmp_path / "library" / "audiobooks"),
            "incoming_music_root": str(tmp_path / "library" / "incoming-music"),
            "music_root": str(tmp_path / "music"),
        }
    )
    (tmp_path / "library" / "books").mkdir(parents=True)
    report = assemble_calibre_renormalize(settings, apply=False)
    assert report["available"] is False
    assert "No Calibre" in report["presence"]


def test_maintain_calibre_api(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    clear_session_secret_cache()
    clear_rate_limits()
    client = TestClient(create_app(tmp_path))
    assert client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"}).status_code == 200
    preview = client.get("/api/maintain/calibre-renormalize")
    assert preview.status_code == 200
    body = preview.json()
    assert "presence" in body
    assert "available" in body
