from librarian.auth import hash_password, seed_env_owner, verify_password
from librarian.db import Database


def test_seed_creates_owner_once(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "will")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "hunter2xx")
    db = Database(tmp_path / "librarian.db")
    first = seed_env_owner(db)
    second = seed_env_owner(db)
    assert first == second
    user = db.get_user(first)
    assert user["display_name"] == "will"
    assert user["role"] == "owner"
    assert verify_password("hunter2xx", user["password_hash"])
    assert db.owner_count() == 1


def test_seed_refuses_weak_password(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "short")
    db = Database(tmp_path / "librarian.db")
    assert seed_env_owner(db) is None
    assert db.owner_count() == 0


def test_seed_does_not_clobber_different_owner(tmp_path, monkeypatch):
    db = Database(tmp_path / "librarian.db")
    db.create_local_user(
        user_id="local-existing",
        display_name="ada",
        password_hash=hash_password("oldpassword"),
        role="owner",
    )
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "will")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "newpassword")
    assert seed_env_owner(db) is None
    assert db.get_user_by_display_name("ada")["role"] == "owner"
    assert db.get_user_by_display_name("will") is None


def test_seed_rotates_password_for_same_owner(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_OWNER_USERNAME", "owner")
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "password123")
    db = Database(tmp_path / "librarian.db")
    user_id = seed_env_owner(db)
    monkeypatch.setenv("LIBRARIAN_OWNER_PASSWORD", "rotated99")
    assert seed_env_owner(db) == user_id
    user = db.get_user(user_id)
    assert verify_password("rotated99", user["password_hash"])
    assert not verify_password("password123", user["password_hash"])


def test_missing_password_skips_seed(tmp_path, monkeypatch):
    monkeypatch.delenv("LIBRARIAN_OWNER_PASSWORD", raising=False)
    db = Database(tmp_path / "librarian.db")
    assert seed_env_owner(db) is None
