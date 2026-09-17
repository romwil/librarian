# Library roots migrate (Automat cutover)

Operator runbook to move Librarian-owned media under `/data/media/library/*`
without wiping production data. **Prefer copy-then-cutover.** Do not delete
`/data/media/books` until Hall / reader smoke passes.

Sibling contract: [automat-media-contract.md](../automat-media-contract.md).

## Target layout

```text
/data/media/library/
  books/           # {Author}/{Title}/  ← blend Calibre/LonesomeLib here
  magazines/       # create empty; park Archive Historical later
  comics/          # create empty
  audiobooks/      # create empty (Plex Music-as-Audiobooks library root)
  incoming-music/  # staging; Promote → /data/media/music
/data/media/music/ # UNCHANGED (Smart Map + Plexamp)
```

Defaults in `librarian/config.py` / `settings.example.json` already point at `library/*`.
Live Automat may still have old paths in `/config/settings.json` until you rebind.

## 0. Inventory (read-only)

From a maintainer mount (`/Volumes/data`) or Unraid:

```bash
ls /data/media/books
ls "/data/media/books/LonesomeLib/Calibre Library" | head
ls /data/media/newlib | head   # second Calibre lib — blend carefully
test -d /data/media/library && ls /data/media/library || echo "library/ missing"
```

Expected today: `books/LonesomeLib`, `books/Archive Historical`, no `library/`,
no top-level `audiobooks`/`comics`/`magazines`. Music stays at `/data/media/music`.

## 1. Create empty library siblings

On the Unraid host (or any process that can write `/data`):

```bash
# From the Librarian kit / checkout
./scripts/create-library-roots.sh /data/media
# or dry-run via Python:
DATA_DIR=/config .venv/bin/python -m librarian.migrate_library \
  --media-root /data/media --create-roots
# add --apply to actually mkdir
```

`music_root` is **not** created or moved.

**Archive Historical:** flat PDFs — park under `library/magazines/Archive Historical/`
or `library/books/_archive/Archive Historical/` after books verify. Do not auto-flatten.

## 2. Dry-run books blend (always first)

```bash
# Inside container or venv with /data mounted
python -m librarian.migrate_library \
  --media-root /data/media \
  --migrate-books

# Sample over a slow laptop mount (SMB):
python -m librarian.migrate_library \
  --media-root /Volumes/data/media \
  --migrate-books --limit 100

# Include the sibling newlib Calibre tree (collisions → report, never overwrite)
python -m librarian.migrate_library \
  --media-root /data/media \
  --migrate-books \
  --include-newlib
```

Run the full dry-run **on Unraid** (local disk), not over `/Volumes/data`, before `--apply`.
Folder-name planning skips OPF reads when the destination is empty (ISBN checks only on collision).

What it does:

- Finds `LonesomeLib/Calibre Library` (or a Calibre root with `metadata.db`)
- Strips Calibre `(id)` from title folders
- Plans `{Author}/{Title}/` under `library/books`
- Prefers **EPUB** as canonical; keeps AZW3/MOBI/PDF as sidecars in the plan
- Skips Calibre junk (`.config`, `.calnotes`, `ssl`, …)
- **Collision** when the destination already has books (ISBN match → skip; mismatch → collision)
- Default dry-run; `--apply` copies (not moves). `--move` only after a verified copy cutover

Review the collision list before any `--apply`.

## 3. Apply copy (still recoverable)

Pause Watch / new organizes if active. Then:

```bash
python -m librarian.migrate_library \
  --media-root /data/media \
  --create-roots --migrate-books \
  --apply
# optional later: --include-newlib --apply  (expect many collisions if overlap)
```

Sources under `/data/media/books/LonesomeLib` remain until you archive them.

## 4. Rebind Settings + Scan

In Librarian Settings (or edit `/config/settings.json` — no secrets in this doc):

| Field | Value |
|-------|--------|
| `books_root` | `/data/media/library/books` |
| `magazines_root` | `/data/media/library/magazines` |
| `comics_root` | `/data/media/library/comics` |
| `audiobooks_root` | `/data/media/library/audiobooks` |
| `incoming_music_root` | `/data/media/library/incoming-music` |
| `music_root` | `/data/media/music` (unchanged) |

Restart the container if needed, then **Scan the shelves** (catalog only — does not move files).

## 5. Verify

- Hall rails: Books populate; Magazines/Comics/Audiobooks empty but no root errors
- Open a known EPUB work → Reading Room
- Review bag: migration collisions (if any) are honest slips — do not silent-overwrite
- Spot-check an AZW3+EPUB title: EPUB is the readable file

## 6. Archive old tree (after verify)

```bash
# On Unraid — rename, do not rm
mv /data/media/books /data/media/books_migrated_YYYYMMDD
# Keep Calibre junk out of library/; leave music alone
```

Optional: move `incoming-music` → `library/incoming-music` with a similar copy/verify,
then point Settings at the new path.

## Audiobooks / Plex / Plexamp

Plex has **no** dedicated Audiobooks library type. Household pattern:

1. Create a **Music** library in Plex named e.g. “Audiobooks”
2. Folder = `audiobooks_root` (`/data/media/library/audiobooks`)
3. Enable store track progress / long-form controls; in Plexamp use speed + skip
4. Layout: `{Author}/{Title}/` (Author ≈ album artist, Title ≈ album)
5. **Never** put audiobooks in `/data/media/music` (Plexamp music library)

See [HELP.md](../HELP.md) § Music and audiobooks.

## Fail-closed rules

- No silent overwrite on collision
- No delete of the old `books/` tree in the migrate tool
- Dry-run unless `--apply`
- Do not invent ISBNs; OPF ISBN is used only for skip/collision hints
