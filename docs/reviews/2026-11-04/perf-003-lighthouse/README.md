# PERF-003 — Lighthouse Hall / Search baseline

Captured **2026-11-06** against Automat LAN `http://10.10.1.202:8793` (product **1.0.11**).

## Artifacts

| File | Route | Form factor | Notes |
| --- | --- | --- | --- |
| `2026-11-06-hall-desktop.json` | `/` | desktop | Full Lighthouse performance JSON |
| `2026-11-06-hall-390.json` | `/` | mobile 390×844 | Same |
| `2026-11-06-search-desktop.json` | `/search` | desktop | Same |
| `2026-11-06-search-390.json` | `/search` | mobile 390×844 | Same |
| `2026-11-06-summary.json` | — | — | Extracted LCP / CLS / transfer |
| `2026-11-06-owner-session-vitals.json` | `/` + `/search` | live owner tab | CDP PerformanceObserver LCP (signed-in) |

## How to re-run

```bash
# Foyer / unauthenticated shell (no cookie):
node scripts/capture-lighthouse.mjs

# Signed-in Hall/Search (HttpOnly cookie from a browser session):
BASE_URL=http://10.10.1.202:8793 COOKIE='librarian_session=…' node scripts/capture-lighthouse.mjs
```

## Budget rule

Treat this folder as the **baseline**. Later releases: median of three runs; fail only on unexplained **>10% LCP** regression (or CLS / transfer spike) vs these numbers — do not cargo-cult micro-optimizations.
