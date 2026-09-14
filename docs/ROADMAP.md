# Librarian roadmap

Living product/build checklist. Flip boxes when a slice ships. Append the story to [build-progress.md](build-progress.md). Design north star: [2026-09-14 librarian design](superpowers/specs/2026-09-14-librarian-design.md).

## Build status

| | |
| --- | --- |
| **Date** | 2026-09-14 |
| **Branch** | `main` |
| **Last SHA** | pending commit (Phase 1 gaps) |
| **Green** | `127 passed`, coverage **78%** (floor 70%); ruff + scoped mypy clean; frontend `5 passed` (`node --test`). |
| **Next** | Automat `docker-run.sh` smoke on `:8793`; Hub `romwil/librarian` later. |

## North star

A household **library for readers**. People peruse shelves, see What’s New, open a book or issue, and request what’s missing. Books, magazines, and comics (CBZ, Newznab `7030`) share first-tier rank. Audiobooks and music are first-tier listening — music Promotes to Plexamp; audiobooks never do.

## Locked decisions

- Retriever: SABnzbd at `http://downloader.sl`.
- `/data` ← host `/mnt/user/data`. Per-media roots are Settings paths under `/data`.
- First indexer: NZBFinder Newznab **v2 JSON**. Token in env/settings only. User-Agent required. Never commit tokens.
- Music: `incoming_music_root` → **Promote** → `music_root` (`/data/media/music`) for Plexamp only.
- Audiobooks: `audiobook_target` default **`plex`**. Never `music_root`.
- Comics: `7030`, canonical **CBZ**, `{Series}/{Issue-or-Year}/` + ComicInfo + cover.
- Gaps: owned vs expected, honest missing cards, **confirm before** SAB. Fail closed.
- Auto-organize only when identify is confident. Unexpected → Review.
- BYO LLM may assist later. LLM never invents an ISBN.
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
- [x] pytest + ruff + scoped mypy green (`127 passed`, 78% coverage)
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
- [x] TV/movies/XXX categories refused at parse
- [x] Live capabilities ping (opt-in, not CI)
- [ ] RSS subscriptions (phase 2)

### SABnzbd

- [x] Client for `http://downloader.sl`: addurl / queue / history
- [x] `nzo_id` status machine: queued → downloading → extracting → organized | review | failed
- [x] Reader Request → `asked` slip (no SAB) until op/owner confirms
- [x] Background poller loop in the running process

### Identify / organize

- [x] Newznab cat → kind (7030 comic, 7010 mag, 70xx book, 3030 audiobook, 3010/3040/3999 music; 2/5/6xxx refuse)
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

### Catalog

- [x] SQLite WAL: users, invites, works, files, jobs, shelves, Favorites
- [x] `review_state`, `music_state`, series fields
- [x] FTS5 local search
- [x] Dedicated `indexers` table (NZBFinder row synced from settings)
- [x] Continue / in-progress reads

### Gaps

- [x] Local magazine `YYYY-MM` holes
- [x] Local comic issue-number holes
- [x] Confirm-before-queue API (`POST /api/gaps/confirm`)
- [ ] Book series gaps (Open Library / Hardcover) — phase 2 catalogs
- [x] Audiobook parts (local completeness)
- [ ] Audiobook series (catalogs, later)
- [x] Music track-number holes (local)
- [ ] MusicBrainz discography (phase 2)

### UX (Reading Room)

- [x] Reading Room tokens landed (brass `#c9954a`, Literata + Source Sans 3; spec in `docs/ux/reading-room.md`)
- [x] Animated foyer login + `/join?token=` (lamp dust, spines, unfinished page-turn; reduced-motion still)
- [x] The Hall landing + hero search (“What are you looking for?”)
- [x] Local-first search, then Beyond the shelves (kind chips + advanced drawer)
- [x] Peek overlay `min(44rem, 100vw - 1.5rem)` with visible 148×222 cover; cover click does not navigate
- [x] Role-aware chrome (Review is an op/owner bag badge)
- [x] Work hero (blurred wash + chips + Favorite/Promote)
- [x] Living Request chips after Beyond peek Request
- [x] Frontend unit tests (cover cloth / peek click / job labels)
- [x] Continue rail (progress API; Hall hides finished)
- [ ] Browser-verified Hall / login / peek

### Automat

- [x] `docs/DOCKER.md` — `/config` + `/data`, port 8793, env owner, PUID/PGID, extra_hosts
- [x] `docs/ops/AUTOMAT.md` — LAN truth `:8793`, kit path, first-boot env, rsync
- [x] `docs/SECURITY.md` — exhaustive handshake, `LIBRARIAN_TRUST_PROXY_HEADERS` fail-closed, rate limits
- [x] `docker-run.sh` on-host build; does not wipe config; refuses 8788/8790/8791/8792
- [x] `rollout.sh` Hub-pull stub (fails until `romwil/librarian` exists)
- [ ] Deployed kit at `/mnt/user/appdata/librarian`
- [ ] Hub `romwil/librarian` published (later; not this slice)

## Later phases (not v1)

- [ ] Phase 2: MusicBrainz / Open Library / Comic Vine gap catalogs
- [ ] Phase 2: in-browser reader (foliate-js, CBZ `comic-book.js`, paper/page-turn)
- [ ] Phase 2: covers, RSS poller, more Newznab hosts, Audiobookshelf API match
- [ ] Phase 2b: in-app audiobook player or deep-link to Plex/ABS
- [ ] Later: OIDC / Plex sign-in, Goodreads / Hardcover
- [ ] Blue sky: OPDS 2, highlights, TTS, barcode Review, offline PWA, kid shelf

### Out of v1

Goodreads, built-in reader, Hub as the only ship path, NZBGet, Plex/OIDC login, Calibre plugins / USB sync / content-server skin, TV/movies.
