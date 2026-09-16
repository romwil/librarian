from librarian.config import ENV_TO_FIELD, load_merged_settings, mask_settings, save_settings


def test_settings_json_wins_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SABNZBD_URL", "http://env.example")
    monkeypatch.setenv("BOOKS_ROOT", "/env/books")
    from librarian.config import Settings

    save_settings(
        tmp_path,
        Settings(sabnzbd_url="http://downloader.sl", books_root="/data/media/books"),
    )
    settings = load_merged_settings(tmp_path)
    assert settings.sabnzbd_url == "http://downloader.sl"
    assert settings.books_root == "/data/media/books"


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
            comicvine_api_key="comicvine-test-key",
        )
    )
    assert masked["nzbfinder_api_token"] == ""
    assert masked["nzbfinder_api_token_set"] is True
    assert masked["sabnzbd_api_key"] == ""
    assert masked["hardcover_api_token"] == ""
    assert masked["hardcover_api_token_set"] is True
    assert masked["comicvine_api_key"] == ""
    assert masked["comicvine_api_key_set"] is True
    assert "secret-token" not in str(masked)
    assert "hardcover-test-token" not in str(masked)
    assert "comicvine-test-key" not in str(masked)


def test_audiobookshelf_blank_secret_takes_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOBOOKSHELF_API_TOKEN", "from-env")
    from librarian.config import Settings

    save_settings(tmp_path, Settings(audiobookshelf_api_token=""))
    settings = load_merged_settings(tmp_path)
    assert settings.audiobookshelf_api_token == "from-env"


def test_invalid_audiobook_target_falls_back_to_plex():
    from librarian.config import Settings

    settings = Settings.from_mapping({"audiobook_target": "plexamp"})
    assert settings.audiobook_target == "plex"


def test_watch_enabled_coerces_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCH_ENABLED", "true")
    monkeypatch.setenv("WATCH_ROOT", "/data/inbox")
    settings = load_merged_settings(tmp_path)
    assert settings.watch_enabled is True
    assert settings.watch_root == "/data/inbox"


def test_env_to_field_includes_settings_seeded_secrets():
    assert ENV_TO_FIELD["HARDCOVER_API_TOKEN"] == "hardcover_api_token"
    assert ENV_TO_FIELD["COMICVINE_API_KEY"] == "comicvine_api_key"
    assert ENV_TO_FIELD["AUDIOBOOKSHELF_URL"] == "audiobookshelf_url"
    assert ENV_TO_FIELD["AUDIOBOOKSHELF_API_TOKEN"] == "audiobookshelf_api_token"


def test_comicvine_blank_secret_takes_env(tmp_path, monkeypatch):
    monkeypatch.setenv("COMICVINE_API_KEY", "from-env")
    from librarian.config import Settings

    save_settings(tmp_path, Settings(comicvine_api_key=""))
    settings = load_merged_settings(tmp_path)
    assert settings.comicvine_api_key == "from-env"
