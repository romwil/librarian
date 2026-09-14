# Librarian

A household **library for readers** on Automat — books, magazines, comics (CBZ), audiobooks, and incoming music. People peruse shelves, see What’s New, open a work, and request what’s missing.

**Port 8793.** Automat already uses 8788 (Projectionist), 8790 (Smart Map), 8791/8792 (Lobby). Never collide those.

## Roles

| Role | Can |
| --- | --- |
| **owner** | Everything: Settings, indexers, SAB/LLM, people, invites, Review, gaps, queue, promote music |
| **op** | Invite readers; edit / Review / confirm gaps / queue downloads |
| **reader** | The Hall, local search, Favorites, download. Beyond-the-shelves **Request** files an “asked the house” slip (no SAB) |

Auth is on from first boot. The owner is seeded from Docker/env. New humans join only via HMAC invite.

## Local run

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[web,dev]"
cp .env.example .env
# set LIBRARIAN_OWNER_PASSWORD (≥ 8) and LIBRARIAN_SESSION_SECRET
cd frontend && npm install && npm run build && cd ..
DATA_DIR=./config PORT=8793 LIBRARIAN_SKIP_DOTENV=1 .venv/bin/python -m librarian.web
```

`GET /api/health` → `{"status":"ok","ok":true,...}` on [http://127.0.0.1:8793](http://127.0.0.1:8793).

Frontend hot reload: `cd frontend && npm run dev` (proxies `/api` to `:8793`).

## Docker / Automat

See [docs/DOCKER.md](docs/DOCKER.md) and the maintainer playbook [docs/ops/AUTOMAT.md](docs/ops/AUTOMAT.md). Kit path: `/mnt/user/appdata/librarian`. LAN check: `http://10.10.1.202:8793`. Never treat public DNS as version truth.

```bash
cp .env.example .env
./docker-run.sh
```

Volumes: `/config` (SQLite WAL + settings.json) and `/data` (media). settings.json wins over env. `docker-run.sh` does not wipe `./config`.

## Retriever and indexer

- SABnzbd: `http://downloader.sl`
- First indexer: NZBFinder Newznab **v2 JSON** (`api_token` + User-Agent)

Tokens never belong in git. `.env.example` keeps empty placeholders.

## Docs

- **[docs/ROADMAP.md](docs/ROADMAP.md)** — permanent build roadmap and status
- [docs/build-progress.md](docs/build-progress.md) — append-only shipped log
- [docs/ops/AUTOMAT.md](docs/ops/AUTOMAT.md) — Automat kit, LAN hosts, first-boot env
- [docs/DOCKER.md](docs/DOCKER.md) — volumes, PUID/PGID, extra_hosts
- [docs/TESTING.md](docs/TESTING.md) / [TESTING.md](TESTING.md) — value-based tests
- [docs/SECURITY.md](docs/SECURITY.md) — handshake allowlist, proxy trust, invite HMAC
- [docs/HELP.md](docs/HELP.md) — how to use The Hall
- [Design spec](docs/superpowers/specs/2026-09-14-librarian-design.md) — north star and UX contracts
- [Reading Room UX](docs/ux/reading-room.md) — brass tokens, peek, covers (mockups in `docs/ux/mockups/`)

## Tests

```bash
LIBRARIAN_PBKDF2_ITERATIONS=1000 LIBRARIAN_SKIP_APP_BOOT=1 .venv/bin/python -m pytest tests/
```

Coverage floor is **70%** (`--cov-fail-under=70`).
