# Testing Guide

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
ships with value-based tests, not a later cleanup pass. See [docs/ops/MAJOR_BUILDS.md](docs/ops/MAJOR_BUILDS.md).

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

## Related

- Playwright / docs gate: [docs/TESTING.md](docs/TESTING.md)
- Major-build protocol (sprints, lanes, coverage, UX gates): [docs/ops/MAJOR_BUILDS.md](docs/ops/MAJOR_BUILDS.md)
- Handshake allowlist + proxy fail-closed: [docs/SECURITY.md](docs/SECURITY.md)
- Automat kit: [docs/ops/AUTOMAT.md](docs/ops/AUTOMAT.md)
