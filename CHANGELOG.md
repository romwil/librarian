# Changelog

## [Unreleased]

### Added

- **Kind shelf totals.** Stacks, Hall kind rails, and Search kind chips show household counts for the active media type (e.g. “1,234 books on the shelves”, “56 audiobooks”) from browse/hall totals — no extra clutter.

## [0.4.2] — 2026-09-19

### Added

- **Live progress for Add to the shelves.** Pointing at a dump parent (e.g. `/data/usenet/complete/books`) expands each child, runs in the background, and polls `GET /api/ingest/status` with phase, current path, and shelved / needs you / skipped counts under the Add button.

### Fixed

- **Enrich abort on locked shelf folders.** Writing `cover.jpg` into a root-owned library folder (`PermissionError` / Errno 13) no longer fails the whole enrich batch. Cover writes fall soft to `/config/covers/{id}/` when the shelf is not writable, progress shows household copy instead of raw Errno 13, and the trickle continues.
- **Ingest Internal Server Error on comic convert.** `BadZipFile` during loose-image → CBZ no longer 500s the Add request; convert fails soft and identify continues.
- **SAB complete organize left dumps behind.** Confident shelve from SAB now moves (same as manual ingest / watch); Review and collisions still keep the staging folder.
- **Stale “Adding…” after a rebuild.** A `running` progress blob with no live worker clears to a household “lamp was restarted” message.

## [0.4.1] — 2026-09-19

### Fixed

- **Bestsellers “LLM HTTP 400” on Gemini.** An OpenAI-shaped `LLM_API_KEY` (or leftover active key) is no longer stamped onto the Gemini profile — Google returns HTTP 400 “API key not valid” for `sk-…` keys. Provider error bodies now surface as household copy (bad key / bad model) instead of bare `LLM HTTP 400`.
- **`docker-run.sh` forwards Gemini/Anthropic/OpenAI env aliases** (`GEMINI_API_KEY`, `GOOGLE_API_KEY`, `LLM_PROVIDER`, etc.) so kit `.env` keys actually reach the container.

## [0.4.0] — 2026-09-19

### Highlights

- **Audiobook scene → Audnexus → M4B shelf.** Dump names scrub to author/title/narrator/series/ASIN; Audnexus scores matches into organize or Review; multipart audio remuxes to a single tagged `{Title}.m4b` under the series-aware shelf layout.
- **Comics scene → ComicVine → clean CBZ.** Scene scrub + volume-year disambiguation; ComicInfo.xml in the archive; publisher/series shelf paths with fail-soft Komga scan + Open in Komga.
- **Audiobookshelf scan + listen progress.** After shelving, Librarian asks ABS to scan; Listen pulls/pushes progress for matched titles without wiping a better local bookmark.

### Added

- `audiobook_normalize` / `audnexus` / `m4b` (ffmpeg in the image) + golden scene fixtures.
- `comic_normalize` / deepened ComicVine match + `komga` federation client and Settings fields.
- ABS library scan notify + bidirectional listen progress sync on work/Listen APIs.
- Review / peek / Settings polish for Audnexus candidates, Komga links, and ABS progress.

### Changed

- Media contract: audiobooks `{Author}/{Series}/{Index} - {Title} ({Year})/` with `{Title}.m4b`; comics `{Publisher}/{Series} ({VolumeYear})/` (legacy scan still accepted).
- Organize dest layouts and identify/enrich paths for spoken-word and sequential-art authority.

### Fixed

- Enrich progress reporting stays honest across longer Audnexus/ComicVine match runs.

## [0.3.1] — 2026-09-19

### Highlights

- **Edit metadata and Fix match on title pages.** Owners and ops can correct wrong enrich blurbs (like Open Library’s Springsteen+Morpurgo *Born to Run* corruption), pick an alternate catalog match, or undo enrich.
- **Multi-provider BYO LLM.** Settings supports OpenAI, Anthropic, and Gemini profiles; Find uses LLM best-match with remembered alternates, disclosures, and clearer 429 handling.
- **Bestsellers and chase polish.** Cover cards and request-missing chase/auto-request flows; Enrich/Review actions show busy feedback.

### Added

- Catalog Edit / Fix match / Undo enrich on work pages (`PATCH /api/works/{id}/metadata`, match-candidates, apply-match, clear-enrich).
- Open Library title+author scoring that rejects foreign co-author corruptions and prefers memoir/autobiography when the author matches.
- Native LLM provider catalog (`librarian/llm_providers.py`) + Settings panel.
- Search rank memory + trace disclosures; Bestsellers UI cover improvements; shared action busy labels.

### Fixed

- Enrich no longer blindly takes Open Library’s first search hit when the author list includes unrelated co-authors.
- Pytest isolates maintainer `.env` LLM keys so enrich/review tests stay offline.

## [0.3.0] — 2026-09-18

### Highlights

- **Listen to audiobooks in the Reading Room.** Phase 2b ships an in-app player (chapters, progress) with deep-links when Plex/ABS is configured — peeks and work pages say Listen, not a raw Read.
- **Bestsellers from your BYO LLM.** Curated list presets match the household shelves, then chase missing titles as books and audiobooks (confirm before SAB). Optional NYT Books API remains a soft-deprecated fallback.
- **Stuck unpacks can recover.** Archive-only / empty SAB dumps go through organize (par2+unar) and land a Review slip instead of failing with no work — so audiobook RAR recoveries stay visible in Queue/Review.
- **Finish-set ETA and smart re-grab deepen.** Size-aware approximate ETAs when samples are thin; re-grab ranks by series/base, part markers, size, and host with clearer diffs.
- **Community UX polish.** Clear Read CTAs, peeks that open the full work page, and book→audiobook companion Listen when the matching title is already shelved.

### Added

- In-app audiobook Listen (`librarian/listen.py`, `AudiobookPlayer`) + chapter API; book→audiobook companion CTAs.
- LLM curated lists (`librarian/lists.py`) + chase (book and audiobook); Bestsellers panel on Find; optional NYT Books client as fallback.
- `NYT_BOOKS_API_KEY` env wiring in `docker-run.sh` / Automat playbook.

### Changed

- Finish-set ETA returns approximate size-scaled minutes when median samples are scarce; labels use `≈` vs `~`.
- Review re-grab candidate ranking and human diffs (same series, part markers, % size, host).
- Phase 2b Listen marked done on the living roadmap.

### Fixed

- `poll_job` no longer marks `unpack_stuck` failed with no `work_id` — organize/Review recovery stays available for audiobook archives.

## [0.2.3] — 2026-09-17

### Fixed

- **Discover/Find cover titles no longer ellipsis-truncate.** Cloth card primary titles wrap fully (cards grow with the title); cover-art frames stay fixed. Same principle as Smart Map Browse — titles you can actually read.

## [0.2.2] — 2026-09-17

### Highlights

- **What’s New greets you on first visit.** Missing `last_seen` (new browser / cleared storage) opens the modal for the current version; dismiss sets last-seen. Upgrades still greet when runtime is newer.

### Fixed

- Stop silently seeding `librarian.last_seen_version` on first visit so What’s New never appears.

## [0.2.1] — 2026-09-17

### Highlights

- **Cover cards lead with the real title.** Publisher-heavy NZB names (TOKYOPOP, IMAGE COMICS, and friends) no longer crowd out the series on Discover and Find — primary labels show the distinctive title; the raw dump stays on hover/peek.

### Fixed

- Demote publisher prefixes on Discover/Find cover cards (`displayTitle`) so cloth labels stay readable.

## [0.2.0] — 2026-09-17

### Highlights

- **What’s New greets you after an upgrade.** Runtime version vs last-seen opens a short modal; Settings keeps the full release-notes history (generated from this CHANGELOG).
- **Multipart sets know their holes.** Catalog `part_set` tracks owned vs total; Find groups Part N/M / CDn sets, chases missing NZBs when listed, and stays honest when gaps are unlisted.
- **Tonight’s shelf and quiet delight.** Continue + a quick gap + a Discover surprise; cover stories, series ribbons, celebrations, Plexamp handoff (music only), whispers, quiet hours for Review, finish-set ETA, and ambient prefs.
- **Advanced Search and Find fields suggest while you type.** Author, title, series, artist, album, and year pull from the household catalog first (optional on-disk cache under `/config/suggest-cache`). Freeform typing still works; owners can refresh the seed from Settings.
- **Volumes already on disk can be filed.** Owners and ops Add a `/data` folder or file — confident identify moves and renames; anything unexpected waits in Review. A Watch folder does the same for drops. Scan still only catalogs; it does not move files.
- **Find asks the indexer the way Newznab expects.** Kind chips swap the form: books/magazines send title, author, and ISBN; comics search series and issue in `7030`; music uses artist and album (never a book ISBN); audiobooks stay on `3030`. Request stores what you sought, what you picked, and the metadata the indexer actually returned — not SABnzbd’s dump name.
- **The downloader tells the truth.** Completed SAB jobs use the real complete folder (mapped through SAB complete root), failed unpacks say Failed with a reason, and the catalog title stays the title you asked for — not the Usenet dump name.
- **Thin books get a real catalog.** Owner Enrich pulls description, series, year, and cover from Hardcover (token in Settings) then Open Library. The LLM still never invents an ISBN.
- **Find can peruse what’s trending.** Empty Find is Discover: real indexer category feeds from capabilities (not a second Hall, not auto-SAB). Show categories (off by default) adds Movies/TV/XXX — those go to the downloader / *arr, never The Hall.
- **Hall Gaps know the rest of the run.** Missing series volumes, comic issues, and album tracks come from Hardcover / Open Library, Comic Vine, and MusicBrainz. Clicking a hole opens Find — SAB never fires from a shelf browse.
- **Goodreads shelves land on Favorites.** Upload a CSV export; rows match by ISBN. Missing books become thin works that need Find.
- **The Hall remembers where you left off.** Opening a volume plants a Continue bookmark; Finished clears it. Covers are real `cover.jpg` when we can fetch them.
- **Identify can convert and ask the house LLM.** CBR→CBZ via `unar`, PDF-only books via `ebook-convert` when present, BYO LLM never invents an ISBN. SAB jobs poll in the running process, not only when you open Queue.
- **Automat-ready kit.** Maintainer playbook at `docs/ops/AUTOMAT.md`, `/config` + `/data` mounts that survive recreate, and a Hub `rollout.sh` stub for later. LAN truth is `http://10.10.1.202:8793` — not a public VIP.
- **Safe behind your reverse proxy.** `LIBRARIAN_TRUST_PROXY_HEADERS` is off unless you opt in. Spoofed `X-Forwarded-*` cannot mark cookies Secure, cannot rotate the login throttle, and cannot pretend the hop is HTTPS. Login and invite routes are rate-limited.

### Added

- What’s New upgrade modal (`WhatsNewGate`) + Settings release-notes panel; `scripts/generate-release-notes.sh` → `frontend/public/release-notes.json`.
- Catalog multipart `part_set` (owned / total / style / base) with Hall/Work “Find missing parts”, Review regrab hints, and Find PartSet chase (honest when NZBs are unlisted).
- Part E delight: Tonight’s shelf, cover stories, series ribbons, celebration banners, Plexamp toast (music Promote), whispers, quiet hours, finish-set ETA, ambient prefs, finish-set labels.
- Typeahead suggestions for Search/Find advanced fields (`GET /api/suggest`) plus owner **Refresh suggestions from shelves** (`POST /api/settings/suggest-cache`). Catalog-first; optional bounded MusicBrainz seed.
- Owner/op **Add to the shelves** (`GET /api/fs`, `POST /api/ingest`) and **Watch folder** (`watch_root` / `watch_enabled`). Identify/organize when confident; Review when not. Scan does not move files.
- Kind-morphing Find fields + NZBFinder v2 `books` ISBN param; job payload `sought` / `selected` / `retrieved`.
- Honest SAB complete-path remap, fail/unpack reasons, and Find title/kind kept through identify.
- Owner **Enrich the shelves** / work-page Enrich: Hardcover GraphQL then Open Library; covers reuse indexer URL / Open Library ISBN / CBZ page 1.
- Catalog gaps: Hardcover then Open Library series volumes; Comic Vine issue lists (`comicvine_api_key`, masked); MusicBrainz track lists (User-Agent + polite rate limit). Magazines stay local `YYYY-MM`. Hall Gaps open Find; confirm stays off the shelf.
- Extra Newznab v2 hosts in Settings; Find merges/dedupes by guid and keeps NZBFinder hits if another host 502s.
- Find **Discover** (`GET /api/discover`): capabilities category feeds, latest-in-cat via v2 search or `/rss?t=`. Show categories (owner; `show_extra_categories`) can include Movies/TV/XXX. Movie/TV Request queues SAB then tells Radarr/Sonarr to expect; XXX is SAB default folder only.
- RSS subscriptions (owner/op on Find or Settings): poll in-process; new items become **Asked** jobs for confirm — not silent SAB.
- Optional Audiobookshelf URL + token (masked; env `AUDIOBOOKSHELF_API_TOKEN`). Match by ISBN then author+title; quiet **On the player** chip. Does not replace `audiobook_target` default Plex.
- Owner **Import Goodreads CSV** onto Favorites, matched by ISBN-10 or ISBN-13. No Goodreads OAuth.
- `hardcover_api_token` in settings.json (masked on GET; env `HARDCOVER_API_TOKEN` seeds first boot).
- `comicvine_api_key` in settings.json (masked on GET; env `COMICVINE_API_KEY` seeds first boot). Hardcover does not cover issue-numbered comics.
- `docs/ops/AUTOMAT.md` runbook (kit path, first-boot env, rsync, deploy).
- Proxy-header fail-closed (`librarian/proxy.py`) + per-IP rate limits on login / invite validate / redeem.
- `PUID`/`PGID` 99/100 on Unraid, `extra_hosts` for `downloader.sl` when the host can resolve it, `rollout.sh` Hub pull stub.
- Continue rail + per-user progress; cover fetch (indexer / Open Library ISBN / CBZ page 1); CBR→CBZ (`unar` in the image); on-demand `ebook-convert` cache under `/config/conversions`.
- BYO LLM identify (structured JSON; invented ISBN dropped); background SAB poller; `indexers` table + owner **Ping NZBFinder**.
- Local audiobook part holes and music track-number holes.

## [0.1.0] — 2026-09-14

Initial household reading-room kit on Automat.

### Highlights

- **The Hall, not a grabber.** FastAPI + Vite Reading Room on port **8793**, with owner / op / reader roles and invite-only join.
- **Stacks that know their kinds.** Books (EPUB), magazines, comics (CBZ + ComicInfo), audiobooks (Plex target by default), incoming music with Promote.
- **Honest gaps.** Local magazine `YYYY-MM` holes and comic issue-number holes — confirm before SAB.
- **Automat kit.** `/config` + `/data`, `docker-run.sh` on-host build, settings.json wins, no collision with 8788 / 8790 / 8791 / 8792.

### Added

- Python 3.12 package `librarian/` with SQLite WAL catalog, HMAC invites, NZBFinder v2 client, SABnzbd status machine, identify/organize, FTS search.
- Docs: README, DOCKER, TESTING, SECURITY, HELP, and the 2026-09-14 design spec.
