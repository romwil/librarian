# Canonical catalog — owner pass

Phase 4 tooling for one card per title on the finished `m0003` model. **Do not run
Purge or duplicate-merge against live Automat** until a named snapshot exists and
the owner has walked a clone. Nightly backup is already on Maintain.

Wanted / Get still never send SABnzbd. Confirm on Downloads is a product control,
not legal safety.

## What shipped

| Sprint | What the box does |
| --- | --- |
| 4.1 Schema | `m0008`: foreign keys + `ON DELETE CASCADE` on catalog children (including Sorting's `review_diagnosis`); indexes on `files.path`, `works.isbn`, `jobs.indexer_guid`; `_connect` closes SQLite; `works_fts` stays in sync via triggers. Nightly backup on Maintain is the restore path — this step does not snapshot inside the migration transaction. |
| 4.2 Canonical | `m0009` backfill: browse author facets, More by, work page authors/editions, and ISBN search read `work_authors` / `editions` / `work_identifiers`. `works.author` stays a display cache. |
| 4.3 Duplicate merge | One matcher (`librarian.identity.match`). Calibre `(11630)` suffixes strip on match and on apply. Merge runs **only after a named snapshot**. Rollback is restore-from-snapshot, not Safe undo. |
| 4.4 Shell pass | Preview names wishlist stubs vs true shells (`kept_reasons`). Purge still asks for the typed count and snapshots first. `delete_work` leaves no edition / author orphans. |

## Duplicate merge (after snapshot)

Preview is safe:

```bash
# Owner session against a clone, never against live 8793 this sprint
curl -s -b cookies http://127.0.0.1:8793/api/maintain/duplicate-merge/preview
```

Maintain → **Duplicate merge** → Preview, then type the extra-row count. Apply writes
`config/backups/pre-duplicate-merge-YYYYmmdd-HHMMSS.db`. Canonical cleanup Approve
also snapshots (`pre-canonical-cleanup-YYYY-MM-DD.db`).

Restore (container stopped):

```bash
cd /mnt/user/appdata/librarian
docker stop librarian
mv config/librarian.db config/librarian.db.pre-merge
rm -f config/librarian.db-wal config/librarian.db-shm
cp config/backups/pre-duplicate-merge-YYYYmmdd-HHMMSS.db config/librarian.db
chmod 600 config/librarian.db
./docker-run.sh
```

Walk one merged work (authors, editions, files, progress) before inviting anyone.

## Shell owner pass (~5,541 stubs)

Member views are already file-backed. The remaining work is **naming**:

1. `GET /api/maintain/purge-shells/preview` — `would_purge`, `kept_reasons.wishlist_stub`, samples.
2. Decide which ISBN-only rows are real wants and which are junk.
3. Type the purge count. A `pre-purge-shells-*.db` snapshot is taken first.

Engineering will not auto-name the live pile. Wishlist stubs (`review_state=none`, ISBN set, no folder) stay until the owner says otherwise.

## Leftover

- Live Automat catalog is unchanged by this sprint (no `docker-run`, no merge, no purge).
- Fuzzy title/author-only clusters stay in `possible_duplicates` for the owner to name; they are not auto-merged.
- Legacy `works.author` / `works.isbn` columns remain as cache; dropping them is post-1.0.
