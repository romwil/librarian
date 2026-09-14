# Librarian security

Household library on a trusted LAN. Auth is **on from first boot**. There is no anonymous browse.

## Public handshake (exhaustive)

There is **no** `/api/auth/` prefix leak. Ingress matches **explicit method+path pairs**. If a route is not on this list, it needs a session.

| Method | Path |
| --- | --- |
| GET | `/api/health` |
| GET | `/api/features` |
| GET | `/api/invites/validate` |
| POST | `/api/invites/redeem/local` |
| POST | `/api/auth/local/login` |
| POST | `/api/auth/logout` |

`GET /api/auth/me` is **not** public. Session cookie: `librarian_session`, HttpOnly, SameSite=Lax; Secure when the request is HTTPS.

## Session secret (S2)

`LIBRARIAN_SESSION_SECRET` must be a long random value. The public development default `librarian-dev-session-secret` is **refused** — the process will not start with it. If env is unset, a secret is generated under `{DATA_DIR}/session_secret` (mode `0600`). Invite HMACs use this same secret.

## Invites

1. Raw token = `secrets.token_urlsafe(32)`. Stored as **SHA-256 hash only**.
2. URL token = `invite_id.raw.hmac` — HMAC-SHA256 over `LIBRARIAN_SESSION_SECRET`.
3. `parse_invite_token` fails closed **before** any DB lookup (no timing oracle on garbage).
4. TTL default 7 days. Status `pending` → `redeemed` | `revoked`.
5. **One SQLite transaction** (`BEGIN IMMEDIATE`): insert user + mark invite redeemed. Concurrent double-redeem: one winner.
6. Role comes from the invite (`reader` or `op`), never the joiner. Cannot redeem as `owner`.
7. Owner invites `op` or `reader`. Op invites `reader` only.

## Owner seed

`seed_env_owner` creates the local owner from `LIBRARIAN_OWNER_USERNAME` / `LIBRARIAN_OWNER_PASSWORD` (PBKDF2, ≥ 8 chars). Same username + rotated env password updates the hash. A **different** existing owner is never clobbered. Password is never logged.

## Bind (S3)

Default bind is `0.0.0.0:8793` so Docker port maps work. Do not port-forward bare 8793 to the WAN without a trusted TLS proxy. This is a household LAN app.

## Operator checklist

1. Set `LIBRARIAN_SESSION_SECRET` and a ≥ 8 owner password in the Unraid template / `.env`.
2. Keep NZBFinder and SAB keys out of git and out of backups you share.
3. Restrict who can mount `/config`.
4. Do not expose OpenAPI (it is disabled).
