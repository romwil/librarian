# End-to-end and release testing

For **value-based backend unit tests**, see the root [TESTING.md](../TESTING.md).

## Docs gate

Every user-facing change updates the relevant guide **and** adds a benefit-led `### Highlights` entry to `CHANGELOG.md`. Docs are a first-class deliverable.

## Layers

| Layer | Command | Secrets? |
| --- | --- | --- |
| Backend unit | `LIBRARIAN_PBKDF2_ITERATIONS=1000 LIBRARIAN_SKIP_APP_BOOT=1 .venv/bin/python -m pytest tests/ -v` | No |
| Frontend build | `cd frontend && npm run build` | No |
| Docker health | `./docker-run.sh` then `GET /api/health` | Owner env only |

Mock NZBFinder, extra Newznab hosts, SABnzbd, LLM, Hardcover, Open Library, Comic Vine, MusicBrainz, Audiobookshelf, and RSS HTTP in unit tests. Live indexer/downloader pings stay opt-in (`POST /api/indexers/ping`) and out of default CI.

## Port trap

Librarian is **8793**. Do not point tests at 8788 (Projectionist), 8790 (Smart Map), or 8791/8792 (Lobby).
