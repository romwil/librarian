# Changelog

## [Unreleased]

## [0.5.2] — 2026-09-25

### Highlights

- **Lamp rituals.** The Hall washes with dawn and dusk; when Continue waits, a quiet welcome-back greets you under the lamp.
- **Ceremony for small acts.** Peek opens with a soft ritual settle; Finished glows once — “The lamp remembers.”
- **Motion stays kind.** Rituals inherit settle tokens and respect `prefers-reduced-motion` — presence stays, motion drops.

### Added

- **`lampRituals.js`.** Local-hour Hall period (dawn/day/dusk/night), welcome-back copy, finish ceremony line.
- **Hall.** `data-lamp-period` wash + welcome-back when Continue / Continue listening has volumes.
- **Peek / Finished.** `peek-ritual` open motion; Work page finish glow + status line.
- **Playwright.** Hall lamp rituals journey (port 8794).

### Changed

- **`motion.css`.** `--motion-ritual`, dawn/dusk/night washes, peek-ritual / finish-glow; reduced-motion clears them.

## [0.5.1] — 2026-09-25

### Highlights

- **Smart Holds desk.** Hold slips sort into piles by why they paused — Extra files, Unpack stuck, Collision — so Review feels like sorting returns, not a ticket queue.
- **One recommended motion.** Each pile and slip names a primary next step (Repair, Clear extra-files, Skip…) with the filled CTA matching that motion.
- **Library voice stays.** Holds desk / hold slips chrome; Apply still files once the folder is ready.

### Added

- **`review_recommended_motion`** on `GET /api/review` → `work.actions.recommended_motion`.
- **FE grouping** (`groupHoldSlipsByReason`) and recommended-motion CTA helpers in `review.js`.
- **Playwright** Holds desk grouped populated journey (port 8794).

### Changed

- **Review page.** Heading **Sorting returns**; groups with soft-enter; primary vs outline CTAs from recommended motion.

## [0.5.0] — 2026-09-25

### Highlights

- **The living library opens.** Tonight’s Shelf breathes under a soft lamp wash — covers settle in, and Continue rails remember where you left the lamp.
- **Presence without surveillance.** “The room kept your place” greets you on the Hall; Continue kickers speak lamp, not KPI.
- **Motion stays kind.** Shelf breath and cover settle-in respect `prefers-reduced-motion` — presence stays, motion drops.

### Changed

- **Tonight’s Shelf.** Alive chrome (`tonight-shelf-alive`, lamp glow, presence line); staggered cover settle-in on Continue / gap / surprise slots.
- **Continue rails.** `presence` prop on Hall Continue + Continue listening — lamp kicker copy and settle-in covers.
- **`motion.css`.** `--motion-breath`, `shelf-breath`, `cover-settle`; reduced-motion clears breath and settle.
- **Playwright.** Hall Tonight’s Shelf mocked journey + reduced-motion (port 8794).

## [0.4.25] — 2026-09-25

### Highlights

- **The room settles in.** Pages arrive with a soft settle, hold slips ease onto the desk, and the lamp warms while shelves load — motion that respects `prefers-reduced-motion`.
- **No empty flash.** Queue, Stacks, Reading room, People, Settings, and Inbox show warm lamp skeletons instead of blank panels.
- **Lights Up and Lights Down stay readable.** Alerts, callouts, chips, and Settings nav pick up a real `--fg` ink so cream-on-cream and dark-on-dark stop sneaking through.

### Changed

- **`frontend/src/styles/motion.css`.** Motion tokens (`--motion-presence`, `--motion-settle`, `--motion-warm`), page-settle / lamp-warm / soft-enter, consolidated reduced-motion paths.
- **Warm loads.** Shared `WarmLoad` on Queue, Browse, Work, People, Settings, Inbox; Hall / Holds desk keep their lexicon warming copy.
- **Contrast.** `--fg` in both themes; alert/callout/Maintain/Review ink; live-chip label contrast.
- **Copy.** Sterile “Internal Server Error” never reaches the household — filing-slip warmth instead.
- **Playwright.** Hall reduced-motion smoke; Settings Library card menu; Holds desk lexicon retained (port 8794).

## [0.4.24] — 2026-09-25

### Highlights

- **Holds desk, not bagging.** Review speaks library — hold slips wait at the Holds desk; the supermarket “bagging area” leaves the chrome.
- **Library card in the corner.** The personal menu is labeled Library card — theme, text size, inbox, and library preferences under one household name.
- **Settings → Shelving.** Complete-root setup is Shelving (`#shelving`); legacy `#bagging` still deep-links.

### Changed

- **Copy / Review / HELP.** Empty, loading, and fallback Review strings; hold-slip wording; HELP Review section + motif glossary.
- **Settings nav.** `bagging` → `shelving` with hash alias; Setup complete-root kicker matches.
- **Playwright.** Review and Settings e2e assert Holds desk / Shelving (port 8794).

## [0.4.23] — 2026-09-25

### Highlights

- **A letter from the library.** Opt into a weekly or monthly newsletter — recent arrivals, introduced in a voice shaped by what you Continue, Favorite, and Request.
- **You choose the path.** Editions land in the inbox and/or email only when you opt in; email never leaves without Mail configured and your channel choice.
- **Owner can send early.** From Profile → Notifications, push a personalized edition to yourself or everyone opted in — cadence still waits on the scheduled path.

### Added

- **`librarian/notifications/newsletters.py`.** Personalized edition builder (taste intro + recent additions), cadence due checks, `deliver_editions` fan-out.
- **API.** `POST /api/newsletters/push` (owner early/self-test), `POST /api/newsletters/run` (due-by-cadence seam).
- **Prefs.** Newsletter kind cadence is weekly | monthly; `newsletter_last_edition_at` stamped after a real delivery.
- **SPA.** Newsletter cadence controls on Notifications prefs; owner “Send library letter now” panel.

### Changed

- Notification timings include `monthly`; newsletter editions email immediately when the email channel is opted in (they are the scheduled unit, not digest-queue filler).
- Library newsletter catalog help text describes the live edition.

## [0.4.22] — 2026-09-25

### Highlights

- **The desk has an inbox.** A top-bar badge and `/inbox` hold calm notices — arrivals, Needs you, quiet hours, shelf health, and household whispers — without a KPI strip.
- **You choose what lands.** Profile and Settings → Notifications let every member pick kinds, in-app and/or email, and realtime vs daily/weekly digest timing.
- **Email stays opt-in.** Mail only leaves when the owner configured transport and you turned email on for that kind with an address.

### Added

- **`librarian/notifications/`.** Kind catalog, per-kind prefs, `deliver_notification` fan-out, daily/weekly email digest queue + flush.
- **`user_notifications` + `notification_digest_queue` SQLite tables.** Inbox rows and deferred email digests.
- **API.** `GET/POST /api/notifications`, `GET/PUT /api/notifications/prefs`, owner `POST /api/notifications/test` and digest flush.
- **SPA.** Inbox page, top-bar badge, Notifications prefs panel (Settings + `/notifications`), Profile links.
- Starting kinds: asked confirm, arrived, Needs you, quiet hours wake, newsletter (prefs seam), someone finished, shelf health.

### Changed

- `GET /api/auth/me` includes `inbox_unread`; `GET /api/features` exposes notification channel offerings.

## [0.4.21] — 2026-09-25

### Highlights

- **Mail leaves the house when you ask it to.** Owner Settings now has SMTP or Resend install — host, from address, API key — so household notices can travel once notifications land.
- **Secrets stay put.** Leave password or Resend key blank on save and Librarian keeps what you already stored (Projectionist-style retain-on-empty). Keys live in settings.json / env only.
- **Send a test before you trust it.** Settings → Mail includes a one-shot test send so you know the transport works before anyone opts in.

### Added

- **`librarian/mail/`.** SMTP + Resend transport (`send_mail`, `mail_configured`) for outbound email.
- **`settings.mail` nested block.** Provider, from, SMTP/Resend fields; masked on GET; retain-on-empty on PUT.
- **`POST /api/settings/mail/test`.** Owner test send with explicit `to_email`.
- **Settings → Mail panel.** Owner UI for transport + template + test send (`#mail`).

### Changed

- Settings nav lists Mail between Language model and Integrations.
- `settings.example.json` documents the mail block (empty secrets).

## [0.4.20] — 2026-09-25

### Highlights

- **Web API lives in routers.** `create_app` stays the composition root; auth, catalog, review, ingest, maintain, and settings each own their routes — easier to grow without a 2k-line `app.py`.
- **Maintain Shelf health.** Scan/enrich sit under a named Shelf health section with a live permission report and copy-paste `chown` tip; the telemetry dock still covers grooming jobs.
- **Identify ↔ organize ↔ ingest boundaries.** `identify_evidence` is public; ingest no longer imports organize at module load — no more lazy organize↔ingest cycle.

### Added

- **`GET /api/maintain/shelf-health`.** Owner permission report for configured library roots plus PUID ownership guidance.
- **`librarian/web/routers/`.** Domain route registrars wired from `create_app`.
- **`librarian/shelf_health.py`.** Writability probe + chown tip shared by Maintain.

### Changed

- **`librarian/web/app.py`.** Slim composition root (middleware, deps, SPA) — handlers moved to routers.
- **ingest → organize.** `organize_identified` is imported inside `progress_ingest_job` so organize can depend on ingest expand helpers without a cycle.
- HELP / ROADMAP note Shelf health; Hub publish remains deferred (host `./docker-run.sh`).

## [0.4.19] — 2026-09-25

### Highlights

- **Dead chrome leaves the room.** Soft-deprecated NYT Books Settings copy, CelebrationBanner, unused wizard/celebration CSS, and Hall compact Add-to-library are gone — Bestsellers stay on BYO LLM.
- **One vocabulary for Review reasons.** Canonical `review_reasons` constants drive SQLite filters and diagnosis; `missing_folder` stays distinct from `no_payload`; Clear extra-files queries by reason.
- **Docs match Automat truth.** HELP covers Maintain, Indexers, and collection Clear; AGENTS / AUTOMAT / ROADMAP say host `./docker-run.sh` is the ship path — not a missing Hub `docker-release.sh`.
- **Maintain/Review kickoff is race-safe.** Concurrent POSTs can no longer double-begin the same background job.

### Fixed

- **`BackgroundJobSlot.start_if_idle`.** Progress “already running” is evaluated under the slot lock with thread creation (callable `is_running`), and a live worker alone blocks a second begin.

### Removed

- CelebrationBanner + FE `celebrationSeen` client; SetupWizard default export; AddToLibrary `compact` / `hall-ingest` path; wizard / enrich-progress / celebration CSS dead weight.
- Settings NYT Books API key field and FIELD_HELP; FE `nytList` / `nytListNames` clients (LLM lists remain).

### Changed

- **`librarian/review_reasons.py`.** Single source for Review reason codes; identify / audnexus / delight / app import from there.
- **`Database.list_works(..., review_reason=)`.** Clear extra-files and counts filter in SQL instead of page-and-filter.
- **Identify missing folders.** Gone paths keep `missing_folder` instead of collapsing to `no_payload`.
- HELP / ROADMAP / AGENTS / AUTOMAT / DOCKER / SECURITY Automat + Maintain / Indexers / Clear truth.

## [0.4.18] — 2026-09-25

### Highlights

- **One progress kit for every long job.** Scan, enrich, shelving, Clear, and Purge share `progress_job` plumbing — less drift when a new Maintain/Review job lands.
- **Maintain shows status in one dock.** Telemetry lives in MaintainStatusDock; the embedded Add-to-library panel no longer duplicates shelving meters.
- **Review Clear/Purge reuse the same progress UI.** Shared `JobProgress` + `useProgressJob` keep Clear and Purge meters consistent with the Maintain dock.

### Changed

- **`librarian/progress_job.py`.** Shared JSON progress blob + `BackgroundJobSlot` for create_app kickoffs; thin wrappers remain the public API for each job kind.
- **MaintainStatusDock / Review progress.** Render through `JobProgress`; poll through `useProgressJob`.

## [0.4.17] — 2026-09-25

### Highlights

- **Review list stays read-only.** Opening bagging no longer rewrites slips in SQLite; soft-repair for stuck archives runs in the background poller instead, so list polls cannot race Apply.
- **Enrich status tells the truth after restart.** A dead enrich worker no longer leaves Settings stuck on “running” — same clear-on-stale pattern as ingest and scan.

### Fixed

- **GET `/api/review` SQLite soft-repair.** Response still overlays `unpack_stuck` for the UI; persistence moved to `soft_repair_review_reasons` on the job poller.
- **GET `/api/settings/enrich/status` stale running.** Clears orphaned progress when the enrich thread is gone after a lamp restart.

## [0.4.16] — 2026-09-25

### Highlights

- **Major builds have a house protocol.** Phases and sprints ship as GitHub feature releases with parallel agent lanes, coverage that stays ≥70%, and Playwright plus interactive browser UX gates — so living-library work does not invent process mid-flight.
- **Mocked Playwright smoke is runnable.** Hall, Review bagging empty copy, Settings nav, and health/shell land on a dedicated e2e port (8794) without live NZBFinder or SABnzbd.

### Added

- **Major-build protocol docs.** `docs/ops/MAJOR_BUILDS.md` plus AGENTS / TESTING pointers for codegraph-first navigation, exclusive lane ownership, sprint release cadence, and Automat host `./docker-run.sh` truth.
- **Playwright scaffold.** Root `npm run test:e2e` (frontend delegates), `scripts/start-e2e-server.mjs`, chromium install note in `docs/TESTING.md`, baseline smoke specs.

## [0.4.15] — 2026-09-25

### Fixed

- **Review Apply PUID path.** Shelf `PermissionError` now names the locked path so operators can fix the right author tree (or bulk-chown `library/books`) instead of guessing.

### Added

- **Maintain shelf-lock tip.** Scan/enrich lede documents host `chown -R 99:100` for Calibre-migrated uid-1000 author folders; HELP Review table and AUTOMAT ops tip match.

## [0.4.14] — 2026-09-24

### Fixed

- **Review progress bleed.** Clear extra-files and Purge duplicates each bind their own status summary — a running Clear job no longer overwrites the Purge panel’s bottom line. Completed meters dismiss after a short dwell instead of sticking around and mirroring another job.

## [0.4.13] — 2026-09-24

### Fixed

- **Collection dumps vs “extra files.”** Flat NYT / Usenet Fiction folders (many distinct ebook stems) auto-expand into per-title ingest instead of parking one confusing `extra_files` Review slip. Apply peel shelves the confirmed title and expands the rest the same way — no leftover slip that forces Apply 29 times. Clear extra-files still repairs residual collection slips in one click.
- **Review copy for collections.** Household language distinguishes multi-title collection dumps from true same-title ambiguity; Clear extra-files is the call to action.

## [0.4.12] — 2026-09-24

### Fixed

- **Review Apply on multi-title dumps.** Flat NYT / Usenet Fiction folders (many `Title - Author.epub` siblings) no longer 500 on Apply. Apply peels the confirmed title onto the shelf and leaves a leftover `extra_files` slip for the rest; Clear-extra / ingest expand one target per stem. Shelf `PermissionError` (PUID-locked author folders) returns readable 400 guidance instead of a bare Internal Server Error.
- **Alert contrast.** `.alert` uses theme text on a soft danger wash (readable in lights-up and lights-down) — never pale-on-pink.
- **Empty-body 500 copy.** `humanError` no longer masks a bare “Internal Server Error” behind the generic stacks line; filing slips get explicit log guidance, and Apply permission detail stays visible.

## [0.4.11] — 2026-09-24

### Fixed

- **Comic + ebook blends.** Mass-import / Clear-extra no longer shelves a `.cbz` next to `.epub`/`.azw3`/`.mobi` as one comic work. Mixed folders split into separate comic and book volumes on ingest; Apply / Clear extra-files peel the same way instead of force-organizing as comic.
- **Work detail width.** Work meta / files use the full reading column (same Maintain-style max-width fix) so long filenames and dual CTAs are not pinned to a phone column.

### Added

- **Maintain Split comic/book blends.** Owner bulk repair finds shelved works whose file rows mix comic archives with ebook encodings, moves the ebooks under `books_root`, and leaves the comic on its own work — media is never deleted.

## [0.4.10] — 2026-09-23

### Fixed

- **Shelf shells off browse.** Hall, Stacks, kind counts, and local search only show volumes with registered media files — dismissed Review slips and dump-title ghosts no longer appear “on the shelves.”
- **Maintain page width.** Maintain sections use the full admin-room width (same as Settings/Review) instead of a 42rem phone column that wrapped path fields and ledes oddly.

### Added

- **Maintain Purge shells.** Owner bulk cleanup deletes catalog rows with no file rows and no payload on disk (wishlist ISBN stubs and folders that still hold media are kept). Background job with a live progress meter.
- **Skip / Purge duplicates delete slips.** Dismissing a Review slip removes the catalog row instead of leaving a `resolved` ghost that could reappear on browse.

## [0.4.9] — 2026-09-23

### Added

- **Review Purge duplicates.** Owner/op bulk button dismisses safely redundant slips: same media fingerprint already on the shelf (Calibre rename twins included), or exact duplicate slips of each other (keeps the oldest). Ambiguous Identify singles without a twin stay put. Background job with a live progress meter, same pattern as Clear extra-files.

## [0.4.8] — 2026-09-23

### Fixed

- **Review Apply on Calibre duplicates.** When the shelf already holds the same media bytes under Calibre filenames (`Title - Author.epub`) but `dest_layout` would write `Title.epub`, Apply no longer 400s as a hard collision — it treats the slip as an ignored duplicate and dismisses it.
- **Review error copy.** Collision / Apply guidance is no longer masked as “Something went wrong in the stacks” when the API message is slightly over the generic length cap.
- **Review loading state.** Bagging-area skeleton while `/api/review` loads so empty copy does not flash first.

## [0.4.7] — 2026-09-22

### Highlights

- **Add-to-shelves knows the tree before it starts.** Deep folders get a recursive pre-scan so the progress meter denominator matches real volume count, with live “found N volumes / M files” while scanning.
- **Seen / added / ignored duplicates.** Completion (and the Maintain dock) report household tallies — including binary-identical copies skipped early or when the shelf already holds the same bytes.

### Added

- **Ingest pre-scan inventory.** Background worker expands Calibre-style trees with progress ticks (`volumes_found`, `files_found`) before organizing.
- **Content fingerprint duplicates.** Batch copies sharing the same media payload are ignored up front; shelf collisions that are byte-identical (size+inode or SHA-256) skip Review instead of parking a collision slip.
- **Richer shelving UI.** Phase, depth-friendly path, running tallies, recent activity log, and indeterminate scan meter on Maintain Add-to-shelves / status dock.

### Changed

- **Ingest progress summary.** Finished line is `seen / added / ignored duplicates` (plus needs you / skipped / failed when present). Job status `skipped` covers ignored duplicates.

## [0.4.6] — 2026-09-22

### Highlights

- **Hall is search again.** Hero and search paint first; Tonight’s Shelf and rails lazy-load with a clear warming state. Bestsellers, add-on-disk, and celebration notes left the Hall.
- **Owner Maintain.** Curated lists, ingest, Review/Clear extra-files, scan/enrich, and Goodreads live on `/maintain` with a telemetry status dock. Credentials stay in Settings.
- **Settings you can find.** Sticky section list replaces Next/Previous wizard chrome. Indexers (NZBFinder + additional Newznab hosts + RSS) are a first-class section.

### Added

- **Maintain page (owner).** `/maintain` — bestsellers entry, Add to the shelves, Review link, Clear extra-files, scan/enrich/suggestions, Goodreads CSV, and a status dock for scan/enrich/ingest/clear jobs (same progress pattern as Review/Settings).
- **Hall deferred shelves.** Search hero renders immediately; bottom rails fetch after paint with `hall-shelves-loading` warming copy.
- **Settings Indexers section.** NZBFinder, Add indexer / edit / remove for `extra_indexers`, RSS subscribe panel, and category extras — no longer buried under collapsed “Extra Newznab hosts”.

### Changed

- **Settings IA.** Persistent section nav (Appearance · Downloader · Indexers · Shelves · Bagging · Language model · Integrations · Household · Watch folder · About). Setup Prev/Next removed; deep-links keep working (`#indexer` → Indexers, `#release-notes` → About).
- **Hall / Search chrome.** Hall keeps Discover as a muted link only; grooming and curated-list CTAs moved to Maintain.
- **Settings Ingest.** Watch folder credentials remain; add-on-disk points to Maintain.

### Removed

- **Hall celebration banner** (e.g. “Nth Author this year” + Quiet) — no longer shown on the public Hall surface.

## [0.4.5] — 2026-09-22

### Highlights

- **Review Clear and ingest progress you can see.** Extra-files Clear runs in the background with a live meter; Add-to-shelves progress sits above the path list with a percent meter.
- **Kind shelf totals.** Hall, Stacks, and Search show how many titles are on each media shelf.

### Added

- **Kind shelf totals.** Stacks, Hall kind rails, and Search kind chips show household counts for the active media type (e.g. “1,234 books on the shelves”, “56 audiobooks”) from browse/hall totals — no extra clutter.
- **Review Clear extra-files progress.** Bulk clear runs in the background with a live meter (shelved / split / applied / failed); the Clear CTA stays visible for backlog past the page window and mid-run jobs.
- **Ingest progress meter.** Shelving progress sits above the path list with a percent meter and safer legacy-job detection.

### Fixed

- **Clear extra-files no longer hangs on author dumps.** Large Calibre author folders enqueue title children for the ingest poller (with progress heartbeats) instead of sync-organizing hundreds of books on the Clear thread; per-item timeouts skip stuck slips. SQLite mutations use a Projectionist-style write serializer so Review Apply/Suggest stay responsive while Clear runs.
- **Review API hang from library-root parent rglob.** Suggest skips `rglob` of library-root parents and only runs when diagnosis has a problem, so `GET /api/review` finishes in seconds.
- **Peek contrast + multi-format extra files.** Rematch Peek tokens for lights-up readability; expand Calibre ingest trees; owners can clear `extra_files` slips without dead Retry/Repair actions.
- **Ingest PermissionError / collisions.** Park PermissionError organizes in Review, isolate poller failures, and preflight multi-file dest collisions before any relocate.
- **Retired Gemini models.** Coerce known-retired Gemini ids to the recommended Flash model with friendlier errors; ProfileMenu stays open while using the text-size slider.

## [0.4.4] — 2026-09-20

### Added

- **Settings sections: Ingest + About.** Jump nav is Downloader · Indexer · Shelves · Bagging · Ingest · About. Add to the shelves and Watch folder live under Ingest; version, build stamp, and What’s New / release notes live under About. Hall keeps its compact add control. Deep-links: `/settings#ingest`, `/settings#about`, `/settings#release-notes`.

### Changed

- Health payload includes optional `build` from `/app/.build-info` when the image was stamped.

## [0.4.3] — 2026-09-20

### Added

- **Profile menu + personal appearance.** Click the name/role chip for theme (Lights Up / Lights Down / Match system), a six-step text-size slider (default + five larger), room wash (off / paper / lamp), owner links, and Logout at the bottom. Prefs persist via `api.prefs` + localStorage; Settings “Your appearance” shares the same store. Quiet hours stay household-only.

## [0.4.2] — 2026-09-19

### Added

- **Live progress for Add to the shelves.** Pointing at a dump parent (e.g. `/data/usenet/complete/books`) expands each child, runs in the background, and polls `GET /api/ingest/status` with phase, current path, and shelved / needs you / skipped counts under the Add button.

### Fixed

- **Enrich abort on locked shelf folders.** Writing `cover.jpg` into a root-owned library folder (`PermissionError` / Errno 13) no longer fails the whole enrich batch. Cover writes fall soft to `/config/covers/{id}/` when the shelf is not writable, progress shows household copy instead of raw Errno 13, and the trickle continues.
- **Ingest Internal Server Error on comic convert.** `BadZipFile` during loose-image → CBZ no longer 500s the Add request; convert fails soft and identify continues.
- **SAB complete organize left dumps behind.** Confident shelve from SAB now moves (same as manual ingest / watch); Review and collisions still keep the staging folder.
- **Stale “Adding…” after a rebuild.** A `running` progress blob with no live worker clears to a household “lamp was restarted” message.

## [0.4.1] — 2026-09-19

### Fixed

- **Bestsellers “LLM HTTP 400” on Gemini.** An OpenAI-shaped `LLM_API_KEY` (or leftover active key) is no longer stamped onto the Gemini profile — Google returns HTTP 400 “API key not valid” for `sk-…` keys. Provider error bodies now surface as household copy (bad key / bad model) instead of bare `LLM HTTP 400`.
- **`docker-run.sh` forwards Gemini/Anthropic/OpenAI env aliases** (`GEMINI_API_KEY`, `GOOGLE_API_KEY`, `LLM_PROVIDER`, etc.) so kit `.env` keys actually reach the container.

## [0.4.0] — 2026-09-19

### Highlights

- **Audiobook scene → Audnexus → M4B shelf.** Dump names scrub to author/title/narrator/series/ASIN; Audnexus scores matches into organize or Review; multipart audio remuxes to a single tagged `{Title}.m4b` under the series-aware shelf layout.
- **Comics scene → ComicVine → clean CBZ.** Scene scrub + volume-year disambiguation; ComicInfo.xml in the archive; publisher/series shelf paths with fail-soft Komga scan + Open in Komga.
- **Audiobookshelf scan + listen progress.** After shelving, Librarian asks ABS to scan; Listen pulls/pushes progress for matched titles without wiping a better local bookmark.

### Added

- `audiobook_normalize` / `audnexus` / `m4b` (ffmpeg in the image) + golden scene fixtures.
- `comic_normalize` / deepened ComicVine match + `komga` federation client and Settings fields.
- ABS library scan notify + bidirectional listen progress sync on work/Listen APIs.
- Review / peek / Settings polish for Audnexus candidates, Komga links, and ABS progress.

### Changed

- Media contract: audiobooks `{Author}/{Series}/{Index} - {Title} ({Year})/` with `{Title}.m4b`; comics `{Publisher}/{Series} ({VolumeYear})/` (legacy scan still accepted).
- Organize dest layouts and identify/enrich paths for spoken-word and sequential-art authority.

### Fixed

- Enrich progress reporting stays honest across longer Audnexus/ComicVine match runs.

## [0.3.1] — 2026-09-19

### Highlights

- **Edit metadata and Fix match on title pages.** Owners and ops can correct wrong enrich blurbs (like Open Library’s Springsteen+Morpurgo *Born to Run* corruption), pick an alternate catalog match, or undo enrich.
- **Multi-provider BYO LLM.** Settings supports OpenAI, Anthropic, and Gemini profiles; Find uses LLM best-match with remembered alternates, disclosures, and clearer 429 handling.
- **Bestsellers and chase polish.** Cover cards and request-missing chase/auto-request flows; Enrich/Review actions show busy feedback.

### Added

- Catalog Edit / Fix match / Undo enrich on work pages (`PATCH /api/works/{id}/metadata`, match-candidates, apply-match, clear-enrich).
- Open Library title+author scoring that rejects foreign co-author corruptions and prefers memoir/autobiography when the author matches.
- Native LLM provider catalog (`librarian/llm_providers.py`) + Settings panel.
- Search rank memory + trace disclosures; Bestsellers UI cover improvements; shared action busy labels.

### Fixed

- Enrich no longer blindly takes Open Library’s first search hit when the author list includes unrelated co-authors.
- Pytest isolates maintainer `.env` LLM keys so enrich/review tests stay offline.

## [0.3.0] — 2026-09-18

### Highlights

- **Listen to audiobooks in the Reading Room.** Phase 2b ships an in-app player (chapters, progress) with deep-links when Plex/ABS is configured — peeks and work pages say Listen, not a raw Read.
- **Bestsellers from your BYO LLM.** Curated list presets match the household shelves, then chase missing titles as books and audiobooks (confirm before SAB). Optional NYT Books API remains a soft-deprecated fallback.
- **Stuck unpacks can recover.** Archive-only / empty SAB dumps go through organize (par2+unar) and land a Review slip instead of failing with no work — so audiobook RAR recoveries stay visible in Queue/Review.
- **Finish-set ETA and smart re-grab deepen.** Size-aware approximate ETAs when samples are thin; re-grab ranks by series/base, part markers, size, and host with clearer diffs.
- **Community UX polish.** Clear Read CTAs, peeks that open the full work page, and book→audiobook companion Listen when the matching title is already shelved.

### Added

- In-app audiobook Listen (`librarian/listen.py`, `AudiobookPlayer`) + chapter API; book→audiobook companion CTAs.
- LLM curated lists (`librarian/lists.py`) + chase (book and audiobook); Bestsellers panel on Find; optional NYT Books client as fallback.
- `NYT_BOOKS_API_KEY` env wiring in `docker-run.sh` / Automat playbook.

### Changed

- Finish-set ETA returns approximate size-scaled minutes when median samples are scarce; labels use `≈` vs `~`.
- Review re-grab candidate ranking and human diffs (same series, part markers, % size, host).
- Phase 2b Listen marked done on the living roadmap.

### Fixed

- `poll_job` no longer marks `unpack_stuck` failed with no `work_id` — organize/Review recovery stays available for audiobook archives.

## [0.2.3] — 2026-09-17

### Fixed

- **Discover/Find cover titles no longer ellipsis-truncate.** Cloth card primary titles wrap fully (cards grow with the title); cover-art frames stay fixed. Same principle as Smart Map Browse — titles you can actually read.

## [0.2.2] — 2026-09-17

### Highlights

- **What’s New greets you on first visit.** Missing `last_seen` (new browser / cleared storage) opens the modal for the current version; dismiss sets last-seen. Upgrades still greet when runtime is newer.

### Fixed

- Stop silently seeding `librarian.last_seen_version` on first visit so What’s New never appears.

## [0.2.1] — 2026-09-17

### Highlights

- **Cover cards lead with the real title.** Publisher-heavy NZB names (TOKYOPOP, IMAGE COMICS, and friends) no longer crowd out the series on Discover and Find — primary labels show the distinctive title; the raw dump stays on hover/peek.

### Fixed

- Demote publisher prefixes on Discover/Find cover cards (`displayTitle`) so cloth labels stay readable.

## [0.2.0] — 2026-09-17

### Highlights

- **What’s New greets you after an upgrade.** Runtime version vs last-seen opens a short modal; Settings keeps the full release-notes history (generated from this CHANGELOG).
- **Multipart sets know their holes.** Catalog `part_set` tracks owned vs total; Find groups Part N/M / CDn sets, chases missing NZBs when listed, and stays honest when gaps are unlisted.
- **Tonight’s shelf and quiet delight.** Continue + a quick gap + a Discover surprise; cover stories, series ribbons, celebrations, Plexamp handoff (music only), whispers, quiet hours for Review, finish-set ETA, and ambient prefs.
- **Advanced Search and Find fields suggest while you type.** Author, title, series, artist, album, and year pull from the household catalog first (optional on-disk cache under `/config/suggest-cache`). Freeform typing still works; owners can refresh the seed from Settings.
- **Volumes already on disk can be filed.** Owners and ops Add a `/data` folder or file — confident identify moves and renames; anything unexpected waits in Review. A Watch folder does the same for drops. Scan still only catalogs; it does not move files.
- **Find asks the indexer the way Newznab expects.** Kind chips swap the form: books/magazines send title, author, and ISBN; comics search series and issue in `7030`; music uses artist and album (never a book ISBN); audiobooks stay on `3030`. Request stores what you sought, what you picked, and the metadata the indexer actually returned — not SABnzbd’s dump name.
- **The downloader tells the truth.** Completed SAB jobs use the real complete folder (mapped through SAB complete root), failed unpacks say Failed with a reason, and the catalog title stays the title you asked for — not the Usenet dump name.
- **Thin books get a real catalog.** Owner Enrich pulls description, series, year, and cover from Hardcover (token in Settings) then Open Library. The LLM still never invents an ISBN.
- **Find can peruse what’s trending.** Empty Find is Discover: real indexer category feeds from capabilities (not a second Hall, not auto-SAB). Show categories (off by default) adds Movies/TV/XXX — those go to the downloader / *arr, never The Hall.
- **Hall Gaps know the rest of the run.** Missing series volumes, comic issues, and album tracks come from Hardcover / Open Library, Comic Vine, and MusicBrainz. Clicking a hole opens Find — SAB never fires from a shelf browse.
- **Goodreads shelves land on Favorites.** Upload a CSV export; rows match by ISBN. Missing books become thin works that need Find.
- **The Hall remembers where you left off.** Opening a volume plants a Continue bookmark; Finished clears it. Covers are real `cover.jpg` when we can fetch them.
- **Identify can convert and ask the house LLM.** CBR→CBZ via `unar`, PDF-only books via `ebook-convert` when present, BYO LLM never invents an ISBN. SAB jobs poll in the running process, not only when you open Queue.
- **Automat-ready kit.** Maintainer playbook at `docs/ops/AUTOMAT.md`, `/config` + `/data` mounts that survive recreate, and a Hub `rollout.sh` stub for later. LAN truth is `http://10.10.1.202:8793` — not a public VIP.
- **Safe behind your reverse proxy.** `LIBRARIAN_TRUST_PROXY_HEADERS` is off unless you opt in. Spoofed `X-Forwarded-*` cannot mark cookies Secure, cannot rotate the login throttle, and cannot pretend the hop is HTTPS. Login and invite routes are rate-limited.

### Added

- What’s New upgrade modal (`WhatsNewGate`) + Settings release-notes panel; `scripts/generate-release-notes.sh` → `frontend/public/release-notes.json`.
- Catalog multipart `part_set` (owned / total / style / base) with Hall/Work “Find missing parts”, Review regrab hints, and Find PartSet chase (honest when NZBs are unlisted).
- Part E delight: Tonight’s shelf, cover stories, series ribbons, celebration banners, Plexamp toast (music Promote), whispers, quiet hours, finish-set ETA, ambient prefs, finish-set labels.
- Typeahead suggestions for Search/Find advanced fields (`GET /api/suggest`) plus owner **Refresh suggestions from shelves** (`POST /api/settings/suggest-cache`). Catalog-first; optional bounded MusicBrainz seed.
- Owner/op **Add to the shelves** (`GET /api/fs`, `POST /api/ingest`) and **Watch folder** (`watch_root` / `watch_enabled`). Identify/organize when confident; Review when not. Scan does not move files.
- Kind-morphing Find fields + NZBFinder v2 `books` ISBN param; job payload `sought` / `selected` / `retrieved`.
- Honest SAB complete-path remap, fail/unpack reasons, and Find title/kind kept through identify.
- Owner **Enrich the shelves** / work-page Enrich: Hardcover GraphQL then Open Library; covers reuse indexer URL / Open Library ISBN / CBZ page 1.
- Catalog gaps: Hardcover then Open Library series volumes; Comic Vine issue lists (`comicvine_api_key`, masked); MusicBrainz track lists (User-Agent + polite rate limit). Magazines stay local `YYYY-MM`. Hall Gaps open Find; confirm stays off the shelf.
- Extra Newznab v2 hosts in Settings; Find merges/dedupes by guid and keeps NZBFinder hits if another host 502s.
- Find **Discover** (`GET /api/discover`): capabilities category feeds, latest-in-cat via v2 search or `/rss?t=`. Show categories (owner; `show_extra_categories`) can include Movies/TV/XXX. Movie/TV Request queues SAB then tells Radarr/Sonarr to expect; XXX is SAB default folder only.
- RSS subscriptions (owner/op on Find or Settings): poll in-process; new items become **Asked** jobs for confirm — not silent SAB.
- Optional Audiobookshelf URL + token (masked; env `AUDIOBOOKSHELF_API_TOKEN`). Match by ISBN then author+title; quiet **On the player** chip. Does not replace `audiobook_target` default Plex.
- Owner **Import Goodreads CSV** onto Favorites, matched by ISBN-10 or ISBN-13. No Goodreads OAuth.
- `hardcover_api_token` in settings.json (masked on GET; env `HARDCOVER_API_TOKEN` seeds first boot).
- `comicvine_api_key` in settings.json (masked on GET; env `COMICVINE_API_KEY` seeds first boot). Hardcover does not cover issue-numbered comics.
- `docs/ops/AUTOMAT.md` runbook (kit path, first-boot env, rsync, deploy).
- Proxy-header fail-closed (`librarian/proxy.py`) + per-IP rate limits on login / invite validate / redeem.
- `PUID`/`PGID` 99/100 on Unraid, `extra_hosts` for `downloader.sl` when the host can resolve it, `rollout.sh` Hub pull stub.
- Continue rail + per-user progress; cover fetch (indexer / Open Library ISBN / CBZ page 1); CBR→CBZ (`unar` in the image); on-demand `ebook-convert` cache under `/config/conversions`.
- BYO LLM identify (structured JSON; invented ISBN dropped); background SAB poller; `indexers` table + owner **Ping NZBFinder**.
- Local audiobook part holes and music track-number holes.

## [0.1.0] — 2026-09-14

Initial household reading-room kit on Automat.

### Highlights

- **The Hall, not a grabber.** FastAPI + Vite Reading Room on port **8793**, with owner / op / reader roles and invite-only join.
- **Stacks that know their kinds.** Books (EPUB), magazines, comics (CBZ + ComicInfo), audiobooks (Plex target by default), incoming music with Promote.
- **Honest gaps.** Local magazine `YYYY-MM` holes and comic issue-number holes — confirm before SAB.
- **Automat kit.** `/config` + `/data`, `docker-run.sh` on-host build, settings.json wins, no collision with 8788 / 8790 / 8791 / 8792.

### Added

- Python 3.12 package `librarian/` with SQLite WAL catalog, HMAC invites, NZBFinder v2 client, SABnzbd status machine, identify/organize, FTS search.
- Docs: README, DOCKER, TESTING, SECURITY, HELP, and the 2026-09-14 design spec.
