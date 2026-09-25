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

## 4. GitHub release cadence

End of sprint:

1. CHANGELOG `### Highlights` (benefit-led)
2. Bump `pyproject.toml` + `frontend/package.json` in lockstep
3. Commit → push → tag when that is the house habit
4. Automat smoke: `./docker-run.sh` then `GET http://10.10.1.202:8793/api/health`

Release **feature names** match sprint IDs (PR title / CHANGELOG / What’s New).

**Never bind or document Librarian on 8788, 8790, 8791, or 8792.** Product port is **8793**.

## 5. UX verification (Playwright + interactive browser)

### Playwright (mocked e2e)

- Dedicated port **8794** — not product **8793**, not Automat 8788 / 8790 / 8791 / 8792, and not Projectionist’s e2e default 8799.
- No live NZBFinder / SABnzbd required; ephemeral `DATA_DIR` + seeded owner.
- Assert lexicon strings, Hall empty states, Review/Holds empty/load, Settings nav, warm-load copy, reduced-motion smoke as those surfaces land.

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

After the final sprint of a major build: full pytest + frontend unit + Playwright suite + interactive Hall → Find → Review/Holds → Maintain → Library card pass on Automat LAN (`http://10.10.1.202:8793`).

## 6. Kickoff loop (orchestrator)

1. Refresh codegraph; confirm lanes and owners.
2. Start all **currently unblocked** lanes in parallel.
3. On lane green: merge, run coverage gate, cut GitHub release if sprint-complete.
4. Immediately launch newly unblocked work.
5. After final sprint: full-build QA; only then declare the major build done.

## Sprint gate checklist

- [ ] Backend: `LIBRARIAN_PBKDF2_ITERATIONS=1000 LIBRARIAN_SKIP_APP_BOOT=1 .venv/bin/python -m pytest tests/` (≥70% coverage)
- [ ] Frontend unit: `cd frontend && npm test`
- [ ] Playwright: `npm run test:e2e` (when the sprint touches UI or as baseline smoke)
- [ ] CHANGELOG `### Highlights` + version bump
- [ ] Automat `./docker-run.sh` smoke on `:8793` when shipping to the household host
