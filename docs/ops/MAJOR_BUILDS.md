# Major builds protocol

Canonical process for multi-sprint Librarian feature arcs (and every major build after).
Baseline for the living-library arc: **0.4.15**; Phase 0 protocol ship is **0.4.16** (`major-build-protocol`).

Each **sprint** = one **GitHub feature release** (CHANGELOG `### Highlights` + version bump + push + Automat smoke). Phases group sprints. Automat stays **host `./docker-run.sh`** until Hub is its own milestone — do not invent Hub docker-release as the Automat path.

## 1. Codegraph first (local intelligence)

- Prefer [`.codegraph/`](../../.codegraph/) for symbol lookup, callers/callees, and navigation before blind `rg` sweeps.
- Refresh before kickoff and after large moves (router split, new packages):

```bash
codegraph sync    # incremental
# or after big moves:
codegraph index -f
```

- If MCP codegraph is inactive for the session, still use the local index / CLI. Do not invent architecture from memory.
- `.codegraph/` is gitignored — local only.

## 2. Parallel agents without collisions

- Split work into **lanes** with **exclusive file ownership** (table per phase in the build plan). One agent owns a lane; no two agents edit the same files.
- Shared seams (`copy.js`, `app.py` until split, `settingsNav.js`) are **single-writer** or sequenced behind a merge steward.
- Launch the next **unblocked** lane as soon as its dependencies land — do not wait for a whole phase if a sprint gate is green.
- Prefer Task/subagents for isolated lanes; the orchestrator merges, runs gates, and cuts the GitHub release.

## 3. Coverage stays green while we build

- **Every sprint PR/ship** keeps backend coverage ≥ **70%** (`pyproject.toml` `--cov-fail-under=70`) and frontend unit tests green (`cd frontend && npm test`).
- New behavior ships **with** value-based tests — see [TESTING.md](../../TESTING.md). Not a cleanup pass later.
- Coverage must not drop relative to the prior release on touched packages; if a refactor shrinks lines, replace with tests on the new surface.
- Mock NZBFinder / SAB / LLM HTTP only; **never mock SQLite**.
- Front-end ships follow the **Testing Triad** and release-tier cadence in
  [UI_TESTING_ARCHITECTURE.md](UI_TESTING_ARCHITECTURE.md) (target: Vitest + Playwright + axe-core;
  interim Layer 1 = Node `npm test` until the Vitest migration sprint).

## 4. GitHub release cadence

End of sprint:

1. CHANGELOG `### Highlights` (benefit-led)
2. Bump `pyproject.toml` + `frontend/package.json` in lockstep
3. Commit → push → tag when that is the house habit
4. Automat smoke: `./docker-run.sh` then `GET http://10.10.1.202:8793/api/health`

Release **feature names** match sprint IDs (PR title / CHANGELOG / What’s New).

**Never bind or document Librarian on 8788, 8790, 8791, or 8792.** Product port is **8793**.

## 5. UX verification (Testing Triad + interactive browser)

Canonical rules: [UI_TESTING_ARCHITECTURE.md](UI_TESTING_ARCHITECTURE.md) — adversarial perimeter,
semantic locators, Visual State Triad, and **cadence by release tier** (minor/patch vs major/full gauntlet).

**Sprint / patch UI gate:** Layer 1 on touched surfaces + targeted Playwright; axe when core chrome
(Hall shell, top bar, Settings, auth gate) changes. **Major / full-build closeout:** full Layer 1,
Playwright viewport matrix (desktop 1080p/4K-class + reasonable mobile), axe WCAG 2.1 AA on `/`,
login/setup, Hall, Review/Holds, Settings, plus unauthenticated client-side fuzz for secret leakage.
Gate language: zero unit failures; lint as applicable; build succeeds; no unexplained SPA bundle
size regressions.

### Playwright (mocked e2e)

- Dedicated port **8794** — not product **8793**, not Automat 8788 / 8790 / 8791 / 8792, and not Projectionist’s e2e default 8799.
- No live NZBFinder / SABnzbd required; ephemeral `DATA_DIR` + seeded owner.
- **Semantic locators only** (`getByRole`, `getByLabel`) — no CSS class/id/path selectors.
- Assert lexicon strings, Hall empty/loading/overflow, Review/Holds empty/load, Settings nav, warm-load copy, reduced-motion smoke as those surfaces land.

```bash
# once per machine
cd /path/to/librarian && npm install
npx playwright install chromium

npm run test:e2e
# or: cd frontend && npm run test:e2e
```

Override with `E2E_PORT` / `E2E_BASE_URL` when needed. Server launcher: `scripts/start-e2e-server.mjs`.

### Interactive browser

After Automat deploy or local build, walk delight/alive criteria on the real SPA with `cursor-ide-browser` — especially screenshot-reported issues. Trust scrolled UI, not bundle greps.

### Full-build closeout

After the final sprint of a major build: full pytest + frontend unit (Layer 1) + Playwright matrix +
axe on primary entry points (when wired) + interactive Hall → Find → Review/Holds → Maintain →
Library card pass on Automat LAN (`http://10.10.1.202:8793`).

## 6. Kickoff loop (orchestrator)

1. Refresh codegraph; confirm lanes and owners.
2. Start all **currently unblocked** lanes in parallel.
3. On lane green: merge, run coverage gate, cut GitHub release if sprint-complete.
4. Immediately launch newly unblocked work.
5. After final sprint: full-build QA; only then declare the major build done.

## Sprint gate checklist

- [ ] Backend: `LIBRARIAN_PBKDF2_ITERATIONS=1000 LIBRARIAN_SKIP_APP_BOOT=1 .venv/bin/python -m pytest tests/` (≥70% coverage)
- [ ] Frontend unit (Layer 1): `cd frontend && npm test` — Vitest when migrated; see [UI_TESTING_ARCHITECTURE.md](UI_TESTING_ARCHITECTURE.md)
- [ ] Playwright: `npm run test:e2e` on **:8794** — targeted for patch UI; full matrix for major closeout
- [ ] axe WCAG 2.1 AA when core chrome touched or on major gauntlet (once axe-core is wired)
- [ ] `cd frontend && npm run build` succeeds; no unexplained Vite bundle-size regression
- [ ] CHANGELOG `### Highlights` + version bump
- [ ] Automat `./docker-run.sh` smoke on `:8793` when shipping to the household host
