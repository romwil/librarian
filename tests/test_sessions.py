import pytest

from librarian.sessions import (
    DEV_SESSION_SECRET,
    clear_session_secret_cache,
    create_session_token,
    is_dev_session_secret,
    parse_session_token,
    resolve_session_secret,
)


def test_refuse_public_default(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_SESSION_SECRET", DEV_SESSION_SECRET)
    clear_session_secret_cache()
    assert is_dev_session_secret(DEV_SESSION_SECRET) is True
    with pytest.raises(RuntimeError, match="public development default"):
        resolve_session_secret(tmp_path)


def test_roundtrip_token(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_SESSION_SECRET", "unit-test-session-secret-value")
    clear_session_secret_cache()
    token = create_session_token("local-abc", data_dir=tmp_path)
    payload = parse_session_token(token, data_dir=tmp_path)
    assert payload["uid"] == "local-abc"
    assert parse_session_token("garbage", data_dir=tmp_path) is None


def test_persist_generated_secret_when_env_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("LIBRARIAN_SESSION_SECRET", raising=False)
    clear_session_secret_cache()
    secret = resolve_session_secret(tmp_path)
    assert secret != DEV_SESSION_SECRET
    assert (tmp_path / "session_secret").read_text(encoding="utf-8").strip() == secret
    clear_session_secret_cache()
    assert resolve_session_secret(tmp_path) == secret
