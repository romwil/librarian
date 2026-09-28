"""P2-HIGH-01: auth_gate caches owner_ready to avoid per-request owner_count connects."""

from __future__ import annotations

from fastapi.testclient import TestClient

from librarian.config import Settings, save_settings
from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache
from librarian.web.app import create_app


def test_auth_gate_caches_owner_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    monkeypatch.setattr("librarian.config.load_dotenv", lambda path=None: None)
    save_settings(tmp_path, Settings(llm_api_key=""))
    clear_session_secret_cache()
    clear_rate_limits()

    calls = {"owner_count": 0}
    app = create_app(tmp_path)
    assert app.state.owner_ready is True

    real_owner_count = app.state.db.owner_count

    def counting_owner_count():
        calls["owner_count"] += 1
        return real_owner_count()

    monkeypatch.setattr(app.state.db, "owner_count", counting_owner_count)
    client = TestClient(app)
    assert (
        client.post(
            "/api/auth/local/login",
            json={"username": "owner", "password": "password123"},
        ).status_code
        == 200
    )
    # Login still checks owner_ready for the handshake path; reset after that.
    calls["owner_count"] = 0
    # Authenticated traffic must not re-hit owner_count via auth_gate.
    for _ in range(5):
        assert client.get("/api/auth/me").status_code == 200
    assert calls["owner_count"] == 0


