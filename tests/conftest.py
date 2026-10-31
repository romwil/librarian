import os
from urllib.parse import urlparse

os.environ.setdefault("LIBRARIAN_SKIP_APP_BOOT", "1")
os.environ.setdefault("LIBRARIAN_PBKDF2_ITERATIONS", "1000")
os.environ.setdefault("LIBRARIAN_SESSION_SECRET", "unit-test-session-secret-value")
os.environ.setdefault("LIBRARIAN_OWNER_USERNAME", "owner")
os.environ.setdefault("LIBRARIAN_OWNER_PASSWORD", "password123")

import pytest
from starlette.testclient import TestClient as StarletteTestClient

from librarian.rate_limit import clear_rate_limits
from librarian.services.search import clear_beyond_cache
from librarian.sessions import clear_session_cache, clear_session_secret_cache

_SKIP_ORIGIN_HEADER = "x-librarian-test"


@pytest.fixture(autouse=True)
def _isolate_session_secret(monkeypatch, tmp_path_factory):
    data = tmp_path_factory.mktemp("data-default")
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("LIBRARIAN_SESSION_SECRET", "unit-test-session-secret-value")
    monkeypatch.setenv("LIBRARIAN_SKIP_APP_BOOT", "1")
    monkeypatch.setenv("LIBRARIAN_PBKDF2_ITERATIONS", "1000")
    monkeypatch.delenv("LIBRARIAN_TRUST_PROXY_HEADERS", raising=False)
    # Block maintainer .env LLM keys (load_dotenv does not override existing env).
    for key in (
        "LLM_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "LLM_EMBEDDING_MODEL",
    ):
        monkeypatch.setenv(key, "")
    clear_session_secret_cache()
    clear_session_cache()
    clear_rate_limits()
    clear_beyond_cache()
    yield
    clear_rate_limits()
    clear_session_cache()
    clear_session_secret_cache()
    clear_beyond_cache()


def _client_origin(client) -> str:
    base = str(getattr(client, "base_url", "") or "http://testserver")
    parsed = urlparse(base)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return "http://testserver"


@pytest.fixture(autouse=True)
def _origin_headers_for_tests(monkeypatch):
    """SPA sends Origin + X-Librarian; pytest clients do the same unless skipped."""
    original = StarletteTestClient.request

    def wrapped(self, method, url, **kwargs):
        headers = dict(kwargs.get("headers") or {})
        lowered = {str(key).lower(): str(key) for key in headers}
        skip_key = lowered.get(_SKIP_ORIGIN_HEADER)
        if skip_key:
            headers.pop(skip_key, None)
        else:
            if "origin" not in lowered:
                headers["Origin"] = _client_origin(self)
            if "x-librarian" not in lowered:
                headers["X-Librarian"] = "1"
        kwargs["headers"] = headers
        return original(self, method, url, **kwargs)

    monkeypatch.setattr(StarletteTestClient, "request", wrapped)
