# Librarian roadmap

Living product/build source of truth: what’s shipped, what’s next, and the longer horizon.
Flip boxes when a slice ships. Append the story to [build-progress.md](build-progress.md).
Design north star: [2026-09-14 librarian design](superpowers/specs/2026-09-14-librarian-design.md).
Major-build cadence: [ops/MAJOR_BUILDS.md](ops/MAJOR_BUILDS.md).
Active staged plan (agent pickup): `~/.cursor/plans/librarian_unified_recommend_dd19f677.plan.md`.

---

## 1. Status / current version

| | |
| --- | --- |
| **Date** | 2026-09-27 |
| **Branch** | `main` |
| **Version** | **0.5.9** |
| **Arc** | Living-library Phases **0–5** complete; Phase R done; Phase D — **D2** `ingest-preview` + `beautiful-finished` → **0.5.9**. |
| **Green** | pytest coverage floor **70%**; frontend `npm test`; Playwright e2e on **8794**. LAN truth `http://10.10.1.202:8793`. |
| **Next** | **D3** `shelf-health-score` + `reading-room-calm` (see §3 / unified plan). |
| **Automat** | Host `./docker-run.sh` only. Hub `romwil/librarian` deferred. Never bind **8788 / 8790 / 8791 / 8792**. |

---

## 2. Shipped

### Living-library major build (Phases 0–5)

| Phase | Sprint | Feature | Version | Status |
| --- | --- | --- | --- | --- |
| 0 | — | `major-build-protocol` | 0.4.16 | done |
| 1 | 1.1 | `review-get-readonly` | 0.4.17 | done |
| 1 | 1.2 | `unified-progress` | 0.4.18 | done |
| 1 | 1.3 | `dead-weight-docs-truth` | 0.4.19 | done |
| 2 | 2.1 | `web-routers-shelf-health` | 0.4.20 | done |
| 3 | 3.1 | `mail-transport` | 0.4.21 | done |
| 3 | 3.2 | `notifications-inbox` | 0.4.22 | done |
| 3 | 3.3 | `newsletters-edition` | 0.4.23 | done |
| 4 | 4.1 | `library-lexicon` | 0.4.24 | done |
| 4 | 4.2 | `ux-alive-pass` | 0.4.25 | done |
| 5 | 5.1 | `tonights-shelf-alive` | **0.5.0** | done |
| 5 | 5.2 | `smart-holds-desk` | 0.5.1 | done |
| 5 | 5.3 | `lamp-rituals` | 0.5.2 | done |

Full-build QA closed with 0.5.2. Patches: **0.5.3** enrich author placeholder; **0.5.4** notification email clear sticks. **R1** `security-perimeter` → **0.5.5**. **R2** `queue-and-dock-calm` → **0.5.6**. **R3** `api-boundary` → **0.5.7**. **D1** `morning-brief` + `series-catch-up` → **0.5.8**. **D2** `ingest-preview` + `beautiful-finished` → **0.5.9**.

### Library-first kit (pre-arc, still true)

Auth (owner/op/reader, invite HMAC, session refuse-default), NZBFinder v2 + SAB, identify/organize/Review, catalog FTS + scan/enrich/Hardcover/OL, gaps + Find confirm, Reading Room SPA (Hall / Search / Find / Discover / peek / reader), Automat kit on `:8793`. Details: [CHANGELOG.md](../CHANGELOG.md), [build-progress.md](build-progress.md).

---

## 3. Next staged sprints (active build)

Remediation first (2026-09-25 review Critical/High), then Top-10 delight. Each sprint = one GitHub feature release. Parallel lanes + exclusive file ownership per [MAJOR_BUILDS](ops/MAJOR_BUILDS.md). Do **not** bump version here until the sprint ships.

| Sprint | Feature | Version | Focus |
| --- | --- | --- | --- |
| **R1** | `security-perimeter` | **0.5.5** | **done** — SPA jail; indexer scrub; cover/download + organize preview jails; cover URL SSRF allowlist |
| **R2** | `queue-and-dock-calm` | **0.5.6** | **done** — `GET /api/queue` readonly; Maintain dock idle + hidden-tab pause; auth-gate `owner_ready` cache |
| **R3** | `api-boundary` | **0.5.7** | **done** — allowlist `public_work` + admin serializer; explicit router imports; `route_imports` hub deleted (catalog split deferred) |
| **D1** | `morning-brief` + `series-catch-up` | **0.5.8** | **done** — Maintain morning desk (“tend these three”) + Hall series catch-up invitation |
| **D2** | `ingest-preview` + `beautiful-finished` | **0.5.9** | **done** — Look first ingest map + Finished ceremony whisper |

After D2: continue Phase D sequenced Top-10 (one owner + one reader per minor when possible). See unified plan.

---

## 4. Top-10 delight backlog

Score and ship at most **one owner + one reader** delight per minor unless tiny. Every delight PR: reduced-motion path, lights-up + lights-down, one-line “why this feels alive” in CHANGELOG.

### Owner

| # | Item | Status |
| --- | --- | --- |
| 1 | **Morning shelf brief** — Maintain as morning desk; “tend these three,” not a KPI strip | **landed** 0.5.8 |
| 2 | **Smart Review inbox** → Smart Holds desk | **landed** 0.5.1 |
| 3 | **Ingest preview** — quiet map before the lamp shelves a dump | **landed** 0.5.9 |
| 4 | **Shelf health score** — living pulse + one tend action | open |
| 5 | **Indexer scorecard** — hosts as lanterns; mute a sick host | open |
| 6 | **Quiet hours that wake up** | polish (mail/notify shipped 0.4.21–0.4.22) |
| 7 | **Ask-the-house digest** | polish (newsletters 0.4.23) |
| 8 | **Safe undo for grooming** | open |
| 9 | **Deploy What’s New that never lies** | open |
| 10 | **One-button re-normalize Calibre dump** | open |

### Reader / household

| # | Item | Status |
| --- | --- | --- |
| 1 | **Tonight’s Shelf that feels alive** | **landed** 0.5.0 |
| 2 | **Series catch-up** — missing issues as invitation | **landed** 0.5.8 |
| 3 | **Beautiful Finished** (+ optional household whisper) | **landed** 0.5.9 |
| 4 | **Reading room calm** | open |
| 5 | **Listen that remembers** | open |
| 6 | **Peek that teaches** | open |
| 7 | **Named household shelves** | open |
| 8 | **Gaps as gifts** | open |
| 9 | **Search that forgives** | open |
| 10 | **Lamp rituals** | **landed** 0.5.2 |

Personalized recs and HTML scrape of indexer Discover remain **skipped on purpose**.

---

## 5. Review debt (2026-09-25)

Full write-up: [reviews/review-2026-09-25.md](reviews/review-2026-09-25.md). Ship Critical before more feature growth; land High before more delight surface leans on leaky shapes.

### Critical

| ID | Issue | Target sprint |
| --- | --- | --- |
| [P3-CRIT-01](reviews/review-2026-09-25.md#p3-crit-01--unauthenticated-spa-path-traversal) | Unauthenticated SPA catch-all path traversal | R1 |
| [P3-CRIT-02](reviews/review-2026-09-25.md#p3-crit-02--indexer-tokens--raw-newznab-blobs-on-find-beyond-responses) | Indexer tokens / raw Newznab blobs on Find-beyond (+ queue) | R1 |
| [P2-CRIT-01](reviews/review-2026-09-25.md#p2-crit-01--get-apiqueue-performs-mutating-poller-work) | `GET /api/queue` performs mutating poller work | **done** R2 / 0.5.6 |

### High

| ID | Issue | Target sprint |
| --- | --- | --- |
| [P3-HIGH-01](reviews/review-2026-09-25.md#p3-high-01--cover-and-download-paths-served-without-data-jail) | Cover/download paths without `/data` jail | R1 |
| [P3-HIGH-02](reviews/review-2026-09-25.md#p3-high-02--organizepreview-accepts-unconstrained-filesystem-paths) | `organize/preview` unconstrained paths | R1 |
| [P3-HIGH-03](reviews/review-2026-09-25.md#p3-high-03--ownerop-cover_url-is-server-side-ssrf) | Owner/op `cover_url` SSRF | R1 |
| [P1-HIGH-01](reviews/review-2026-09-25.md#p1-high-01--router-split-still-coupled-through-star-import-bag) | Star-import `route_imports` hub | **done** R3 / 0.5.7 |
| [P1-HIGH-02](reviews/review-2026-09-25.md#p1-high-02--public_work-bleeds-storage-engine-fields-into-the-api) | `public_work` bleeds storage fields | **done** R3 / 0.5.7 |
| [P4-HIGH-01](reviews/review-2026-09-25.md#p4-high-01--filesystem-paths-disclosed-to-every-household-role) | Filesystem paths disclosed to every role | **done** R3 / 0.5.7 |
| [P2-HIGH-01](reviews/review-2026-09-25.md#p2-high-01--per-request-sqlite-connect-storm-in-auth-gate--api) | Per-request SQLite connect storm in auth gate | **done** R2 / 0.5.6 |
| [P2-HIGH-02](reviews/review-2026-09-25.md#p2-high-02--maintain-dock-keeps-four-idle-progress-polls-forever) | Maintain dock four forever idle polls | **done** R2 / 0.5.6 |

Medium findings stay in the review doc; pick up opportunistically inside R\* lanes when they touch the same files.

---

## 6. Later / blue sky

- [ ] Hub `romwil/librarian` published (+ real pull-only rollout; not Automat path now)
- [ ] Full MusicBrainz / Open Library dumps for typeahead (v1 is catalog + optional bounded MB from owned artists)
- [ ] OIDC / Plex sign-in (not v1)
- [ ] Shared Python package with Smart Map: **contract first**; thin shared lib only if mutagen + filename agreement proves high reuse
- [ ] Shared JSON+NZB **grab/traffic service** (fourth Automat container) — only if two apps emit the same envelope
- [ ] Blue sky: OPDS 2, highlights, TTS, barcode Review, offline PWA, kid shelf

### Out of product / locked out

Hub as the only ship path (today), NZBGet, Calibre plugins / USB sync / content-server skin, Movies/TV/XXX as Hall library kinds (extras are Find/SAB/arr only), Goodreads live OAuth (CSV shipped).

---

## North star

A household **library for readers**. The Library is the product: scan `/data`, enrich, read, then grow catalog gaps. Search is local shelves only. Find is not a nav tab — it is the post-search door (**Find beyond the shelves**) plus **Discover** when Find is empty. Books, magazines, and comics (CBZ, Newznab `7030`) share first-tier rank. Audiobooks and music are first-tier listening — music Promotes to Plexamp; audiobooks never do. Extra categories (movies / TV / XXX) are optional Find plumbing to SAB / *arr (`show_extra_categories`, default **off**). They never become Hall works.

**Alive criteria** (every delight ship): presence · gilt/cream/paper · recognition without surveillance · ceremony for Finish/shelve/Request/open · honest Needs you with warmth.

**Anti-patterns:** KPI dashboards, badge piles, purple SaaS glow, motion that ignores `prefers-reduced-motion`, supermarket “bagging.”

## Locked decisions

- Retriever: SABnzbd at `http://downloader.sl`.
- `/data` ← host `/mnt/user/data`. Per-media roots are Settings paths under `/data`.
- First indexer: NZBFinder Newznab **v2 JSON**. Token in env/settings only. User-Agent required. Never commit tokens.
- Music: `incoming_music_root` → **Promote** → `music_root` (`/data/media/music`) for Plexamp only.
- Audiobooks: `audiobook_target` default **`plex`**. Never `music_root`.
- Comics: `7030`, canonical **CBZ**, `{Series}/{Issue-or-Year}/` + ComicInfo + cover.
- Gaps: owned vs expected, honest missing cards. **Confirm lives on Find** so SAB never fires from a shelf browse. Fail closed.
- Search = local FTS only (Hall hero + `/search`). Peek / Open / Favorite. No Beyond on Search.
- Find = post-search **Find beyond the shelves** → `/find` with `q`/kind prefilled, then Beyond. Find is not a nav tab.
- Empty Find is **Discover**: trending indexer category feeds from capabilities. Not a second Hall. Not auto-SAB. No HTML scrape.
- `show_extra_categories` default **off**. Never Hall kinds.
- Household job words: **Asked / On the way / Arrived / Needs you / Failed**. **Finished** is reading progress. **Promote** is incoming music → `music_root`.
- Lexicon: **Holds desk** · Hold slip · **Library card** · **Shelving** (legacy `#bagging` maps). Routes stay `/review`.
- Auto-organize only when identify is confident. Unexpected → Review. Scan never moves files; ingest/watch may.
- BYO LLM may assist later. LLM never invents an ISBN.
- Automat media contract: [automat-media-contract.md](automat-media-contract.md). **No shared Python package** until mutagen + filename agreement proves high reuse.
- No fourth Automat **grab/traffic** container unless two apps emit the same JSON+NZB envelope.
- Port **8793**. Never 8788 / 8790 / 8791 / 8792. Playwright e2e **8794**.
- Auth on from first boot. Roles owner / op / reader. Docker-seed owner. Invite-only join (HMAC).
- `LIBRARIAN_TRUST_PROXY_HEADERS` opt-in (default off). Public `librarian-dev-session-secret` refused.
