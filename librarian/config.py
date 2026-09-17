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
    "HOUSEHOLD_NAME": "household_name",
    "HARDCOVER_API_TOKEN": "hardcover_api_token",
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
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    household_name: str = "The Hall"
    hardcover_api_token: str = ""
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
        if "extra_indexers" in filtered:
            from librarian.indexers.hosts import normalize_extra_indexers

            filtered["extra_indexers"] = normalize_extra_indexers(filtered["extra_indexers"])
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
    return Settings.from_mapping(merged)


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
    merged = asdict(existing)
    for key, value in incoming.items():
        if key not in merged:
            continue
        if key in SECRET_FIELDS and not str(value or "").strip():
            continue
        if key == "extra_indexers":
            from librarian.indexers.hosts import merge_extra_indexers

            merged[key] = merge_extra_indexers(value, existing.extra_indexers)
            continue
        merged[key] = value
    return merged


def mask_settings(settings: Settings) -> Dict[str, Any]:
    from librarian.indexers.hosts import mask_extra_indexers

    payload = asdict(settings)
    for name in SECRET_FIELDS:
        payload[f"{name}_set"] = bool(str(payload.get(name) or "").strip())
        payload[name] = ""
    payload["extra_indexers"] = mask_extra_indexers(settings.extra_indexers)
    return payload
