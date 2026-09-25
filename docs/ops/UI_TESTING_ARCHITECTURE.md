# UI & Testing Architecture

Canonical front-end testing stance for Librarian. Wire major-build gates through
[MAJOR_BUILDS.md](MAJOR_BUILDS.md); command inventory lives in [docs/TESTING.md](../TESTING.md)
and root [TESTING.md](../../TESTING.md).

## Core operational stance

The SPA is the **outermost perimeter**. Treat every user-facing surface as adversarial:

- Untrusted input (search, forms, settings fields, join tokens, query strings)
- Malicious / malformed payloads (XSS strings, oversized text, truncated UTF-8, control chars)
- Resource exhaustion (huge lists, rapid navigation, repeated submits)
- Async state abuse (double-clicks, overlapping fetches, mid-flight navigation, socket/API drops)

**No testing arithmetic** (counting mocks called, toggling in-memory flags) and **no mocked state
toggles** as proof that the UI is safe. Tests must prove **real DOM truth**: visible structure,
roles/labels users can perceive, and resilience under hostile interaction.

Backend value-based rules still apply ([TESTING.md](../../TESTING.md)): exact outcomes, not shape-only
asserts. Front-end unit and e2e extend that discipline to the DOM.

## Testing triad

| Layer | Job | Where it runs |
| --- | --- | --- |
| **1. Vitest** (target) | Logic, component contract, & fuzzing — isolated component state, pure utilities, input validation, malformed-payload fuzz | In-memory / jsdom (no live server) |
| **2. Playwright** | User journey, visual truth, & concurrency — e2e workflows, layout integrity, multi-viewport, slow-socket, browser races | Chromium against ephemeral server on **:8794** |
| **3. axe-core** | Semantic, layout, & access integrity — WCAG 2.1 AA, focus traps, keyboard Escape, Lights Up / Lights Down legibility | Playwright (or dedicated a11y runner) against primary entry points |

### Interim vs target (migration honesty)

**Target triad:** Vitest + Playwright + axe-core.

**Current interim:**

| Slot | Today | Next adoption |
| --- | --- | --- |
| Unit / contract / fuzz | Node’s built-in runner (`cd frontend && npm test` / `node --test`) | Focused **Vitest migration sprint** — do not boil-the-ocean mid-feature |
| Journey / visual / concurrency | Playwright scaffolded on dedicated port **8794** (product **8793**) | Grow matrix + adversarial journeys per release-tier cadence below |
| Access / semantic | Not wired yet | Add axe-core (dependency + smoke import in e2e) in a small dedicated patch; note for next patch release rather than cutting a release solely for scaffolding |

Until Vitest lands, treat `npm test` as the triad’s Layer 1 stand-in: same rigor (DOM/contract truth,
boundary fuzz on touched utilities), different runner.

**Ports:** Product / Automat = **8793**. Playwright webServer = **8794**.
**Never** document or bind Librarian on **8788**, **8790**, **8791**, or **8792**.

## Librarian surface map

Adapt Projectionist “theater / kiosk” language to the household reading room:

| Draft / theater language | Librarian equivalent |
| --- | --- |
| Theater shell / kiosk | Hall shell, top bar / rail chrome, auth gate (foyer login / join) |
| `/theater` entry | `/` (Hall), `/search` · Find, `/review` (Holds / bagging area), `/maintain`, library-card entry (`/login`, `/join`) |
| Dark / lights-down legibility | **Lights Down** theme (+ Lights Up contrast) in Appearance |
| Core chrome | Hall, top nav, Settings, auth gate — not every Maintain panel |

Primary axe / full-gauntlet entry points: `/`, login/setup, Hall, Review/Holds, Settings.

## Adversarial guardrails

### 1. Payload & input hostility

Prove the UI does not trust the wire or the form:

- **XSS / injection:** pasted script-like strings in search, name, settings paths, review drafts — must render as text, never execute or break the shell.
- **Truncation / exhaustion:** oversized titles, paths, and lists must not collapse layout or hang the main thread; overflow stays within Visual State Triad boundaries (below).
- **Form / action tampering:** disabled CTAs stay inert; double-submit does not duplicate side effects; forged query params do not leak owner-only chrome to guests.

Layer 1 owns pure validators and fuzz corpora; Playwright owns “hostile string still leaves Hall/Settings usable.”

### 2. State desync & concurrency

- Overlapping async (rapid Hall → Find → Review, slow `/api` responses) must not show stale tickets as current or blank the shell permanently.
- Connection drop / abort: loading regions recover to empty or error copy — no silent half-painted cards.
- Browser races (two tabs, back/forward during save): last coherent server truth wins; UI does not invent success.

Prefer real timing / route delays in Playwright over fake store flips.

### 3. Layout, visual, and focus bounding

**Semantic locators only** in Playwright (and Testing Library-style unit queries):

- Prefer `getByRole`, `getByLabel` (Playwright) / `getByLabelText` (Testing Library naming).
- **Banned in new e2e:** CSS class selectors, id selectors (`#…`), XPath/CSS path chains, and brittle DOM structure paths.
- `data-testid` may remain on product markup for unit source checks, but **e2e must not depend on it** once a role/label exists — migrate specs to roles/labels; treat leftover testid queries as debt.

**Visual State Triad** — every primary surface asserts at least:

| State | Meaning (Librarian) |
| --- | --- |
| **Empty / Unlit** | No data yet — Hall bare shelves, empty bagging area, quiet queue |
| **Loading / Interpolating** | Warming lamp / skeleton / `aria-busy` — not a blank white flash |
| **Overflow / Boundary** | Long titles, many tickets, narrow viewport — scroll/clip without covering chrome or trapping focus |

**Focus isolation:** overlays (What’s New, peek, dialogs) trap sensibly; **Escape** (and an explicit dismiss control) returns focus to a safe landmark. No focus leak into `aria-hidden` backdrop content.

## Cadence by release tier

Gate language for every ship: **zero unit failures**; lint as applicable (Ruff / frontend lint when present); **build succeeds** (`cd frontend && npm run build`). SPA size: **no unexplained Vite bundle size regressions** (investigate deltas; do not treat unexplained growth as green).

### Minor / patch

- Layer 1 (Vitest **or** current `npm test`) **mandatory** on touched surfaces + boundary fuzz for new/changed input paths.
- Playwright **targeted** to the touched feature/route (not the full matrix).
- axe: **passive / editor judgment** unless core chrome changed (Hall shell, top bar, Settings, auth gate) — then run axe on those entry points.

### Major / full gauntlet

- Full Layer 1 suite green.
- Playwright **matrix:** desktop ~1080p and a large desktop (4K-class) viewport, plus a **reasonable mobile / narrow** viewport. Librarian is a **household reading room**, not a theater kiosk — exercise Hall, Find, Review/Holds, Maintain, and library-card (`/login` / `/join`) entry points rather than a `/theater` path.
- axe **WCAG 2.1 AA** on primary entry points: `/`, login/setup, Hall, Review/Holds, Settings (Lights Up and Lights Down where theme toggles exist).
- Client-side fuzz on **unauthenticated** routes: no secret leakage into `localStorage` / `sessionStorage` / console (tokens, NZBFinder/SAB keys, session material).

Full-build closeout still pairs this with interactive browser QA on Automat LAN (`http://10.10.1.202:8793`) per [MAJOR_BUILDS.md](MAJOR_BUILDS.md).

## Sprint checklist (UI slice)

- [ ] Layer 1 green on touched FE (`cd frontend && npm test`; Vitest when migrated)
- [ ] Playwright: targeted (patch) or matrix (major) on **:8794**
- [ ] Semantic locators only in new/changed e2e
- [ ] Visual State Triad covered for touched primary surfaces
- [ ] axe when core chrome or major gauntlet applies
- [ ] `npm run build` succeeds; no unexplained bundle-size regression
- [ ] Backend pytest ≥70% still green when the sprint touches Python
