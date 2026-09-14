# Build progress

Scratch pad for shipped work. Append when a task completes (date + SHA if known). Do not rewrite history.

Plan: [librarian_automat_rss](file:///Users/willrompala/.cursor/plans/librarian_automat_rss_277e525b.plan.md) · Roadmap: [ROADMAP.md](ROADMAP.md) · Design: [2026-09-14 librarian design](superpowers/specs/2026-09-14-librarian-design.md)

## Shipped

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
- **2026-09-14** `12d6f6f` — Restored `.cover.is-progress::after` (broken CSS brace blocked `npm run build`). Browser-verified Automat foyer + local Hall/peek.

## In progress / next

- [x] Private `romwil/librarian` exists (`https://github.com/romwil/librarian`)
- [x] Automat `docker-run.sh` health smoke — `8db903a` on `:8793`, owner seed ok, `/config`+`/data` mounted. Phase 1 is on `main` but not in the running image yet.
- [x] Browser QA: Automat foyer (`data-testid=foyer`, lamp shaft, page-turn, dust). Local Hall: Continue empty copy, Dune cover opens peek without leaving `/`; Esc dismisses peek.
- [ ] Rebuild Automat image to current `main`
- [ ] Hub `romwil/librarian` (later)
