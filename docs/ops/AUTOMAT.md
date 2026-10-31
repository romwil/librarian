# Automat environments — maintainer runbook

Task-first notes for the **Automat** Unraid host that runs Librarian. Audience: developers and Cursor agents working on this repo’s live stack — not generic install docs (see [DOCKER.md](../DOCKER.md)).

Jump to: [LAN hosts](#lan-hosts-source-of-truth) · [Kit](#kit--appdata) · [First boot](#first-boot-env) · [Deploy](#deploy-now-on-host-build) · [Backups](#backups-and-restore) · [Audiobookshelf](#audiobookshelf) · [See also](#see-also)

---

## LAN hosts (source of truth)

| Role | Base URL | Use for |
|------|----------|---------|
| **Librarian** | `http://10.10.1.202:8793` | SPA, liveness `GET /api/health` (`{"status":"ok"}` only), owner `GET /api/status` |
| **Audiobookshelf** | `http://10.10.1.202:13378` | Audiobook player. Reads `audiobooks` read-only |
| **Projectionist prod** | `http://10.10.1.202:8788` | Sibling app — **never** stop it for Librarian work |
| **Smart Map** | `http://10.10.1.202:8790` | Sibling app — **never** stop it |
| **Lobby / QA Lobby** | `:8791` / `:8792` | Projectionist theater — do not bind Librarian here |
| **Public hostname** | any `*.automat.vip` | Member-facing access only — **not** version or admin truth |

Prefer a direct LAN check. Public health is process-up only — version truth is the image stamp:

```bash
curl -s http://10.10.1.202:8793/api/health
# {"status":"ok"}
# On Unraid SSH — this is the always-applied version source of truth:
docker exec librarian cat /app/.build-info
# Owner session: GET /api/status → version, rev, built_at, notes_match (from the image, not /config)
```

**Never treat public DNS as version truth.** Agents (and humans) have concluded a household app was still on an older build by hitting a VIP or an SSH tunnel while LAN was already newer. `localhost:8793` on a maintainer laptop may be a tunnel — not a local `python -m librarian.web`. Do not parse version or rev from unauthenticated `/api/health`.

**Never bind Librarian or Audiobookshelf to 8788, 8790, 8791, 8792, 8793, or 8794.** Audiobookshelf uses **13378**.

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
├── config/                           # settings.json, librarian.db, session_secret, backups/ — KEEP; never wipe
├── .env                              # owner + session secret + indexer keys — not in git
├── docker-run.sh                     # on-host build — **current Automat path**
├── rollout.sh                        # Hub pull stub only (fails until image exists; not current truth)
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

Leave the Audiobookshelf lines blank until the player is up. The house URL is `http://10.10.1.202:13378`. See [Audiobookshelf](#audiobookshelf).

Leave `LIBRARIAN_TRUST_PROXY_HEADERS` **unset** until a trusted TLS proxy is in front.

---

## Deploy (now: on-host build)

```bash
ssh automat
mkdir -p /mnt/user/appdata/librarian/config /mnt/user/data
cd /mnt/user/appdata/librarian
./docker-run.sh
curl -s http://127.0.0.1:8793/api/health
# {"status":"ok"}
docker exec librarian cat /app/.build-info
```

`docker-run.sh` waits for `/api/health` (liveness), prints `/app/.build-info` (version truth), starts Audiobookshelf on **13378**, and does **not** wipe `./config` or `/mnt/user/appdata/audiobookshelf`. Owner `GET /api/status` reports `notes_match` from the image’s release notes, not `/config`.

**Do not invent Hub publish as the current Automat path.** There is no active `docker-release.sh` /
Hub pull-only ship for Librarian yet. `./rollout.sh` is a stub that fails until `romwil/librarian`
exists — use `./docker-run.sh` on the kit. Hub publish stays a later milestone.

Do **not** stop Projectionist (`:8788`) or Smart Map (`:8790`) while deploying Librarian.

---

## Backups and restore

The poller takes a SQLite snapshot of the catalog nightly (first poll after a new local day) into
`/mnt/user/appdata/librarian/config/backups/` (`/config/backups` in the container): the newest
**7 daily** (`librarian-YYYY-MM-DD.db`) and **4 weekly** (`librarian-weekly-YYYY-Www.db`). Each copy
is taken with SQLite's online backup, passes `PRAGMA integrity_check` before it is kept, and is
`0600` in a `0700` folder. A failed check keeps the older snapshots and shows on Maintain.
Maintain → **Nightly backup** shows the last backup.

`session_secret` and `settings.json` are **not** in a snapshot (they hold keys and API tokens).
They stay in `/config`; copy them separately if you rebuild the host.

Restore (the container must be stopped so nothing writes while you swap the file):

```bash
cd /mnt/user/appdata/librarian
docker stop librarian
mv config/librarian.db config/librarian.db.broken
rm -f config/librarian.db-wal config/librarian.db-shm
cp config/backups/librarian-YYYY-MM-DD.db config/librarian.db
chmod 600 config/librarian.db
./docker-run.sh
curl -s http://10.10.1.202:8793/api/health
```

Use a weekly file the same way when no daily is old enough. Keep `librarian.db.broken` until the
shelves look right.

Duplicate merge and Purge shells take their own named snapshots (`pre-duplicate-merge-*`,
`pre-purge-shells-*`, `pre-canonical-cleanup-*`). Those files are the
rollback for catalog mutations — not the 200-row Safe undo. Owner pass:
[CATALOG.md](CATALOG.md). **Do not merge or purge the live Automat catalog** until that walk
happens on a clone.

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

On Automat, library folders should be writable by PUID/PGID (often 99:100).
If titles were migrated as uid 1000 with mode 755, the lamp (99) cannot write
into author folders — Review **Apply** returns a PUID lock error (with the locked
path), and enrich falls soft for `cover.jpg` to `/config/covers/{id}/`. Prefer a
bulk host fix over one author at a time (Maintain surfaces the same tip):

```bash
# Prefer matching PUID to the folder owner, or grant group write:
chown -R 99:100 /mnt/user/data/media/library/books   # intentional after Calibre migrate
# chmod -R g+w /mnt/user/data/media/library/books      # milder alternative
```

Do **not** blindly `chmod -R 777`. Covers still show via `cover_path` when cached under `/config`.

### Audiobooks on Plex / Plexamp

Plex has no Audiobooks library type. Create a **Music** library named e.g. “Audiobooks” whose folder is `audiobooks_root`, enable track progress / long-form, and keep that folder out of the Plexamp music library (`music_root`).

## Audiobookshelf

The kit starts Audiobookshelf from the same host command as Librarian: `./docker-run.sh`. Compose service name is `audiobookshelf` in `docker-compose.yml` (same image, port, and mounts). Unraid does not use `docker compose up` for this kit.

| | |
|---|---|
| Image | `ghcr.io/advplyr/audiobookshelf:latest` |
| Container | `audiobookshelf` |
| Host port | **13378** → container port 80 |
| LAN | `http://10.10.1.202:13378` |
| Audiobooks | `/mnt/user/data/media/library/audiobooks` → `/audiobooks` **read-only** |
| Config | `/mnt/user/appdata/audiobookshelf/config` → `/config` |
| ABS metadata cache | `/mnt/user/appdata/audiobookshelf/metadata` → `/metadata` |

Config lives under appdata, **beside** the Librarian kit, not inside `/mnt/user/appdata/librarian`. The kit rsync does not touch it. Librarian remains the only writer of the audiobook folders.

Do not bind 8788, 8790, 8791, 8792, 8793, or 8794.

### First-time library setup

After `./docker-run.sh` on the host (do this on Automat, not from a laptop agent):

1. Open `http://10.10.1.202:13378` and create the Audiobookshelf admin account.
2. Add a library. Folder inside the container: `/audiobooks`. Media type: **Book**.
3. Create an API token for that admin user (Settings → Users → the account → API token).
4. Put the LAN URL and token in `/mnt/user/appdata/librarian/.env` (or Librarian Settings):

```
AUDIOBOOKSHELF_URL=http://10.10.1.202:13378
AUDIOBOOKSHELF_API_TOKEN=
```

Use the LAN URL, not `host.docker.internal`, so “Open in player” links work in a browser. Leave the token blank in git. Restart Librarian with `./docker-run.sh` so the container sees `.env`.

When both the URL and the token are set and the household has not saved an audiobook target, Librarian uses `audiobook_target=audiobookshelf`. A saved `plex` or `librarian_only` is left alone. Titles that are not linked still play in Librarian.

### What the scanner reads

New audiobooks shelve as `Author/Series/Book N - Title/` or `Author/Title/`. Beside the audio, organize writes:

- `metadata.json` — title, authors, series, year, description, ISBN, ASIN, narrator
- `desc.txt` — description, when there is one
- `reader.txt` — narrator, when there is one
- `cover.jpg` — when a real cover already exists or a cover fetch succeeds

After shelving, Librarian asks Audiobookshelf to scan. Match prefers ASIN, then ISBN, then title and author, and stores `abs_item_id` on the work. Existing folders are not moved until the cleanup job exists. Listening progress still syncs both ways for linked titles.

## Komga (comics federation)

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

- [INVITE_CHECKLIST.md](INVITE_CHECKLIST.md) — owner steps before first real invites (Public URL, Sorting morning, shells, mail off)
- [VOICEOVER.md](../a11y/VOICEOVER.md) — first VoiceOver script (login, join, Read, Listen, Sorting)
- [DOCKER.md](../DOCKER.md) — volumes, PUID/PGID, extra_hosts
- [SECURITY.md](../SECURITY.md) — handshake, proxy trust, cookies
- [automat-media-contract.md](../automat-media-contract.md) — shared `/data/media` roots with Smart Map
- [LIBRARY_MIGRATE.md](LIBRARY_MIGRATE.md) — library/* cutover + Calibre blend
- [CATALOG.md](CATALOG.md) — canonical works, duplicate merge after snapshot, shell owner pass
- [AGENTS.md](../../AGENTS.md) — boot / test / LAN table
