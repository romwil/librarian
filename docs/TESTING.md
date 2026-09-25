# End-to-end and release testing

For **value-based backend unit tests**, see the root [TESTING.md](../TESTING.md).
For **multi-sprint major builds** (lanes, coverage discipline, release cadence, UX gates), see
[ops/MAJOR_BUILDS.md](ops/MAJOR_BUILDS.md).

## Docs gate

Every user-facing change updates the relevant guide **and** adds a benefit-led `### Highlights` entry to `CHANGELOG.md`. Docs are a first-class deliverable.

## Layers

| Layer | Command | Secrets? |
| --- | --- | --- |
| Backend unit | `LIBRARIAN_PBKDF2_ITERATIONS=1000 LIBRARIAN_SKIP_APP_BOOT=1 .venv/bin/python -m pytest tests/ -v` | No |
| Frontend unit | `cd frontend && npm test` | No |
| Frontend build | `cd frontend && npm run build` | No |
| Playwright e2e (mocked) | `npm install && npx playwright install chromium && npm run test:e2e` | No (ephemeral owner seed) |
| Docker health | `./docker-run.sh` then `GET /api/health` | Owner env only |

Backend coverage floor is **`--cov-fail-under=70`** (`pyproject.toml`). Every sprint keeps pytest + frontend unit green; new behavior ships with value-based tests. Mock NZBFinder, extra Newznab hosts, SABnzbd, LLM, Hardcover, Open Library, Comic Vine, MusicBrainz, Audiobookshelf, and RSS HTTP in unit tests. Live indexer/downloader pings stay opt-in (`POST /api/indexers/ping`) and out of default CI. **Never mock SQLite.**

## Playwright (mocked e2e)

Scaffold mirrors Projectionist’s pattern but uses Librarian ports:

| Role | Port |
| --- | --- |
| Product / Automat | **8793** |
| Playwright webServer | **8794** (default `E2E_PORT`) |

**Never** bind or point e2e at 8788 (Projectionist), 8790 (Smart Map), 8791/8792 (Lobby), or product 8793 (so reuseExistingServer cannot hit a live household instance). Projectionist’s e2e default is 8799 — Librarian stays on **8794**.

```bash
# once per machine
npm install
npx playwright install chromium

# from repo root (or: cd frontend && npm run test:e2e)
npm run test:e2e
```

`scripts/start-e2e-server.mjs` builds `frontend/dist` if missing, seeds a throwaway owner into a temp `DATA_DIR`, and starts `python -m librarian.web` on **8794**. No live NZBFinder / SABnzbd required. Override with `E2E_PORT` / `E2E_BASE_URL` when needed.

Baseline smoke: health/shell, Hall loads, Review empty bagging copy, Settings section nav.

## Port trap

Librarian product is **8793**. Do not point tests at 8788 (Projectionist), 8790 (Smart Map), or 8791/8792 (Lobby). Playwright uses **8794**.
