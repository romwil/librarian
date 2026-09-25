---
name: interactive-ui-qa
description: >-
  Run Interactive UI QA against Librarian Automat LAN (:8793) or local (:8793)
  in full or delta mode. Use when the user asks for browser QA, UI QA, absolute
  baseline, or delta regression. Prove visual triad and adversarial spots —
  never Projectionist ports (:8788/:8790/:8791/:8792/:8799); mocked e2e fallback
  is :8794 only.
---

# Interactive UI QA (Librarian)

Checklist-oriented browser QA for the household library SPA. Prefer
**cursor-ide-browser**. Prove [UI & Testing Architecture](../../rules/ui-testing-architecture.mdc)
on every in-scope surface — not page-load alone.

## When to use

- Browser / UI QA, absolute baseline, or delta retest
- After chrome / lexicon / delight ships
- Screenshot-reported UI bugs on Automat or local

Do **not** use for free-form exploratory discovery as the only method, or for hitting Projectionist/Smart Map.

## Target environment (hard rules)

| Item | Value |
|------|--------|
| Automat LAN | `http://10.10.1.202:8793` |
| Local | `http://127.0.0.1:8793` (`DATA_DIR=./config PORT=8793`) |
| Never | `:8788`, `:8790`, `:8791`, `:8792`, Projectionist e2e `:8799` |
| Mocked e2e fallback | `:8794` (`npm run test:e2e`) — not a live Automat substitute for delight walks |
| Credentials | Owner/member from the user’s local `.env` or Automat kit `.env` — **do not invent or log passwords** |

`localhost:8793` may be a tunnel to Automat — confirm with the user if version looks wrong.

## Modes

### `full` — absolute characterization

Hall → Find → Review/Holds → Maintain → Settings → Library card / auth gate. Both themes (Lights Up + Lights Down) once each. Visual triad on each primary surface. Write a dated notes file if the user wants artifacts (repo-local or path they name — do not invent a Projectionist `qa-scripts` tree).

### `delta` — default

Retest open bugs + surfaces matching recent CHANGELOG / files touched / user scope.

## Severity / verdict

| Severity | Meaning |
|----------|---------|
| `blocker` | Core path broken; auth break; data loss |
| `major` | Primary control wrong; serious layout/hydration on a primary surface |
| `minor` | Workaround exists |
| `polish` | Cosmetic / delight only |

**FAIL** if any `blocker` or `major` remains open. Page-load alone is **never** PASS.

## Architecture proofs

On each in-scope surface that accepts input, shows async state, or hosts an overlay:

- **Visual triad** — empty, loading (`aria-busy`), overflow/boundary
- **Semantic locators** — prefer role/label; no CSS/DOM-path inventing
- **Adversarial spots** — hostile paste in search/settings; double-submit; Escape restores focus
- **Lexicon** — prefer Holds desk / Library card / Shelving labels when asserting copy ([library-lexicon.mdc](../../rules/library-lexicon.mdc))

Stay defensive: no exploit PoCs.

## Primary surfaces (checklist seeds)

Extend this list when new chrome ships:

| ID | Surface | Pass sketch |
|----|---------|-------------|
| `hall` | `/` Hall | Loads; empty/loading readable; chrome intact |
| `find` | `/search` · Find | Search usable; hostile paste safe |
| `holds` | `/review` | Empty/load; Hold actions reachable |
| `maintain` | `/maintain` | Dock/status usable; no permanent whiteout |
| `settings` | Settings | Nav reachable; Shelving/Bagging section as shipped |
| `card` | `/login` · `/join` · Library card menu | Auth gate; member prefs entry |
| `theme` | Appearance | Lights Up + Lights Down once each in full runs |

## Procedure

1. Confirm mode (`full` \| `delta`) and host (Automat vs local).
2. Browser: desktop (~1280×800), then a narrow/mobile pass when chrome moved.
3. Exercise real clicks; grade findings; screenshot fails + representative gating/theme passes.
4. Report: Mode, Host, Verdict, Bugs, Checklist results.
