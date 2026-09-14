import os

os.environ.setdefault("LIBRARIAN_SKIP_APP_BOOT", "1")
os.environ.setdefault("LIBRARIAN_PBKDF2_ITERATIONS", "1000")
os.environ.setdefault("LIBRARIAN_SESSION_SECRET", "unit-test-session-secret-value")
os.environ.setdefault("LIBRARIAN_OWNER_USERNAME", "owner")
os.environ.setdefault("LIBRARIAN_OWNER_PASSWORD", "password123")

import pytest

from librarian.rate_limit import clear_rate_limits
from librarian.sessions import clear_session_secret_cache


@pytest.fixture(autouse=True)
def _isolate_session_secret(monkeypatch, tmp_path_factory):
    data = tmp_path_factory.mktemp("data-default")
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("LIBRARIAN_SESSION_SECRET", "unit-test-session-secret-value")
    monkeypatch.setenv("LIBRARIAN_SKIP_APP_BOOT", "1")
    monkeypatch.setenv("LIBRARIAN_PBKDF2_ITERATIONS", "1000")
    monkeypatch.delenv("LIBRARIAN_TRUST_PROXY_HEADERS", raising=False)
    clear_session_secret_cache()
    clear_rate_limits()
    yield
    clear_rate_limits()
    clear_session_secret_cache()
