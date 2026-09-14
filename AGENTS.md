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
  Coverage is auto-enabled via `pyproject.toml` (`--cov-fail-under=70`).
- **Ruff:** `.venv/bin/ruff check librarian tests`
- **Mypy (scoped):** `.venv/bin/python -m mypy`
- Value-based tests only — see [TESTING.md](TESTING.md). Mock NZBFinder / SAB / LLM HTTP. Never mock SQLite.

### Automat LAN
When checking the live Automat Unraid stack, use LAN hosts — **not** a public hostname.

| Role | URL |
|------|-----|
| Librarian | `http://10.10.1.202:8793` |
| Projectionist prod | `:8788` |
| Smart Map | `:8790` |
| Lobby / QA Lobby | `:8791` / `:8792` |

**Never bind Librarian to 8788, 8790, 8791, or 8792.** Kit: `/mnt/user/appdata/librarian`.
On-host build now (`./docker-run.sh`); Hub `romwil/librarian` + pull-only `rollout.sh` later.
Do not treat public DNS as version truth.

### Secrets
NZBFinder / SAB / session tokens live in `.env` or `/config/settings.json` only.
Never commit real tokens. The public `librarian-dev-session-secret` is refused.
