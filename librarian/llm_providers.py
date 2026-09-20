"""BYO LLM provider catalog — OpenAI, Anthropic, Gemini.

Keeps recommended models, default base URLs, and per-provider profile blobs
so Settings can switch without wiping keys. Never logs secrets.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, MutableMapping, Optional

LLM_PROVIDERS = ("openai", "anthropic", "gemini")

# Household-cost defaults first; "recommended" is the autofill target.
PROVIDER_CATALOG: Dict[str, Dict[str, Any]] = {
    "openai": {
        "id": "openai",
        "label": "OpenAI",
        "default_base_url": "https://api.openai.com/v1",
        "key_url": "https://platform.openai.com/api-keys",
        "key_help": "Create an API key in the OpenAI dashboard.",
        "models": [
            {"id": "gpt-4o-mini", "label": "GPT-4o mini", "recommended": True, "note": "Best cost for lists & ranking"},
            {"id": "gpt-4o", "label": "GPT-4o", "recommended": False, "note": "Higher quality, higher cost"},
        ],
    },
    "anthropic": {
        "id": "anthropic",
        "label": "Anthropic",
        "default_base_url": "https://api.anthropic.com",
        "key_url": "https://console.anthropic.com/settings/keys",
        "key_help": "Create an API key in the Anthropic console.",
        "models": [
            {
                "id": "claude-sonnet-4-5",
                "label": "Claude Sonnet 4.5",
                "recommended": True,
                "note": "Strong default for household use",
            },
            {
                "id": "claude-haiku-4-5",
                "label": "Claude Haiku 4.5",
                "recommended": False,
                "note": "Faster / cheaper",
            },
        ],
    },
    "gemini": {
        "id": "gemini",
        "label": "Google Gemini",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
        "key_url": "https://aistudio.google.com/apikey",
        "key_help": "Create a Gemini API key in Google AI Studio.",
        "models": [
            {
                "id": "gemini-3.6-flash",
                "label": "Gemini 3.6 Flash",
                "recommended": True,
                "note": "Fast and inexpensive — recommended",
            },
            {
                "id": "gemini-flash-latest",
                "label": "Gemini Flash (latest)",
                "recommended": False,
                "note": "Rolling alias — follows Google’s current Flash",
            },
        ],
    },
}

# Google retires Flash/Pro ids for new keys; remap so saved Settings keep working.
_RETIRED_GEMINI_MODELS = frozenset(
    {
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-2.0-flash",
        "gemini-2.0-flash-001",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-pro",
    }
)


def normalize_provider(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if text in {"google", "google_gemini", "google_ai", "gemini_api"}:
        return "gemini"
    if text in {"openai_compatible", "openai_compat", "compatible", "oai"}:
        return "openai"
    if text in {"claude"}:
        return "anthropic"
    if text in LLM_PROVIDERS:
        return text
    return "openai"


def recommended_model(provider: str) -> str:
    catalog = PROVIDER_CATALOG.get(normalize_provider(provider)) or PROVIDER_CATALOG["openai"]
    for row in catalog.get("models") or []:
        if row.get("recommended"):
            return str(row["id"])
    models = catalog.get("models") or []
    return str(models[0]["id"]) if models else ""


def coerce_llm_model(provider: str, model: str) -> str:
    """Swap known-retired provider model ids for the household recommended default."""
    pid = normalize_provider(provider)
    text = str(model or "").strip()
    if not text:
        return recommended_model(pid)
    if pid == "gemini" and text.lower() in _RETIRED_GEMINI_MODELS:
        return recommended_model(pid)
    return text


def default_base_url(provider: str) -> str:
    catalog = PROVIDER_CATALOG.get(normalize_provider(provider)) or PROVIDER_CATALOG["openai"]
    return str(catalog.get("default_base_url") or "")


def provider_catalog_public() -> List[Dict[str, Any]]:
    """Settings UI payload — no secrets."""
    out: List[Dict[str, Any]] = []
    for provider_id in LLM_PROVIDERS:
        row = dict(PROVIDER_CATALOG[provider_id])
        out.append(row)
    return out


def empty_profile(provider: str = "openai") -> Dict[str, str]:
    pid = normalize_provider(provider)
    return {
        "base_url": default_base_url(pid),
        "api_key": "",
        "model": recommended_model(pid),
    }


def normalize_profile(provider: str, data: Any) -> Dict[str, str]:
    pid = normalize_provider(provider)
    base = empty_profile(pid)
    if not isinstance(data, Mapping):
        return base
    base_url = str(data.get("base_url") or "").strip()
    model = str(data.get("model") or "").strip()
    api_key = str(data.get("api_key") or "").strip()
    return {
        "base_url": base_url or base["base_url"],
        "model": model or base["model"],
        "api_key": api_key,
    }


def normalize_profiles(raw: Any) -> Dict[str, Dict[str, str]]:
    src = raw if isinstance(raw, Mapping) else {}
    out: Dict[str, Dict[str, str]] = {}
    for provider_id in LLM_PROVIDERS:
        out[provider_id] = normalize_profile(provider_id, src.get(provider_id))
    return out


def mask_profiles(profiles: Mapping[str, Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Public settings shape — keys become *_set flags."""
    out: Dict[str, Dict[str, Any]] = {}
    for provider_id in LLM_PROVIDERS:
        row = normalize_profile(provider_id, profiles.get(provider_id) if profiles else None)
        out[provider_id] = {
            "base_url": row["base_url"],
            "model": row["model"],
            "api_key": "",
            "api_key_set": bool(row["api_key"]),
        }
    return out


def merge_profiles(
    incoming: Any,
    existing: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Dict[str, str]]:
    """Blank api_key in an incoming profile keeps the stored key."""
    current = normalize_profiles(existing)
    src = incoming if isinstance(incoming, Mapping) else {}
    for provider_id in LLM_PROVIDERS:
        if provider_id not in src:
            continue
        row = src.get(provider_id)
        if not isinstance(row, Mapping):
            continue
        merged = dict(current[provider_id])
        if "base_url" in row:
            text = str(row.get("base_url") or "").strip()
            merged["base_url"] = text or default_base_url(provider_id)
        if "model" in row:
            text = str(row.get("model") or "").strip()
            if text:
                merged["model"] = text
        if "api_key" in row:
            text = str(row.get("api_key") or "").strip()
            if text:
                merged["api_key"] = text
        current[provider_id] = normalize_profile(provider_id, merged)
    return current


def sync_active_into_profiles(
    *,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    profiles: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Dict[str, str]]:
    """Write the active llm_* fields into the selected provider profile."""
    pid = normalize_provider(provider)
    out = normalize_profiles(profiles)
    out[pid] = normalize_profile(
        pid,
        {
            "base_url": base_url,
            "api_key": api_key or out[pid].get("api_key", ""),
            "model": model,
        },
    )
    return out


def apply_profile_to_active(settings_map: MutableMapping[str, Any]) -> None:
    """Ensure active llm_* mirrors llm_profiles[llm_provider]."""
    provider = normalize_provider(settings_map.get("llm_provider"))
    settings_map["llm_provider"] = provider
    profiles = normalize_profiles(settings_map.get("llm_profiles"))
    # Prefer explicit active key if set and shape-compatible; otherwise profile.
    active_key = str(settings_map.get("llm_api_key") or "").strip()
    profile = dict(profiles[provider])
    if active_key and api_key_fits_provider(active_key, provider):
        profile["api_key"] = active_key
    elif active_key and not api_key_fits_provider(active_key, provider):
        # Drop mismatched active key; keep a fitting profile key if present.
        settings_map["llm_api_key"] = str(profile.get("api_key") or "")
        if settings_map["llm_api_key"] and not api_key_fits_provider(
            settings_map["llm_api_key"], provider
        ):
            settings_map["llm_api_key"] = ""
            profile["api_key"] = ""
    base = str(settings_map.get("llm_base_url") or "").strip()
    if base:
        profile["base_url"] = base
    model = str(settings_map.get("llm_model") or "").strip()
    if model:
        profile["model"] = model
    profiles[provider] = normalize_profile(provider, profile)
    settings_map["llm_profiles"] = profiles
    settings_map["llm_base_url"] = profiles[provider]["base_url"]
    settings_map["llm_api_key"] = profiles[provider]["api_key"]
    settings_map["llm_model"] = profiles[provider]["model"]


def api_key_fits_provider(api_key: str, provider: str) -> bool:
    """True when the key's well-known shape matches the selected provider.

    Unknown shapes are allowed (proxies / enterprise keys). Clear mismatches
    (OpenAI ``sk-`` against Gemini, ``AIza`` against OpenAI, etc.) return False
    so we never POST a wrong-vendor key and get a cryptic HTTP 400.
    """
    key = str(api_key or "").strip()
    if not key:
        return True
    pid = normalize_provider(provider)
    if key.startswith("sk-ant"):
        return pid == "anthropic"
    if key.startswith("AIza"):
        return pid == "gemini"
    if key.startswith("sk-"):
        return pid == "openai"
    return True


def resolve_llm_connection(settings: Any) -> Dict[str, str]:
    """Resolved provider + credentials for LLMClient."""
    provider = normalize_provider(getattr(settings, "llm_provider", None))
    profiles = normalize_profiles(getattr(settings, "llm_profiles", None))
    profile = profiles.get(provider) or empty_profile(provider)
    api_key = str(getattr(settings, "llm_api_key", "") or "").strip() or profile["api_key"]
    if api_key and not api_key_fits_provider(api_key, provider):
        # Prefer a same-provider profile key over a mismatched active/env key.
        profile_key = str(profile.get("api_key") or "").strip()
        if profile_key and api_key_fits_provider(profile_key, provider):
            api_key = profile_key
        else:
            api_key = ""
    base_url = str(getattr(settings, "llm_base_url", "") or "").strip() or profile["base_url"]
    model = str(getattr(settings, "llm_model", "") or "").strip() or profile["model"]
    if not base_url:
        base_url = default_base_url(provider)
    if not model:
        model = recommended_model(provider)
    model = coerce_llm_model(provider, model)
    return {
        "provider": provider,
        "base_url": base_url.rstrip("/"),
        "api_key": api_key,
        "model": model,
    }


def llm_status(settings: Any) -> Dict[str, Any]:
    """Household status for Settings — no secrets."""
    resolved = resolve_llm_connection(settings)
    has_key = bool(resolved["api_key"])
    catalog = PROVIDER_CATALOG.get(resolved["provider"]) or PROVIDER_CATALOG["openai"]
    sources = getattr(settings, "_llm_key_sources", None) or {}
    active_source = ""
    if has_key:
        active_source = str(sources.get(resolved["provider"]) or sources.get("active") or "settings")
    return {
        "provider": resolved["provider"],
        "provider_label": catalog.get("label") or resolved["provider"],
        "model": resolved["model"],
        "configured": has_key,
        "status": "connected" if has_key else "missing_key",
        "key_source": active_source if has_key else "",
        "status_copy": (
            (
                f"Ready — {catalog.get('label')} · {resolved['model']}"
                + (" (from env)" if active_source == "env" else "")
            )
            if has_key
            else f"Add a {catalog.get('label')} API key to enable list naming, Review suggest, and search ranking."
        ),
    }


# Env aliases that seed per-provider profiles (never logged).
PROVIDER_API_KEY_ENV: Dict[str, tuple[str, ...]] = {
    "gemini": (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_AI_API_KEY",
        "LIBRARIAN_GEMINI_API_KEY",
    ),
    "anthropic": (
        "ANTHROPIC_API_KEY",
        "LIBRARIAN_ANTHROPIC_API_KEY",
    ),
    "openai": (
        "OPENAI_API_KEY",
        "LIBRARIAN_OPENAI_API_KEY",
    ),
}

PROVIDER_BASE_URL_ENV: Dict[str, tuple[str, ...]] = {
    "gemini": ("GEMINI_BASE_URL", "GOOGLE_AI_BASE_URL", "LIBRARIAN_GEMINI_BASE_URL"),
    "anthropic": ("ANTHROPIC_BASE_URL", "LIBRARIAN_ANTHROPIC_BASE_URL"),
    "openai": ("OPENAI_BASE_URL", "LIBRARIAN_OPENAI_BASE_URL"),
}

PROVIDER_MODEL_ENV: Dict[str, tuple[str, ...]] = {
    "gemini": ("GEMINI_MODEL", "GOOGLE_AI_MODEL", "LIBRARIAN_GEMINI_MODEL"),
    "anthropic": ("ANTHROPIC_MODEL", "LIBRARIAN_ANTHROPIC_MODEL"),
    "openai": ("OPENAI_MODEL", "LIBRARIAN_OPENAI_MODEL"),
}


def _first_env(names: tuple[str, ...], environ: Optional[Mapping[str, str]] = None) -> str:
    import os

    env = environ if environ is not None else os.environ
    for name in names:
        value = str(env.get(name) or "").strip()
        if value:
            return value
    return ""


def _profile_secret_blocked(stored: Mapping[str, Any], provider: str) -> bool:
    """settings.json already has a non-blank key for this provider profile."""
    profiles = stored.get("llm_profiles") if isinstance(stored.get("llm_profiles"), Mapping) else {}
    row = profiles.get(provider) if isinstance(profiles, Mapping) else None
    if isinstance(row, Mapping) and str(row.get("api_key") or "").strip():
        return True
    return False


def seed_llm_profiles_from_env(
    merged: MutableMapping[str, Any],
    stored: Mapping[str, Any],
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    """Fill empty provider profiles from env aliases. Returns key_source by provider.

    settings.json secrets win. Active LLM_API_KEY / LLM_* still apply via ENV_TO_FIELD.
    """
    import os

    env = environ if environ is not None else os.environ
    sources: Dict[str, str] = {}
    profiles = normalize_profiles(merged.get("llm_profiles"))

    # Normalize provider from env alias forms (openai_compatible → openai).
    provider = normalize_provider(merged.get("llm_provider"))
    merged["llm_provider"] = provider

    for pid in LLM_PROVIDERS:
        row = dict(profiles[pid])
        if not row.get("api_key") and not _profile_secret_blocked(stored, pid):
            key = _first_env(PROVIDER_API_KEY_ENV.get(pid, ()), env)
            if key:
                row["api_key"] = key
                sources[pid] = "env"
        if not str(row.get("base_url") or "").strip() or row.get("base_url") == default_base_url(pid):
            base = _first_env(PROVIDER_BASE_URL_ENV.get(pid, ()), env)
            if base:
                row["base_url"] = base
        model_env = _first_env(PROVIDER_MODEL_ENV.get(pid, ()), env)
        if model_env and (
            not str(row.get("model") or "").strip() or row.get("model") == recommended_model(pid)
        ):
            # Only override default recommended when env sets a model and profile had default/empty
            if pid not in (stored.get("llm_profiles") or {}) or not str(
                ((stored.get("llm_profiles") or {}).get(pid) or {}).get("model") or ""
            ).strip():
                row["model"] = model_env
        profiles[pid] = normalize_profile(pid, row)

    # If active key empty but selected provider profile has env key, promote it.
    active_key = str(merged.get("llm_api_key") or "").strip()
    if active_key and not api_key_fits_provider(active_key, provider):
        # Generic LLM_API_KEY often holds an OpenAI key while Settings selects Gemini.
        # Do not stamp that key onto the wrong provider (Gemini returns HTTP 400).
        merged["llm_api_key"] = ""
        active_key = ""
        if profiles[provider].get("api_key") and api_key_fits_provider(
            profiles[provider]["api_key"], provider
        ):
            merged["llm_api_key"] = profiles[provider]["api_key"]
            active_key = merged["llm_api_key"]
            sources["active"] = sources.get(provider) or "env"
    if not active_key and profiles[provider].get("api_key"):
        profile_key = profiles[provider]["api_key"]
        if api_key_fits_provider(profile_key, provider):
            merged["llm_api_key"] = profile_key
            sources["active"] = sources.get(provider) or "env"
    elif active_key:
        # Active LLM_API_KEY from ENV_TO_FIELD — mark source if not in settings.json
        stored_key = str(stored.get("llm_api_key") or "").strip()
        sources["active"] = "settings" if stored_key else "env"
        sources[provider] = sources.get(provider) or sources["active"]
        # Keep active key on the selected provider profile only when shapes match.
        if not profiles[provider].get("api_key") and api_key_fits_provider(active_key, provider):
            profiles[provider]["api_key"] = active_key

    if not str(merged.get("llm_base_url") or "").strip():
        merged["llm_base_url"] = profiles[provider]["base_url"]
    if not str(merged.get("llm_model") or "").strip():
        merged["llm_model"] = profiles[provider]["model"]

    merged["llm_profiles"] = profiles
    apply_profile_to_active(merged)
    return sources
