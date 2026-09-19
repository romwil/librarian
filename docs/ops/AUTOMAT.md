# Automat environments — maintainer runbook

Task-first notes for the **Automat** Unraid host that runs Librarian. Audience: developers and Cursor agents working on this repo’s live stack — not generic install docs (see [DOCKER.md](../DOCKER.md)).

Jump to: [LAN hosts](#lan-hosts-source-of-truth) · [Kit](#kit--appdata) · [First boot](#first-boot-env) · [Deploy](#deploy-now-on-host-build) · [See also](#see-also)

---

## LAN hosts (source of truth)

| Role | Base URL | Use for |
|------|----------|---------|
| **Librarian** | `http://10.10.1.202:8793` | Version, `/api/health`, UI, “is it up?” |
| **Projectionist prod** | `http://10.10.1.202:8788` | Sibling app — **never** stop it for Librarian work |
| **Smart Map** | `http://10.10.1.202:8790` | Sibling app — **never** stop it |
| **Lobby / QA Lobby** | `:8791` / `:8792` | Projectionist theater — do not bind Librarian here |
| **Public hostname** | any `*.automat.vip` | Member-facing access only — **not** version or admin truth |

Prefer a direct LAN check:

```bash
curl -s http://10.10.1.202:8793/api/health
# Optional: confirm image metadata inside the container (on Unraid SSH)
# docker exec librarian cat /app/.build-info
```

**Never treat public DNS as version truth.** Agents (and humans) have concluded a household app was still on an older build by hitting a VIP or an SSH tunnel while LAN was already newer. `localhost:8793` on a maintainer laptop may be a tunnel — not a local `python -m librarian.web`.

**Never bind Librarian to 8788, 8790, 8791, or 8792.**

---

## Public SSL / household perimeter

Members may later reach the library through a **user reverse proxy** (Caddy / NPM / Cloudflare Tunnel). That hostname is TLS + proxy, not an extra auth layer. Treat every inbound packet as hostile; follow [SECURITY.md](../SECURITY.md).

| Topic | Automat note |
|-------|----------------|
| **Bind** | Container listens `0.0.0.0:8793`. Do not port-forward bare **8793** to the internet. |
| **Proxy trust** | Set `LIBRARIAN_TRUST_PROXY_HEADERS=1` **only** on the container behind Caddy/NPM. Never on a laptop tunnel. Untrusted `X-Forwarded-*` is ignored for client IP, rate limits, and `Secure` cookies. |
| **WAN** | Household auth is on from first boot. Spoofed forwarded proto/IP never unlocks a “trusted HTTPS” hop and never rotates the rate-limit key. |
| **SAB** | Retriever URL is `http://downloader.sl` (LAN DNS). `docker-run.sh` pins that hostname when the Unraid host can resolve it. |

---

## Kit / appdata

| Path | Where |
|------|--------|
| Unraid kit | `/mnt/user/appdata/librarian` |
| Config (DATA_DIR) | `/mnt/user/appdata/librarian/config` → `/config` |
| Media share | `/mnt/user/data` → `/data` |
| Port | **8793** |

```
/mnt/user/appdata/librarian/          # kit (Dockerfile, docker-run.sh, source)
├── config/                           # settings.json, librarian.db, session_secret — KEEP; never wipe
├── .env                              # owner + session secret + indexer keys — not in git
├── docker-run.sh                     # on-host build (current path)
├── rollout.sh                        # Hub pull later (romwil/librarian)
└── .source-rev                       # stamped at rsync time
```

**Do not** `git clone` into appdata as the long-term layout. Until Hub exists, the kit is a rsync of this checkout **minus** `.git/`, `.venv/`, `config/`, and `.env`. Development belongs on a maintainer laptop.

Same-named containers are stop/rm only — `./config` is never wiped.

### Sync kit from a real checkout

```bash
# From the laptop checkout (does not restart the container by itself)
git rev-parse --short HEAD > .source-rev
rsync -az --delete \
  --exclude '.git/' --exclude '.venv/' --exclude '.venv-test/' \
  --exclude 'node_modules/' --exclude 'frontend/node_modules/' \
  --exclude 'frontend/dist/' --exclude 'config/' --exclude '.env' \
  --exclude '__pycache__/' --exclude '.pytest_cache/' --exclude '.mypy_cache/' \
  --exclude '.ruff_cache/' --exclude 'htmlcov/' --exclude '.coverage' \
  ./ automat:/mnt/user/appdata/librarian/
```

---

## First-boot env

Seed `/mnt/user/appdata/librarian/.env` **on the host** from the operator. Do not invent production passwords in git.

Required:

| Variable | Notes |
|----------|-------|
| `LIBRARIAN_OWNER_USERNAME` | Default `owner` |
| `LIBRARIAN_OWNER_PASSWORD` | ≥ 8 characters |
| `LIBRARIAN_SESSION_SECRET` | Long random; generate on the host (`openssl rand -base64 48`). The public `librarian-dev-session-secret` is refused. If unset, a secret is written under `/config/session_secret` (mode `0600`). |

Typical Automat extras (same shape as Smart Map / Projectionist appdata `.env`):

```
TZ=America/New_York
PUID=99
PGID=100
SABNZBD_URL=http://downloader.sl
SABNZBD_API_KEY=
NZBFINDER_URL=https://nzbfinder.ws
NZBFINDER_API_TOKEN=
HARDCOVER_API_TOKEN=
NYT_BOOKS_API_KEY=
COMICVINE_API_KEY=
AUDIOBOOKSHELF_URL=
AUDIOBOOKSHELF_API_TOKEN=
```

Leave `LIBRARIAN_TRUST_PROXY_HEADERS` **unset** until a trusted TLS proxy is in front.

---

## Deploy (now: on-host build)

```bash
ssh automat
mkdir -p /mnt/user/appdata/librarian/config /mnt/user/data
cd /mnt/user/appdata/librarian
./docker-run.sh
curl -s http://127.0.0.1:8793/api/health
```

`docker-run.sh` waits for `/api/health`, prints `/app/.build-info`, and does **not** wipe `./config`.

**Later:** Hub `romwil/librarian` + pull-only `./rollout.sh X.Y.Z`. A host `docker build` is not Unraid CA proof.

Do **not** stop Projectionist (`:8788`) or Smart Map (`:8790`) while deploying Librarian.

---

## Media roots (`library/*`)

Librarian-owned trees live under `/data/media/library/{books,magazines,comics,audiobooks,incoming-music}`.
**Music stays** at `/data/media/music` (shared with Smart Map / Plexamp). Never put audiobooks in `music`.

Create empty siblings + dry-run Calibre blend before cutover:

```bash
./scripts/create-library-roots.sh /data/media
python -m librarian.migrate_library --media-root /data/media --migrate-books
# review collisions, then --apply for copy-then-cutover
```

Full operator steps (rebind Settings, Scan, archive old `books/`): [LIBRARY_MIGRATE.md](LIBRARY_MIGRATE.md).

### Audiobooks on Plex / Plexamp

Plex has no Audiobooks library type. Create a **Music** library named e.g. “Audiobooks” whose folder is `audiobooks_root`, enable track progress / long-form, and keep that folder out of the Plexamp music library (`music_root`).

### Komga (comics federation)

Librarian is the **sole writer** of `comics_root`. Komga (and Panels via Komga OPDS-PSE) are read clients.

Suggested compose mount for Komga on Automat:

```yaml
# fragment — keep in the media compose alongside Librarian
services:
  komga:
    image: gotson/komga
    volumes:
      - /mnt/user/data/media/library/comics:/comics:ro
    # …ports, appdata, PUID/PGID as usual
```

In Librarian Settings set `komga_url`, `komga_api_key`, and `komga_library_id` (the library whose root is `/comics`). After a successful comic organize, Librarian POSTs `/api/v1/libraries/{id}/scan` fail-soft. Work Peek offers **Open in Komga**. There is no in-app Guided View reader.

## See also

- [DOCKER.md](../DOCKER.md) — volumes, PUID/PGID, extra_hosts
- [SECURITY.md](../SECURITY.md) — handshake, proxy trust, cookies
- [automat-media-contract.md](../automat-media-contract.md) — shared `/data/media` roots with Smart Map
- [LIBRARY_MIGRATE.md](LIBRARY_MIGRATE.md) — library/* cutover + Calibre blend
- [AGENTS.md](../../AGENTS.md) — boot / test / LAN table
