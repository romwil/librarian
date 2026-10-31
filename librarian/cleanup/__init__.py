"""Conservative catalog cleanup: preview first, then owner-approved changes."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from librarian.backup import backup_dir_for, snapshot_named
from librarian.file_identity import files_byte_identical
from librarian.identify import list_payload_files
from librarian.identify.paths import dest_layout
from librarian.identity.authors import author_match_key, display_name, sort_name, split_authors
from librarian.identity.isbn import canonical_isbn13
from librarian.identity.match import duplicate_groups
from librarian.identity.titles import title_sort
from librarian.kinds import KIND_AUDIOBOOK
from librarian.metadata import write_audiobook_sidecars
from librarian.progress_job import ProgressJob

PROGRESS = ProgressJob(
    filename="cleanup_progress.json",
    defaults=lambda: {
        "status": "idle", "phase": "", "done": 0, "total": 0, "logs": [],
        "error": "", "started_at": "", "finished_at": "", "heartbeat_at": "",
        "report": {}, "awaiting_approval": False,
    },
    heartbeat=True,
    heartbeat_stale_s=300,
)


def read_progress(data_dir: Path) -> Dict[str, Any]:
    return PROGRESS.read(data_dir)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _rows(db: Any, sql: str, args: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with db._connect() as conn:
        return [dict(row) for row in conn.execute(sql, tuple(args)).fetchall()]


def _write(db: Any, operation: Any) -> Any:
    return db.run_write(operation, label="catalog_cleanup")


def _backfill(db: Any) -> Dict[str, int]:
    files = _rows(db, "SELECT * FROM files ORDER BY id")
    hashed = 0
    for row in files:
        path = Path(str(row.get("path") or ""))
        if not row.get("sha256") and path.is_file():
            db.set_file_sha256(str(row["id"]), _sha256(path))
            hashed += 1

    works = _rows(db, "SELECT * FROM works ORDER BY id")
    updated = 0
    for work in works:
        isbn13 = canonical_isbn13(work.get("isbn"))
        values = (title_sort(work.get("title")), sort_name(work.get("author")), str(work["id"]))
        def update_work(values=values) -> None:
            with db._connect() as conn:
                conn.execute(
                    "UPDATE works SET title_sort=?, author_sort=?, updated_at=strftime('%s','now') WHERE id=?",
                    values,
                )
        _write(db, update_work)
        if isbn13:
            db.upsert_work_identifier(scheme="isbn13", value=isbn13, work_id=str(work["id"]))
        updated += 1
    return {"hashed": hashed, "backfilled": updated}


def _authors(db: Any) -> int:
    works = _rows(db, "SELECT id, author FROM works WHERE trim(coalesce(author,'')) != ''")
    groups: dict[str, list[str]] = defaultdict(list)
    for work in works:
        for author in split_authors(work["author"]):
            groups[author_match_key(author)].append(author)
    chosen: dict[str, dict[str, Any]] = {}
    for key, spellings in groups.items():
        # Count display-normalized spellings so "Last, First" never wins simply by order.
        names = [display_name(value) for value in spellings]
        name = sorted(Counter(names).items(), key=lambda pair: (-pair[1], pair[0].casefold()))[0][0]
        author = db.upsert_author({"display_name": name, "sort_name": sort_name(name)})
        for alias in set(spellings + names):
            db.upsert_author_alias(author_id=author["id"], alias=alias)
        chosen[key] = author
    for work in works:
        people = [chosen[author_match_key(author)] for author in split_authors(work["author"]) if author_match_key(author) in chosen]
        if not people:
            continue
        db.set_work_authors(work_id=work["id"], author_ids=[person["id"] for person in people])
        shown = " & ".join(person["display_name"] for person in people)
        def update_work(work_id=work["id"], shown=shown) -> None:
            with db._connect() as conn:
                conn.execute("UPDATE works SET author=?, author_sort=? WHERE id=?", (shown, sort_name(shown), work_id))
        _write(db, update_work)
    return len(chosen)


def _groups(db: Any) -> tuple[list[list[str]], list[list[str]]]:
    return duplicate_groups(db)


def _quarantine_root(settings: Any, today: str) -> Path:
    roots = [getattr(settings, name, "") for name in ("books_root", "magazines_root", "comics_root", "audiobooks_root")]
    for root in roots:
        path = Path(str(root or ""))
        if path.name in {"books", "magazines", "comics", "audiobooks"}:
            return path.parent / ".quarantine" / today
    return Path("/data/media/library/.quarantine") / today


def _merge_group(db: Any, ids: list[str], *, settings: Any, quarantine: Path) -> Dict[str, Any]:
    # Stable canonical choice makes previews and an approval rerun deterministic.
    survivor = sorted(ids, reverse=True)[0]
    moved_files = quarantined = 0
    entries: list[dict[str, str]] = []
    def operation() -> None:
        nonlocal moved_files, quarantined
        with db._connect() as conn:
            source_works = conn.execute(
                f"SELECT * FROM works WHERE id IN ({','.join('?' for _ in ids)})", ids
            ).fetchall()
            for work in source_works:
                isbn13 = canonical_isbn13(work["isbn"])
                if isbn13 or work["publisher"]:
                    conn.execute(
                        """
                        INSERT INTO editions(id,work_id,kind,isbn13,publisher,year,folder_path,cover_path)
                        VALUES(lower(hex(randomblob(16))),?,?,?,?,?,?,?)
                        """,
                        (survivor, work["kind"], isbn13 or None, work["publisher"], work["year"], work["folder_path"], work["cover_path"]),
                    )
            existing = {
                row["sha256"]: row["id"] for row in conn.execute(
                    "SELECT id, sha256 FROM files WHERE work_id=? AND sha256 IS NOT NULL", (survivor,)
                )
            }
            for source in (work_id for work_id in ids if work_id != survivor):
                for file in conn.execute("SELECT * FROM files WHERE work_id=?", (source,)).fetchall():
                    digest = file["sha256"]
                    if digest and digest in existing:
                        old = Path(file["path"])
                        if old.is_file():
                            target = quarantine / f"{file['id']}-{old.name}"
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(old), str(target))
                            entries.append({"original": str(old), "quarantined": str(target)})
                            quarantined += int(target.stat().st_size)
                        conn.execute("DELETE FROM files WHERE id=?", (file["id"],))
                        continue
                    conn.execute("UPDATE files SET work_id=? WHERE id=?", (survivor, file["id"]))
                    if digest:
                        existing[digest] = file["id"]
                    moved_files += 1
                for table, columns in (
                    ("shelf_items", "shelf_id, added_at"),
                    ("progress", "user_id, position, fraction, updated_at"),
                ):
                    rows = conn.execute(f"SELECT {columns} FROM {table} WHERE work_id=?", (source,)).fetchall()
                    for row in rows:
                        if table == "shelf_items":
                            conn.execute("INSERT OR IGNORE INTO shelf_items(shelf_id,work_id,added_at) VALUES(?,?,?)", (row["shelf_id"], survivor, row["added_at"]))
                        else:
                            conn.execute("INSERT OR REPLACE INTO progress(user_id,work_id,position,fraction,updated_at) VALUES(?,?,?,?,?)", (row["user_id"], survivor, row["position"], row["fraction"], row["updated_at"]))
                    conn.execute(f"DELETE FROM {table} WHERE work_id=?", (source,))
                conn.execute("UPDATE wanted SET work_id=? WHERE work_id=?", (survivor, source))
                conn.execute(
                    "UPDATE works SET abs_item_id=coalesce(nullif(abs_item_id,''), (SELECT abs_item_id FROM works WHERE id=?)) WHERE id=?",
                    (source, survivor),
                )
                conn.execute("UPDATE editions SET work_id=? WHERE work_id=?", (survivor, source))
                conn.execute(
                    """
                    DELETE FROM work_identifiers
                    WHERE work_id = ?
                      AND EXISTS (
                        SELECT 1 FROM work_identifiers kept
                        WHERE kept.work_id = ?
                          AND kept.scheme = work_identifiers.scheme
                          AND kept.value = work_identifiers.value
                      )
                    """,
                    (source, survivor),
                )
                conn.execute("UPDATE work_identifiers SET work_id=? WHERE work_id=?", (survivor, source))
                conn.execute("INSERT OR IGNORE INTO work_authors(work_id,author_id) SELECT ?,author_id FROM work_authors WHERE work_id=?", (survivor, source))
                conn.execute("DELETE FROM work_authors WHERE work_id=?", (source,))
                conn.execute("DELETE FROM review_suggestions WHERE work_id=?", (source,))
                conn.execute("DELETE FROM works WHERE id=?", (source,))
    _write(db, operation)
    return {"merged": len(ids) - 1, "moved_files": moved_files, "quarantined_bytes": quarantined, "entries": entries}


def _audiobook_identity_from_work(work: Dict[str, Any]) -> Dict[str, Any]:
    """dest_layout's identity shape, built from a shelved audiobook's catalog row."""
    return {
        "kind": KIND_AUDIOBOOK,
        "title": work.get("title") or "",
        "author": work.get("author") or "",
        "series_name": work.get("series_name") or "",
        "series_index": work.get("series_index") or "",
        "asin": work.get("asin") or "",
        "narrator": work.get("narrator") or "",
        "description": work.get("description") or "",
        "year": work.get("year"),
        "isbn": work.get("isbn") or "",
    }


def _audiobook_canonical_folder(work: Dict[str, Any], settings: Any) -> Optional[Path]:
    """Where organize's own dest_layout would place this audiobook today."""
    identity = _audiobook_identity_from_work(work)
    if not str(identity.get("title") or "").strip():
        return None
    try:
        return dest_layout(identity, settings, filename="placeholder.m4b").parent
    except ValueError:
        return None


def _is_audiobook_layout_current(folder: Path, canonical: Path) -> bool:
    try:
        return folder.resolve() == canonical.resolve()
    except OSError:
        return str(folder) == str(canonical)


def _audiobook_sidecar_plan(work: Dict[str, Any], source_folder: Path) -> List[str]:
    """Sidecars write_audiobook_sidecars would (re)write at the new folder."""
    names = ["metadata.json"]
    if str(work.get("description") or "").strip():
        names.append("desc.txt")
    if str(work.get("narrator") or "").strip():
        names.append("reader.txt")
    for name in ("cover.jpg", "cover.jpeg", "folder.jpg"):
        candidate = source_folder / name
        try:
            if candidate.is_file() and candidate.stat().st_size >= 256:
                names.append("cover.jpg")
                break
        except OSError:
            continue
    return names


def _audiobook_relayout_candidates(db: Any, settings: Any) -> List[Dict[str, Any]]:
    """Shelved audiobooks not already laid out Author/Series/Book N - Title or Author/Title."""
    works = _rows(
        db,
        "SELECT * FROM works WHERE kind = 'audiobook' AND review_state != 'needs_review'",
    )
    candidates: List[Dict[str, Any]] = []
    for work in works:
        folder_raw = str(work.get("folder_path") or "")
        if not folder_raw:
            continue
        folder = Path(folder_raw)
        if not folder.is_dir():
            continue
        canonical = _audiobook_canonical_folder(work, settings)
        if canonical is None or _is_audiobook_layout_current(folder, canonical):
            continue
        candidates.append(
            {
                "work_id": work["id"],
                "title": work.get("title") or "",
                "author": work.get("author") or "",
                "from": str(folder),
                "to": str(canonical),
                "sidecars": _audiobook_sidecar_plan(work, folder),
            }
        )
    return candidates


def _relayout_audiobook(db: Any, settings: Any, work: Dict[str, Any], *, quarantine: Path) -> Dict[str, Any]:
    """Move one audiobook's files onto dest_layout's canonical folder and write sidecars.

    Never deletes: a file that collides byte-for-byte with its destination is
    quarantined (same dated path cleanup already uses), and a file that collides
    with different bytes is left exactly where it is.
    """
    folder = Path(str(work.get("folder_path") or ""))
    if not folder.is_dir():
        return {"moved": 0, "quarantined_bytes": 0, "entries": []}
    identity = _audiobook_identity_from_work(work)
    canonical = _audiobook_canonical_folder(work, settings)
    if canonical is None or _is_audiobook_layout_current(folder, canonical):
        return {"moved": 0, "quarantined_bytes": 0, "entries": []}

    moved = 0
    quarantined_bytes = 0
    entries: List[Dict[str, str]] = []
    for src in list_payload_files(folder):
        dest = dest_layout(identity, settings, filename=src.name, source=src)
        if dest.resolve() == src.resolve():
            continue
        if dest.exists():
            if files_byte_identical(src, dest):
                target = quarantine / f"{work['id']}-{src.name}"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(target))
                entries.append({"original": str(src), "quarantined": str(target)})
                quarantined_bytes += int(target.stat().st_size)
            # A different file already answers to that name at the destination —
            # leave this one in place rather than overwrite or delete it.
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        old_path = str(src)
        shutil.move(str(src), str(dest))
        moved += 1

        def _update_file(old=old_path, new=dest) -> None:
            with db._connect() as conn:
                conn.execute(
                    "UPDATE files SET path=?, filename=? WHERE work_id=? AND path=?",
                    (str(new), new.name, work["id"], old),
                )

        _write(db, _update_file)

    # Sidecars land at the new folder; a cover left behind in the old one (images are
    # not payload media) is still picked up via ``source``.
    write_audiobook_sidecars(canonical, identity, source=folder)

    if moved:
        def _update_work() -> None:
            with db._connect() as conn:
                conn.execute(
                    "UPDATE works SET folder_path=?, updated_at=strftime('%s','now') WHERE id=?",
                    (str(canonical), work["id"]),
                )

        _write(db, _update_work)

    return {"moved": moved, "quarantined_bytes": quarantined_bytes, "entries": entries}


def cleanup_library(db: Any, settings: Any, *, apply: bool = False, data_dir: Path | None = None) -> Dict[str, Any]:
    """Run a report or its approved mutation pass. The first call must be dry-run."""
    root = Path(data_dir or ".")
    prior = read_progress(root)
    if apply and not prior.get("awaiting_approval"):
        raise ValueError("Run cleanup preview before approving changes.")
    PROGRESS.begin(root, start_log="Inspecting the catalog…", phase="backfill")
    if apply:
        backfill = _backfill(db)
        author_count = _authors(db)
    else:
        file_rows = _rows(db, "SELECT path, sha256 FROM files")
        backfill = {
            "hashed": sum(1 for row in file_rows if not row.get("sha256") and Path(str(row.get("path") or "")).is_file()),
            "backfilled": len(_rows(db, "SELECT id FROM works")),
        }
        author_count = len(
            {
                author_match_key(row["author"])
                for row in _rows(db, "SELECT author FROM works WHERE trim(coalesce(author,'')) != ''")
            }
        )
    automatic, possible = _groups(db)
    files = _rows(db, "SELECT path, size FROM files WHERE sha256 IN (SELECT sha256 FROM files GROUP BY sha256 HAVING count(*) > 1)")
    audiobook_relayout = _audiobook_relayout_candidates(db, settings)
    report: Dict[str, Any] = {
        **backfill, "authors": author_count, "merge_groups": len(automatic),
        "works_to_merge": sum(len(group) - 1 for group in automatic),
        "possible_duplicates": len(possible),
        "sample_groups": automatic[:5], "possible_samples": possible[:5],
        "quarantine_bytes": sum(int(row.get("size") or 0) for row in files),
        "audiobooks_to_relayout": len(audiobook_relayout),
        "audiobook_relayout_samples": audiobook_relayout[:5],
    }
    if not apply:
        PROGRESS.finish(root, result=report, finish_log=lambda *_: "Preview ready for owner approval.")
        PROGRESS.patch(root, awaiting_approval=True, report=report)
        return report
    stamp = date.today().isoformat()
    snapshot_file = snapshot_named(
        db.path, backup_dir_for(root), f"pre-canonical-cleanup-{stamp}"
    ).name
    report["snapshot"] = snapshot_file
    quarantine = _quarantine_root(settings, date.today().isoformat())
    totals = {"merged": 0, "moved_files": 0, "quarantined_bytes": 0}
    manifest_entries: list[dict[str, str]] = []
    for group in automatic:
        result = _merge_group(db, group, settings=settings, quarantine=quarantine)
        for key in totals:
            totals[key] += result[key]
        manifest_entries.extend(result["entries"])
    # Keep title/author-only matches intact, but surface them on Sorting.
    for group in possible:
        for work_id in group:
            def hold(work_id=work_id) -> None:
                with db._connect() as conn:
                    conn.execute("UPDATE works SET review_state='needs_review', review_reason='possible_duplicate' WHERE id=?", (work_id,))
            _write(db, hold)
    relayout_totals = {"relayouts": 0, "relayout_files_moved": 0, "relayout_quarantined_bytes": 0}
    for candidate in audiobook_relayout:
        work = db.get_work(candidate["work_id"])
        if not work:
            continue
        outcome = _relayout_audiobook(db, settings, work, quarantine=quarantine)
        if outcome["moved"]:
            relayout_totals["relayouts"] += 1
        relayout_totals["relayout_files_moved"] += outcome["moved"]
        relayout_totals["relayout_quarantined_bytes"] += outcome["quarantined_bytes"]
        manifest_entries.extend(outcome["entries"])
        totals["quarantined_bytes"] += outcome["quarantined_bytes"]
    if quarantine.exists():
        manifest = quarantine / "manifest.json"
        manifest.write_text(json.dumps({"created": date.today().isoformat(), **totals, "entries": manifest_entries}, indent=2) + "\n", encoding="utf-8")
    result = {
        **report, **totals, **relayout_totals,
        "quarantine": str(quarantine), "possible_duplicates_held": sum(map(len, possible)),
    }
    PROGRESS.finish(root, result=result, finish_log=lambda *_: "Cleanup applied; files remain restorable in quarantine.")
    PROGRESS.patch(root, awaiting_approval=False, report=result)
    return result


def restore_quarantine(manifest_path: Path) -> int:
    """Restore every still-quarantined file recorded in a cleanup manifest."""
    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    restored = 0
    for entry in payload.get("entries", []):
        source = Path(str(entry.get("quarantined") or ""))
        target = Path(str(entry.get("original") or ""))
        if not source.is_file() or not target:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        restored += 1
    return restored

