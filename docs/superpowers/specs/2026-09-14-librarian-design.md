# Librarian design spec (2026-09-14)

North-star source of truth distilled from the approved Automat plan. Implementation tracks this file.

## North star

A household **library for readers**, not an admin grabber and not Calibre-in-a-browser. The **Library** is the product: scan what’s on `/data`, enrich it, read it, then grow catalog gaps. **Find** is the quiet door after a local miss — NZBFinder, Request, SABnzbd — not a second home screen.

People peruse shelves, see What’s New, open a book or issue, read its metadata, download it, or add it to Favorites.

**First-tier reading:** Books, **Magazines**, **Comics** — same rank. Books are EPUB; magazines are issue folders; comics are **CBZ** (Newznab `7030`). Audiobooks and music are first-tier *listening*. Music may Promote to Plexamp. Audiobooks do not.

Calibre’s *features* are an advisory roadmap. Visual bar: Projectionist Explore + title-detail, applied to books/magazines/comics/music, with a night reading-room soul (cloth, gilt, paper dust, warm lamp).

## Locked contracts

- Retriever: SABnzbd at `http://downloader.sl`. Find jobs only: poll queue then history; store `nzo_id`; on Completed remap `storage` via `complete_root` and identify/organize. SAB’s Usenet filename is not the library title.
- `/data` ← host `/mnt/user/data`. Per-media roots are Settings paths under `/data`.
- First indexer: **NZBFinder** Newznab **v2 JSON**. Token in env/settings only. User-Agent required.
- Music: organize into `incoming_music_root`, **Promote** → `music_root` (`/data/media/music`) for **Plexamp only**. Promote is that move, not a job status.
- Audiobooks: first-class kind. Publish target `audiobook_target` default **`plex`**. Never `music_root`.
- Comics: Newznab **`7030`**. Canonical file **CBZ**. Layout `{Publisher}/{Series} ({VolumeYear})/` plus embedded `ComicInfo.xml` + cover. Legacy `{Series}/{Issue}/` still scanned.
- Gaps: owned vs expected, honest missing cards. **Confirm lives on Find** so SAB never fires from a shelf browse. Fail closed.
- Auto-organize only when identify is confident. Unexpected → **Review**.
- BYO LLM (same settings shape as Smart Map / Projectionist) may assist later. LLM never invents an ISBN.
- Port **8793**. Never 8788 / 8790 / 8791 / 8792.
- Auth on from first boot. Roles **owner / op / reader**. Owner seeded from Docker env. Join is invite-only. No Plex PIN, no OIDC.

## Media layouts

| Kind | Setting | Default | Layout |
| --- | --- | --- | --- |
| book | `books_root` | `/data/media/library/books` | `{Author}/{Title}/{Title}.epub` + opf/cover |
| magazine | `magazines_root` | `/data/media/library/magazines` | `{Title}/{Year-or-Volume}/` |
| comic | `comics_root` | `/data/media/library/comics` | `{Publisher}/{Series} ({VolumeYear})/{Series} v{VolumeYear} #{Issue} ({Year}).cbz` + embedded ComicInfo |
| audiobook | `audiobooks_root` | `/data/media/library/audiobooks` | `{Author}/{Title}/` (m4b preferred) |
| music staging | `incoming_music_root` | `/data/media/library/incoming-music` | `{Artist}/{Album}/` — original filename, or `{NN} - {Title}{ext}` only with a trustworthy track tag |
| music Plexamp | `music_root` | `/data/media/music` | same after Promote |

Shared Automat `/data/media` roots and the music filename rule: [automat-media-contract.md](../../automat-media-contract.md). Do not extract a shared Python package.

### Audiobook targets

`audiobook_target` = `plex` | `audiobookshelf` | `librarian_only` (default **`plex`**). Plexamp is not a target.

## Indexers and kinds

Newznab cat → kind: **`7030` comic**; `7010` magazine; other `70xx` book; **`3030` audiobook**; `3010`/`3040`/`3999` music; `2000`/`5000`/`6000` refuse.

Indexer search: books form for `70xx` except comics; comics use `search` + `cat=7030`. TV/movies/XXX stay off Hall identify. RSS subscriptions (Librarian kinds only) shipped as Find extras. Extra categories may appear on Find when `show_extra_categories` is on.

## Identify / organize / Review

Order: indexer fields → sidecar/OPF/tags → deterministic Usenet parse → BYO LLM when weak.

Confidence floor: ISBN + author + title (books) or series + issue (comics/mags) → auto-organize. `unknown`, missing series/issue, extra/unexpected files, convert fail, collision → Review.

Review reasons: `unknown_identity`, `low_confidence`, `unexpected_kind`, `no_payload`, `extra_files`, `convert_failed`, `collision`.

Canonical files: books → EPUB; comics → CBZ; magazines → EPUB or PDF as arrived. Convert on demand (`/config/conversions/{work_id}/`). Keep `original.*` siblings when converting.

## Catalog

`indexers` (settings-backed v1), `works`, `files`, `jobs`, `shelves`, `shelf_items`.

- `works.kind` includes `comic` and `audiobook`
- `works.review_state` — `none` | `needs_review` | `resolved`
- `works.music_state` — `incoming` | `promoted`
- Favorites = seeded personal shelf named **Favorites**
- FTS5 on author, title, genre, description — **Search is owned media only**
- Scan: walk Settings roots (`books_root`, `magazines_root`, `comics_root`, `audiobooks_root`, `incoming_music_root`, `music_root`). Upsert `works` + `files` from layout + OPF/ComicInfo/tags. Idempotent; do not move files; collisions → Review. Owner “Scan the shelves” on Settings.

## Household job words (Find / Queue only)

Three machines share English; the UI does not. **Peek and Find chips use five words.** Keep SAB’s raw string on the Queue card’s muted line for ops (`Verifying · nzo_…`). Library pages never show job status except **On the way** if this work is still inbound.

| Word | Meaning |
| --- | --- |
| **Asked** | Reader slip; no SAB yet |
| **On the way** | Queued, downloading, extracting, or identifying |
| **Arrived** | Organized; the work exists |
| **Needs you** | Review |
| **Failed** | SAB or identify failed |

**Finished** is reading progress, not a job terminal. **Promote** moves incoming music to `music_root`. **organized** is a job terminal, not a shelf label.

## Gaps

Hall **Gaps** rail stays Library (honest missing cards). **Confirm** lives on Find.

| Kind | Expected set | Local holes | Remote catalogs (shipped) |
| --- | --- | --- | --- |
| magazine | issue calendar | `YYYY-MM` holes between owned min/max | — |
| comic | issue list | integer holes between owned min/max | Comic Vine (or Hardcover comics if the token covers it) |
| book / audiobook | series / parts | local completeness where we have it | Open Library + Hardcover series |
| music | discography / tracks | track-number holes | MusicBrainz discography |

## UX: the Reading Room

Projectionist *structures* (hero, peek drawer, cover rails) with a different soul. Visual handoff: [docs/ux/reading-room.md](../../ux/reading-room.md).

- **Foyer:** dust in a lamp shaft, spine silhouettes, unfinished page-turn. `/login` and `/join?token=` share it. Invite role is a quiet seal. `prefers-reduced-motion` = still.
- **The Hall:** land here. Hero search (search the stacks, not “then the world”). Rails: Continue, What’s New, Favorites, by area, Gaps.
- **Search (`/search?q=`):** local shelves only (FTS + kind chips). Peek, Open, Favorite. No Beyond rail, no Request, no SAB chips. `/search` never auto-fires Beyond.
- **Find (not a nav tab):** After local results — including zero hits — **Find beyond the shelves** opens `/find?q=…&kind=…` (plus kind-appropriate fields). Find prepopulates that query and **runs Beyond immediately**. Find owns NZBFinder, Request, living job chips (five words), Gaps **confirm**, Queue, Review bag. Empty Find (`/find` without a query) is **Discover** — trending indexer category feeds, not a second Hall, not auto-SAB. Hall Gaps **Find this hole** deep-links the same way.
- **Peek:** centered modal, Hall scroll stays put, Esc/scrim returns focus. ⌘-click keeps peek and opens a tab. Work/peek: Incoming / Review chips; media note when there is no file; Open/Download only when files exist; hide **Finished** on music.
- Chrome: lamp mark, **Hall / Search / Favorites / You**. Find is not a top-level tab. Queue and Review stay op links (or Find sub-pages). Settings, People, invites stay owner chrome.

## Household auth

Copy the secure parts of Projectionist invites; skip Plex PIN / OIDC in v1 and keep them **later / out**. Hardcover is a settings token (never committed), not a login provider.

See [SECURITY.md](../../SECURITY.md). One owner. Last owner cannot be demoted. Public handshake is exhaustive.

## OSS stack

- Read: **foliate-js** for EPUB; CBZ via `comic-book.js`. Open on the work page when `can_download` and kind is book/magazine/comic. Not Calibre-web. Shipped.
- Listen: HTML5 audio + Media Session; mutagen chapters via `GET /api/works/{id}/chapters`. Dest remains Plex/ABS. Phase 2b shipped (Listening room + Continue bookmarks).
- Metadata: isbnlib, Open Library, **Hardcover** (live token in settings), MusicBrainz, ebooklib, calibre `ebook-convert` when present. **Goodreads CSV / shelf export** import onto Favorites, matched by ISBN — not live Goodreads OAuth (the public API is effectively dead).
- Do not vendor Calibre-web, Kavita, or Audiobookshelf as the product.

## Phased roadmap

- **v1 (this repo):** kit + auth + NZBFinder + SAB + identify/organize + Review + local gaps + Reading Room SPA + Automat `docker-run.sh`.
- **Library first (landed):** scan `/data` roots; enrich (Open Library + Hardcover; Goodreads CSV); in-browser reader (foliate-js EPUB + CBZ); catalog gaps (Hardcover/OL, Comic Vine, MusicBrainz); Find extras (RSS, extra Newznab hosts, Audiobookshelf match); Search = local only; Find = post-search Beyond + Discover; five household job words.
- **Phase 2b (landed):** in-app audiobook player + deep-link to Plex/ABS
- **Later / out:** OIDC / Plex sign-in. Hub publish. Shared Python package only if reuse is proven. Shared grab/traffic service only if two apps emit the same envelope. NZBGet, Calibre-web skin.
- **Out of v1:** Hub publish, NZBGet, Plex/OIDC login, Movies/TV/XXX as Hall kinds, Goodreads live OAuth, genre enrichment if slow. (Scan, Hardcover/Goodreads CSV, and the built-in reader shipped in Library first.)

## Automat contract

| Container | Host |
| --- | --- |
| `/config` | `/mnt/user/appdata/librarian/config` |
| `/data` | `/mnt/user/data` |
| `:8793` | host 8793 |
