# Librarian — Docker / Unraid

Librarian is a single container. The web UI listens on **8793**.

Everyday path **now:** on-host build with `docker-run.sh` (same early Smart Map kit). **Later:** Hub `romwil/librarian` + pull-only `rollout.sh`. Never treat public DNS as version truth; LAN host only.

## Ports — do not collide

| App | Port |
| --- | --- |
| **Librarian** | **8793** |
| Projectionist | 8788 |
| Smart Map / Projectionist QA | 8790 |
| Lobby / QA Lobby | 8791 / 8792 |

## Volumes

| Container | Host (Automat) | Purpose |
| --- | --- | --- |
| `/config` | `/mnt/user/appdata/librarian/config` | `settings.json`, `librarian.db` (WAL + shm), session secret |
| `/data` | `/mnt/user/data` (`DATA_HOST`) | books / magazines / comics / audiobooks / incoming-music / music |

SQLite WAL needs `librarian.db`, `librarian.db-wal`, and `librarian.db-shm` on the same mount. Keep `/config` on the cache pool.

`docker-run.sh` **never wipes** `./config`. Same-named containers are stop/rm only.

## Environment owner

On first boot `seed_env_owner` reads:

- `LIBRARIAN_OWNER_USERNAME` (default `owner`)
- `LIBRARIAN_OWNER_PASSWORD` (required, ≥ 8; refuse weak)
- `LIBRARIAN_SESSION_SECRET` (required; refuse the public development default)

Rotating the env password on restart updates the **same** username’s hash (Unraid lockout recovery). It never clobbers a different existing owner. The container serves `/api/health` before an owner exists; library APIs return 503 until one is seeded.

`settings.json` wins for keys already saved in the UI. Env fills missing keys. Blank secrets still take env until you save a key.

## Unraid (no Compose)

Stock Unraid has no Compose. Kit lives at `/mnt/user/appdata/librarian`:

```bash
ssh automat
cd /mnt/user/appdata/librarian
./docker-run.sh
```

Or Compose on a host that has it:

```bash
cp .env.example .env
DATA_HOST=/mnt/user/data docker compose up --build -d
```

Open **http://localhost:8793**.

## Data layout

| Path | Contents |
| --- | --- |
| `/config/settings.json` | Roots, SAB/NZBFinder/LLM, `audiobook_target` (file mode `0600`) |
| `/config/librarian.db` | Users, invites, works, files, jobs, shelves |

WAL-safe backup: `sqlite3 librarian.db ".backup 'librarian-YYYYMMDD.db'"` — do not copy only the `.db` file while the container is writing.

## Build caching

The image is **multi-stage**: Node builds the Vite SPA, then a slim Python runtime copies `frontend/dist` and installs `.[web]`. BuildKit is required for `--mount=type=cache`. `docker-run.sh` exports `DOCKER_BUILDKIT=1`.
