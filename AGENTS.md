# AGENTS.md

Librarian is a **single service**: a Python 3.12 FastAPI backend (`python -m librarian.web`) that
also serves the pre-built React SPA from `frontend/dist`. There is **no separate database/cache/queue**
to run — state is SQLite under `DATA_DIR` (WAL). SABnzbd / NZBFinder / LLM are optional integrations
and are **not** required to boot or test the app. Household auth is **on from first boot**.

### Environment
- Python venv at `.venv` (`python3 -m venv .venv`; package installed editable with `.[web,dev]` extras).
- Frontend deps in `frontend/`. Build the SPA (`frontend/dist`) before the backend can serve the UI.

### Run the dev server
```bash
DATA_DIR=./config PORT=8793 .venv/bin/python -m librarian.web
```
Serves on http://127.0.0.1:8793 (`GET /api/health` → `{"status":"ok"}`).
`LIBRARIAN_SKIP_APP_BOOT=1` is for pytest only — do not set it when running the server.
Backend has **no hot reload**; restart after Python changes. After frontend edits:
`cd frontend && npm run build` (or `npm run dev`, which proxies `/api` to `:8793`).

### Lint / test
- **Backend:** `LIBRARIAN_PBKDF2_ITERATIONS=1000 LIBRARIAN_SKIP_APP_BOOT=1 .venv/bin/python -m pytest tests/`
  Coverage is auto-enabled via `pyproject.toml` (`--cov-fail-under=70`). Every sprint keeps this floor green.
- **Frontend unit:** `cd frontend && npm test` (Node `node --test` interim; **target Layer 1 = Vitest**).
- **Playwright e2e (mocked):** `npm run test:e2e` — dedicated port **8794** (not 8793 / 8788 / 8790 / 8791 / 8792).
  Install once: `npm install && npx playwright install chromium`. See [docs/TESTING.md](docs/TESTING.md).
  Semantic locators only (`getByRole` / `getByLabel`).
- **axe-core:** not wired yet — required for major gauntlet / core-chrome changes once adopted.
- **Ruff:** `.venv/bin/ruff check librarian tests`
- **Mypy (scoped):** `.venv/bin/python -m mypy`
- Value-based tests only — see [TESTING.md](TESTING.md). Mock NZBFinder / SAB / LLM HTTP. Never mock SQLite.
- **Must follow** front-end Testing Triad + adversarial stance:
  [docs/ops/UI_TESTING_ARCHITECTURE.md](docs/ops/UI_TESTING_ARCHITECTURE.md).

### Major builds
Multi-sprint arcs follow [docs/ops/MAJOR_BUILDS.md](docs/ops/MAJOR_BUILDS.md): phases/sprints as GitHub
feature releases, parallel agent lanes with exclusive file ownership, coverage ≥70% every sprint,
Testing Triad + interactive browser UX gates (see [docs/ops/UI_TESTING_ARCHITECTURE.md](docs/ops/UI_TESTING_ARCHITECTURE.md)),
and the kickoff loop. Automat path is host `./docker-run.sh`.

### Local intelligence (codegraph)
Prefer [`.codegraph/`](.codegraph/) (`codegraph` CLI: `query` / `explore` / `callers` / `node`) for
symbol navigation and impact on major work before blind `rg` sweeps. Refresh with `codegraph sync`
(or `codegraph index -f` after large moves). Index is gitignored / local-only.

### Automat LAN
When checking the live Automat Unraid stack, use LAN hosts — **not** a public hostname.

| Role | URL |
|------|-----|
| Librarian | `http://10.10.1.202:8793` |
| Projectionist prod | `:8788` |
| Smart Map | `:8790` |
| Lobby / QA Lobby | `:8791` / `:8792` |

**Never bind Librarian to 8788, 8790, 8791, or 8792.** Kit: `/mnt/user/appdata/librarian`
(`config/` → `/config`, `/mnt/user/data` → `/data`). Playbook: [docs/ops/AUTOMAT.md](docs/ops/AUTOMAT.md).
**Automat deploy path now is host `./docker-run.sh` only** — there is no Hub pull-only release
script in active use, and no `docker-release.sh` to run for this kit yet. Hub `romwil/librarian`
+ pull-only `rollout.sh` stay deferred. Do not treat public DNS as version truth.
`LIBRARIAN_TRUST_PROXY_HEADERS` is opt-in (default off).

### Secrets
NZBFinder / SAB / session tokens live in `.env` or `/config/settings.json` only.
Never commit real tokens. The public `librarian-dev-session-secret` is refused.
