# Build progress

Scratch pad for shipped work. Append when a task completes (date + SHA if known). Do not rewrite history.

Plan: [librarian_automat_rss](file:///Users/willrompala/.cursor/plans/librarian_automat_rss_277e525b.plan.md) · Roadmap: [ROADMAP.md](ROADMAP.md) · Design: [2026-09-14 librarian design](superpowers/specs/2026-09-14-librarian-design.md)

## Shipped

- **2026-09-15** — Automat media contract (`docs/automat-media-contract.md`): shared `/data/media` roots with Smart Map; music `{Artist}/{Album}/` keeps the original filename unless a trustworthy track tag exists (`NN - Title.ext`). Audiobooks never `music_root`.
- **2026-09-14** `d79591b` — First tree: FastAPI + Vite kit on **8793**, SQLite WAL, settings.json wins, AGENTS/CHANGELOG/DOCKER/TESTING/SECURITY/HELP/design spec. `.gitignore` blocks `smart.map` / `projectionist` copies. `.env.example` has empty SAB/NZBFinder placeholders only.
- **2026-09-14** — Auth: owner/op/reader, `seed_env_owner`, HMAC invites (hash at rest, fail-closed parse, one-tx redeem), exhaustive public handshake, session secret refuse-default.
- **2026-09-14** — NZBFinder v2 JSON client (caps/search/books/details/download URL, User-Agent + `api_token`) with token-stripped fixture. TV/movies/XXX dropped.
- **2026-09-14** — SABnzbd addurl/queue/history + `nzo_id` status machine. Reader Request is an `asked` slip.
- **2026-09-14** — Identify/organize layouts (EPUB/CBZ/magazine/audiobook/incoming music), OPF + ComicInfo, Review reasons, music Promote, `audiobook_target=plex`.
- **2026-09-14** — Catalog (works/files/jobs/shelves/Favorites) + FTS5. Local magazine `YYYY-MM` and comic issue holes; confirm-before-queue API.
- **2026-09-14** — Reading Room SPA: foyer login/join, The Hall, hero search (local then indexer), peek then work page, role-aware chrome.
- **2026-09-14** — Automat kit files: Dockerfile, compose, `docker-run.sh` (no config wipe; refuse sibling ports).

- **2026-09-14** — Roadmap + append-only `docs/build-progress.md`; README points at ROADMAP.
- **2026-09-14** — Value tests green: 54 passed, 77% coverage (floor 70%). Ruff + scoped mypy clean. Book parse splits `Author - Title` before tidy. HTTP authz: reader 403 Settings/invites; op cannot mint `op`.
- **2026-09-14** — `frontend/package-lock.json` + `npm run build` (SPA in `frontend/dist`, gitignored).
- **2026-09-14** — Reading Room handoff copied to `docs/ux/reading-room.md` + `docs/ux/mockups/`. SPA `:root` is brass `#c9954a`, Literata + Source Sans 3; peek `min(44rem, 100vw - 1.5rem)`; covers 148×222 / 160 square; cover click opens peek.
- **2026-09-14** — NZBFinder v2 fixtures copied (no live refetch): `tests/fixtures/nzbfinder/{capabilities,books-linux,search-magazine,details-linux}.json`. Confirmed no `api_token` / `apikey` in JSON. Exact `newznab_cat_to_kind` at `librarian/indexers/kind_map.py`; 33 value tests in `tests/test_kind_map.py`. Client parses v2 `results` from those fixtures.
- **2026-09-14** — CSS: standalone `.muted { color: var(--muted); }`; Settings labels use `.field` like login (dropped leftover `login-field`).
- **2026-09-14** — CSS: standalone `.muted { color: var(--muted) }`; Settings uses login `.field` (dropped leftover `login-field`).
- **2026-09-14** `bbb9bef` — Phase 1 gaps: Continue rail + progress; cover fetch; CBR→CBZ (`unar`); on-demand `ebook-convert`; BYO LLM identify (no invented ISBN); SAB background poller; `indexers` table + opt-in caps ping; local audiobook part + music track holes.
- **2026-09-14** `8db903a` — Automat playbook (`docs/ops/AUTOMAT.md`), proxy-header fail-closed (`LIBRARIAN_TRUST_PROXY_HEADERS` default off), auth/invite rate limits, PUID/PGID 99/100, live `docker-run.sh` on `http://10.10.1.202:8793`. GitHub About filled; repo stays private.
- **2026-09-14** — Identify: comic/magazine `review_reason` clears only after a successful high-confidence LLM; extra files stay Review. Convert: `pdf_to_cbz` matches pdftoppm JPEGs by literal prefix so Usenet `[brackets]` convert instead of globbing as a character class.
- **2026-09-14** `12d6f6f` — Restored `.cover.is-progress::after` (broken CSS brace blocked `npm run build`). Browser-verified Automat foyer + local Hall/peek.
- **2026-09-14** — Automat `docker-run.sh` rebuilt `librarian` to **`86ac87f`**. Health ok on `:8793`. `./config` kept. Projectionist `:8788` and Smart Map `:8790` stayed up.
- **2026-09-14** — Second Automat rebuild to **`1d7f18a`** (identify/convert Review fixes). Health ok on `:8793`. `./config` kept.
- **2026-09-14** — Convert: `pdf_to_cbz` unlinks leftover pdftoppm JPEGs in a `finally` if rasterize succeeds but zip/convert fails.
- **2026-09-15** — Review: identify form (title/author/ISBN/kind/folder) always shown; `no_payload` is missing files at SAB storage (often `/downloads` on Unraid vs laptop). Apply uses identity; 400 if still no files. Optional `complete_root` remaps `/downloads`.
- **2026-09-15** — Reading Room UX pass: kind-skinned covers (book/magazine/comic/audiobook/music), clamped gilt overlay, search status + beyond callout, `?` field help, Settings four-step wizard, Review bagging tickets. Hall stays open while configured.
- **2026-09-15** — Enrich: Hardcover GraphQL then Open Library fill thin books (description/series/year/cover). Goodreads CSV import matches ISBN onto Favorites; missing ISBNs create thin works. LLM still never invents an ISBN. Token `hardcover_api_token` in settings only.
- **2026-09-15** — Catalog gaps: Hardcover then Open Library series volumes; Comic Vine issue lists (masked `comicvine_api_key`; Hardcover has no issue catalog); MusicBrainz release tracks (User-Agent + 1.1s pacing). Magazines stay local `YYYY-MM`. Hall Gaps open Find; SAB never queues from a shelf browse.
- **2026-09-15** — Find extras: extra Newznab v2 hosts (fail closed per host, merge by guid); RSS subscriptions become Asked slips (TV/movies/XXX refused for Librarian-kind feeds); Audiobookshelf HTTP match by ISBN then author+title. SAB stays the retriever. Search stays local.
- **2026-09-15** — Ingest: owner/op Add to the shelves (`/data` browse + paste) and Watch folder. Confident identify moves into the Settings root; unexpected → Review. Scan still does not move files. No browser OS file picker, no inotify.
- **2026-09-15** — Search / Find split: Search is local FTS only (Hall hero + `/search`; Peek / Open / Favorite). **Find beyond the shelves** opens `/find` with `q`/kind and kind-appropriate fields, then Beyond. Find is not a nav tab. Five job words: Asked / On the way / Arrived / Needs you / Failed. SAB raw stays on Queue detail. Job payload sought / selected / retrieved — catalog title is what was asked.
- **2026-09-15** — Scan the shelves: owner Settings walks `/data` roots into works+files. Idempotent. Does not move files. Collisions → Review. Separate from ingest/watch, which may move when identify is confident.
- **2026-09-15** — In-browser reader: foliate-js EPUB + CBZ `comic-book.js` (and PDF) on `can_download` book/magazine/comic. Open on the work page; peek Open deep-links `?read=1`. Not Calibre-web. Audiobooks/music stay out (Phase 2b).
- **2026-09-18** — Phase 2b Listen: Listening room (HTML5 + Media Session, mutagen chapters), Work/peek **Listen** primary + ABS/Plex **Open in player**, Continue rail for audiobook progress. Never Promote audiobooks to Plexamp.
- **2026-09-15** — Work/peek honesty: Incoming / Review chips, media note when there is no file, hide Finished on music. Continue bookmarks; Finished is reading progress, not a job word.
- **2026-09-15** — Discover: empty Find shows trending indexer category feeds from capabilities (v2 search or `/rss?t=`). Not a second Hall, not auto-SAB, no HTML scrape. Owner `show_extra_categories` (default off) adds Movies/TV/XXX — SAB then Radarr/Sonarr for movies/TV, SAB folder only for XXX; no arr token still queues SAB and chips Needs you. Never Hall works.
- **2026-09-15** — Docker layer cache: npm ci / pip extras before source. `docker-run.sh` passes HARDCOVER, COMICVINE, ABS, SHOW_EXTRA_CATEGORIES, RADARR/SONARR, SAB_MOVIE/TV_CATEGORY, COMPLETE_ROOT. Does not wipe `./config`.
- **2026-09-15** — Identify: tags, album vs single track, Automat media contract `{Artist}/{Album}/` keeps the original filename unless a trustworthy track tag exists (`NN - Title.ext`). Audiobooks never `music_root`. Honest SAB `complete_root` remap and fail/unpack reasons.

## Next / later

Library-first Phase 2 is landed. Do not list scan, Search/Find, job chips, Discover, ingest, or the reader here.

- Hub `romwil/librarian` published (later; `rollout.sh` stays a stub)
- Shared Python package with Smart Map — **only if** mutagen + filename agreement proves high reuse; contract first
- Shared JSON+NZB grab/traffic service (fourth container) — **only if** two apps actually emit the same envelope; until then each app keeps its own indexer/SAB/arr client
- OIDC / Plex sign-in (not v1, not Phase 2)
- Blue sky: OPDS 2, highlights, TTS, barcode Review, offline PWA, kid shelf

Personalized recs and HTML scrape of indexer Discover stay skipped on purpose.
- **2026-09-18** `203962d` — Ship **0.3.0**: Phase 2b Listen player, LLM bestsellers (+ audiobook chase), finish-ETA/smart re-grab deepen, community Read/peek/companion UX, `unpack_stuck` Review recovery for audiobook archives. Automat rebuild to follow.
- **2026-09-18** — Automat `docker-run.sh` rebuilt `librarian` to **`f343292`** (0.3.0). Health ok on `:8793`. `./config` kept.
- **2026-09-19** `7d183c2` — Ship **0.3.1**: Edit metadata / Fix match / Undo enrich; Open Library co-author rejection; multi-provider BYO LLM; Find rank memory + disclosures; Bestsellers/chase polish; Enrich/Review busy feedback.
- **2026-09-19** — Automat `docker-run.sh` rebuilt `librarian` to **`7d183c2`** (0.3.1). Health ok on `:8793`. `./config` kept.
- **2026-09-19** `b1adcad` — Ship **0.4.0**: audiobook scene→Audnexus→M4B, comics scene→ComicVine→CBZ+Komga, ABS scan + listen progress sync, media-contract shelf layouts.
- **2026-09-19** `90509f3` — Fix Audnexus author substring false matches and ABS multipart progress without duration.
- **2026-09-19** — Automat `docker-run.sh` rebuilt `librarian` to **`90509f3`** (0.4.0). Health ok on `:8793`. `./config` kept.
