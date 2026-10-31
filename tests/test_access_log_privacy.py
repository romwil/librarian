import logging

from fastapi.testclient import TestClient

from librarian.web.app import create_app
from librarian.web.logging_config import configure_logging, route_template

SENTINEL = "PRIVACY_SENTINEL_XYZ"
APIKEY = "apikey=super-secret-token"


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    return TestClient(create_app(tmp_path))


def test_configure_logging_pins_httpx_warning():
    configure_logging()
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
    assert logging.getLogger("uvicorn.access").propagate is False


def test_access_log_is_route_template_without_query_or_secrets(tmp_path, monkeypatch, caplog):
    client = _client(tmp_path, monkeypatch)
    with caplog.at_level(logging.INFO, logger="librarian.web.access"):
        resp = client.get(f"/api/search?q={SENTINEL}&{APIKEY}")
    assert resp.status_code == 401
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert SENTINEL not in joined
    assert "apikey=" not in joined.lower()
    assert "super-secret-token" not in joined
    assert "?" not in joined
    assert "GET /api/search 401" in joined


def test_access_log_authenticated_search_still_omits_query(tmp_path, monkeypatch, caplog):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/auth/local/login", json={"username": "owner", "password": "password123"})
    with caplog.at_level(logging.INFO, logger="librarian.web.access"):
        client.get(f"/api/search?q={SENTINEL}")
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert SENTINEL not in joined
    assert "GET /api/search" in joined
    data_text = ""
    for path in tmp_path.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".txt", ".log"}:
            data_text += path.read_text(encoding="utf-8", errors="ignore")
    assert SENTINEL not in data_text


def test_route_template_collapses_path_ids():
    class _Req:
        scope = {"path": "/api/works/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "route": None}

    assert route_template(_Req()) == "/api/works/{id}"
