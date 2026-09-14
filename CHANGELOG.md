# Changelog

## [Unreleased]

### Highlights

- **Automat-ready kit.** Maintainer playbook at `docs/ops/AUTOMAT.md`, `/config` + `/data` mounts that survive recreate, and a Hub `rollout.sh` stub for later. LAN truth is `http://10.10.1.202:8793` — not a public VIP.
- **Safe behind your reverse proxy.** `LIBRARIAN_TRUST_PROXY_HEADERS` is off unless you opt in. Spoofed `X-Forwarded-*` cannot mark cookies Secure, cannot rotate the login throttle, and cannot pretend the hop is HTTPS. Login and invite routes are rate-limited.

### Added

- `docs/ops/AUTOMAT.md` runbook (kit path, first-boot env, rsync, deploy).
- Proxy-header fail-closed (`librarian/proxy.py`) + per-IP rate limits on login / invite validate / redeem.
- `PUID`/`PGID` 99/100 on Unraid, `extra_hosts` for `downloader.sl` when the host can resolve it, `rollout.sh` Hub pull stub.

## [0.1.0] — 2026-09-14

Initial household reading-room kit on Automat.

### Highlights

- **The Hall, not a grabber.** FastAPI + Vite Reading Room on port **8793**, with owner / op / reader roles and invite-only join.
- **Stacks that know their kinds.** Books (EPUB), magazines, comics (CBZ + ComicInfo), audiobooks (Plex target by default), incoming music with Promote.
- **Honest gaps.** Local magazine `YYYY-MM` holes and comic issue-number holes — confirm before SAB.
- **Automat kit.** `/config` + `/data`, `docker-run.sh` on-host build, settings.json wins, no collision with 8788 / 8790 / 8791 / 8792.

### Added

- Python 3.12 package `librarian/` with SQLite WAL catalog, HMAC invites, NZBFinder v2 client, SABnzbd status machine, identify/organize, FTS search.
- Docs: README, DOCKER, TESTING, SECURITY, HELP, and the 2026-09-14 design spec.
