# Librarian roadmap

Living product/build checklist. Flip boxes when a slice ships. Append the story to [build-progress.md](build-progress.md). Design north star: [2026-09-14 librarian design](superpowers/specs/2026-09-14-librarian-design.md).

## Build status

| | |
| --- | --- |
| **Date** | 2026-09-14 |
| **Branch** | `main` |
| **Last SHA** | first local commit (SHA recorded in build-progress after push) |
| **Green** | `54 passed`, coverage **77%** (floor 70%); ruff + scoped mypy clean; `GET /api/health` → `{status: ok}`; `frontend` Vite build succeeds. |
| **Next** | Private `romwil/librarian` + push; Automat `docker-run.sh` smoke; cover fetch / living Request chips / Continue rail. |

## North star

A household **library for readers**, not an admin grabber and not Calibre-in-a-browser. People peruse shelves, see What’s New, open a book or issue, and request what’s missing. Books, magazines, and comics (CBZ, Newznab `7030`) share first-tier rank. Audiobooks and music are first-tier listening — music Promotes to Plexamp; audiobooks never do.

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
- [x] pytest + ruff + scoped mypy green (`54 passed`, 77% coverage)
- [x] `frontend/package-lock.json` + production `npm run build`
- [ ] Private GitHub `romwil/librarian` + first push

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
- [x] TV/movies/XXX categories refused at parse
- [ ] Live capabilities ping (opt-in, not CI)
- [ ] RSS subscriptions (phase 2)

### SABnzbd

- [x] Client for `http://downloader.sl`: addurl / queue / history
- [x] `nzo_id` status machine: queued → downloading → extracting → organized | review | failed
- [x] Reader Request → `asked` slip (no SAB) until op/owner confirms
- [ ] Background poller loop in the running process (poll is on-demand / queue GET today)

### Identify / organize

- [x] Newznab cat → kind (7030 comic, 7010 mag, 70xx book, 3030 audiobook, 30xx music; 2/5/6xxx refuse)
- [x] Usenet parse: magazine `No.10.2026` → `2026-10`; comic `Series.2024.001`
- [x] Layouts from the plan (EPUB / CBZ / incoming music / audiobook `{Author}/{Title}/`)
- [x] `metadata.opf` + `ComicInfo.xml`
- [x] Review reasons; collision / PDF-only book / CBR / no payload
- [x] Music Promote incoming → `music_root`
- [x] `audiobook_target` default `plex`
- [ ] Cover fetch
- [ ] CBR/PDF → CBZ convert
- [ ] `ebook-convert` / on-demand formats
- [ ] BYO LLM identify (structured JSON; never invent ISBN)

### Catalog

- [x] SQLite WAL: users, invites, works, files, jobs, shelves, Favorites
- [x] `review_state`, `music_state`, series fields
- [x] FTS5 local search
- [ ] Dedicated `indexers` table (v1 is settings-backed NZBFinder)
- [ ] Continue / in-progress reads

### Gaps

- [x] Local magazine `YYYY-MM` holes
- [x] Local comic issue-number holes
- [x] Confirm-before-queue API (`POST /api/gaps/confirm`)
- [ ] Book series gaps (Open Library / Hardcover)
- [ ] Audiobook parts / series
- [ ] MusicBrainz discography / track holes

### UX (Reading Room)

- [x] Animated foyer login + `/join?token=` (lamp dust, spines, unfinished page-turn; reduced-motion still)
- [x] The Hall landing + hero search
- [x] Local-first search, then Beyond the shelves
- [x] Peek drawer then `/works/:id` (plain click peek; Open full page)
- [x] Role-aware chrome (Review/Queue/People/Settings gated)
- [~] Projectionist-grade work detail (hero + files + Favorite/Promote; no rails yet)
- [ ] Continue rail
- [ ] Living Request chips on search cards
- [ ] Frontend unit tests (naming / filters / review copy)
- [ ] Browser-verified Hall / login / peek

### Automat

- [x] `docs/DOCKER.md` — `/config` + `/data`, port 8793, env owner
- [x] `docker-run.sh` on-host build; does not wipe config; refuses 8788/8790/8791/8792
- [ ] Deployed kit at `/mnt/user/appdata/librarian`
- [ ] Hub `romwil/librarian` + pull-only `rollout.sh`

## Later phases (not v1)

- [ ] Phase 2: MusicBrainz / Open Library / Comic Vine gap catalogs
- [ ] Phase 2: in-browser reader (foliate-js, CBZ `comic-book.js`, paper/page-turn)
- [ ] Phase 2: covers, RSS poller, more Newznab hosts, Audiobookshelf API match
- [ ] Phase 2b: in-app audiobook player or deep-link to Plex/ABS
- [ ] Later: OIDC / Plex sign-in, Goodreads / Hardcover
- [ ] Blue sky: OPDS 2, highlights, TTS, barcode Review, offline PWA, kid shelf

### Out of v1

Goodreads, built-in reader, Hub as the only ship path, NZBGet, Plex/OIDC login, Calibre plugins / USB sync / content-server skin, TV/movies.
