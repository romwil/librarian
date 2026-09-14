# Librarian — Docker / Unraid

Librarian is a single container. The web UI listens on **8793**.

Everyday path **now:** on-host build with `docker-run.sh` (same early Smart Map kit). **Later:** Hub `romwil/librarian` + pull-only `rollout.sh`. Never treat public DNS as version truth; LAN host only — [ops/AUTOMAT.md](ops/AUTOMAT.md).

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
| `/config` | `/mnt/user/appdata/librarian/config` | `settings.json` (mode `0600`), `librarian.db` (WAL + shm), session secret |
| `/data` | `/mnt/user/data` (`DATA_HOST`) | books / magazines / comics / audiobooks / incoming-music / music |

SQLite WAL needs `librarian.db`, `librarian.db-wal`, and `librarian.db-shm` on the same mount. Keep `/config` on the **cache pool**, not the array.

`docker-run.sh` **never wipes** `./config`. Same-named containers are stop/rm only.

## Unraid user (PUID / PGID)

Media writes under `/data` should match linuxserver *arr / SABnzbd on this household.

| Variable | Automat default | Notes |
| --- | --- | --- |
| `PUID` | `99` | Unraid `nobody` |
| `PGID` | `100` | Unraid `users` |
| `TZ` | `America/New_York` | |

The entrypoint `chown`s `/config` when needed and drops privileges with `gosu`. `docker-run.sh` passes `99:100`; if those env vars are unset in a generic image run, the entrypoint falls back to `1000:1000`.

## extra_hosts / `.sl` DNS

SABnzbd is `http://downloader.sl`. Unraid Docker usually inherits host DNS. `docker-run.sh` also:

- always adds `host.docker.internal:host-gateway`
- pins `downloader.sl` to the host-resolved IP when `getent hosts downloader.sl` succeeds
- accepts `EXTRA_HOSTS=name:ip,name:ip` for other LAN names

Compose equivalent: `extra_hosts: ["host.docker.internal:host-gateway"]`. Add `downloader.sl:<LAN-IP>` only if the container cannot resolve `.sl`.

## Environment owner

On first boot `seed_env_owner` reads:

- `LIBRARIAN_OWNER_USERNAME` (default `owner`)
- `LIBRARIAN_OWNER_PASSWORD` (required, ≥ 8; refuse weak)
- `LIBRARIAN_SESSION_SECRET` (refuse the public development default; empty → auto-file under `/config`)
- `LIBRARIAN_TRUST_PROXY_HEADERS` (opt-in; default off — see [SECURITY.md](SECURITY.md))

Rotating the env password on restart updates the **same** username’s hash (Unraid lockout recovery). It never clobbers a different existing owner. The container serves `/api/health` before an owner exists; library APIs return 503 until one is seeded.

`settings.json` wins for keys already saved in the UI. Env fills missing keys. Blank secrets still take env until you save a key.

## Unraid (no Compose)

Stock Unraid has no Compose. Kit lives at `/mnt/user/appdata/librarian`:

```bash
ssh automat
cd /mnt/user/appdata/librarian
./docker-run.sh          # on-host build (current)
# ./rollout.sh           # Hub pull later — fails until romwil/librarian exists
```

When rsyncing the kit, stamp the checkout rev so `.build-info` is honest:

```bash
git rev-parse --short HEAD > .source-rev
```

Or Compose on a host that has it:

```bash
cp .env.example .env
DATA_HOST=/mnt/user/data docker compose up --build -d
```

Open **http://10.10.1.202:8793** on Automat LAN (not a public VIP).

## Data layout

| Path | Contents |
| --- | --- |
| `/config/settings.json` | Roots, SAB/NZBFinder/LLM, `audiobook_target` (file mode `0600`) |
| `/config/librarian.db` | Users, invites, works, files, jobs, shelves |
| `/config/session_secret` | Auto-generated when env is unset (mode `0600`) |

WAL-safe backup: `sqlite3 librarian.db ".backup 'librarian-YYYYMMDD.db'"` — do not copy only the `.db` file while the container is writing. Stop-then-copy the whole `config/` directory if you do not have `sqlite3` on the host.

```bash
docker stop librarian
cp -a /mnt/user/appdata/librarian/config /mnt/user/backups/librarian-$(date +%Y%m%d)
docker start librarian
```

## Build caching

The image is **multi-stage**: Node builds the Vite SPA, then a slim Python runtime copies `frontend/dist` and installs `.[web]`. BuildKit is required for `--mount=type=cache`. `docker-run.sh` exports `DOCKER_BUILDKIT=1`.

`.dockerignore` must keep host `*.egg-info`, `build/`, `dist/`, `.venv`, and `config/` out of `COPY .`.

## Related documentation

- [ops/AUTOMAT.md](ops/AUTOMAT.md) — kit path, LAN truth, first-boot env
- [SECURITY.md](SECURITY.md) — handshake, proxy trust, cookies
