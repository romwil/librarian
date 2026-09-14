# Librarian design spec (2026-09-14)

North-star source of truth distilled from the approved Automat plan. Implementation tracks this file.

## North star

A household **library for readers**, not an admin grabber and not Calibre-in-a-browser. People peruse shelves, see What’s New, open a book or issue, read its metadata, download it, or add it to Favorites.

**First-tier reading:** Books, **Magazines**, **Comics** — same rank. Books are EPUB; magazines are issue folders; comics are **CBZ** (Newznab `7030`). Audiobooks and music are first-tier *listening*. Music may Promote to Plexamp. Audiobooks do not.

Calibre’s *features* are an advisory roadmap. Visual bar: Projectionist Explore + title-detail, applied to books/magazines/comics/music, with a night reading-room soul (cloth, gilt, paper dust, warm lamp).

## Locked contracts

- Retriever: SABnzbd at `http://downloader.sl`.
- `/data` ← host `/mnt/user/data`. Per-media roots are Settings paths under `/data`.
- First indexer: **NZBFinder** Newznab **v2 JSON**. Token in env/settings only. User-Agent required.
- Music: organize into `incoming_music_root`, **Promote** → `music_root` (`/data/media/music`) for **Plexamp only**.
- Audiobooks: first-class kind. Publish target `audiobook_target` default **`plex`**. Never `music_root`.
- Comics: Newznab **`7030`**. Canonical file **CBZ**. Layout `{Series}/{Issue-or-Year}/` plus `ComicInfo.xml` + cover.
- Gaps: owned vs expected, honest missing cards, **confirm before** SAB. Fail closed.
- Auto-organize only when identify is confident. Unexpected → **Review**.
- BYO LLM (same settings shape as Smart Map / Projectionist) may assist later. LLM never invents an ISBN.
- Port **8793**. Never 8788 / 8790 / 8791 / 8792.
- Auth on from first boot. Roles **owner / op / reader**. Owner seeded from Docker env. Join is invite-only.

## Media layouts

| Kind | Setting | Default | Layout |
| --- | --- | --- | --- |
| book | `books_root` | `/data/media/books` | `{Author}/{Title}/{Title}.epub` + opf/cover |
| magazine | `magazines_root` | `/data/media/magazines` | `{Title}/{Year-or-Volume}/` |
| comic | `comics_root` | `/data/media/comics` | `{Series}/{Issue-or-Year}/{Series} #{Issue}.cbz` + ComicInfo + cover |
| audiobook | `audiobooks_root` | `/data/media/audiobooks` | `{Author}/{Title}/` (m4b preferred) |
| music staging | `incoming_music_root` | `/data/media/incoming-music` | `{Artist}/{Album}/{Title}.{ext}` |
| music Plexamp | `music_root` | `/data/media/music` | same after Promote |

### Audiobook targets

`audiobook_target` = `plex` | `audiobookshelf` | `librarian_only` (default **`plex`**). Plexamp is not a target.

## Indexers and kinds

Newznab cat → kind: **`7030` comic**; `7010` magazine; other `70xx` book; **`3030` audiobook**; `3010`/`3040`/`3999` music; `2000`/`5000`/`6000` refuse.

Search: books form for `70xx` except comics; comics use `search` + `cat=7030`. TV/movies/XXX refused. RSS is phase 2.

## Identify / organize / Review

Order: indexer fields → sidecar/OPF/tags → deterministic Usenet parse → BYO LLM when weak.

Confidence floor: ISBN + author + title (books) or series + issue (comics/mags) → auto-organize. `unknown`, missing series/issue, extra/unexpected files, convert fail, collision → Review.

Review reasons: `unknown_identity`, `low_confidence`, `unexpected_kind`, `no_payload`, `extra_files`, `convert_failed`, `collision`.

Canonical files: books → EPUB; comics → CBZ; magazines → EPUB or PDF as arrived. Convert on demand later (`/config/conversions/{work_id}/`). Keep `original.*` siblings when converting.

## Catalog

`indexers` (settings-backed v1), `works`, `files`, `jobs`, `shelves`, `shelf_items`.

- `works.kind` includes `comic` and `audiobook`
- `works.review_state` — `none` | `needs_review` | `resolved`
- `works.music_state` — `incoming` | `promoted`
- Favorites = seeded personal shelf named **Favorites**
- FTS5 on author, title, genre, description

## Gaps

| Kind | Expected set | Local v1 |
| --- | --- | --- |
| magazine | issue calendar | `YYYY-MM` holes between owned min/max |
| comic | issue list | integer holes between owned min/max |
| book / audiobook / music | series / parts / discography | later (Open Library, Audnexus, MusicBrainz) |

UI: Gaps rail on The Hall (op/owner). Confirm chip queues NZBFinder (`cat=7030` for comics).

## UX: the Reading Room

Projectionist *structures* (hero, peek drawer, cover rails) with a different soul. Visual handoff: [docs/ux/reading-room.md](../../ux/reading-room.md).

- **Foyer:** dust in a lamp shaft, spine silhouettes, unfinished page-turn. `/login` and `/join?token=` share it. Invite role is a quiet seal. `prefers-reduced-motion` = still.
- **The Hall:** land here. Hero search. Rails: Continue, What’s New, Favorites, by area, Gaps.
- **One search:** local FTS first, then Beyond the shelves. Peek then full page `/works/:id`. Reader Request is an asked slip.
- **Peek:** centered modal, Hall scroll stays put, Esc/scrim returns focus. ⌘-click keeps peek and opens a tab.
- Chrome: lamp mark, Hall, Search; Review is an op/owner bag. Mobile bottom bar Hall / Search / Favorites / You.

## Household auth

Copy the secure parts of Projectionist invites; skip Plex PIN / OIDC in v1.

See [SECURITY.md](../../SECURITY.md). One owner. Last owner cannot be demoted. Public handshake is exhaustive.

## OSS stack (when those phases start)

- Read: **foliate-js** + optional StPageFlip on already-paginated spreads. Not v1.
- Listen: HTML5 audio + Media Session; **music-metadata** / mutagen for chapters. Dest remains Plex/ABS.
- Metadata: isbnlib, Open Library, MusicBrainz, ebooklib, calibre `ebook-convert` later.
- Do not vendor Calibre-web, Kavita, or Audiobookshelf as the product.

## Phased roadmap

- **v1 (this repo):** kit + auth + NZBFinder + SAB + identify/organize + Review + local gaps + Reading Room SPA + Automat `docker-run.sh`
- **Phase 2:** external gap catalogs, in-browser reader (foliate-js including CBZ), covers, RSS, more Newznab hosts, ABS API match
- **Phase 2b:** in-app audiobook player or deep-link to Plex/ABS
- **Later:** OIDC / Plex sign-in, Goodreads/Hardcover
- **Out of v1:** Goodreads, built-in reader, Hub publish, NZBGet, Plex/OIDC login, genre enrichment if slow

## Automat contract

| Container | Host |
| --- | --- |
| `/config` | `/mnt/user/appdata/librarian/config` |
| `/data` | `/mnt/user/data` |
| `:8793` | host 8793 |
