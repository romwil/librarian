# Librarian roadmap

Living product/build checklist. Flip boxes when a slice ships. Append the story to [build-progress.md](build-progress.md). Design north star: [2026-09-14 librarian design](superpowers/specs/2026-09-14-librarian-design.md).

## Build status

| | |
| --- | --- |
| **Date** | 2026-09-25 |
| **Branch** | `main` |
| **Last SHA** | sprint **2.1** ships **0.4.20** on this commit |
| **Green** | pytest coverage floor **70%**; frontend `npm test`; Playwright e2e on **8794**. LAN truth `http://10.10.1.202:8793`. |
| **Next** | Sprint **3.1** `mail-transport` → **0.4.21**. Automat path remains host `./docker-run.sh` (Hub deferred). |

## Living library major build

Protocol: [ops/MAJOR_BUILDS.md](ops/MAJOR_BUILDS.md). Phase 1 engine-room sprints:

| Sprint | Feature | Version | Status |
| --- | --- | --- | --- |
| 1.1 | `review-get-readonly` | 0.4.17 | shipped |
| 1.2 | `unified-progress` | 0.4.18 | shipped |
| 1.3 | `dead-weight-docs-truth` | 0.4.19 | shipped |
| 2.1 | `web-routers-shelf-health` | 0.4.20 | this release |
| 3.1 | `mail-transport` | 0.4.21 | next |

## North star

A household **library for readers**. The Library is the product: scan `/data`, enrich, read, then grow catalog gaps. Search is local shelves only. Find is not a nav tab — it is the post-search door (**Find beyond the shelves**) plus **Discover** when Find is empty. Books, magazines, and comics (CBZ, Newznab `7030`) share first-tier rank. Audiobooks and music are first-tier listening — music Promotes to Plexamp; audiobooks never do. Extra categories (movies / TV / XXX) are optional Find plumbing to SAB / *arr (`show_extra_categories`, default **off**). They never become Hall works.

## Locked decisions

- Retriever: SABnzbd at `http://downloader.sl`.
- `/data` ← host `/mnt/user/data`. Per-media roots are Settings paths under `/data`.
- First indexer: NZBFinder Newznab **v2 JSON**. Token in env/settings only. User-Agent required. Never commit tokens.
- Music: `incoming_music_root` → **Promote** → `music_root` (`/data/media/music`) for Plexamp only.
- Audiobooks: `audiobook_target` default **`plex`**. Never `music_root`.
- Comics: `7030`, canonical **CBZ**, `{Series}/{Issue-or-Year}/` + ComicInfo + cover.
- Gaps: owned vs expected, honest missing cards. **Confirm lives on Find** so SAB never fires from a shelf browse. Fail closed.
- Search = local FTS only (Hall hero + `/search`). Peek / Open / Favorite. No Beyond on Search.
- Find = post-search **Find beyond the shelves** → `/find` with `q`/kind (and kind-appropriate fields) prefilled, then Beyond. Find is not a nav tab.
- Empty Find is **Discover**: trending indexer category feeds from capabilities (v2 search or `/rss?t=`). Not a second Hall. Not auto-SAB. No HTML scrape.
- `show_extra_categories` default **off**. When on, Discover/Find may offer Movies / TV / XXX if the indexer lists them. Never Hall kinds.
- Household job words (Find / Queue): **Asked / On the way / Arrived / Needs you / Failed**. **Finished** is reading progress. **Promote** is incoming music → `music_root`.
- Auto-organize only when identify is confident. Unexpected → Review. Scan never moves files; ingest/watch may.
- BYO LLM may assist later. LLM never invents an ISBN.
- Automat media contract: [automat-media-contract.md](automat-media-contract.md). Shared `/data/media/music` is `{Artist}/{Album}/` with original filenames unless a trustworthy track tag exists (`NN - Title.ext`). Audiobooks never `music_root`. **No shared Python package** until mutagen + filename agreement proves high reuse.
- No fourth Automat **grab/traffic** container unless two apps actually emit the same JSON+NZB envelope. Until then each app keeps its own indexer / SAB / arr client.
- Port **8793**. Never 8788 / 8790 / 8791 / 8792.
- Auth on from first boot. Roles owner / op / reader. Docker-seed owner. Invite-only join (HMAC).

## v1 checklist

### Kit

- [x] Python 3.12 package `librarian/` + FastAPI `GET /api/health`
- [x] Port **8793**
- [x] `pyproject.toml` with ruff, scoped mypy, pytest-cov fail-under **70%**
- [x] Vite React SPA in `frontend/` served from `frontend/dist` when built
- [x] SQLite WAL on `/config` (`DATA_DIR`); settings.json wins
- [x] `AGENTS.md`, `.gitignore` (incl. `smart.map` / `projectionist` copies), `.env.example` placeholders
- [x] README / CHANGELOG / DOCKER / TESTING / SECURITY / HELP / design spec
- [x] Dockerfile, `docker-compose.yml`, `docker-run.sh`, `settings.example.json`
- [x] pytest + ruff + scoped mypy green (`270 passed`, 78% coverage on this pass)
- [x] `frontend/package-lock.json` + production `npm run build`
- [x] Private GitHub `romwil/librarian` + first push

### Auth

- [x] Roles owner / op / reader
- [x] `seed_env_owner` (weak password refuse; same-user rotate; never clobber a different owner)
- [x] HMAC invite `invite_id.raw.hmac`; SHA-256 hash at rest; fail-closed parse; one-tx redeem
- [x] Public handshake allowlist (no `/api/auth/*` wildcard)
- [x] Session cookie `librarian_session`; refuse public `LIBRARIAN_SESSION_SECRET` default
- [x] Reader 401/403 on Settings / invite-create / People
- [x] Op cannot invite `op`/`owner` (module + HTTP)

### NZBFinder

- [x] v2 JSON client: capabilities, search, books, details, download URL
- [x] User-Agent `Librarian/…` + `api_token` (also `apikey` alias)
- [x] Token-stripped search fixture
- [x] NZBFinder v2 fixtures in `tests/fixtures/nzbfinder/` (capabilities / books / magazine / details; no tokens)
- [x] Exact `newznab_cat_to_kind` in `librarian/indexers/kind_map.py` (33 value cases)
- [x] TV/movies/XXX categories refused at Hall identify (extras are Find-only behind the owner flag)
- [x] Live capabilities ping (opt-in, not CI)
- [x] Extra Newznab v2 hosts; merge/dedupe by guid
- [x] RSS subscriptions → Asked slips (confirm before SAB). TV/movies/XXX refused for RSS of Librarian kinds; extra-category Request is a different path

### SABnzbd

- [x] Client for `http://downloader.sl`: addurl / queue / history
- [x] `nzo_id` status machine: queued → downloading → extracting → organized | review | failed
- [x] Reader Request → `asked` slip (no SAB) until op/owner confirms
- [x] Background poller loop in the running process
- [x] Honest complete-path remap (`complete_root`); fail/unpack reasons
- [x] Job payload sought / selected / retrieved. Catalog title is what was asked, not the SAB dump name

### Identify / organize

- [x] Newznab cat → kind (7030 comic, 7010 mag, 70xx book, 3030 audiobook, 3010/3040/3999 music; 2/5/6xxx refuse at identify)
- [x] Usenet parse: magazine `No.10.2026` → `2026-10`; comic `Series.2024.001`
- [x] Layouts from the plan (EPUB / CBZ / incoming music / audiobook `{Author}/{Title}/`)
- [x] `metadata.opf` + `ComicInfo.xml`
- [x] Review reasons; collision / PDF-only book / CBR / no payload
- [x] Music Promote incoming → `music_root`
- [x] `audiobook_target` default `plex`
- [x] Cover fetch (indexer URL, Open Library ISBN, CBZ page 1)
- [x] CBR/PDF → CBZ convert (`unar` in image; `pdftoppm` when present; else Review)
- [x] `ebook-convert` / on-demand formats (cache under `/config/conversions`; 422 if missing)
- [x] BYO LLM identify (structured JSON; never invent ISBN)
- [x] Identify: tags, album vs single track, Automat media contract `{Artist}/{Album}/` original filename unless trustworthy `NN - Title.ext`; audiobooks never `music_root`
- [x] Add to the shelves + Watch folder (move when confident; Review when not). Scan still does not move files.

### Catalog

- [x] SQLite WAL: users, invites, works, files, jobs, shelves, Favorites
- [x] `review_state`, `music_state`, series fields
- [x] FTS5 local search (Hall hero + `/search`; no Beyond on Search)
- [x] Scan Settings `/data` roots into works+files (idempotent; scan does not move files; collisions → Review; owner “Scan the shelves”)
- [x] Dedicated `indexers` table (NZBFinder row synced from settings)
- [x] Continue bookmarks; Finished is reading progress, not a job word
- [x] Work/peek honesty: Incoming / Review chips, media note when no file, hide Finished on music
- [x] Enrich: Hardcover GraphQL then Open Library (description/series/year/cover); LLM never invents ISBN
- [x] Goodreads CSV import onto Favorites by ISBN-10/13; unmatched ISBN → thin work; no OAuth

### Gaps

- [x] Local magazine `YYYY-MM` holes
- [x] Local comic issue-number holes
- [x] Confirm-before-queue API (`POST /api/gaps/confirm`)
- [x] Book series gaps (Hardcover then Open Library); confirm only in Find
- [x] Audiobook parts (local completeness)
- [x] Audiobook series (Hardcover then Open Library)
- [x] Music track-number holes (local)
- [x] MusicBrainz discography / release tracks
- [x] Comic Vine issue lists (`comicvine_api_key`); Hall Gaps open Find
- [x] Magazines stay local `YYYY-MM` (no remote calendar)

### UX (Reading Room)

- [x] Reading Room tokens landed (brass `#c9954a`, Literata + Source Sans 3; spec in `docs/ux/reading-room.md`)
- [x] Animated foyer login + `/join?token=` (lamp dust, spines, unfinished page-turn; reduced-motion still)
- [x] The Hall landing + hero search (“What are you looking for?”)
- [x] Search = local shelves only; **Find beyond the shelves** opens `/find?q=&kind=` (plus kind-appropriate fields) and runs Beyond; Find is not a nav tab
- [x] Kind-morphing Find fields (books/mags: title/author/ISBN; comics: series/issue `7030`; music: artist/album; audiobooks `3030`)
- [x] Household job chips: Asked / On the way / Arrived / Needs you / Failed (SAB raw stays on Queue detail only)
- [x] Discover: empty Find shows trending indexer category feeds from capabilities. Not a second Hall, not auto-SAB. No HTML scrape
- [x] Show extra categories (owner; `show_extra_categories`, default **off**): Movies/TV/XXX if the indexer lists them. Never Hall works. Movies: SAB category (default `movies`) then Radarr add (search off) + DownloadedMoviesScan. TV: SAB `tv` then Sonarr series add + DownloadedEpisodesScan. XXX: SAB default folder only, no arr. No arr token: still queue SAB, chip Needs you
- [x] Peek overlay `min(44rem, 100vw - 1.5rem)` with visible 148×222 cover; cover click does not navigate
- [x] Role-aware chrome (Review is an op/owner bag badge)
- [x] Work hero (blurred wash + chips + Favorite/Promote)
- [x] Living Request chips after Find peek Request
- [x] In-browser reader: foliate-js EPUB + CBZ `comic-book.js` on `can_download` book/magazine/comic
- [x] Frontend unit tests (cover cloth / peek click / job labels / reader / Find)
- [x] Continue rail (progress API; Hall hides finished)
- [x] Browser-verified Hall / login / peek (Automat foyer; local Hall cover → peek, Esc keeps `/`)
- [x] Kind-skinned covers, search “searched X · N on shelves”, `?` field help, Settings wizard, Review tickets
- [x] Audiobookshelf match (ISBN then author+title); quiet On the player chip; does not replace Plex `audiobook_target`

### Automat

- [x] `docs/DOCKER.md` — `/config` + `/data`, port 8793, env owner, PUID/PGID, extra_hosts
- [x] `docs/ops/AUTOMAT.md` — LAN truth `:8793`, kit path, first-boot env, rsync
- [x] `docs/SECURITY.md` — exhaustive handshake, `LIBRARIAN_TRUST_PROXY_HEADERS` fail-closed, rate limits
- [x] `docker-run.sh` on-host build; does not wipe config; refuses 8788/8790/8791/8792
- [x] Docker layer cache: npm ci / pip extras before source; `docker-run.sh` passes HARDCOVER, COMICVINE, ABS, SHOW_EXTRA_CATEGORIES, RADARR/SONARR, SAB_MOVIE/TV_CATEGORY, COMPLETE_ROOT
- [x] Automat media contract doc (shared with Smart Map conceptually; no shared Python package yet)
- [x] `rollout.sh` Hub-pull stub (fails until `romwil/librarian` exists)
- [x] Deployed kit at `/mnt/user/appdata/librarian` (container `librarian`, `:8793`)
- [x] Rebuild Automat image to then-`main` (`1d7f18a`; identify/convert Review fixes; `/config` kept)
- [ ] Hub `romwil/librarian` published (later; not this slice)

## Library first — landed

Sequence (history): scan → enrich/Hardcover → reader → catalog gaps → RSS/ABS, with Search/Find split and five job words in the first slices. Those slices are shipped. Remaining work lives under Phase 2b / Later — do not treat scan, Find, or the reader as undone.

- [x] **Scan** Settings `/data` roots (`books_root`, `magazines_root`, `comics_root`, `audiobooks_root`, `incoming_music_root`, `music_root`) into the catalog; idempotent; do not move files; collisions → Review
- [x] Work/peek honesty: Incoming / Review chips, media note when no file, hide Finished on music
- [x] **Enrich:** Open Library + **Hardcover** (live token in settings, never committed)
- [x] **Goodreads CSV / shelf export** import onto Favorites, matched by ISBN (no live Goodreads OAuth)
- [x] **In-browser reader:** foliate-js EPUB + CBZ `comic-book.js` on `can_download` book/magazine/comic
- [x] **Catalog gaps:** Hardcover/OL series, Comic Vine, MusicBrainz; Hall Gaps stay Library; confirm only in Find
- [x] **Find extras:** RSS subscriptions, additional Newznab hosts, Audiobookshelf API match (SAB client stays)
- [x] Search / Find split + household job words + Discover + optional extra categories
- [x] Advanced Search/Find typeahead (`GET /api/suggest` catalog-first; owner **Refresh suggestions from shelves**)

### Phase 2b

- [x] In-app audiobook player or deep-link to Plex/ABS

### Later

- [ ] Hub `romwil/librarian` published
- [ ] Full MusicBrainz / Open Library dumps for typeahead (v1 is catalog + optional bounded MB from owned artists)
- [ ] OIDC / Plex sign-in (not v1, not Phase 2)
- [ ] Shared Python package with Smart Map: **contract first**; thin shared lib only if mutagen + filename agreement proves high reuse
- [ ] Shared JSON+NZB **grab/traffic service** (fourth Automat container): too much now. Worthwhile as a **future refactor if two apps actually emit the same envelope** (Librarian extras + Projectionist). Until then each app keeps its own indexer/SAB/arr client
- [ ] Blue sky: OPDS 2, highlights, TTS, barcode Review, offline PWA, kid shelf

Personalized recs and HTML scrape of indexer Discover are **skipped on purpose**.

### Out of v1 / product lock

Hub as the only ship path, NZBGet, Plex/OIDC login, Calibre plugins / USB sync / content-server skin, Movies/TV/XXX as Hall library kinds (extras are Find/SAB/arr only), Goodreads live OAuth (CSV shipped). The built-in reader shipped in Library first.
