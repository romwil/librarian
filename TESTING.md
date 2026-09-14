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

## What to assert

| Area | Exact values |
| --- | --- |
| Health | `{"status": "ok"}` |
| Invites | garbage HMAC raises before DB; replay redeem fails; concurrent redeem one winner |
| Owner seed | env owner created once; weak password refused; different owner not clobbered |
| Kinds | `7030` → `comic`; `2000`/`5000`/`6000` → `None` |
| Identify | `Linux-Magazin.No.10.2026` → title + `2026-10` |
| Organize | `{Author}/{Title}/{Title}.epub` and collision → Review |
| Gaps | owned `2026-08` + `2026-10` → missing `["2026-09"]`; audiobook parts 1+3 → `["2"]` |
| SAB | history `Completed` → `completed`; addurl returns that `nzo_id` |
| Covers | Open Library URL is `https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg` |
| LLM | invented ISBN dropped; `kind=unknown` → Review |

Frontend unit tests for naming/filters/review copy land with the SPA polish pass.

## Related

- Playwright / docs gate: [docs/TESTING.md](docs/TESTING.md)
- Handshake allowlist + proxy fail-closed: [docs/SECURITY.md](docs/SECURITY.md)
- Automat kit: [docs/ops/AUTOMAT.md](docs/ops/AUTOMAT.md)
