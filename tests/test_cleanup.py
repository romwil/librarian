"""Catalog cleanup values run against real SQLite."""

from pathlib import Path

from librarian.cleanup import cleanup_library, read_progress, restore_quarantine
from librarian.config import Settings
from librarian.db import Database


def _work(db, work_id, *, isbn, author="Nikole Hannah-Jones", title="The 1619 Project: A New Origin Story"):
    return db.upsert_work({"id": work_id, "kind": "book", "title": title, "author": author, "isbn": isbn})


def test_cleanup_dry_run_then_identifier_merge_moves_household_state(tmp_path):
    db = Database(tmp_path / "librarian.db")
    def add_owner():
        with db._connect() as conn:
            conn.execute(
                "INSERT INTO users(id,display_name,role,password_hash,created_at) VALUES('owner','Owner','owner','hash',0)"
            )
    db.run_write(add_owner, label="test_owner")
    owner = {"id": "owner"}
    shelf = db.create_named_shelf(owner["id"], "Reading")
    first = _work(db, "86f007ee", isbn="9780593230572")
    second = _work(db, "5172a6bf", isbn="0593230574", author="Hannah-Jones, Nikole")
    media = tmp_path / "second.epub"
    media.write_bytes(b"same bytes")
    db.add_file({"work_id": second["id"], "path": str(media), "filename": media.name, "kind": "book", "size": media.stat().st_size})
    db.add_favorite(owner["id"], second["id"])
    db.add_to_named_shelf(shelf["id"], owner["id"], second["id"])
    db.upsert_progress(user_id=owner["id"], work_id=second["id"], position="chapter 3", fraction=.4)

    preview = cleanup_library(db, Settings(books_root=str(tmp_path / "library" / "books")), data_dir=tmp_path)
    assert preview["merge_groups"] == 1
    assert read_progress(tmp_path)["awaiting_approval"] is True

    result = cleanup_library(db, Settings(books_root=str(tmp_path / "library" / "books")), apply=True, data_dir=tmp_path)
    assert result["merged"] == 1
    assert db.get_work(second["id"]) is None
    assert db.is_favorite(owner["id"], first["id"])
    assert db.is_on_shelf(shelf["id"], first["id"])
    assert db.get_progress(owner["id"], first["id"])["position"] == "chapter 3"
    db.close()


def test_cleanup_keeps_distinct_isbns_as_editions_and_holds_fuzzy_matches(tmp_path):
    db = Database(tmp_path / "librarian.db")
    _work(db, "hardback", isbn="9780593230572")
    _work(db, "ebook", isbn="9780593230589", title="The 1619 Project")
    _work(db, "uncertain", isbn="", title="The 1619 Project")

    preview = cleanup_library(db, Settings(), data_dir=tmp_path)
    assert preview["merge_groups"] == 1
    assert preview["possible_duplicates"] == 1
    cleanup_library(db, Settings(), apply=True, data_dir=tmp_path)
    assert db.list_editions_for_work("hardback") or db.list_editions_for_work("ebook")
    held = [db.get_work("uncertain"), db.get_work("hardback"), db.get_work("ebook")]
    assert any(row and row["review_reason"] == "possible_duplicate" for row in held)
    db.close()


def test_cleanup_relayouts_audiobook_folder_without_deleting(tmp_path):
    db = Database(tmp_path / "librarian.db")
    settings = Settings(audiobooks_root=str(tmp_path / "library" / "audiobooks"))

    # Dumped flat — not the Author/Title (or Author/Series/Book N - Title) layout.
    old_folder = tmp_path / "incoming" / "random-dump"
    old_folder.mkdir(parents=True)
    audio = old_folder / "book.m4b"
    audio.write_bytes(b"m4b-bytes")
    work = db.upsert_work(
        {
            "kind": "audiobook",
            "title": "The Left Hand of Darkness",
            "author": "Ursula K. Le Guin",
            "narrator": "Ruth Franklin",
            "description": "A winter journey on Gethen.",
            "folder_path": str(old_folder),
            "review_state": "none",
        }
    )
    db.add_file(
        {
            "work_id": work["id"],
            "path": str(audio),
            "filename": audio.name,
            "kind": "audiobook",
            "size": audio.stat().st_size,
        }
    )

    preview = cleanup_library(db, settings, data_dir=tmp_path)
    assert preview["audiobooks_to_relayout"] == 1
    sample = preview["audiobook_relayout_samples"][0]
    assert sample["work_id"] == work["id"]
    assert sample["from"] == str(old_folder)
    assert "metadata.json" in sample["sidecars"]
    assert "desc.txt" in sample["sidecars"]
    assert "reader.txt" in sample["sidecars"]
    assert audio.is_file()  # dry run never touches the file

    result = cleanup_library(db, settings, apply=True, data_dir=tmp_path)
    assert result["relayouts"] == 1
    assert result["relayout_files_moved"] == 1

    stored = db.get_work(work["id"])
    dest_folder = Path(settings.audiobooks_root) / "Ursula K Le Guin" / "The Left Hand of Darkness"
    assert stored["folder_path"] == str(dest_folder)
    assert not audio.is_file()  # moved, not copied
    moved_files = db.files_for_work(work["id"])
    assert len(moved_files) == 1
    assert Path(moved_files[0]["path"]).parent == dest_folder
    assert Path(moved_files[0]["path"]).is_file()
    assert (dest_folder / "metadata.json").is_file()
    assert (dest_folder / "desc.txt").is_file()
    assert (dest_folder / "reader.txt").is_file()

    # A second preview finds nothing left to relayout.
    again = cleanup_library(db, settings, data_dir=tmp_path)
    assert again["audiobooks_to_relayout"] == 0
    db.close()


def test_cleanup_quarantine_manifest_restores_byte_identical_copy(tmp_path):
    db = Database(tmp_path / "librarian.db")
    first = _work(db, "first", isbn="9780593230572")
    second = _work(db, "second", isbn="0593230574")
    left, right = tmp_path / "left.epub", tmp_path / "right.epub"
    left.write_bytes(b"identical")
    right.write_bytes(b"identical")
    for work, path in ((first, left), (second, right)):
        db.add_file({"work_id": work["id"], "path": str(path), "filename": path.name, "kind": "book", "size": path.stat().st_size})

    settings = Settings(books_root=str(tmp_path / "library" / "books"))
    cleanup_library(db, settings, data_dir=tmp_path)
    result = cleanup_library(db, settings, apply=True, data_dir=tmp_path)
    manifest = Path(result["quarantine"]) / "manifest.json"
    assert manifest.is_file()
    assert restore_quarantine(manifest) == 1
    assert left.is_file() and right.is_file()
    db.close()
