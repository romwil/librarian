# 00 · Platform map — Librarian — run 2026-11-04

Shared reconnaissance for every department in this run. This document maps the product and records observed facts; it does not grade them. Department verdicts live in `01_2026-11-04_product-strategy.md` through `10_2026-11-04_operations-support.md`.

| Review fact | Value |
|---|---|
| Live target | Automat LAN `http://10.10.1.202:8793` |
| Image truth | **1.0.10**, revision **480eff0**, built `2026-11-02T18:26:34Z` |
| Checkout during review | `fced2be`; Batch 6 must continue to distinguish checkout from image evidence |
| Walked as | Existing authenticated **owner** session; review-only, no invitations or destructive actions |
| Live mode | Local household auth; `llm_configured: true`; theme **Lights Down** |
| Scale | Books 10,762 · Music 97 · Audiobooks 74 · Magazines 17 · Comics 14 |
| Owner load | Sorting badge 27 · queue approximately 80 jobs · People 2 users / 0 invites |
| Known probe limit | Maintain shelf-health timed out once; screenshot tool timed out, so live evidence is route/API/a11y snapshot unless named otherwise |

Companion handoff: [`_status.md`](_status.md). Product rulings: [`01_2026-11-04_product-strategy.md`](01_2026-11-04_product-strategy.md).

---

## 1. What the platform is

Librarian is a self-hosted household reading room with acquisition and shelf-tending built in. A single FastAPI process serves a React SPA, owns a SQLite catalog, scans host-mounted media, searches the owned library first, and opens a deliberately quieter door to external discovery. A reader can browse, search, continue, favorite, collect works into shelves, read supported formats, listen to audio, and **Ask the house** for something missing. An owner or operator can confirm that request into SABnzbd, resolve uncertain identification in **Sorting**, maintain paths and integrations, and tend catalog health.

The product is not a public book marketplace, a social reading network, or an Arr dashboard with a prettier skin. Its explicit value is the combination of a calm owned-library experience and a controlled acquisition loop. The distinction matters: the reader's first screen is the **Hall**, not a download queue; external discovery does not silently start SAB; uncertain files fail into Sorting rather than being confidently mis-shelved.

The deployment reviewed is one household on one Unraid host. Platform administration therefore collapses into the owner role. There is no separate support organization, moderation console, billing system, tenant model, public signup funnel, or marketing site.

## 2. Stack, runtime, and deployment

| Layer | Choice | Evidence / operating meaning |
|---|---|---|
| Runtime | Python 3.12 | `AGENTS.md`; package requires the web extra |
| Web | FastAPI + Uvicorn | `python -m librarian.web`; one process owns API and SPA |
| Front end | React 18.3, React Router 6.28, Vite build | `frontend/package.json`; compiled assets served from `frontend/dist` |
| Reader engines | foliate-js, pdfjs-dist, CBZ support | Browser reading for EPUB/PDF/comics; audio has Listen path |
| Primary state | SQLite in WAL mode under `DATA_DIR` | No database, cache, queue, or worker service to operate separately |
| Media state | Host paths mounted under `/data` | Catalog rows point at books, magazines, comics, audiobooks, incoming music, and Plexamp music |
| Job execution | In-process poller and job rows | Queue tick, scan, enrich, cleanup, noted refresh, RSS polling, backup |
| Product port | `0.0.0.0:8793` in container | Automat product port; mocked e2e uses 8794 |
| Distribution | Unraid appdata kit | `/mnt/user/appdata/librarian`; current rollout is host `./docker-run.sh` |
| Release truth | Image `.build-info` | Public health is liveness only and must not be treated as version truth |
| Test gates | pytest ≥70%, Vitest, Playwright/axe | `AGENTS.md`; semantic locators; e2e isolated on 8794 |

The one-process shape is operationally appropriate for a private appliance today: a household starts one container, gets one catalog, and backs up one configuration tree. It also concentrates risk. Slow catalog work competes with the web process, and the live shelf-health timeout is a concrete prompt for Architecture and Performance to test isolation and budgets rather than assuming that “SQLite is small.”

### Deployment and environment contract

- Automat is authoritative at `http://10.10.1.202:8793`.
- Projectionist `:8788`, Smart Map `:8790`, and lobby ports `:8791`/`:8792` are sibling services and must never be reused.
- `GET /api/health` returns only `{"status":"ok"}`.
- Owner `GET /api/status` and `docker exec librarian cat /app/.build-info` carry version and notes-match truth.
- `localhost:8793` can be an SSH tunnel to Automat; it is not proof of a local dev server.
- The active rollout is `cd /mnt/user/appdata/librarian && ./docker-run.sh`; Hub-first rollout remains deferred.
- Secrets live in host `.env` or `/config/settings.json`; the known public development session secret is refused.
- Proxy headers are ignored unless `LIBRARIAN_TRUST_PROXY_HEADERS` is explicitly enabled behind a real reverse proxy.

## 3. Integrations and background work

| Integration | Product job | Required to boot? | Notes |
|---|---|---|---|
| SABnzbd | Fetch owner-confirmed jobs | No | Confirm is the safety boundary; live host is household infrastructure |
| NZBFinder / Newznab | Search beyond shelves | No | Multiple indexer hosts can be configured |
| OpenAI / Anthropic / Gemini-compatible LLM | Rank or chase lists | No | Live reports configured; it may rank, never invent identifiers |
| Hardcover / Open Library | Book metadata and covers | No | Outbound metadata disclosure belongs in Privacy |
| Comic Vine | Comics metadata | No | Optional key and provider failure states |
| Audnexus | Audiobook metadata/matching | No | `audnexus_unmatched` is visible in live Sorting reasons |
| MusicBrainz | Music identity | No | Music has a staging-and-promote lifecycle |
| Audiobookshelf | Optional match/listen sync | No | Plex remains the default audiobook publish target |
| Mail / notification transport | Invites, newsletters, alerts | No | Quiet hours and digest behavior remain product polish |
| OPDS | External reader feed | No | Publicly routable surface whose auth contract must remain explicit |

Background work runs inside the service: scans, metadata enrichment, queue polling, review repair, noted cache refresh, RSS polls, cleanup, and nightly backups. Backups retain seven daily and four weekly copies, run SQLite integrity checking, and exclude session secrets/settings from the catalog backup set. This is a product strength only if restore is periodically proven; see `10_2026-11-04_operations-support.md`.

## 4. Route and surface inventory

### 4.1 Public / unauthenticated

| Route | Purpose | Product note |
|---|---|---|
| `/login` | **Foyer** local username/password entry | Household framing, not a marketing conversion page |
| `/join` | Redeem a signed invitation | Invite-only acquisition |
| `/reset` | Redeem password reset | Owner-mediated account recovery |
| `/api/health` | Process liveness | Deliberately no version payload |
| `/api/features` | Foyer bootstrap | Household name, owner readiness, auth methods, version |
| `/robots.txt` | Crawler posture | Private product |
| `/release-notes.json` | What's New payload | Paired with image notes-match |
| `/opds*` | External-reader feed | Security and privacy teams should verify authentication |

There is no pricing page, public registration, SEO catalog, anonymous browsing, or public profile. That absence is intentional for a private appliance rather than an incomplete SaaS funnel.

### 4.2 Consumer / reader

| Route | Label | Primary job |
|---|---|---|
| `/` | **Hall** | Search, continue, revisit favorites, see recent and noted works |
| `/browse` | **Stacks** | Browse facets, kinds, and shelves |
| `/search` | **Search** | Owned results first; Discover and Beyond as progressive disclosure |
| `/find` | Redirect to Search | Compatibility route; user-facing noun remains Search |
| `/noted` | New & noted | Curated/current discovery |
| `/noted/history` | Noted history | Revisit prior lists |
| `/wanted` | Wanted | Track desired titles and external searches |
| `/works/:id` | Work detail | Read, Listen, inspect editions/files, favorite, shelve |
| `/card` | **Library card** | Theme, font, personal preferences, account entry |
| `/inbox` | Inbox | Household and system notices |
| `/notifications` | Notification preferences | Channel and quiet-hours behavior |
| `/help` | HELP | Role-sensitive product instructions |

The consumer journey is intentionally shelf-first. API evidence supports the same model: `frontend/src/api.js:66-137` exposes Hall, browse, owned search, Beyond search, works, favorites, shelves, and **Ask the house** as distinct operations. The separation prevents an external hit from masquerading as owned content.

### 4.3 Owner and operator

| Route | Role | Primary job |
|---|---|---|
| `/queue` | owner, op | **Downloads**: inspect Asked jobs, confirm SAB, retry/dismiss terminal states |
| `/review` | owner, op | **Sorting**: diagnose and resolve uncertain or malformed shelf items |
| `/maintain` | owner | Morning brief, shelf pulse, cleanup, lanterns, duplicate work, Calibre normalization |
| `/settings` | owner | Paths, indexers, SAB, LLM, mail, scan/enrich, integrations |
| `/people` | owner | Users, roles, resets, disable/delete, signed invitations |

The route `/review` intentionally presents as **Sorting**. API code gives the desk broad powers: paginated/reason-filtered review, candidates, apply/skip/repair/retry, bulk-by-reason, trusted apply, duplicate purge, and undo (`frontend/src/api.js:159-206`). Maintain exposes shelf health and morning brief directly (`frontend/src/api.js:207-237`). Downloads exposes queue, tick, confirm, retry, and dismiss (`frontend/src/api.js:238-242`).

### 4.4 Administration

There is no separate admin product. Settings, People, Maintain, Sorting, and Downloads are the administrative plane for one household. This is efficient while “owner” and “platform administrator” are the same human. It becomes a product decision—not merely an implementation task—if Librarian later supports multiple households, delegated support, or hosted service.

## 5. Roles, permissions, and trust boundaries

| Role | Intended capability |
|---|---|
| **owner** | All settings, people/invites, scans, integrations, queue confirm, Sorting, Maintain, music promote |
| **op** | Invite readers, act on Sorting, confirm queue/gaps, add media on disk; no crown-jewel settings |
| **reader** | Use Hall/Stacks/Search/work/reading/listening/shelves; download owned files; Ask the house |

The role vocabulary is code-level truth: `librarian/auth.py:26-29` defines `owner`, `op`, and `reader`, while invites are restricted to op and reader. `librarian/auth.py:277-283` rejects missing users with 401 and disallowed roles with 403. The API client separates reader Ask from owner Confirm (`frontend/src/api.js:107`, `238-242`), which is a useful product-level manifestation of authorization rather than only a backend rule.

Trust boundaries later teams must preserve:

1. A reader request creates an Asked slip; it does not call SAB.
2. Confirming a queue job is owner/op work.
3. Identification below confidence thresholds goes to Sorting.
4. Unsafe API requests require the expected Origin and `X-Librarian: 1` posture.
5. Auth is on from first boot; there is no anonymous household mode.
6. Invitations are signed and bounded; live had zero open invitations.
7. LLM output may assist ranking but cannot become identifier truth.
8. File moves and ingestion remain inside configured path jails.

## 6. Data model and content model

SQLite stores users, invitations, sessions, resets, security events, works, files, editions, authors, work-author links, identifiers, jobs, shelves, shelf items, reading/listening progress, indexers, review diagnosis, Sorting undo, noted cache, metrics, and provider call/cache state. Media bytes remain on host-mounted shelves.

The central product object is a **work**, not a queue job. Works can have files, editions, contributors, identifiers, progress, favorite/shelf membership, and provider enrichment. This supports the product's library identity across formats. Queue jobs and Sorting diagnoses are operational objects that should resolve into or maintain works; they should not become the dominant navigation model.

Supported kinds have different physical and product contracts:

- **Books:** EPUB-first, with PDF where present; 10,762 live.
- **Audiobooks:** matched and listened to as books-in-audio; 74 live; never promoted to music root.
- **Comics:** CBZ and Newznab category 7030; 14 live.
- **Magazines:** issue-oriented folders; 17 live.
- **Music:** incoming staging followed by explicit **Promote** to Plexamp root; 97 live.

## 7. Design system and language system

- Tokens and themes: `frontend/src/styles/tokens.css`.
- Font, chrome, stacks, owner, work, reader, and motion styles: `frontend/src/styles/*.css`.
- User-facing lexicon: `frontend/src/copy.js` plus `.cursor/rules/library-lexicon.mdc`.
- Product north star: `docs/superpowers/specs/2026-09-14-librarian-design.md`.
- Reading-room detail: `docs/ux/reading-room.md`.
- Components: `frontend/src/components/`; no separate component-library package.

The visual identity is a brass, leather, paper, and lamp reading room with **Lights Up** and **Lights Down**, not “cinema gold,” generic dark SaaS, or Calibre desktop chrome. Language is equally structural: Hall, Stacks, shelves, slip, Sorting, Asked, On the way, Arrived, Needs you, and Failed encode the household mental model. “Finished” is reserved for reading progress; “Promote” is reserved for staged music.

## 8. Personas and jobs to be done

### 8.1 Core personas

| Persona | Context / device / frequency | Goal | Top three tasks |
|---|---|---|---|
| Invited first-time visitor | Phone or laptop; once | Understand the household library and enter safely | Read foyer proposition; sign in/redeem; find first owned work |
| Returning reader | Phone, tablet, laptop; daily–weekly | Resume or choose something owned | Continue; search; Read/Listen |
| Power reader | Desktop/tablet; weekly | Curate and hunt across kinds | Fielded search; Discover/Noted/Wanted; shelves/favorites |
| New owner | Desktop LAN; setup week | Reach a trustworthy first shelf | Configure roots/integrations; scan; invite and confirm first Ask |
| Established owner at scale | Desktop; several times weekly | Keep the library calm as volume grows | Clear Sorting; confirm Downloads; run morning brief/health |
| Operator | Desktop; as needed | Share desk work without full control | Confirm Asked; resolve Sorting; add on-disk media |
| Platform admin | Same person as owner | Keep service recoverable | People/security; settings; backup/restore |
| Household support agent | Owner via product and SSH | Explain and recover | Reset access; inspect job state; consult runbook/logs |

### 8.2 Edge personas

| Persona | Context | Top tasks | Review implication |
|---|---|---|---|
| Screen-reader reader | Browser + AT | Hall search; open work; Read/Listen | Skip link, landmarks, listbox semantics, manageable Sorting DOM |
| Keyboard-only operator | Desktop | `/` search; j/k/x Sorting; confirm | Shortcuts must be discoverable and announced |
| Low-bandwidth mobile reader | 390px, weak Wi-Fi | Hall rails; peek; open work | Cover loading and rail payloads must degrade gracefully |
| Older / low-vision reader | Tablet, Lights Up/Down | Increase font; search; read | Library-card font step and contrast are core, not polish |
| Non-native English reader | Any | Interpret library metaphors | Keep metaphors consistent and pair rare terms with plain explanations |
| Privacy-sensitive household member | Shared private server | Know what leaves the box | Provider disclosure and optional mail/LLM controls |

## 9. Sacred-cow register

These are embedded assumptions for departments to rule on. IDs are stable cross-document anchors.

| ID | Assumption | Evidence | Primary reviewers |
|---|---|---|---|
| SC-01 | Auth is on from first boot; joining is invite-only | `/login`, `/join`, role model | Product, Security |
| SC-02 | The owned library is the product; Beyond is a quiet door | Hall default, Search split | Product, UX |
| SC-03 | Confirm-before-SAB is non-negotiable | Queue confirm API | Product, Security, Ops |
| SC-04 | Readers Ask the house; they never start SAB | Ask vs confirm APIs | Product, Security |
| SC-05 | `/review` remains a technical route but the product word is Sorting | Live nav, lexicon | UX, Product |
| SC-06 | Five job words are enough: Asked / On the way / Arrived / Needs you / Failed | HELP and queue states | Product, Content |
| SC-07 | Finished means reading progress; Promote means music only | Lexicon | Product |
| SC-08 | Low-confidence identity must fail into Sorting | Review reasons and actions | Product, Architecture |
| SC-09 | LLMs may rank/chase but never invent identifiers | Configured live LLM | Product, Security |
| SC-10 | One FastAPI process plus SQLite WAL is sufficient | Deployment shape | Architecture, Performance |
| SC-11 | Port 8793 is the fixed Automat product contract | Ops rules | Operations |
| SC-12 | Lights Up/Down reading-room identity should survive owner tooling | Tokens/live theme | Design, Product |
| SC-13 | Five media kinds belong in one household library | Live counts | Product |
| SC-14 | Music needs incoming → Promote; audiobooks never use music root | Settings and routes | Product, Ops |
| SC-15 | Owner Settings + Maintain are enough administration | No admin console | Product, Ops |
| SC-16 | Host-built `docker-run.sh` remains the deploy path for now | Runbook | Architecture, Ops |
| SC-17 | `/api/health` is liveness only | Live payload | Ops, Security |
| SC-18 | Unsafe API calls require Origin + `X-Librarian: 1` | API client/security docs | Security |
| SC-19 | Favorites and named shelves are one shelf model | API and Hall | Product, UX |
| SC-20 | Peek precedes full work detail | Reader components | UX |
| SC-21 | Nightly catalog backups exclude live secrets | Backup contract | Ops, Privacy |
| SC-22 | Public hostname must be explicitly allowlisted | 1.0.10 origin fix | Security, Ops |
| SC-23 | The public development session secret must hard-fail | Boot contract | Security |
| SC-24 | Test floors and axe are release contracts | AGENTS.md | Architecture, A11y |
| SC-25 | Calibre is advisory inspiration, not the product to reproduce | Design roadmap | Product |
| SC-26 | Separate Downloads, Sorting, Maintain, and Settings are learnable | Live owner chrome | Product, UX |
| SC-27 | Sorting is a permanent exception desk rather than a near-empty safety net | Live 27 slips | Product, Red team |
| SC-28 | Named shelves deserve first-class Hall presence | `named_shelves` live count 0 | Product, Growth |

## 10. Live walkthrough

### Method and limits

The existing browser session was authenticated as owner on Automat. No invitations were minted, no person was changed, no SAB job was confirmed, no file was moved, and no setting was saved. Browser screenshot capture timed out repeatedly, so the run records accessibility snapshots, route state, and authenticated API observations. Later batches should cite `screenshots/README.md` and their own evidence rather than pretending PNGs exist.

### Hall `/`

- Owner chrome: Hall · Stacks · Search · Favorites · Wanted · Downloads · **Sorting 27** · Inbox · Library card (owner).
- Theme: **Lights Down**.
- Hero Search is a labeled combobox with typeahead listbox.
- Kind chips report Books 10,762; Music 97; Audiobooks 74; Magazines 17; Comics 14.
- Rails include Continue reading, Recently added, Favorites, and New & noted.
- Hall API reported `named_shelves` count 0, despite the shipped shared-shelf model.

The Hall proves the library-first proposition at meaningful scale. The caveat is emotional: an owner sees “Sorting 27” on every page, so operational debt leaks into the reading room.

### Search `/search`

- Kind controls: All, Book, Magazine, Comic, Audiobook, Music.
- Owned-library search remains primary.
- “More ways to search,” Discover, New & noted, and Beyond are secondary doors.
- The API exposes reader Ask separately from owner queue confirmation (`frontend/src/api.js:95-107`, `238-242`).

### Sorting `/review`

- Live badge/open count: 27.
- Reason distribution observed: low confidence 22, Audnexus unmatched 2, unknown identity 2, missing folder 1.
- Reason filter chips, keyboard triage, bulk-by-reason, repair/retry, duplicate purge, and undo exist.
- Accessibility snapshot exceeded roughly 1,000 nodes, making list scale a performance and AT concern even though only 27 slips were open.

### Downloads `/queue`

- Approximately 80 jobs were returned during reconnaissance.
- The product supports explicit confirm, retry, and dismiss actions.
- The raw count mixes operational history with actions and risks making confirmation feel like a generic SAB queue.

### Maintain `/maintain`

- Morning brief and shelf-health are first-class API operations (`frontend/src/api.js:226-229`).
- Shelf-health timed out once during this run. One timeout is not proof of chronic failure, but at 10.8k books it is enough to require a budget, cache, and observed SLO.
- Cleanup, duplicate merge, shell purge, mixed-kind split, indexer scorecard, grooming undo, and Calibre re-normalize show substantial owner power.

### People and household

- Two users existed; zero invitations were open.
- No invitation was created for review.
- The three-role model exists even if this small household may not exercise op heavily.

## 11. Benchmarks

These are pattern references, not templates to copy.

| Product | Comparable strength | Pattern worth borrowing | Pattern to reject |
|---|---|---|---|
| Audiobookshelf | Self-hosted listening and progress | Cross-device progress, calm owned-library focus | Turning all kinds into audiobook-shaped metadata |
| Kavita | Multi-format reading | Series/issue continuity and reader-first library navigation | Admin density on the home page |
| Komga | Comics/magazines | Strong issue order, resumable reading, collection integrity | Treating prose books as comics |
| Calibre-Web | Metadata power | Dense owner editing and explicit format visibility | Making the reader Hall a metadata spreadsheet |
| Hardcover | Taste and shelves | Lightweight shared lists and “what next” prompts | Building a public social network into a private kit |
| Readarr / Arr tools | Acquisition automation | Clear job state and provider diagnostics | Making queue metrics the product's home |

The benchmark conclusion is not “copy Calibre-Web.” Librarian should preserve its reader calm, then borrow power patterns only inside owner desks. Nor should it become a public Goodreads competitor; household shelves and quiet recommendations are enough.

## 12. Pointers for department passes

1. **Product / UX:** decide whether Downloads, Sorting, and Maintain remain separate or become one Desk shell; do not block near-term triage on a large IA rewrite.
2. **Product / Growth:** investigate why live named shelves remain zero and whether activation copy is enough.
3. **Performance / Architecture:** measure Hall payloads, Sorting DOM, and shelf-health at 10.8k books.
4. **Security:** verify every queue confirm, Sorting mutation, People mutation, and settings mutation has server-side role checks; do not rely on hidden navigation.
5. **Privacy:** inventory every outbound provider call and the content sent to configured LLM/mail services.
6. **Operations:** prove backup restore, not only backup creation.
7. **Accessibility:** run live axe when tooling permits; manually exercise Hall → work → Read and owner Sorting keyboard flow.
8. **Design:** keep Hall tokens and reading-room hierarchy while making dense owner desks scannable.
9. **Red team:** challenge whether better Sorting UI is enough, or whether identification should make Sorting nearly empty.

## 13. Handoff

- Start from the authoritative LAN host `http://10.10.1.202:8793`.
- Reuse the existing owner session; never record credentials or mint review invitations.
- Read [`_status.md`](_status.md) for environment and screenshot limitations.
- Treat image 1.0.10 / `480eff0` as live truth; cite checkout code separately.
- Do not use a public VIP as version truth.
- Do not bind or stop sibling services.
- Store any later screenshots under `screenshots/` with department prefixes.
- Re-run the app only if a department genuinely needs local instrumentation; normal interactive QA should use the live LAN target.
- Preserve the review-only boundary: no confirms, purges, invites, people changes, file moves, or setting saves.

### Known gaps

- No anonymous browser walk outside the authenticated session.
- No reader-role or op-role interactive walk.
- No actual Read/Listen media launch.
- No OPDS client test.
- No mobile 390px screenshot in the foundation pass.
- No successful PNG capture due to tool timeout.
- No behavior conclusion from one shelf-health timeout beyond “measure and budget it.”

Those gaps are explicit so later findings can use `Likely` or `Suspected` confidence rather than converting mapped code into observed behavior.
