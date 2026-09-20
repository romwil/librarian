"""Multi-provider LLM catalog, env seeding, native clients."""

from __future__ import annotations

import json

import httpx

from librarian.config import Settings, load_merged_settings, mask_settings, save_settings
from librarian.llm import LLMClient, client_from_settings, reset_llm_rate_limit_state
from librarian.llm_providers import (
    normalize_provider,
    recommended_model,
    seed_llm_profiles_from_env,
)


def test_normalize_provider_aliases():
    assert normalize_provider("openai_compatible") == "openai"
    assert normalize_provider("Google") == "gemini"
    assert normalize_provider("claude") == "anthropic"
    assert normalize_provider("gemini") == "gemini"


def test_recommended_models():
    assert recommended_model("openai") == "gpt-4o-mini"
    assert recommended_model("anthropic").startswith("claude")
    assert recommended_model("gemini") == "gemini-3.6-flash"


def test_coerce_retired_gemini_models():
    from librarian.llm_providers import coerce_llm_model, resolve_llm_connection

    assert coerce_llm_model("gemini", "gemini-2.5-flash") == "gemini-3.6-flash"
    assert coerce_llm_model("gemini", "gemini-2.0-flash") == "gemini-3.6-flash"
    assert coerce_llm_model("gemini", "gemini-3.6-flash") == "gemini-3.6-flash"
    assert coerce_llm_model("openai", "gpt-4o-mini") == "gpt-4o-mini"

    resolved = resolve_llm_connection(
        Settings(
            llm_provider="gemini",
            llm_api_key="AIzaSyFakeKeyForUnitTestOnly",
            llm_model="gemini-2.5-flash",
            llm_profiles={"gemini": {"api_key": "AIzaSyFakeKeyForUnitTestOnly", "model": "gemini-2.5-flash"}},
        )
    )
    assert resolved["model"] == "gemini-3.6-flash"


def test_seed_gemini_env_aliases(tmp_path, monkeypatch):
    # Isolate from the developer .env (load_dotenv would re-inject LLM_API_KEY).
    monkeypatch.setattr("librarian.config.load_dotenv", lambda path=None: None)
    for name in (
        "LLM_API_KEY",
        "LLM_PROVIDER",
        "LLM_MODEL",
        "LLM_BASE_URL",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_AI_API_KEY",
        "LIBRARIAN_GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret-from-env")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")

    cfg = load_merged_settings(tmp_path)
    assert cfg.llm_provider == "gemini"
    assert cfg.llm_api_key == "gemini-secret-from-env"
    assert cfg.llm_profiles["gemini"]["api_key"] == "gemini-secret-from-env"
    assert cfg.llm_model

    public = mask_settings(cfg)
    assert public["llm_api_key"] == ""
    assert public["llm_api_key_set"] is True
    assert public["llm_api_key_source"] == "env"
    assert public["llm_profiles"]["gemini"]["api_key_set"] is True
    assert public["llm_profiles"]["gemini"]["api_key"] == ""
    assert public["llm_status"]["configured"] is True
    assert "from env" in public["llm_status"]["status_copy"]


def test_settings_json_key_wins_over_env(tmp_path, monkeypatch):
    monkeypatch.setattr("librarian.config.load_dotenv", lambda path=None: None)
    for name in ("LLM_API_KEY", "LLM_PROVIDER", "GEMINI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    save_settings(
        tmp_path,
        Settings(
            llm_provider="gemini",
            llm_api_key="json-key",
            llm_model="gemini-2.5-flash",
            llm_profiles={"gemini": {"api_key": "json-key", "model": "gemini-2.5-flash", "base_url": ""}},
        ),
    )
    cfg = load_merged_settings(tmp_path)
    assert cfg.llm_api_key == "json-key"
    public = mask_settings(cfg)
    assert public["llm_api_key_source"] == "settings"


def test_switch_profiles_remember_keys():
    from librarian.config import merge_secret_fields

    existing = Settings(
        llm_provider="openai",
        llm_api_key="openai-key",
        llm_model="gpt-4o-mini",
        llm_base_url="https://api.openai.com/v1",
        llm_profiles={
            "openai": {"api_key": "openai-key", "model": "gpt-4o-mini", "base_url": "https://api.openai.com/v1"},
            "gemini": {"api_key": "gemini-key", "model": "gemini-2.5-flash", "base_url": ""},
        },
    )
    merged = merge_secret_fields(
        {
            "llm_provider": "gemini",
            "llm_api_key": "",  # blank keeps gemini profile key via sync
            "llm_model": "gemini-2.5-flash",
            "llm_profiles": {
                "openai": {"api_key": "openai-key", "model": "gpt-4o-mini", "base_url": "https://api.openai.com/v1"},
                "gemini": {"api_key": "gemini-key", "model": "gemini-2.5-flash", "base_url": ""},
            },
        },
        existing,
    )
    assert merged["llm_provider"] == "gemini"
    assert merged["llm_api_key"] == "gemini-key"
    assert merged["llm_profiles"]["openai"]["api_key"] == "openai-key"


def test_native_openai_chat(monkeypatch):
    reset_llm_rate_limit_state()
    monkeypatch.setattr("librarian.llm.time.sleep", lambda _s: None)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers.get("authorization", "").startswith("Bearer ")
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi-openai"}}]})

    client = LLMClient(
        "https://api.openai.com/v1",
        "k",
        "gpt-4o-mini",
        provider="openai",
        transport=httpx.MockTransport(handler),
    )
    assert client.chat_raw(system="s", user="u") == "hi-openai"


def test_native_anthropic_messages(monkeypatch):
    reset_llm_rate_limit_state()
    monkeypatch.setattr("librarian.llm.time.sleep", lambda _s: None)

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/v1/messages")
        assert request.headers.get("x-api-key") == "anth-key"
        assert request.headers.get("anthropic-version") == "2023-06-01"
        # Must NOT be OpenAI chat completions.
        assert "/chat/completions" not in str(request.url)
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "hi-claude"}]},
        )

    client = LLMClient(
        "https://api.anthropic.com",
        "anth-key",
        "claude-sonnet-4-5",
        provider="anthropic",
        transport=httpx.MockTransport(handler),
    )
    assert client.chat_raw(system="s", user="u") == "hi-claude"


def test_native_gemini_generate_content(monkeypatch):
    reset_llm_rate_limit_state()
    monkeypatch.setattr("librarian.llm.time.sleep", lambda _s: None)

    def handler(request: httpx.Request) -> httpx.Response:
        assert "generateContent" in str(request.url)
        assert "/chat/completions" not in str(request.url)
        assert request.url.params.get("key") == "gem-key"
        body = json.loads(request.content.decode())
        assert body["system_instruction"]["parts"][0]["text"] == "s"
        assert body["contents"][0]["parts"][0]["text"] == "u"
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "hi-gemini"}]}}]},
        )

    client = LLMClient(
        "https://generativelanguage.googleapis.com/v1beta",
        "gem-key",
        "gemini-2.5-flash",
        provider="gemini",
        transport=httpx.MockTransport(handler),
    )
    assert client.chat_raw(system="s", user="u") == "hi-gemini"


def test_client_from_settings_gemini():
    settings = Settings(
        llm_provider="gemini",
        llm_api_key="gem",
        llm_model="gemini-2.5-flash",
        llm_base_url="",
    )
    client = client_from_settings(settings)
    assert client is not None
    assert client.provider == "gemini"
    assert client.model == "gemini-3.6-flash"
    assert client.configured()
    client.close()


def test_openai_shaped_env_key_not_stamped_onto_gemini(tmp_path, monkeypatch):
    """LLM_API_KEY=sk-… must not become the Gemini credential (provider 400)."""
    monkeypatch.setattr("librarian.config.load_dotenv", lambda path=None: None)
    for name in (
        "LLM_API_KEY",
        "LLM_PROVIDER",
        "LLM_MODEL",
        "LLM_BASE_URL",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_API_KEY", "sk-openaiEnvKeyThatMustNotHitGemini")
    save_settings(
        tmp_path,
        Settings(
            llm_provider="gemini",
            llm_api_key="",
            llm_model="gemini-2.5-flash",
            llm_base_url="https://generativelanguage.googleapis.com/v1beta",
            llm_profiles={
                "gemini": {
                    "api_key": "",
                    "model": "gemini-2.5-flash",
                    "base_url": "https://generativelanguage.googleapis.com/v1beta",
                },
                "openai": {
                    "api_key": "sk-profileOpenAI",
                    "model": "gpt-4o-mini",
                    "base_url": "https://api.openai.com/v1",
                },
            },
        ),
    )
    cfg = load_merged_settings(tmp_path)
    assert cfg.llm_provider == "gemini"
    assert cfg.llm_api_key == ""
    assert cfg.llm_profiles["gemini"]["api_key"] == ""
    from librarian.llm_providers import resolve_llm_connection

    assert resolve_llm_connection(cfg)["api_key"] == ""
    assert client_from_settings(cfg) is None


def test_gemini_env_wins_over_mismatched_llm_api_key(tmp_path, monkeypatch):
    monkeypatch.setattr("librarian.config.load_dotenv", lambda path=None: None)
    for name in (
        "LLM_API_KEY",
        "LLM_PROVIDER",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_API_KEY", "sk-openaiEnvKey")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyFakeGeminiKeyForUnitTestOnly")
    save_settings(
        tmp_path,
        Settings(
            llm_provider="gemini",
            llm_api_key="",
            llm_model="gemini-2.5-flash",
            llm_profiles={"gemini": {"api_key": "", "model": "gemini-2.5-flash", "base_url": ""}},
        ),
    )
    cfg = load_merged_settings(tmp_path)
    assert cfg.llm_provider == "gemini"
    assert cfg.llm_api_key.startswith("AIza")
    assert cfg.llm_profiles["gemini"]["api_key"].startswith("AIza")


def test_api_key_fits_provider_shapes():
    from librarian.llm_providers import api_key_fits_provider

    assert api_key_fits_provider("sk-abc", "openai")
    assert not api_key_fits_provider("sk-abc", "gemini")
    assert api_key_fits_provider("AIzaSySomething", "gemini")
    assert not api_key_fits_provider("AIzaSySomething", "openai")
    assert api_key_fits_provider("sk-ant-abc", "anthropic")
    assert not api_key_fits_provider("sk-ant-abc", "openai")
    assert api_key_fits_provider("custom-proxy-token", "gemini")  # unknown shape OK
