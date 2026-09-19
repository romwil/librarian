"""Persistent settings: JSON file plus environment seeding.

settings.json wins for fields the household already saved. Env seeds first boot
and Docker. Blank secrets in JSON still take env until a key is saved in the UI.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

ENV_TO_FIELD = {
    "SABNZBD_URL": "sabnzbd_url",
    "SABNZBD_API_KEY": "sabnzbd_api_key",
    "NZBFINDER_URL": "nzbfinder_url",
    "NZBFINDER_API_TOKEN": "nzbfinder_api_token",
    "BOOKS_ROOT": "books_root",
    "MAGAZINES_ROOT": "magazines_root",
    "COMICS_ROOT": "comics_root",
    "AUDIOBOOKS_ROOT": "audiobooks_root",
    "INCOMING_MUSIC_ROOT": "incoming_music_root",
    "MUSIC_ROOT": "music_root",
    "COMPLETE_ROOT": "complete_root",
    "AUDIOBOOK_TARGET": "audiobook_target",
    "LLM_BASE_URL": "llm_base_url",
    "LLM_API_KEY": "llm_api_key",
    "LLM_MODEL": "llm_model",
    "LLM_PROVIDER": "llm_provider",
    "HOUSEHOLD_NAME": "household_name",
    "HARDCOVER_API_TOKEN": "hardcover_api_token",
    "NYT_BOOKS_API_KEY": "nyt_books_api_key",
    "COMICVINE_API_KEY": "comicvine_api_key",
    "WATCH_ROOT": "watch_root",
    "WATCH_ENABLED": "watch_enabled",
    "AUDIOBOOKSHELF_URL": "audiobookshelf_url",
    "AUDIOBOOKSHELF_API_TOKEN": "audiobookshelf_api_token",
    "SHOW_EXTRA_CATEGORIES": "show_extra_categories",
    "RADARR_URL": "radarr_url",
    "RADARR_API_KEY": "radarr_api_key",
    "SONARR_URL": "sonarr_url",
    "SONARR_API_KEY": "sonarr_api_key",
    "SAB_MOVIE_CATEGORY": "sab_movie_category",
    "SAB_TV_CATEGORY": "sab_tv_category",
}

MEDIA_ROOT_FIELDS = (
    "books_root",
    "magazines_root",
    "comics_root",
    "audiobooks_root",
    "incoming_music_root",
    "music_root",
)

SECRET_FIELDS = (
    "sabnzbd_api_key",
    "nzbfinder_api_token",
    "llm_api_key",
    "hardcover_api_token",
    "nyt_books_api_key",
    "comicvine_api_key",
    "audiobookshelf_api_token",
    "radarr_api_key",
    "sonarr_api_key",
)

AUDIOBOOK_TARGETS = ("plex", "audiobookshelf", "librarian_only")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def load_dotenv(path: Optional[Path] = None) -> Optional[Path]:
    """Load KEY=VALUE pairs from .env without overriding existing environment."""
    candidates = []
    if path is not None:
        candidates.append(path)
    else:
        here = Path(__file__).resolve()
        candidates.extend([Path.cwd() / ".env", here.parents[1] / ".env"])
    for candidate in candidates:
        if not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            os.environ[key] = value
        return candidate
    return None


@dataclass
class Settings:
    sabnzbd_url: str = "http://downloader.sl"
    sabnzbd_api_key: str = ""
    nzbfinder_url: str = "https://nzbfinder.ws"
    nzbfinder_api_token: str = ""
    books_root: str = "/data/media/library/books"
    magazines_root: str = "/data/media/library/magazines"
    comics_root: str = "/data/media/library/comics"
    audiobooks_root: str = "/data/media/library/audiobooks"
    incoming_music_root: str = "/data/media/library/incoming-music"
    music_root: str = "/data/media/music"
    complete_root: str = ""
    audiobook_target: str = "plex"
    llm_provider: str = "openai"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_profiles: dict = field(default_factory=dict)
    household_name: str = "The Hall"
    hardcover_api_token: str = ""
    nyt_books_api_key: str = ""
    comicvine_api_key: str = ""
    watch_root: str = ""
    watch_enabled: bool = False
    extra_indexers: list = field(default_factory=list)
    audiobookshelf_url: str = ""
    audiobookshelf_api_token: str = ""
    show_extra_categories: bool = False
    radarr_url: str = ""
    radarr_api_key: str = ""
    sonarr_url: str = ""
    sonarr_api_key: str = ""
    sab_movie_category: str = "movies"
    sab_tv_category: str = "tv"
    music_write_tags: bool = False
    quiet_hours_enabled: bool = False
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Settings":
        known = {item.name for item in fields(cls)}
        filtered = {key: data[key] for key in known if key in data}
        if "watch_enabled" in filtered:
            filtered["watch_enabled"] = _as_bool(filtered["watch_enabled"])
        if "show_extra_categories" in filtered:
            filtered["show_extra_categories"] = _as_bool(filtered["show_extra_categories"])
        if "music_write_tags" in filtered:
            filtered["music_write_tags"] = _as_bool(filtered["music_write_tags"])
        if "quiet_hours_enabled" in filtered:
            filtered["quiet_hours_enabled"] = _as_bool(filtered["quiet_hours_enabled"])
        if "extra_indexers" in filtered:
            from librarian.indexers.hosts import normalize_extra_indexers

            filtered["extra_indexers"] = normalize_extra_indexers(filtered["extra_indexers"])
        if "llm_profiles" in filtered or "llm_provider" in filtered or any(
            key in filtered for key in ("llm_base_url", "llm_api_key", "llm_model")
        ):
            from librarian.llm_providers import apply_profile_to_active, normalize_profiles

            filtered["llm_profiles"] = normalize_profiles(filtered.get("llm_profiles"))
            apply_profile_to_active(filtered)
        settings = cls(**filtered)
        target = str(settings.audiobook_target or "plex").strip().lower()
        if target not in AUDIOBOOK_TARGETS:
            settings.audiobook_target = "plex"
        else:
            settings.audiobook_target = target
        return settings


def settings_path(data_dir: Path) -> Path:
    return data_dir / "settings.json"


def _read_settings_json(data_dir: Path) -> Dict[str, Any]:
    path = settings_path(data_dir)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _json_blocks_env(stored: Mapping[str, Any], field_name: str) -> bool:
    """Env must not clobber a field the user already saved in settings.json."""
    if field_name not in stored:
        return False
    if field_name in SECRET_FIELDS:
        return bool(str(stored.get(field_name) or "").strip())
    return True


def load_merged_settings(data_dir: Path) -> Settings:
    """Load settings.json, then fill missing fields from the environment."""
    load_dotenv()
    stored = _read_settings_json(data_dir)
    merged = asdict(Settings.from_mapping(stored))
    for env_name, field_name in ENV_TO_FIELD.items():
        if env_name not in os.environ:
            continue
        if _json_blocks_env(stored, field_name):
            continue
        merged[field_name] = os.environ[env_name]
    if "watch_enabled" in merged:
        merged["watch_enabled"] = _as_bool(merged["watch_enabled"])
    if "show_extra_categories" in merged:
        merged["show_extra_categories"] = _as_bool(merged["show_extra_categories"])
    if "music_write_tags" in merged:
        merged["music_write_tags"] = _as_bool(merged["music_write_tags"])
    if "quiet_hours_enabled" in merged:
        merged["quiet_hours_enabled"] = _as_bool(merged["quiet_hours_enabled"])
    from librarian.llm_providers import normalize_provider, seed_llm_profiles_from_env

    if "llm_provider" in merged:
        merged["llm_provider"] = normalize_provider(merged.get("llm_provider"))
    key_sources = seed_llm_profiles_from_env(merged, stored)
    settings = Settings.from_mapping(merged)
    # Non-persisted metadata for mask_settings (never written to settings.json).
    settings.__dict__["_llm_key_sources"] = key_sources  # type: ignore[attr-defined]
    return settings


def save_settings(data_dir: Path, settings: Settings) -> Path:
    path = settings_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def merge_secret_fields(incoming: Mapping[str, Any], existing: Settings) -> Dict[str, Any]:
    """On PUT, a blank secret field keeps the stored value."""
    from librarian.llm_providers import normalize_provider

    merged = asdict(existing)
    prior_provider = normalize_provider(existing.llm_provider)
    provider_changed = False
    if "llm_provider" in incoming and incoming.get("llm_provider") is not None:
        provider_changed = normalize_provider(incoming.get("llm_provider")) != prior_provider

    for key, value in incoming.items():
        if key not in merged:
            continue
        if key in SECRET_FIELDS and not str(value or "").strip():
            continue
        if key == "extra_indexers":
            from librarian.indexers.hosts import merge_extra_indexers

            merged[key] = merge_extra_indexers(value, existing.extra_indexers)
            continue
        if key == "llm_profiles":
            from librarian.llm_providers import merge_profiles

            merged[key] = merge_profiles(value, existing.llm_profiles or {})
            continue
        if key == "llm_provider":
            merged[key] = normalize_provider(value)
            continue
        merged[key] = value

    if any(key in incoming for key in ("llm_provider", "llm_base_url", "llm_api_key", "llm_model", "llm_profiles")):
        from librarian.llm_providers import (
            apply_profile_to_active,
            normalize_profiles,
            sync_active_into_profiles,
        )

        # Switching provider with a blank key must not keep the previous provider's key.
        if provider_changed:
            blank_incoming_key = "llm_api_key" not in incoming or not str(incoming.get("llm_api_key") or "").strip()
            if blank_incoming_key:
                profiles = normalize_profiles(merged.get("llm_profiles"))
                new_provider = normalize_provider(merged.get("llm_provider"))
                profile = profiles.get(new_provider) or {}
                merged["llm_api_key"] = str(profile.get("api_key") or "")
                if "llm_base_url" not in incoming or not str(incoming.get("llm_base_url") or "").strip():
                    merged["llm_base_url"] = str(profile.get("base_url") or "")
                if "llm_model" not in incoming or not str(incoming.get("llm_model") or "").strip():
                    merged["llm_model"] = str(profile.get("model") or "")

        apply_profile_to_active(merged)
        merged["llm_profiles"] = sync_active_into_profiles(
            provider=str(merged.get("llm_provider") or "openai"),
            base_url=str(merged.get("llm_base_url") or ""),
            api_key=str(merged.get("llm_api_key") or ""),
            model=str(merged.get("llm_model") or ""),
            profiles=merged.get("llm_profiles") or {},
        )
        apply_profile_to_active(merged)
    return merged


def mask_settings(settings: Settings) -> Dict[str, Any]:
    from librarian.indexers.hosts import mask_extra_indexers
    from librarian.llm_providers import llm_status, mask_profiles, provider_catalog_public

    payload = asdict(settings)
    for name in SECRET_FIELDS:
        payload[f"{name}_set"] = bool(str(payload.get(name) or "").strip())
        payload[name] = ""
    payload["extra_indexers"] = mask_extra_indexers(settings.extra_indexers)
    sources = getattr(settings, "_llm_key_sources", None) or {}
    profiles = mask_profiles(settings.llm_profiles or {})
    for provider_id, row in profiles.items():
        if row.get("api_key_set"):
            row["key_source"] = str(sources.get(provider_id) or sources.get("active") or "settings")
        else:
            row["key_source"] = ""
    payload["llm_profiles"] = profiles
    payload["llm_providers"] = provider_catalog_public()
    payload["llm_status"] = llm_status(settings)
    if payload.get("llm_api_key_set"):
        payload["llm_api_key_source"] = str(sources.get("active") or sources.get(payload.get("llm_provider")) or "settings")
    else:
        payload["llm_api_key_source"] = ""
    return payload
