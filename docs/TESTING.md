# Testing

Canonical testing guide: value-based backend tests, frontend unit tests, Playwright, and axe.
The repo-root [TESTING.md](../TESTING.md) points here.

For **multi-sprint major builds** (lanes, coverage discipline, release cadence, UX gates), see
[ops/MAJOR_BUILDS.md](ops/MAJOR_BUILDS.md).
For the front-end **Testing Triad**, adversarial guardrails, semantic locators, and release-tier
cadence, **must follow** [ops/UI_TESTING_ARCHITECTURE.md](ops/UI_TESTING_ARCHITECTURE.md).

## Why value-based tests

Shape-only tests (`assert "title" in result`) stay green when the title is wrong.
Librarian tests assert **exact** kinds, paths, issue numbers, HMAC failures, and job statuses.

> If your test would still pass when the function returns the wrong answer, it's not testing anything useful.

## How to write one

1. Create an ephemeral database in `tmp_path`.
2. Seed explicit known data (nullable fields included).
3. Call the real function. Mock only NZBFinder / SAB / LLM HTTP.
4. Assert exact values (`assert result["missing"] == ["2026-09"]`).
5. Cover empty, NULL, collision, and refuse-closed edges.

## Docs gate

Every user-facing change updates the relevant guide **and** adds a benefit-led `### Highlights` entry to `CHANGELOG.md`. Docs are a first-class deliverable.

## Commands

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[web,dev]"
LIBRARIAN_PBKDF2_ITERATIONS=1000 LIBRARIAN_SKIP_APP_BOOT=1 \
  LIBRARIAN_SESSION_SECRET=unit-test-session-secret-value \
  .venv/bin/python -m pytest tests/ -v
```

Coverage is configured in `pyproject.toml` (`--cov=librarian --cov-fail-under=70`).
**Every major-build sprint** must keep this floor and `cd frontend && npm test` green — new behavior
ships with value-based tests, not a later cleanup pass. See [ops/MAJOR_BUILDS.md](ops/MAJOR_BUILDS.md).

Front-end work **must follow** the Testing Triad and adversarial stance in
[ops/UI_TESTING_ARCHITECTURE.md](ops/UI_TESTING_ARCHITECTURE.md). **Vitest is still the target**
for Layer 1 and is not yet the runner (`cd frontend && npm test` uses Node `node --test`).
axe-core is wired: Playwright `@axe-core/playwright` in `e2e/axe.spec.ts` on **8794**.

## Layers

| Layer | Command | Secrets? |
| --- | --- | --- |
| Backend unit | `LIBRARIAN_PBKDF2_ITERATIONS=1000 LIBRARIAN_SKIP_APP_BOOT=1 .venv/bin/python -m pytest tests/ -v` | No |
| Frontend unit (Layer 1) | `cd frontend && npm test` (Node `node --test` today; Vitest is the target, not yet the runner) | No |
| Frontend build | `cd frontend && npm run build` | No |
| Playwright e2e (mocked) | `npm install && npx playwright install chromium && npm run test:e2e` | No (ephemeral owner seed) |
| axe-core | Playwright `@axe-core/playwright` on **:8794** (`e2e/axe.spec.ts`) | No |
| Docker health | `./docker-run.sh` then `GET /api/health` | Owner env only |

Backend coverage floor is **`--cov-fail-under=70`** (`pyproject.toml`). Mock NZBFinder, extra Newznab hosts, SABnzbd, LLM, Hardcover, Open Library, Comic Vine, MusicBrainz, Audiobookshelf, and RSS HTTP in unit tests. Live indexer/downloader pings stay opt-in (`POST /api/indexers/ping`) and out of default CI. **Never mock SQLite.**

Front-end proof is **DOM truth**, not mock-call arithmetic — see the Testing Triad in
[ops/UI_TESTING_ARCHITECTURE.md](ops/UI_TESTING_ARCHITECTURE.md).

## What to assert

| Area | Exact values |
| --- | --- |
| Health | `{"status": "ok"}` |
| Invites | garbage HMAC raises before DB; replay redeem fails; concurrent redeem one winner |
| Owner seed | env owner created once; weak password refused; different owner not clobbered |
| Kinds | `7030` → `comic`; `2000`/`5000`/`6000` → `None` |
| Identify | `Linux-Magazin.No.10.2026` → title + `2026-10` |
| Organize | `{Author}/{Title}/{Title}.epub` and collision → Review |
| Gaps | owned `2026-08` + `2026-10` → missing `["2026-09"]`; audiobook parts 1+3 → `["2"]`; Dune 1+3 vs Hardcover 1–3 → missing `"2"`; Comic Vine issues past local min/max; MusicBrainz track 4 when owned 1+3 |
| Find extras | extra host 502 still returns NZBFinder hits + `beyond_error`; RSS new guid once, TV `5000` refused; ABS ISBN match; no ABS token → no HTTP |
| SAB | history `Completed` → `completed`; addurl returns that `nzo_id` |
| Covers | Open Library URL is `https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg` |
| Enrich | Hardcover then Open Library fills description/series/year/cover; title lookup does not write ISBN |
| Goodreads CSV | ISBN13 `="978…"` matches catalog ISBN-10/13 onto Favorites; missing ISBN skipped |
| LLM | invented ISBN dropped; `kind=unknown` → Review |

Frontend unit tests for naming/filters/review copy land with the SPA polish pass.

## Playwright (mocked e2e)

Scaffold mirrors Projectionist’s pattern but uses Librarian ports:

| Role | Port |
| --- | --- |
| Product / Automat | **8793** |
| Playwright webServer | **8794** (default `E2E_PORT`) |

**Never** bind or point e2e at 8788 (Projectionist), 8790 (Smart Map), 8791/8792 (Lobby), or product 8793 (so reuseExistingServer cannot hit a live household instance). Projectionist’s e2e default is 8799 — Librarian stays on **8794**.

Use **semantic locators only** (`getByRole`, `getByLabel`). Do not query by CSS class, element id, or DOM path. Prefer Hall / Find / Review / Maintain / library-card journeys over theater/kiosk metaphors.

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

Librarian product is **8793**. Do not point tests at 8788 (Projectionist), 8790 (Smart Map), or 8791/8792 (Lobby). Playwright uses **8794**. Product ports and deploy live in [ops/AUTOMAT.md](ops/AUTOMAT.md).

## Related

- UI Testing Triad (Vitest target, not yet the runner; Playwright; axe wired in `e2e/axe.spec.ts`): [ops/UI_TESTING_ARCHITECTURE.md](ops/UI_TESTING_ARCHITECTURE.md)
- Major-build protocol (sprints, lanes, coverage, UX gates): [ops/MAJOR_BUILDS.md](ops/MAJOR_BUILDS.md)
- Handshake allowlist + proxy fail-closed: [SECURITY.md](SECURITY.md)
- Automat kit: [ops/AUTOMAT.md](ops/AUTOMAT.md)
