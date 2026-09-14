# Librarian security

Living brief for operators. Status values move between **Open**, **Mitigated**, and **Accepted**. Residual notes describe what remains after mitigations.

## Scope

| In scope | Out of scope |
|----------|----------------|
| Web UI + FastAPI control plane (`librarian/web/`) | Host OS / Unraid / Docker daemon hardening |
| Household auth (local password) + session cookies | Supply-chain / dependency CVE hunting |
| Invite mint / validate / redeem | Multi-tenant SaaS isolation |
| Default Docker / Unraid packaging (non-root via `gosu`) | Third-party NZBFinder / SABnzbd / LLM hosts |

**Trust assumption:** TLS encrypts the pipe; it does not replace household auth. Auth is **on from first boot**. There is no anonymous browse, no guest tour, no self-serve signup. Unauthenticated callers get the exhaustive public handshake below — nothing else.

## Threat model

### Trusted LAN

Typical Unraid / Docker deploy on a private network. Neighbors on the same VLAN (or a compromised device) can hit `:8793`. Default bind is all interfaces (S3). Keep the host on a trusted segment; do not port-forward bare 8793.

### Guest / IoT Wi‑Fi

Guest SSID clients that share L2/L3 with the host are the same as LAN attackers for this app.

### Accidental WAN / reverse proxy

Port-forwarding or exposing `8793` (or a reverse proxy without this app’s auth) exposes login, invite redeem, and — with a stolen session — the catalog, SAB queue, and indexer tokens.

Session forging is trivial if `LIBRARIAN_SESSION_SECRET` is left at the public development default (S2 — refused). Spoofed `X-Forwarded-*` on a direct LAN bind must **not** set `Secure` cookies, must **not** rotate the rate-limit key, and must **not** be treated as a trusted HTTPS hop (S9 / S14).

`LIBRARIAN_TRUST_PROXY_HEADERS=1` is **opt-in, default off.** Set it only on the container that sits behind Caddy / NPM / a Cloudflare Tunnel that you control. Never on a laptop SSH tunnel.

### Public household perimeter

There is **no** `/api/auth/` prefix leak. Ingress matches **explicit method+path pairs** in `PUBLIC_HANDSHAKE_EXACT` (`librarian/auth.py`). If a route is not on this list, it needs a session.

**Exhaustive unauthenticated handshake:**

| Method | Path | Notes |
|--------|------|--------|
| `GET` | `/api/health` | Liveness |
| `GET` | `/api/features` | Stripped flags (household name, owner ready, auth methods) |
| `GET` | `/api/invites/validate` | HMAC-verified token; fail closed; **30 / IP / min** |
| `POST` | `/api/invites/redeem/local` | Local join on a valid invite; **10 / IP / min** |
| `POST` | `/api/auth/local/login` | Existing local users only; **10 / IP / min** |
| `POST` | `/api/auth/logout` | Clears cookie |

Not public: `GET /api/auth/me`, `POST /api/auth/local/register` (no such route), whole `/api/auth/` prefix, Hall, search, settings, queue, Review, People.

```text
SPA ──no session──► /login (foyer) or /join?token=
     ──no session──► exhaustive handshake; else 401
```

**Invites:** URL token is `invite_id.raw.hmac` (HMAC over the session secret). Raw material is hashed at rest (SHA-256). Garbage tokens fail closed without a DB timing oracle. Member insert and `status='redeemed'` happen in **one SQLite transaction**; concurrent double-redeem has one winner. Roles are **owner | op | reader**. Cannot redeem as `owner`. Owner invites `op` or `reader`. Op invites `reader` only.

**Session cookie** (`librarian_session`): HttpOnly, SameSite=Lax, path `/`. **Secure only when the request is actually HTTPS** (`request.url.scheme` or **trusted** `X-Forwarded-Proto: https`). Untrusted forwarded proto is ignored.

**Owner seed:** `LIBRARIAN_OWNER_USERNAME` / `LIBRARIAN_OWNER_PASSWORD` (PBKDF2, ≥ 8). Same username + rotated env password updates the hash. A different existing owner is never clobbered. Password is never logged.

## Findings

| ID | Severity | Location | Exploit one-liner | Status | Residual risk |
|----|----------|----------|-------------------|--------|---------------|
| **S1** | Critical | Control-plane routes without a session. | Unauthenticated `curl` to Hall / settings / queue. | **Mitigated** | Explicit handshake allowlist; no `/api/auth/` wildcard. |
| **S2** | Critical | Session secret fell back to a public default. | Forge `librarian_session` cookies for any `user_id`. | **Mitigated** | Public `librarian-dev-session-secret` refuses to start; empty env auto-generates under `/config/session_secret` (0600). Still set `LIBRARIAN_SESSION_SECRET` in production. |
| **S3** | Critical | App binds `0.0.0.0:8793` in Docker. | Reach the control plane from any host interface / accidental WAN map. | **Open** | Do not port-forward bare 8793; put TLS on a reverse proxy and set proxy trust only there. |
| **S9** | Medium | Session cookie `Secure` from spoofed proto. | Weaker cookie story; CSRF edge cases on a “HTTPS” lie. | **Mitigated** | `Secure` only on socket HTTPS or trusted forwarded proto. |
| **S11** | Medium | Settings JSON stores indexer / SAB keys in plaintext under `/config`. | Read volume / backup → fleet credentials. | **Mitigated** | File mode `0600` on every save. Restrict who can mount `/config`. |
| **S13** | Low | Image historically ran as root. | Container breakout has root inside the image. | **Mitigated** | Entrypoint `chown`s `/config` and drops via `gosu` to `PUID`/`PGID` (Unraid 99/100). |
| **S14** | High | Rate limiter trusted `X-Forwarded-For` on a direct LAN bind. | Rotate spoofed IPs to bypass login / invite throttles. | **Mitigated** | Ignore forwarded headers unless `LIBRARIAN_TRUST_PROXY_HEADERS=1`. |
| **S15** | Medium | FastAPI `/docs` / OpenAPI without auth. | Map mutate endpoints from the LAN. | **Mitigated** | Docs disabled (`docs_url=None`). |
| **S18** | High | Invite redeem created the user then burned the token in a second write. | Crash window: unburned token or orphan user; replay. | **Mitigated** | HMAC on the URL token; hash at rest; insert + redeem in one transaction. |

## Operator checklist

1. **Do not expose bare `8793` to the internet.** Put TLS on Caddy/NPM/Cloudflare Tunnel in front.
2. Set **`LIBRARIAN_TRUST_PROXY_HEADERS=1` only behind that trusted proxy.** Untrusted `X-Forwarded-*` is ignored for client IP, rate limits, `Secure` cookies, and any “this is HTTPS” decision.
3. Set **`LIBRARIAN_SESSION_SECRET`** to a long random value (or accept auto-generated secret under Config). Invite HMACs use this secret. Never commit it. The public development default is refused.
4. Set **`LIBRARIAN_OWNER_PASSWORD`** (≥ 8) in the Unraid template / `.env`. Do not log it.
5. Keep NZBFinder / SAB keys out of git and out of backups you share. `settings.json` is `0600`.
6. Restrict who can mount/read the `/config` volume (session secret + recovery).
7. Automat LAN hosts: [ops/AUTOMAT.md](ops/AUTOMAT.md). Never treat public DNS as version truth.

## Rotating secrets

WAL-safe database backup steps live in [DOCKER.md](DOCKER.md).

1. **Revoke/reissue at the provider first** (NZBFinder token, SAB API key, LLM key).
2. **Update Librarian** — Settings UI (owner) or `.env` + restart.
3. **Verify**, then confirm the old secret is dead.

| Secret | Field / var | Notes |
|--------|-------------|-------|
| Session secret | `LIBRARIAN_SESSION_SECRET` | Rotating invalidates every signed-in session and outstanding invite HMAC |
| Owner password | `LIBRARIAN_OWNER_PASSWORD` | Same username on restart updates the hash (lockout recovery) |
| NZBFinder | `nzbfinder_api_token` | Settings or env; never in git |
| SABnzbd | `sabnzbd_api_key` | Settings or env |
| LLM | `llm_api_key` | Optional |

**Honest limits.** Rotating a key here does not retroactively scrub it from old container logs, shell history, or prior backups.

## Related docs

- [ops/AUTOMAT.md](ops/AUTOMAT.md) — kit path, LAN truth, first-boot env
- [DOCKER.md](DOCKER.md) — volumes, PUID/PGID, backups
- [TESTING.md](TESTING.md) — handshake + proxy fail-closed tests
