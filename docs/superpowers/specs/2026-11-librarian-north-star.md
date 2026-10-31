# Librarian north star (2026-11)

The household **library for readers**. Not an admin grabber, not Calibre-in-a-browser, not Radarr or Sonarr with a lamp.

## The Hall is the living front

Sign-in lands on **The Hall**. Search is the hero. Rails that actually paint: Continue listening, Continue reading, Recently added, Favorites, New & noted. A chip row of kinds and named shelves (count ≥ 1) opens Browse. Unused payload keys are deleted, not left for a page that never reads them.

**Sorting** is the op desk for volumes that need a calm sort (`/review`). It is not Holds. There is no Place a hold.

**Downloads** is where a keeper confirms an Asked slip. Confirm-before-download is a **product control**, never legal safety. Wanted search and Get never send SABnzbd. Readers Ask the house.

## Asked → arrived

A reader who asks sees **Your asks** on the Library card: Looking, Waiting for the owner, On the way, On the shelf. `asked` locks further Wanted searches. When the volume is filed, the row is **arrived** — Wanted says On the shelf, not Asked. Keepers get `asked_confirm`. The asker gets `arrived`. An owner’s own grab does not ping them.

## Model picks

New York Times list names only appear when a NYT Books API key is set. Without it, those lanes are off unless the owner turns on **Show model picks**. They then read as Model picks, with the chip “Suggested by your language model.”

## Locked contracts

- Retriever: SABnzbd. Confirm on Downloads is the only start.
- `/data` ← host `/mnt/user/data`. Per-media roots are Settings paths.
- First indexer: **NZBFinder**. Extra Newznab hosts optional.
- Port **8793**. Never 8788 / 8790 / 8791 / 8792.
- Auth on from first boot. Roles **owner / op / reader**.
- Canonical catalog: one work, editions, authors (`work_authors` / `editions` / `work_identifiers`).
- Duplicate merge is snapshot-gated. Live Automat catalog is not mutated by a merge run.
- Fonts stay in the house. CSP `script-src 'self'`. `robots.txt` Disallow and `X-Robots-Tag: noindex`.
- `LIBRARIAN_TRUST_PROXY_HEADERS` is opt-in.
