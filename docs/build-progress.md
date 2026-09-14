# Build progress

Scratch pad for shipped work. Append when a task completes (date + SHA if known). Do not rewrite history.

Plan: [librarian_automat_rss](file:///Users/willrompala/.cursor/plans/librarian_automat_rss_277e525b.plan.md) · Roadmap: [ROADMAP.md](ROADMAP.md) · Design: [2026-09-14 librarian design](superpowers/specs/2026-09-14-librarian-design.md)

## Shipped

- **2026-09-14** — First tree: FastAPI + Vite kit on **8793**, SQLite WAL, settings.json wins, AGENTS/CHANGELOG/DOCKER/TESTING/SECURITY/HELP/design spec. `.gitignore` blocks `smart.map` / `projectionist` copies. `.env.example` has empty SAB/NZBFinder placeholders only.
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

## In progress / next

- [ ] Commit + private `romwil/librarian` + push
- [ ] Automat `docker-run.sh` health smoke
- [ ] Cover fetch / CBR→CBZ / BYO LLM identify
- [ ] Continue rail + living Request chips + frontend unit tests
