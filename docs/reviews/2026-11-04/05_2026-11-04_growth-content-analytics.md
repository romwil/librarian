# 05 · Growth, Content & Analytics — Librarian — run 2026-11-04

**Reviewed:** Automat `1.0.10 / 480eff0`; ~10.8k books; Sorting 27; Downloads ~80 · **Grade: B**

**Companions:** [Platform map](00_2026-11-04_platform-map.md) · [Architecture](08_2026-11-04_architecture.md) · [Performance](09_2026-11-04_performance-reliability-cost.md) · [Operations](10_2026-11-04_operations-support.md) · [Backlog](2026-11-04_backlog.csv)

# Part A — Conclusions & findings

## 1. Bottom line

Librarian does not need public-acquisition machinery. Growth means an invited relative reaches first value, returns to Continue, or asks for a title, while the owner confirms and resolves work without the desks becoming a second job. The voice and privacy posture are strong, and the owner-only House pulse is the right home for measurement. The largest gap is that the product cannot explain Ask→Confirm→Arrived or Sorting age and resolution (GRO-004). Fix the first-party event contract first; protect invite-only access, the library lexicon, and image-truthful What’s New (GRO-001, GRO-002, GRO-003).

## 2. Key conclusions

1. **Household activation is the growth model.** There is no pricing page, public catalog, or open signup, and adding them would widen the perimeter without serving the product. The useful funnel begins at invite redemption and ends at first shelf value (GRO-001, GRO-004).
2. **The lexicon is an asset, but drift becomes support load.** HELP defines Hall, Sorting, Downloads, Library card, House pulse, Shelving, and the five job words (`docs/HELP.md:30-128`). “Holds,” “Profile,” “Bagging,” and generic “Request” should be treated as defects in rendered copy (GRO-002, GRO-006).
3. **First-party measurement is the correct boundary.** `/api/pulse` is owner-only and explicitly returns household totals without member IDs (`librarian/web/routers/maintain.py:132-136`). Coverage, not a SaaS SDK, is missing (GRO-004).
4. **Backlog counts do not reveal loop health.** Live Sorting 27 and queue ~80 cannot answer Ask→Confirm latency, confirmation success, or median age by Sorting reason (GRO-004).
5. **OPDS is the distribution channel worth growing.** A private 180-day card brings owned shelves into KOReader, Moon+ Reader, or Panels (`docs/HELP.md:130-133`) without making the SPA indexable (GRO-005).
6. **What’s New and New & noted earn their place through honesty.** Status derives release truth from the image (`librarian/web/status.py:53-64`); curated lists never silently queue downloads (`docs/HELP.md:10-27`) (GRO-003, GRO-008).
7. **A/B testing is wrong for one household.** The sample is too small and family inconsistency is a product cost. Compare releases only after a stable baseline exists (GRO-007).

## 3. Foundations challenged

| Assumption | Evidence for | Evidence against | Verdict | Cost | Rationale |
|---|---|---|---|---|---|
| No public marketing site | Private, invite-only household app | Repository discovery is limited | Keep | — | Improve owner docs, not app attack surface. |
| No analytics SDK | Owner-only House pulse exists | Core funnel is unmeasured | Keep boundary; expand events | M | On-box counters answer the question without exporting behavior. |
| Invite-only growth | Auth is on from first boot | Invite conversion is invisible | Keep; measure | S–M | Mechanism fits trust; instrumentation should not change access. |
| Library language everywhere | Canonical glossary exists | Metaphors can obscure controls | Keep voice; use plain actions | S | Warm prose and literal controls can coexist. |
| SEO matters | Install docs may be discoverable | Authenticated SPA is private | Remove from app roadmap | — | OPDS and repository docs are the public surfaces. |
| LLM lists drive retention | Optional fresh lists help | Provider outage/rate limits are normal | Keep optional | S | Activation must not depend on inference. |
| A/B infrastructure is needed | Flags could split behavior | Tiny N; no statistical power | Remove | — | Release comparison is cheaper and honest. |

## 4. If we built it today

The growth system would have three on-box layers: an invite funnel with timestamps and role class; a core-loop ledger for Ask, Confirm, terminal job state, Sorting open, and Sorting resolution; and a four-week House pulse with one north-star plus guardrails. It would store opaque IDs, enums, counts, and durations—never query text, titles, paths, emails, tokens, or prompts. Owners would see household totals only.

The gap is moderate and worth closing because pulse routing, roles, queue states, Sorting reasons, and version stamps already exist. A hosted analytics integration is faster to demo but violates the product boundary; log parsing is cheaper but too brittle. Build a small explicit contract now.

## 5. Findings by surface

**Public.** There is intentionally no public app funnel: the platform map confirms login, join, reset, health, features, release notes, and OPDS are the bounded public surfaces. Install discovery belongs in repository/package docs; member conversion belongs at invite/login. **Grade: B.** IDs: GRO-001, GRO-003.

**Consumer.** Hall, Continue, Favorites, New & noted, and OPDS create credible return paths. Canonical vocabulary is strong; occasional legacy nouns weaken it (GRO-002, GRO-006). OPDS is capable but buried (GRO-005). **Grade: B+.**

**Owner.** Maintain exposes House pulse, backup, poller, and indexer weather, but the pulse cannot show whether the core loop is improving (GRO-004). **Grade: B-.**

**Admin/Ops.** Status and release truth are well designed; poller step status exposes last run/error (`librarian/poller.py:259-281`). No experiment platform is needed (GRO-007). **Grade: B.**

## 6. Findings by theme

**Activation:** strongest at Hall; weakest at unmeasured invite→first-value. **Content:** strongest in the glossary; weakest in legacy synonyms. **Distribution:** OPDS fits; SEO does not. **Analytics:** aggregate boundary is right; transition coverage is not. **Experimentation:** use version windows, not family-member arms.

## 7. Stop doing

- Stop treating raw queue and Sorting counts as proof of value (GRO-004).
- Stop introducing synonyms for glossary terms (GRO-006).
- Do not add hosted analytics, app SEO, experiment cookies, or per-member leaderboards (GRO-001, GRO-004, GRO-007).
- Stop exposing internal review IDs in member-facing release prose (GRO-003).

## 8. Strengths worth protecting

- Invite-only access and first-boot auth (GRO-001).
- Canonical household lexicon at `docs/HELP.md:107-128` (GRO-002).
- Image-derived version/notes truth (GRO-003).
- New & noted’s no-silent-download rule and capped Hall rails (`librarian/web/routers/hall.py:45-68`) (GRO-008).
- Owner aggregates with no third-party analytics (GRO-004).

## 9. Risks of inaction

Roadmap debates will continue to use screenshots and inventory counts instead of activation and resolution data. Sorting automation could improve while the pile grows for unrelated reasons, or regress while cleanup masks it. OPDS remains expert-only, copy drift increases support load, and a future contributor may reach for a hosted SDK because no event contract exists.

## 10. Recommended direction

**Now:** ratify the event/privacy contract and finish the string audit (GRO-004, GRO-006). **Next:** persist daily aggregates, add Ask→Confirm→Arrived and Sorting-open→resolved trends, and surface OPDS activation (GRO-004, GRO-005). **Later:** compare 28-day release windows; do not build A/B infrastructure (GRO-007).

Success in 90 days: Ask→Confirm p50/p95, Arrived/Failed rate, median Sorting age, and resolutions by reason are visible; analytics egress remains zero; deprecated nouns have no new rendered occurrences.

## 11. Scorecard

| Surface | Positioning | Voice | Lifecycle | Measurement | Privacy | Overall |
|---|---:|---:|---:|---:|---:|---:|
| Public | 4 | 4 | 3 | 2 | 5 | 4 |
| Consumer | 4 | 4 | 4 | 2 | 5 | 4 |
| Owner | 4 | 4 | 4 | 2 | 5 | 3 |
| Admin/Ops | 3 | 4 | 4 | 3 | 5 | 4 |

# Part B — Detailed findings

## 12. Scope & method

Reviewed the [platform map](00_2026-11-04_platform-map.md), prior document, backlog CSV, HELP, Automat runbook, package metadata, Hall/Maintain/status/poller source, and supplied live facts. No member-level data or SaaS analytics were queried. Missing: a measured invite cohort and reader-role live walkthrough.

## 13. Strengths

### GRO-001: Protect private household growth

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Public |
| Persona(s) | Owner, invited reader |
| Category | Growth model |
| Severity | High |
| Impact | 5 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 15 |
| Verdict | Protect |
| Dependencies | GRO-004 |
| Labels | invite-only, privacy |

**Evidence:** `docs/HELP.md:1-8`; `docs/ops/AUTOMAT.md:33-47`.

**Current state:** Growth is bounded to a household. **Root cause:** Librarian is a reading room, not a tenant platform.

**Recommendation:** Keep invitation access; measure lifecycle on-box.

**Rationale:** This protects trust and reduces abuse. A separate public project page may come later; open signup should not.

**User story:** As an owner, I want growth to remain invitation-based so my shelves stay private.

**Acceptance criteria:** [ ] No open-signup route. [ ] Invite events contain no email/token.

**Success metric:** Zero uninvited accounts; invite-to-first-value measurable.

**Validation:** Route inventory and first-boot auth test.

### GRO-002: Protect the library lexicon

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | All |
| Category | Voice |
| Severity | Medium |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 8 |
| Verdict | Protect |
| Dependencies | GRO-006 |
| Labels | copy, glossary |

**Evidence:** `docs/HELP.md:107-128`; `frontend/src/copy/glossary.js:3`.

**Current state:** One coherent reading-room model. **Root cause:** terminology is treated as a contract.

**Recommendation:** Require new labels to reuse or extend the glossary.

**Rationale:** Consistency reduces cognitive load; generic SaaS wording would sacrifice identity.

**User story:** As a reader, I want Help and screens to use the same nouns.

**Acceptance criteria:** [ ] New nouns have glossary entries. [ ] Glossary test remains green.

**Success metric:** Zero new synonym drift.

**Validation:** Copy audit and unit test.

### GRO-003: Protect honest What’s New

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Owner |
| Persona(s) | Owner |
| Category | Lifecycle content |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6 |
| Verdict | Protect |
| Dependencies | — |
| Labels | version, whats-new |

**Evidence:** `librarian/web/status.py:15-24,53-64`; `docs/ops/AUTOMAT.md:20-29`.

**Current state:** Notes/version truth comes from the image. **Root cause:** mutable config and public health were deliberately excluded.

**Recommendation:** Keep `notes_match`; retain benefit-led notes.

**Rationale:** Owners need trustworthy upgrades. A remote feed creates stale-state ambiguity.

**User story:** As an owner, I want notes to match the image running now.

**Acceptance criteria:** [ ] Status remains image-based. [ ] About links full notes.

**Success metric:** Zero mismatch incidents.

**Validation:** Compare `.build-info` and owner status.

## 14. Weaknesses

### GRO-004: Instrument the core loop on-box

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Owner, maintainer |
| Category | Analytics |
| Severity | High |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 4.0 |
| Verdict | Add |
| Dependencies | Queue/Sorting states |
| Labels | metrics, house-pulse |

**Evidence:** owner-only aggregate pulse at `librarian/web/routers/maintain.py:132-136`; live Sorting 27/queue ~80; operational status at `librarian/poller.py:259-281` lacks product transitions.

**Current state:** The house counts work but cannot explain flow. **Root cause:** metrics were feature-local rather than lifecycle-led.

**Recommendation:** Add local events and daily rollups under the contract below; keep raw events 90 days and daily aggregates 400 days.

**Rationale:** Required to judge queue/Sorting changes. Logs are brittle; SaaS violates trust. Now is right because these live backlogs drive priorities.

**User story:** As an owner, I want to see where Asks wait so I can improve the loop.

**Acceptance criteria:** [ ] Ask→Confirm p50/p95. [ ] terminal outcome rate. [ ] Sorting age/resolution. [ ] no free text or egress.

**Success metric:** Weekly Arrived-within-seven-days chart; silent SAB additions = 0.

**Validation:** Synthetic events, retention test, role test, outbound-network assertion.

### GRO-006: Complete the string consistency pass

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | All |
| Category | Content |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Likely |
| Priority score | 2.4 |
| Verdict | Fix |
| Dependencies | GRO-002 |
| Labels | copy, lexicon |

**Evidence:** canonical terms at `docs/HELP.md:107-128`; internal `review*` identifiers remain at `frontend/src/api.js:159-206` and must not leak to rendered copy.

**Current state:** Most copy is coherent; edge/error states may preserve old nouns. **Root cause:** internal compatibility outlives UI renames.

**Recommendation:** Audit rendered strings; add an allowlisted deprecated-term check.

**Rationale:** Route renaming is risky and unnecessary. A string contract solves the user problem now at S effort.

**User story:** As a reader, I want labels and Help to match.

**Acceptance criteria:** [ ] No rendered Holds/Profile/Bagging. [ ] role CTA remains Get/Ask the house.

**Success metric:** Zero glossary violations in new chrome.

**Validation:** String scan and four-surface walkthrough.

## 15. Opportunities

### GRO-005: Activate OPDS as private distribution

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Consumer |
| Persona(s) | Power reader |
| Category | Distribution |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Likely |
| Priority score | 2.4 |
| Verdict | Add |
| Dependencies | Library card |
| Labels | opds |

**Evidence:** `docs/HELP.md:130-133`; `frontend/src/api.js:67-69`.

**Current state:** Capable but buried. **Root cause:** treated as integration detail.

**Recommendation:** One Library card panel with named clients, copy action, expiry warning, revoke/regenerate.

**Rationale:** Extends owned shelves without SEO or another reader engine. Do next after copy consistency.

**User story:** As a power reader, I want to connect my reader app in one minute.

**Acceptance criteria:** [ ] One-panel setup. [ ] bearer warning. [ ] regeneration invalidates old link.

**Success metric:** At least one household OPDS client connected.

**Validation:** Connect a supported client on LAN.

### GRO-007: Compare releases instead of A/B testing

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Admin |
| Persona(s) | Maintainer |
| Category | Experimentation |
| Severity | Low |
| Impact | 1 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 0.5 |
| Verdict | Add later |
| Dependencies | GRO-004 |
| Labels | release |

**Evidence:** version/revision at `librarian/web/status.py:53-64`; household sample is intrinsically small.

**Current state:** No outcome comparison. **Root cause:** no stable baseline.

**Recommendation:** Compare 28-day windows with minimum 20 events; label directional, not causal.

**Rationale:** Honest and household-consistent. Later is correct because comparison without baseline is theater.

**User story:** As a maintainer, I want to know whether a release moved the loop.

**Acceptance criteria:** [ ] Minimum samples. [ ] No member assignment.

**Success metric:** One release retro cites pulse trends.

**Validation:** Synthetic version windows.

### GRO-008: Protect New & noted

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Consumer |
| Persona(s) | Returning reader |
| Category | Retention |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6 |
| Verdict | Protect |
| Dependencies | — |
| Labels | noted |

**Evidence:** `docs/HELP.md:10-27`; capped Hall rails at `librarian/web/routers/hall.py:45-68`.

**Current state:** Freshness without automatic acquisition. **Root cause:** discovery is separated from Request.

**Recommendation:** Keep no-silent-download and short rails.

**Rationale:** Retention without feed addiction or queue toil.

**User story:** As a reader, I want fresh lists without hidden downloads.

**Acceptance criteria:** [ ] Lists never auto-request. [ ] Hall remains capped.

**Success metric:** Opens do not increase unconfirmed jobs.

**Validation:** Playwright network assertion.

## Appendix A — Voice, tone, and ten rewrites

**Voice:** calm household librarian—warm, precise, quietly ceremonial. **Controls:** literal verbs and canonical nouns. **Errors:** what happened, what is safe, one next step. **Never:** blame the reader or imply integrations are required.

| Problem | Rewrite |
|---|---|
| reader “Request” | **Ask the house** |
| owner “Request” | **Get** |
| “Holds” | **Sorting** |
| “Profile” | **Library card** |
| “Bagging” | **Shelving** |
| empty Discover | “Nothing is trending for this kind yet. Search for a title above.” |
| empty Sorting | “The desk is clear. The lamp can rest.” |
| Confirm ambiguity | “Confirm and send to the downloader” |
| Failed | “It didn’t land. Open details or try again.” |
| no LLM | “Connect an optional model in Settings. Your shelves still work.” |

## Appendix B — First-party tracking plan

**Contract:** on-box only; opaque IDs, enums, timestamps, counts, durations; no titles, queries, paths, emails, tokens, bodies, or prompts. Owner totals only.

| Event | Allowed properties |
|---|---|
| `invite_redeemed` | role, age bucket |
| `session_start` | role, entry |
| `hall_search` | role, has_query, kind |
| `ask_created` | kind, source |
| `confirm_download` | kind, ask-age bucket |
| `job_terminal` | kind, outcome, elapsed bucket |
| `sorting_open` | reason, count bucket |
| `sorting_resolved` | reason, action, age bucket |
| `continue_open` | kind |
| `opds_token_created` | role |

**North-star:** distinct requests reaching Arrived within seven days. **Guardrails:** silent SAB adds 0; Failed ≤10%; analytics egress 0; no member owner breakdown.

## 16. Remediation plan

| Horizon | ID | Work | Effort | Owner | Dependencies |
|---|---|---|---|---|---|
| Now | GRO-006 | String audit and guard | S | Content + FE | GRO-002 |
| Now | GRO-004 | Ratify event/privacy schema | S | Product + privacy + BE | — |
| Next | GRO-004 | Writer, rollup, pulse trends | M | BE + FE | schema |
| Next | GRO-005 | OPDS activation panel | S | FE + docs | — |
| Later | GRO-007 | Release comparison | S | Maintainer | GRO-004 |

## 17. Quick wins

The ten strings, a one-line OPDS prompt, and pulse metric definitions are XS–S and require no vendor.

## 18. Open questions

1. Should the north-star be Arrived or Sorting-resolved within seven days?
2. Is 90-day raw retention acceptable, or should only aggregates persist?
3. Are role-class breakdowns acceptable, or totals only?
4. What minimum volume makes release comparison useful?

## Self-check

- [x] Full Part A and all four surfaces.
- [x] GRO-004/005/006 preserved with full evidence and ticket fields.
- [x] Voice guide and first-party tracking plan included.
- [x] Alternatives and now/later rationale stated.
