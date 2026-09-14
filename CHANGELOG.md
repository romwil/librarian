# Changelog

## [Unreleased]

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
