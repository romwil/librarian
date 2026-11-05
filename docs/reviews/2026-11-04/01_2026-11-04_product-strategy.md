# 01 · Head of Product — Librarian — run 2026-11-04

**Independent product pass (`PRD`).** Live Automat `http://10.10.1.202:8793`, image **1.0.10** / **480eff0**, existing owner session, review-only. Code evidence is from the Librarian checkout reviewed during this run; live claims are labeled as route/API/snapshot evidence. Shared context: [`00_2026-11-04_platform-map.md`](00_2026-11-04_platform-map.md). **Grade: B+.**

Companion files: [`02_2026-11-04_ux-experience.md`](02_2026-11-04_ux-experience.md) · [`05_2026-11-04_growth-content-analytics.md`](05_2026-11-04_growth-content-analytics.md) · [`10_2026-11-04_operations-support.md`](10_2026-11-04_operations-support.md) · [`20_2026-11-04_cross-examination.md`](20_2026-11-04_cross-examination.md) · [`21_2026-11-04_red-team.md`](21_2026-11-04_red-team.md) · [`31_2026-11-04_big-decisions.md`](31_2026-11-04_big-decisions.md).

---

# Part A — Conclusions & findings

## 1. Bottom line

Librarian is solving a real, coherent household problem: make a large owned media library feel like a place to read and listen, while keeping acquisition controlled and recoverable. At live scale—10,762 books plus four other media kinds—the **Hall-first, owned-first, confirm-before-SAB** proposition remains visible and differentiated. The grade is **B+** because the reader product is stronger than the owner operating loop: 27 Sorting slips and roughly 80 queue jobs show acquisition and identification volume outrunning the desk experience.

The single most important fix is to make **Sorting and Downloads an outcome-managed owner loop**, not merely two feature-rich pages (PRD-003, PRD-011). The single most important thing to protect is the role-separated trust contract: readers **Ask the house**, owner/operators confirm, and uncertain identity goes to Sorting rather than silently contaminating shelves (PRD-010). The next quarter should improve that loop, activate shelves already shipped, and measure household outcomes before adding kinds or primary destinations.

## 2. Key conclusions

1. **The value proposition is unusually coherent for a self-hosted 1.0 product, and it is delivered in the product rather than only claimed in documentation.** The Foyer and Hall use household-library language; the authenticated default is Hall; Search privileges owned works; Beyond and SAB are deliberately separated. That alignment is the reason Librarian feels unlike an Arr dashboard even though it has an acquisition engine. Protecting it means refusing owner widgets that displace hero search and refusing silent download shortcuts (PRD-001, PRD-010).

2. **The reader loop is healthy, but the owner loop is accumulating visible debt.** Continue, favorites, recent additions, Search, work detail, Read/Listen, Wanted, and New & noted give returning readers multiple paths to value. The owner sees “Sorting 27” throughout that experience and faces approximately 80 queue rows. The root cause is not a missing feature; it is that exception volume, terminal-state retention, and triage prioritization have not been productized around a steady-state target. Roadmap implication: set and own “Sorting below 5” and “actionable queue by default” as product outcomes (PRD-003, PRD-005, PRD-011).

3. **Confirm-before-SAB is a trust moat, not removable friction.** The API and roles distinguish reader Ask from owner/operator confirm (`frontend/src/api.js:107`, `238-242`; `librarian/auth.py:26-29,277-283`). A power owner may want fewer clicks, but auto-confirm would transfer model/indexer mistakes directly into bandwidth, disk, and household disputes. The correct roadmap is to make confirmation scannable and fast while preserving the human boundary (PRD-010, PRD-011).

4. **The portfolio is broad enough; the next gains come from depth and consolidation.** The product already spans five kinds, Hall, Stacks, Search/Discover, Noted, Wanted, shelves, readers, queue, Sorting, Maintain, Settings, People, Inbox, newsletters, OPDS, and multiple metadata services. That breadth is credible but creates a temptation to answer operational pain with more destinations. Freeze primary-nav growth and make current owner tools tell one daily story before adding another kind or dashboard (PRD-004, PRD-008, PRD-012).

5. **Named shelves are shipped capability without live activation.** The API supports create, share, add/remove, and delete (`frontend/src/api.js:120-132`), yet the live Hall reported `named_shelves` n=0. This is not evidence that households do not want shelves; it is evidence that feature availability and feature activation are different product jobs. A two-step empty-state action and one suggested starter shelf are a better next investment than a new recommendation surface (PRD-007).

6. **Acquisition for a private product is household activation, not public growth.** Invite-only is the correct default: live had two users and zero open invitations, and there is no public registration or marketing funnel. The product should measure invite redemption, first owned-work open, first Ask, and return behavior locally, without building a SaaS acquisition apparatus or phone-home analytics (PRD-006, PRD-002).

7. **Owner information architecture needs a leadership decision, but a rewrite should not block immediate relief.** Downloads, Sorting, Maintain, and Settings are distinct system concepts; a new owner experiences them as four answers to “what needs me?” The right sequence is education and actionable defaults now, a grouped **Desk** shell next if metrics justify it, and no single-page rewrite. That is the decision in [BD-2](31_2026-11-04_big-decisions.md#bd-2-desk-ia-consolidation-vs-educate-in-place), and PRD-012 remains `DecisionRequired` until leadership records the durable direction.

8. **The 90-day strategy should be “calm at scale,” not “more capability.”** Success means Sorting is habitually below five, actionable queue rows are visible first, shelf-health returns within budget, at least one named shared shelf is active, and the Hall still feels like a library to an owner. This sequence protects differentiation while addressing the only live evidence that threatens it (PRD-003, PRD-007, PRD-009, PRD-011).

## 3. Foundations challenged

| Assumption | Evidence for | Evidence against | Verdict | Cost of change | Rationale |
|---|---|---|---|---|---|
| SC-01 Auth-on, invite-only | Private appliance; live 2 users / 0 invites; no public business model | Adds setup and recovery responsibility to owner | **Keep** | — | Trust and household fit outweigh public funnel reach (PRD-006) |
| SC-02 Library-first home | Hall default; owned Search; coherent reader jobs | Owner badge is visible everywhere | **Keep, repair owner leakage** | S–M | Move operational urgency into a calm Desk pattern, not onto home (PRD-001, PRD-005) |
| SC-03/04 Confirm-before-SAB and Ask | Separate APIs and role boundaries | Adds owner latency | **Keep** | — | The latency should be optimized, not eliminated (PRD-010, PRD-011) |
| SC-05 Sorting label on `/review` | User-facing word is coherent; route compatibility has low cost | Dual terminology appears in code/docs | **Keep label and route** | XS docs | A route rename has no user value if chrome remains consistent |
| SC-08 Low-confidence → Sorting | Prevents wrong shelves; live reasons prove exception taxonomy | 27 slips create owner toil | **Keep; reduce exceptions** | M–L | Better automation must be measured against mis-shelving, not only count (PRD-003) |
| SC-09 BYO LLM for ranking | Live configured; useful for list chase | Cost, privacy disclosure, provider failure | **Keep optional** | — | It is enhancement, not catalog truth; fail-soft is essential |
| SC-10 Single process + SQLite | Simple install, backup, and operations | Shelf-health timed out once at scale | **Investigate, not replace** | L to migrate | Product evidence does not justify distributed infrastructure; performance must prove budgets |
| SC-12 Reading-room identity | Hall, tokens, language, Lights Down all align | Dense owner desks can feel like admin SaaS | **Keep and extend** | M | Differentiation is emotional and functional (PRD-001, PRD-005) |
| SC-13 Five kinds are first-tier | All five have live inventory | Books dominate; music is 97 and has Promote complexity | **Keep now; review music** | M | BD-4 should use support/usage data, not raw count alone |
| SC-15 Owner surfaces are the admin | Correct for one household and one maintainer | Four nouns compete for “needs me” | **Change grouping, not capability** | M | BD-2 governs the shell (PRD-012) |
| SC-19 Named shelves deserve prominence | Complete API and household value | Live n=0 | **Change activation** | S | Prove use before adding shelf complexity (PRD-007) |
| SC-26 Separate owner destinations are learnable | Each has a distinct system object | New owner must learn queue/review/maintain/settings | **Decision required** | M | Educate now, group next, avoid rewrite (PRD-012 / BD-2) |
| SC-27 Sorting is permanent | Exceptions are inevitable across five kinds | Red team asks whether stricter identity can make it near-empty | **Investigate hybrid** | M | BD-3 should compare slip reduction with mis-shelve rate |
| SC-28 Shared shelves will activate themselves | Presence copy and API exist | Live n=0 | **Change** | S | Empty-state activation is a product responsibility |

## 4. If we built it today

Starting from zero, Librarian would still be a single-household, owned-library product. The member shell would remain **Hall · Stacks · Search · My shelves · Inbox · Library card**. Search would show local works first, then offer a clearly bounded “look beyond our shelves” action. A reader could Ask, but never initiate SAB. Work detail would remain the center of reading, listening, progress, and shelving.

The owner experience would be one **Desk** with three jobs, not one giant page: **Confirm** (Asked jobs), **Sort** (identity exceptions), and **Tend** (health and scheduled maintenance). Each tab would expose only actionable items by default, retain history behind a filter, and show one steady-state target. Settings and People would remain separate because they are infrequent configuration, not desk work. The Hall could show at most three owner-only “tends” from the existing morning brief, without replacing search.

The gap to today is mostly shell and prioritization, not substrate. Queue, review reason filters, bulk operations, undo, shelf health, and morning brief already exist (`frontend/src/api.js:159-242`). Closing the gap is worth it incrementally. A full rewrite is not: it would delay the live problems, increase accessibility risk, and erase proven tools. This is why the recommendation is education/actionable defaults now, grouped Desk next, and no consolidated mega-page (PRD-003, PRD-011, PRD-012).

## 5. Findings by surface

### Public

The Foyer communicates a private household library and offers only the actions a real visitor can take: sign in, redeem an invitation, or recover access. The lack of public marketing, pricing, and registration is correct for the current distribution model. The main product obligation is to keep invitation language plain and make first value measurable without introducing phone-home analytics. **Grade: A-.** Findings: PRD-001, PRD-006.

### Consumer

Hall, Stacks, Search, work detail, Continue, favorites, Wanted, Noted, Read, and Listen form a complete owned-library loop. The separation between owned Search, external discovery, Ask, and Confirm is unusually disciplined. The biggest underused asset is named shelves: the capability exists, but live activation is zero. Product should activate what exists before adding another discovery rail. **Grade: A-.** Findings: PRD-001, PRD-007, PRD-010, PRD-013.

### Owner

The owner has substantial power and recovery: reason filters, bulk operations, queue confirmation, retries, undo, morning brief, shelf health, cleanup, indexer scorecard, People, and Settings. The experience is less coherent than the feature set. Twenty-seven open slips and approximately 80 queue jobs are the strongest live product evidence in this review, and the persistent badge makes that debt part of every Hall visit. **Grade: B-.** Findings: PRD-003, PRD-004, PRD-005, PRD-009, PRD-011, PRD-012.

### Admin

Administration is appropriately collapsed into the owner for one household. People, invitation, reset, role, disable, delete, backup, status, and settings cover the likely needs without inventing a SaaS console. The risk is that product growth turns every operational tool into a top-level destination. Keep admin owner-scoped and resist a separate platform shell until a second household or support organization actually exists. **Grade: B+.** Findings: PRD-006, PRD-008, PRD-012.

## 6. Findings by theme

### Value proposition and differentiation

Best example: Hall defaults to owned works and feels like a reading room. Worst risk: the Sorting badge turns every owner page into an incident surface. Direction: preserve Hall hierarchy and contain operational urgency inside deliberate owner affordances (PRD-001, PRD-005).

### Jobs to be done

Reader jobs—find, resume, read/listen, favorite, Ask—are well served. Established-owner jobs are functionally served but not outcome-managed. “Clear what needs me” spans two queues and Maintain without one target or sequence. Direction: make actionable defaults and steady-state metrics explicit (PRD-003, PRD-011, PRD-012).

### Core loops

Acquisition is owner invitation; activation is opening an owned work; retention is Continue, shelves, and new additions; household referral is Ask/shared shelves. Owner retention is the willingness to keep Sorting and Downloads healthy. The loop breaks when terminal queue history and identity exceptions become a permanent pile. Direction: instrument local funnel events and protect the confirm boundary (PRD-002, PRD-010, PRD-011).

### Portfolio and product debt

The platform has enough surfaces. The debt is breadth without weekly prioritization, zero named-shelf activation, and unfinished quiet-hours/digest polish. Direction: freeze primary-nav expansion, publish the weekly owner job, and complete existing loops before adding kinds (PRD-004, PRD-007, PRD-008, PRD-013).

### Measurement

Live counts prove scale, not success. The owner needs local measures: open Sorting slips, actionable Asked age, time to confirm, shelf-health latency, invite-to-first-open, named-shelf adoption, and silent-SAB incidents (target zero). Direction: a small on-box event model, no third-party analytics requirement (PRD-002, PRD-003, PRD-009).

## 7. Stop doing

Stop adding primary navigation destinations for niche owner tools. New actions should fit Confirm, Sort, Tend, Settings, or People unless evidence proves a new recurring job (PRD-008, PRD-012).

Stop treating queue row count as useful without distinguishing actionable from terminal history. The owner should not scan Arrived jobs to find Asked jobs (PRD-011).

Stop assuming shipped shelves will activate through presence copy alone. If a feature is strategically important, give it a concrete first action and measure adoption; otherwise demote it (PRD-007).

Stop adding media kinds or Calibre-shaped metadata power until Sorting is habitually below five and shelf-health meets its budget (PRD-003, PRD-004).

Never add automatic SAB confirmation from Search, Discover, LLM output, or a “trusted indexer” shortcut. Faster review is allowed; removal of the human trust boundary is not (PRD-010).

## 8. Strengths worth protecting

Protect the Foyer/Hall proposition and owned-first Search (PRD-001). Protect invite-only household scope (PRD-006). Protect reader Ask, owner/op Confirm, and fail-to-Sorting behavior (PRD-010). Protect the role model's server-side enforcement rather than relying on hidden links (`librarian/auth.py:277-283`). Protect the reading-room language and Lights Up/Down identity when densifying owner tools.

Protection means adding regression tests and product acceptance criteria, not freezing pixels. The Hall may gain a small owner tend card, but search remains primary. Downloads may become denser, but confirm remains explicit. Sorting may gain better automation, but wrong-shelf rate must remain a guardrail.

## 9. Risks of inaction

Within six months, a persistent Sorting pile will normalize “Needs you” as noise. Owners will stop resolving it, metadata and paths will drift, and reader trust in work detail will erode (PRD-003).

An 80-row queue that mixes action and history will make confirmation slower and invite accidental decisions. Owners may then ask for auto-confirm, creating pressure to remove the product's safest boundary (PRD-011, PRD-010).

Named shelves may remain technically complete but behaviorally absent, leaving personalization at Favorites-only and wasting prior investment (PRD-007).

If owner IA expands without a decision, each new tool will seek its own nav noun. New owners will learn system internals instead of a weekly job, and support burden will increase (PRD-004, PRD-012).

If local outcome measurement remains absent, the roadmap will optimize shipped features and raw catalog size rather than first-open, reading continuation, owner toil, and household return (PRD-002, PRD-009).

## 10. Recommended direction

**Now (0–2 weeks):** make Downloads actionable by default; rank Sorting by the largest reason; publish the “below five” target; enforce the product cut list; document the owner weekly checklist. These changes reduce live pain without waiting for an IA decision (PRD-003, PRD-004, PRD-008, PRD-011).

**Next (2–6 weeks):** activate one named shared shelf; add a bounded owner Hall tend card from morning brief; cache/budget shelf health; test grouped Desk navigation after the first month of metrics. Complete quiet-hours/digest polish only if mail is configured and the content is actionable (PRD-007, PRD-009, PRD-012, PRD-013).

**Later (6+ weeks):** decide whether stricter identification can reduce exceptions without mis-shelving, revisit music's first-tier Hall position using usage/support data, and revisit Hub distribution separately from product IA. Do not schedule a single-page Desk rewrite.

In 90 days, success is: median open Sorting count below five; 95% of queue visits land on an actionable subset; median confirm time below 30 seconds; shelf-health p95 below five seconds or an explicit cached result; at least one named shared shelf with three works; zero silent SAB starts; and no new primary-nav destination.

## 11. Scorecard

| Surface | Value clarity | Job fit | Loop health | Focus | Measurability | Overall |
|---|---:|---:|---:|---:|---:|---|
| Public | 5 | 4 | 3 | 5 | 2 | **A-** — correct private scope, thin activation measures |
| Consumer | 5 | 5 | 4 | 5 | 3 | **A-** — strong library loop, shelves underactivated |
| Owner | 4 | 3 | 2 | 3 | 2 | **B-** — powerful tools, visible backlog and noun sprawl |
| Admin | 4 | 4 | 4 | 4 | 3 | **B+** — right-sized for one household |

---

# Part B — Detailed findings

## 12. Scope and method

The pass used the shared platform map, the existing authenticated owner session, live Hall/Search/Sorting/queue/People observations, authenticated status from the run handoff, and code evidence for routes, roles, shelves, review, queue, and Maintain. It did not create invitations, confirm jobs, move files, trigger cleanup, change settings, or launch media.

Live evidence: Hall kind counts (10,762 / 97 / 74 / 17 / 14), Sorting 27 with reason distribution, queue approximately 80, People 2 / invites 0, `named_shelves` n=0, `llm_configured: true`, Lights Down, and one shelf-health timeout. Screenshot capture failed, so route/snapshot evidence refers to accessibility snapshots and authenticated API observations documented in [`00_2026-11-04_platform-map.md`](00_2026-11-04_platform-map.md).

Code evidence: role constants and guard (`librarian/auth.py:26-29,277-283`); front-end API surface for Hall/Search/Ask/shelves (`frontend/src/api.js:66-137`), Sorting (`:159-206`), Maintain (`:207-237`), and queue confirm (`:238-242`). Public anonymous, reader-role, op-role, actual media playback, OPDS client behavior, and email delivery were not walked. Claims dependent on those are Likely rather than Confirmed.

### Condensed feature inventory

| Feature | Persona value | Complexity | Product verdict |
|---|---|---|---|
| Foyer / invite / reset | Essential household entry | Medium security burden | Protect |
| Hall / Continue / recent / favorites | Core reader value | Medium payload | Protect |
| Stacks / Search / Beyond / Discover | Core findability | High provider breadth | Keep owned-first |
| Work / Read / Listen / progress | Core consumption | High format breadth | Protect |
| Wanted / Noted | Retention and discovery | Medium | Keep; no new peer surface |
| Named shelves | Household curation | Low–medium | Activate or demote |
| Downloads | Trust-controlled acquisition | Medium | Fix actionable default |
| Sorting | Shelf correctness | High | Fix outcome and scale |
| Maintain | Owner resilience/delight | High | Surface only top tends |
| Settings / People | Necessary administration | Medium | Keep owner-scoped |
| Newsletters / quiet hours | Optional lifecycle | Medium | Finish only around actionable jobs |
| OPDS | Power-reader interoperability | Medium | Keep, verify contract |

## 13. Strengths

### PRD-001: Protect the Foyer-to-Hall library proposition

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Public / Consumer |
| Persona(s) | Invited visitor, returning reader |
| Category | Value proposition |
| Severity | Medium |
| Impact | 5 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 5.0 |
| Verdict | Protect |
| Dependencies | PRD-005 |
| Labels | hall, foyer, positioning, sacred-cow |

**Evidence:** Live `/` accessibility snapshot: Hall heading, hero Search, owned-kind chips and reading rails; `/login` is the Foyer; Hall API is `frontend/src/api.js:66`; shared map `00_2026-11-04_platform-map.md` §10.

**Current state:** The product opens as a household library, not as a downloader. Owned works, Continue, recent additions, favorites, and noted material carry the proposition into use.

**Root cause:** A deliberate design and language system, reinforced by Hall as the authenticated default.

**Recommendation:** Keep Hall as `/` and keep hero Search first. Permit no more than one owner-only module above the first reader rail, containing at most three deep-linked tends.

**Rationale:** This framing is the primary differentiator and lowers cognitive load for every reader. A separate owner dashboard home was considered and rejected because it would make owners pay an operational tax on every reading visit. Protect now because PRD-009 proposes an owner card; defer pixel tuning, not hierarchy.

**User story:** As a household reader, I want to enter a library so that I can choose or resume a work without thinking about acquisition machinery.

**Acceptance criteria:**
- [ ] `/` remains Hall for authenticated users.
- [ ] Hero Search precedes owner operations and reading rails.
- [ ] Reader sessions never render queue or Sorting counts in Hall content.

**Success metric:** At least 80% of new members open an owned work in their first two sessions, measured on box.

**Validation:** Interactive Foyer → Hall walkthrough at desktop and 390px; role-gated Playwright assertions.

### PRD-006: Protect invite-only household acquisition

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Public / Admin |
| Persona(s) | Owner, invited visitor |
| Category | Acquisition |
| Severity | Medium |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 8.0 |
| Verdict | Protect |
| Dependencies | PRD-002 |
| Labels | invites, auth, household |

**Evidence:** `/join` and `/login` route inventory; live People 2 users / 0 invites; `librarian/auth.py:26-29` limits invite roles to op and reader.

**Current state:** There is no anonymous registration or public catalog. Owners deliberately admit household members.

**Root cause:** Product-market choice: one private self-hosted household, not a hosted network.

**Recommendation:** Keep invite-only as the only account-creation path. Improve activation measurement and plain-language invite copy without adding open signup.

**Rationale:** Public registration adds abuse, support, and tenancy obligations without serving the current product. “Optional open signup” was rejected because defaults become operational reality. Protect now as remote/VIP access grows; public acquisition can be reconsidered only with a different business model.

**User story:** As an owner, I want only invited people to join so that my household catalog remains private.

**Acceptance criteria:**
- [ ] No anonymous registration route exists.
- [ ] Only owner-authorized invite creation is accepted.
- [ ] Expired/revoked invitation states explain the next safe action.

**Success metric:** Zero accounts created without a valid invitation or owner bootstrap.

**Validation:** Auth route tests and anonymous browser walkthrough.

### PRD-010: Protect Ask → Confirm and fail-to-Sorting

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Consumer / Owner |
| Persona(s) | Reader, operator, owner |
| Category | Core loop / trust |
| Severity | High |
| Impact | 5 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 5.0 |
| Verdict | Protect |
| Dependencies | PRD-003, PRD-011 |
| Labels | sab, trust, sorting, roles |

**Evidence:** Reader Ask `frontend/src/api.js:107`; queue confirm `frontend/src/api.js:238-242`; server role guard `librarian/auth.py:277-283`; live Sorting reasons and explicit confirm UI.

**Current state:** Readers request; owner/operators confirm; uncertain identity becomes a Sorting slip.

**Root cause:** Deliberate separation of recommendation, acquisition, and catalog truth.

**Recommendation:** Add a contract test that enumerates every SAB-starting path and proves it requires owner/op plus explicit confirmation. Preserve confidence thresholds and measure mis-shelving alongside slip count.

**Rationale:** The boundary protects disk, bandwidth, indexer standing, and shelf correctness. Auto-confirm for trusted indexers was rejected because provider health cannot validate household intent or identity. Protect now because queue toil creates understandable pressure to remove the click; make the click faster instead.

**User story:** As an owner, I want every acquisition to require a household decision so that no search, model, or provider silently downloads media.

**Acceptance criteria:**
- [ ] Reader Ask cannot start SAB.
- [ ] Every SAB-starting route rejects reader role and requires explicit confirmation.
- [ ] Low-confidence identity never auto-files without an owner-approved experiment and guardrail.

**Success metric:** Zero silent SAB starts and a mis-shelve rate below 0.1%.

**Validation:** Role-matrix API tests; mocked e2e Search → Ask → owner Confirm.

## 14. Weaknesses

### PRD-011: Make Downloads actionable by default

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Owner, operator |
| Category | Core loop |
| Severity | High |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 4.0 |
| Verdict | Fix |
| Dependencies | PRD-010 |
| Labels | downloads, queue, toil |

**Evidence:** Authenticated `GET /api/queue` returned approximately 80 jobs; queue operations are `frontend/src/api.js:238-242`.

**Current state:** The page must represent Asked items requiring decisions, active transfers, failures, arrivals, and retained history. At live volume, raw total size obscures the confirm job.

**Root cause:** Job lifecycle history and owner action queue share one default view without an explicit actionable-first product contract.

**Recommendation:** Default to **Needs decision** (Asked + actionable Failed/Needs you), show separate counts for Active and History, auto-archive Arrived after seven days, and provide safe bulk dismiss for terminal rows. Preserve a visible “All jobs” escape hatch.

**Rationale:** Faster confirmation strengthens rather than weakens PRD-010. Deleting history was rejected because diagnosis and household accountability matter; a separate new dashboard was rejected because filtering the existing page is sufficient. Ship now because live volume already creates scan cost.

**User story:** As an operator, I want Downloads to open on slips that need a decision so that I can confirm without searching through history.

**Acceptance criteria:**
- [ ] Default view contains only actionable states.
- [ ] Active and History are one tap away with accurate counts.
- [ ] Terminal bulk dismiss requires confirmation and cannot affect active jobs.

**Success metric:** Median time from page open to confirm below 30 seconds; 95% of visits render fewer than 20 default rows.

**Validation:** 80-job fixture in Playwright; API state-transition tests.

### PRD-003: Make Sorting backlog reduction a product outcome

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Established owner, operator |
| Category | Owner loop / product debt |
| Severity | High |
| Impact | 5 |
| Effort | L |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | PRD-010; BD-3 experiment |
| Labels | sorting, review, toil, north-star |

**Evidence:** Live owner chrome “Sorting 27”; reasons low confidence 22, Audnexus unmatched 2, unknown identity 2, missing folder 1; review API supports reason filters and bulk actions at `frontend/src/api.js:159-206`.

**Current state:** Sorting is a capable exception desk, but 27 open slips remain visible on every owner page. The feature has tools without an explicit steady-state objective.

**Root cause:** Identification exceptions arrive faster than the owner ritual clears them; automation quality and triage efficiency are not governed by a shared metric.

**Recommendation:** Product-own a weekly **open slips <5** target. Default Sorting to the largest reason, expose age and “oldest slip,” promote safe bulk actions, and run BD-3's ISBN-strong auto-file experiment with wrong-shelf rate as the guardrail.

**Rationale:** Better UI alone can make a permanent pile tolerable but does not restore calm. Aggressive auto-file alone risks catalog corruption. The hybrid was chosen because it improves throughput while protecting truth. Start now with triage and measurement; run automation only after baseline data.

**User story:** As an owner, I want Sorting to be a small exception list so that “Needs you” remains meaningful.

**Acceptance criteria:**
- [ ] Default filter selects the largest actionable reason and can be reset.
- [ ] Open count and oldest age are visible.
- [ ] Automation experiment reports both slips avoided and mis-shelves.

**Success metric:** Median weekly open count below five within 90 days; no increase in mis-shelve rate.

**Validation:** Weekly on-box metric; seeded reason fixtures; audit sampled auto-filed works.

### PRD-005: Contain owner badge anxiety without hiding truth

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner / Cross-cutting |
| Persona(s) | Owner |
| Category | Information architecture / emotional design |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Rethink |
| Dependencies | PRD-003, PRD-012 |
| Labels | chrome, badge, hall |

**Evidence:** Live Hall and Search owner chrome include “Sorting 27”; `00_2026-11-04_platform-map.md` §10.

**Current state:** Operational truth is always visible, but the badge makes the reading room feel like an incident console for the owner.

**Root cause:** A raw exception count is the only cross-page owner summary.

**Recommendation:** Keep an indicator, but group it under a Desk affordance and distinguish normal from aging work. Show exact count inside the menu; outside, use a quiet dot below five and a count only when the oldest slip exceeds 24 hours or total exceeds five.

**Rationale:** Hiding the count would create false calm; leaving raw counts everywhere imposes permanent anxiety. Thresholded escalation preserves honesty and attention. Do this after PRD-003 establishes the target, not before, so the design does not mask unresolved debt.

**User story:** As an owner-reader, I want to know when work truly needs me without every Hall visit feeling like maintenance.

**Acceptance criteria:**
- [ ] Exact count remains available in one click.
- [ ] Escalation threshold is documented and tested.
- [ ] Reader and op chrome remain role-appropriate.

**Success metric:** Owner can identify desk status in one click while Hall retains hero Search as first focus.

**Validation:** Role-based interactive review at counts 0, 3, 6, and 27.

### PRD-007: Activate named shelves or demote them

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer / Owner |
| Persona(s) | Power reader, owner |
| Category | Activation |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | PRD-002 |
| Labels | shelves, activation, retention |

**Evidence:** Live Hall `named_shelves` n=0; complete shelf API at `frontend/src/api.js:120-132`.

**Current state:** Users can create and share shelves, but the reviewed household has none. Favorites carries the curation job alone.

**Root cause:** The product exposes shelf management but does not create a first successful shared shelf moment.

**Recommendation:** In the zero state, offer three starter names (“Next up,” “For the beach,” “Read together”) plus custom. Creation and adding the current work must complete in two actions. After 60 days, demote named-shelf presence if no shelf reaches three works.

**Rationale:** A guided starter reduces blank-page cost without forcing a taxonomy. Automatically creating shelves was rejected because empty system-generated collections are noise. Act next, after desk quick wins, because this is retention upside rather than operational risk.

**User story:** As a household, I want to make one shared shelf quickly so that we can plan reading together.

**Acceptance criteria:**
- [ ] Zero state creates a named shelf in at most two actions.
- [ ] Suggested names are editable and no shelf is auto-created.
- [ ] Hall shows the shelf only after it contains a work.

**Success metric:** At least one shared shelf with three works in 50% of households that open the zero state.

**Validation:** Empty → create → add → Hall Playwright journey.

### PRD-012: Decide the owner Desk information architecture

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | New owner, established owner, operator |
| Category | Information architecture / product debt |
| Severity | Medium |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 2.7 |
| Verdict | Rethink |
| Dependencies | **BD-2 DecisionRequired**, PRD-003, PRD-011 |
| Labels | desk, ia, lexicon, decision-required |

**Evidence:** Live chrome exposes Downloads and Sorting; Maintain and Settings are separate owner destinations; route inventory in `00_2026-11-04_platform-map.md` §4.3; current leadership memo [BD-2](31_2026-11-04_big-decisions.md#bd-2-desk-ia-consolidation-vs-educate-in-place).

**Current state:** Each noun is defensible, but a new owner must map four system areas onto one intent: “what needs me today?”

**Root cause:** Capabilities shipped by subsystem, while the owner mental model is a recurring desk ritual.

**Recommendation:** Follow BD-2's sequence: (A) publish a weekly HELP checklist now; (B) after 30 days of PRD-003/011 metrics, test a **Desk** menu with Confirm, Sorting, Tend; (C) explicitly reject a single-page rewrite unless task testing proves tab switching is the dominant cost.

**Rationale:** Education is cheap and reversible; grouping can improve learnability without rewriting mature tools; a mega-page would increase complexity and delay the live backlog work. This cannot be settled as a ticket because it changes the owner navigation model. Decide after real triage metrics, not later than the next owner-navigation release.

**User story:** As a new owner, I want one clear entry to today's work so that I do not have to understand internal subsystems first.

**Acceptance criteria:**
- [ ] HELP defines Confirm, Sort, Tend in fewer than ten bullets.
- [ ] A leadership decision is recorded in BD-2.
- [ ] Any grouped prototype preserves direct URLs, focus, and role gates.

**Success metric:** In first-run testing, 90% of owners find queue confirm and Sorting without help in under 30 seconds.

**Validation:** Five-person task test or maintainer-authored proxy test; desktop/390px Playwright nav checks.

### PRD-004: Freeze breadth until owner loop health is green

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | New owner, maintainer |
| Category | Portfolio / feature inventory |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Rethink |
| Dependencies | PRD-003, PRD-011 |
| Labels | portfolio, focus, freeze |

**Evidence:** Route inventory spans Hall, Browse, Search, Noted, Wanted, Queue, Review, Maintain, Settings, People, Inbox, Help, Library card, Work; live owner backlog and shelf-health timeout.

**Current state:** The feature set is broad and credible, but operational health is behind reader breadth.

**Root cause:** Each new provider, kind, or delight has local value, while cross-surface owner cost compounds.

**Recommendation:** Add a release criterion: no new primary route, media kind, or owner subsystem until Sorting median is below five for four weeks and Downloads actionable-default has shipped. Exceptions: security, accessibility, data-loss prevention.

**Rationale:** This is a reversible capacity rule, not a permanent ban. Removing current kinds was rejected because all are live and useful. Waiting to impose focus would let the next attractive feature outrun the owner loop again, so adopt the gate now.

**User story:** As a maintainer, I want roadmap capacity tied to loop health so that the product becomes calmer as it grows.

**Acceptance criteria:**
- [ ] Roadmap template records the two loop-health gates.
- [ ] Any exception names its security/a11y/data-loss rationale.

**Success metric:** Zero new primary destinations before both gates are green.

**Validation:** Release checklist review.

## 15. Opportunities

### PRD-008: Institutionalize the product cut list

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Cross-cutting |
| Persona(s) | All |
| Category | Portfolio / cut list |
| Severity | Medium |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 8.0 |
| Verdict | Remove |
| Dependencies | PRD-001, PRD-010 |
| Labels | cut-list, strategy |

**Evidence:** Hall already delivers library-first value; current route and role model in `00_2026-11-04_platform-map.md` §§4–5.

**Current state:** The product has principles, but future-scope rejection is not yet a durable release criterion.

**Root cause:** “No sacred cows” review pressure can be misread as a requirement to add every benchmark feature.

**Recommendation:** Record the explicit cut list: no Arr/KPI dashboard home, no public marketplace or signup, no social feed, no silent SAB, no Calibre desktop clone, no new top-level owner app before PRD-004 gates.

**Rationale:** Saying no protects maintenance capacity and positioning. Building feature flags for rejected concepts was considered and rejected because dormant code still costs. Do this now at XS effort; revisit only when the product/business model changes.

**User story:** As a household, I want Librarian to stay a reading room so that operational machinery never becomes the experience.

**Acceptance criteria:**
- [ ] Product roadmap includes this cut list.
- [ ] Proposals that conflict identify a leadership decision rather than silently entering backlog.

**Success metric:** No cut-list feature ships in the next two quarters.

**Validation:** Quarterly roadmap review.

### PRD-002: Measure the household loops locally

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Cross-cutting |
| Persona(s) | Owner, maintainer |
| Category | Strategy / measurement |
| Severity | Medium |
| Impact | 4 |
| Effort | M |
| Confidence | Likely |
| Priority score | 2.1 |
| Verdict | Add |
| Dependencies | PRD-006, PRD-007 |
| Labels | metrics, local-first, activation |

**Evidence:** Live counts expose scale but not activation; People 2 / invites 0; named shelves 0; no product funnel evidence was available.

**Current state:** The review can count catalog items and operational backlog but cannot answer invite-to-first-open, first Ask, Continue reuse, or shelf adoption.

**Root cause:** Privacy-positive lack of external analytics also removed decision-grade local product measures.

**Recommendation:** Store daily aggregates only: invite redeemed, first owned-work open, first Ask, first Read/Listen, Continue open, named shelf created/used, confirm latency, Sorting open/age. Expose household-level totals to owner; no phone-home and no raw query text.

**Rationale:** Local aggregates let the roadmap distinguish unused features from undiscovered ones. Third-party analytics was rejected on privacy and deployment grounds; no measurement was rejected because it leaves BD-2/BD-4 opinion-based. Build after immediate queue defaults, but before evaluating feature removal.

**User story:** As an owner-maintainer, I want private household metrics so that I can tell whether the product helps without sending behavior off-box.

**Acceptance criteria:**
- [ ] Event schema excludes query text and content bodies.
- [ ] Metrics remain on box and are exportable/deletable with household data.
- [ ] Owner sees activation and toil measures with plain definitions.

**Success metric:** All 90-day goals in Part A are computable locally.

**Validation:** Privacy review, event contract tests, owner dashboard fixture.

### PRD-009: Add a bounded owner “tend these” Hall card

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Owner |
| Persona(s) | Established owner |
| Category | Retention / owner ritual |
| Severity | Medium |
| Impact | 4 |
| Effort | M |
| Confidence | Likely |
| Priority score | 2.1 |
| Verdict | Add |
| Dependencies | PRD-001, PRD-003, PRD-011 |
| Labels | hall, maintain, morning-brief |

**Evidence:** Maintain morning brief exists at `frontend/src/api.js:226-229`; live Hall did not surface it in the primary content.

**Current state:** The owner learns work from badges or by opening separate destinations.

**Root cause:** Maintain intelligence is isolated from the owner's most frequent landing page.

**Recommendation:** Add one owner-only card after hero Search with at most three actions, ordered: Asked awaiting confirm, aging Sorting slips, health failure. Each is a deep link; hide the card when clear. Do not show generic stats or terminal history.

**Rationale:** A bounded card closes the ritual without making Hall an admin dashboard. A permanent metrics panel was rejected because it violates PRD-001; a separate dashboard was rejected as new IA. Build Next, after actionable definitions are stable.

**User story:** As an owner, I want to see the few things that truly need me when I enter so that I can tend the library and return to reading.

**Acceptance criteria:**
- [ ] Card has zero to three actionable rows and disappears when clear.
- [ ] Reader/op visibility matches role policy.
- [ ] Hero Search remains first content and focus target.

**Success metric:** Half of weekly owner sessions with actionable work use a tend deep link; no increase in reader Hall payload.

**Validation:** Role fixtures for clear, one-action, and three-action states.

### PRD-013: Complete Ask digest and quiet-hours polish

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Consumer / Owner |
| Persona(s) | Reader, owner |
| Category | Lifecycle / retention |
| Severity | Low |
| Impact | 3 |
| Effort | M |
| Confidence | Likely |
| Priority score | 0.8 |
| Verdict | Add |
| Dependencies | PRD-011; mail configured |
| Labels | notifications, digest, quiet-hours |

**Evidence:** Notification and newsletter API exists at `frontend/src/api.js:330-343`; quiet-hours API at `:362-363`; current roadmap/handoff identifies Ask digest polish.

**Current state:** The infrastructure exists, but the owner still has to discover pending Asks by opening Downloads, and quiet-hours controls compete with Sorting work.

**Root cause:** Delivery settings and the acquisition job shipped as adjacent features rather than one lifecycle.

**Recommendation:** Send at most one daily owner digest when actionable Asked slips exist, after quiet hours, with count, oldest age, and a link to the actionable Downloads filter. Suppress empty digests and terminal history. Reader arrival notices remain event-based.

**Rationale:** The digest reduces confirm latency without increasing permanent chrome. Real-time alerts were rejected as noisy; a generic queue summary was rejected as non-actionable. Do Later unless mail is already configured and PRD-011's filter exists, because a digest pointing to an 80-row pile makes the problem worse.

**User story:** As an owner, I want one quiet-hours-aware summary of pending Asks so that I can decide them without checking repeatedly.

**Acceptance criteria:**
- [ ] No digest sends when zero actionable Asks exist.
- [ ] At most one digest sends per quiet-hours cycle.
- [ ] Link opens the actionable filter, not All jobs.

**Success metric:** Median Ask-to-decision time drops 30% among households enabling the digest.

**Validation:** Mail fixture tests across quiet-hours boundaries; link-route e2e.

## 16. Remediation plan

### Now — 0 to 2 weeks

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---:|---|---|
| PRD-011 | Downloads actionable by default | M | Product + frontend | PRD-010 |
| PRD-003 | Sorting target, reason-first default, age | L phased | Product + UX + backend | PRD-010 |
| PRD-004 | Freeze breadth via release gate | XS | Product | PRD-003, PRD-011 |
| PRD-008 | Record cut list | XS | Product | PRD-001 |
| PRD-010 | Add trust-boundary regression contract | M | Backend + security | — |

### Next — 2 to 6 weeks

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---:|---|---|
| PRD-007 | Named shelf activation | S | Product + frontend | — |
| PRD-009 | Bounded owner tend card | M | Product + frontend | PRD-003, PRD-011 |
| PRD-002 | Local product aggregates | M | Product + backend | Privacy review |
| PRD-005 | Thresholded Desk indicator | S | Product + design | PRD-003 |
| PRD-012 | BD-2 grouped Desk prototype | M | Product + UX | 30 days metrics |

### Later — 6+ weeks

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---:|---|---|
| PRD-013 | Ask digest / quiet-hours completion | M | Product + notifications | PRD-011 |
| PRD-003 | BD-3 hybrid auto-file experiment | M | Product + architecture | Baseline mis-shelve metric |
| PRD-012 | Record durable BD-2 decision | XS decision | Maintainer | Prototype evidence |

Sequencing matters. Trust and actionable defaults come before notifications. Triage metrics come before IA consolidation and stronger automation. Activation measurement comes before demoting shelves. This order avoids building more polished doors into unresolved piles.

## 17. Quick wins

- **PRD-008:** put the cut list into roadmap/release review (XS, score 8.0).
- **PRD-004:** add the loop-health release gate (XS, score 6.0).
- **PRD-011:** persist actionable filter as the default (first slice S).
- **PRD-003:** default Sorting to the largest reason and show oldest age (first slice S).
- **PRD-007:** add starter shelf names to the empty state (S).
- **PRD-012:** publish the owner weekly checklist while BD-2 remains open (S).

## 18. Open questions needing product/business input

1. Is the formal steady-state target **zero** Sorting slips or **below five**, and who reviews it weekly?
2. For BD-3, what wrong-shelf rate stops the ISBN-strong auto-file experiment: 0.1%, 0.5%, or any confirmed error?
3. Is the op role actively used on Automat, or should its product onboarding wait for a larger household?
4. Should music remain a first-tier Hall chip at 97 items, or move to Stacks if Promote support cost rises? See BD-4.
5. What is the minimum evidence for BD-2 grouping: five first-run task tests, 30 days of nav telemetry, or both?
6. Are named shelves intended primarily as private personal collections or shared household planning? The default `shared=true` suggests the latter (`frontend/src/api.js:121-122`).
7. Should Ask digests be owner-only, or can operators opt in independently?
8. What retention period is acceptable for local aggregate product events?

---

## Department self-check

- [x] Part A includes all eleven required sections in full prose.
- [x] All four surfaces are covered and graded.
- [x] High findings PRD-003, PRD-010, and PRD-011 appear in the executive narrative.
- [x] Sacred cows have evidence for/against, verdict, cost, and rationale.
- [x] Every finding includes evidence, root cause, exact recommendation, alternatives, why now/later, acceptance criteria, metric, and validation.
- [x] Strengths have full Protect treatment.
- [x] PRD-001 through PRD-013 are unique and preserved.
- [x] PRD-012 remains DecisionRequired and maps to BD-2.
- [x] Companion run files are linked by filename.
- [x] No application code or other review artifact was modified.

**Finding count:** 3 Strengths · 6 Weaknesses · 4 Opportunities.  
**Cut list owner:** PRD-008, reinforced by PRD-004.  
**DecisionRequired:** PRD-012 → [`31_2026-11-04_big-decisions.md` BD-2](31_2026-11-04_big-decisions.md#bd-2-desk-ia-consolidation-vs-educate-in-place).
