from librarian.config import ENV_TO_FIELD, load_merged_settings, mask_settings, save_settings


def test_settings_json_wins_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SABNZBD_URL", "http://env.example")
    monkeypatch.setenv("BOOKS_ROOT", "/env/books")
    from librarian.config import Settings

    save_settings(
        tmp_path,
        Settings(sabnzbd_url="http://downloader.sl", books_root="/data/media/library/books"),
    )
    settings = load_merged_settings(tmp_path)
    assert settings.sabnzbd_url == "http://downloader.sl"
    assert settings.books_root == "/data/media/library/books"


def test_default_media_roots_under_library():
    from librarian.config import Settings

    settings = Settings()
    assert settings.books_root == "/data/media/library/books"
    assert settings.magazines_root == "/data/media/library/magazines"
    assert settings.comics_root == "/data/media/library/comics"
    assert settings.audiobooks_root == "/data/media/library/audiobooks"
    assert settings.incoming_music_root == "/data/media/library/incoming-music"
    assert settings.music_root == "/data/media/music"


def test_blank_secret_takes_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NZBFINDER_API_TOKEN", "from-env")
    from librarian.config import Settings

    save_settings(tmp_path, Settings(nzbfinder_api_token=""))
    settings = load_merged_settings(tmp_path)
    assert settings.nzbfinder_api_token == "from-env"


def test_saved_secret_beats_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NZBFINDER_API_TOKEN", "from-env")
    from librarian.config import Settings

    save_settings(tmp_path, Settings(nzbfinder_api_token="from-json"))
    settings = load_merged_settings(tmp_path)
    assert settings.nzbfinder_api_token == "from-json"


def test_mask_settings_never_returns_token():
    from librarian.config import Settings

    masked = mask_settings(
        Settings(
            nzbfinder_api_token="secret-token",
            sabnzbd_api_key="sab",
            hardcover_api_token="hardcover-test-token",
            nyt_books_api_key="nyt-test-key",
            comicvine_api_key="comicvine-test-key",
        )
    )
    assert masked["nzbfinder_api_token"] == ""
    assert masked["nzbfinder_api_token_set"] is True
    assert masked["sabnzbd_api_key"] == ""
    assert masked["hardcover_api_token"] == ""
    assert masked["hardcover_api_token_set"] is True
    assert masked["nyt_books_api_key"] == ""
    assert masked["nyt_books_api_key_set"] is True
    assert masked["comicvine_api_key"] == ""
    assert masked["comicvine_api_key_set"] is True
    assert "secret-token" not in str(masked)
    assert "hardcover-test-token" not in str(masked)
    assert "nyt-test-key" not in str(masked)
    assert "comicvine-test-key" not in str(masked)


def test_audiobookshelf_blank_secret_takes_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOBOOKSHELF_API_TOKEN", "from-env")
    from librarian.config import Settings

    save_settings(tmp_path, Settings(audiobookshelf_api_token=""))
    settings = load_merged_settings(tmp_path)
    assert settings.audiobookshelf_api_token == "from-env"


def test_abs_credentials_recommend_audiobookshelf_without_clobbering_choice(tmp_path, monkeypatch):
    monkeypatch.delenv("AUDIOBOOK_TARGET", raising=False)
    monkeypatch.delenv("AUDIOBOOKSHELF_URL", raising=False)
    monkeypatch.delenv("AUDIOBOOKSHELF_API_TOKEN", raising=False)
    from librarian.config import settings_path

    settings_path(tmp_path).write_text(
        """{
  "audiobookshelf_url": "http://10.10.1.202:13378",
  "audiobookshelf_api_token": "from-file"
}
""",
        encoding="utf-8",
    )
    recommended = load_merged_settings(tmp_path)
    assert recommended.audiobook_target == "audiobookshelf"
    assert recommended.audiobookshelf_api_token == "from-file"

    monkeypatch.setenv("AUDIOBOOKSHELF_URL", "http://10.10.1.202:13378")
    monkeypatch.setenv("AUDIOBOOKSHELF_API_TOKEN", "from-env")
    (tmp_path / "settings.json").unlink()
    assert load_merged_settings(tmp_path).audiobook_target == "audiobookshelf"

    monkeypatch.setenv("AUDIOBOOK_TARGET", "plex")
    assert load_merged_settings(tmp_path).audiobook_target == "plex"
    monkeypatch.delenv("AUDIOBOOK_TARGET", raising=False)

    # An empty token is not a saved secret, and must not be filled back in from a developer .env.
    monkeypatch.setenv("AUDIOBOOKSHELF_API_TOKEN", "")
    assert load_merged_settings(tmp_path).audiobook_target == "librarian_only"

    settings_path(tmp_path).write_text(
        """{
  "audiobook_target": "librarian_only",
  "audiobookshelf_url": "http://10.10.1.202:13378",
  "audiobookshelf_api_token": "kept"
}
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("AUDIOBOOKSHELF_API_TOKEN", "from-env")
    saved = load_merged_settings(tmp_path)
    assert saved.audiobook_target == "librarian_only"
    assert saved.audiobookshelf_api_token == "kept"

    settings_path(tmp_path).write_text(
        """{
  "audiobook_target": "plex",
  "audiobookshelf_url": "http://abs.example",
  "audiobookshelf_api_token": "kept"
}
""",
        encoding="utf-8",
    )
    assert load_merged_settings(tmp_path).audiobook_target == "plex"


def test_audiobook_target_defaults_to_librarian_only_when_unset():
    from librarian.config import Settings

    assert Settings().audiobook_target == "librarian_only"
    assert Settings.from_mapping({}).audiobook_target == "librarian_only"
    assert Settings.from_mapping({"audiobook_target": ""}).audiobook_target == "librarian_only"
    assert Settings.from_mapping({"audiobook_target": "plexamp"}).audiobook_target == "librarian_only"
    assert Settings.from_mapping({"audiobook_target": "plex"}).audiobook_target == "plex"


def test_unknown_settings_keys_are_ignored(tmp_path, monkeypatch):
    from librarian.config import load_merged_settings, settings_path

    monkeypatch.delenv("AUDIOBOOK_TARGET", raising=False)
    # load_dotenv() refills deleted names from .env. An empty value blocks that
    # and keeps this case on the in-app default.
    monkeypatch.setenv("AUDIOBOOKSHELF_URL", "")
    monkeypatch.setenv("AUDIOBOOKSHELF_API_TOKEN", "")

    settings_path(tmp_path).write_text(
        """{
  "radarr_url": "http://radarr.example",
  "radarr_api_key": "secret",
  "sonarr_url": "http://sonarr.example",
  "sonarr_api_key": "secret",
  "sab_movie_category": "movies",
  "sab_tv_category": "tv",
  "show_extra_categories": true,
  "household_name": "The Hall"
}
""",
        encoding="utf-8",
    )
    settings = load_merged_settings(tmp_path)
    assert settings.household_name == "The Hall"
    assert settings.audiobook_target == "librarian_only"
    assert not hasattr(settings, "radarr_url")
    assert not hasattr(settings, "show_extra_categories")
    assert "secret" not in str(settings)


def test_watch_enabled_coerces_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCH_ENABLED", "true")
    monkeypatch.setenv("WATCH_ROOT", "/data/inbox")
    settings = load_merged_settings(tmp_path)
    assert settings.watch_enabled is True
    assert settings.watch_root == "/data/inbox"


def test_env_to_field_includes_settings_seeded_secrets():
    assert ENV_TO_FIELD["HARDCOVER_API_TOKEN"] == "hardcover_api_token"
    assert ENV_TO_FIELD["NYT_BOOKS_API_KEY"] == "nyt_books_api_key"
    assert ENV_TO_FIELD["COMICVINE_API_KEY"] == "comicvine_api_key"
    assert ENV_TO_FIELD["AUDIOBOOKSHELF_URL"] == "audiobookshelf_url"
    assert ENV_TO_FIELD["AUDIOBOOKSHELF_API_TOKEN"] == "audiobookshelf_api_token"


def test_comicvine_blank_secret_takes_env(tmp_path, monkeypatch):
    monkeypatch.setenv("COMICVINE_API_KEY", "from-env")
    from librarian.config import Settings

    save_settings(tmp_path, Settings(comicvine_api_key=""))
    settings = load_merged_settings(tmp_path)
    assert settings.comicvine_api_key == "from-env"
