from librarian.config import load_merged_settings, mask_settings, save_settings


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

    masked = mask_settings(Settings(nzbfinder_api_token="secret-token", sabnzbd_api_key="sab"))
    assert masked["nzbfinder_api_token"] == ""
    assert masked["nzbfinder_api_token_set"] is True
    assert masked["sabnzbd_api_key"] == ""
    assert "secret-token" not in str(masked)


def test_invalid_audiobook_target_falls_back_to_plex():
    from librarian.config import Settings

    settings = Settings.from_mapping({"audiobook_target": "plexamp"})
    assert settings.audiobook_target == "plex"
