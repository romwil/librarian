# 09 · Performance, Reliability & Cost — Librarian — run 2026-11-04

**Live truth:** Automat `1.0.10 / 480eff0`; ~10.8k books; Sorting 27; queue ~80; Maintain shelf-health timed out · **Grade: B-**

**Companions:** [Platform map](00_2026-11-04_platform-map.md) · [Growth](05_2026-11-04_growth-content-analytics.md) · [Architecture](08_2026-11-04_architecture.md) · [Operations](10_2026-11-04_operations-support.md) · [Backlog](2026-11-04_backlog.csv)

# Part A — Conclusions & findings

## 1. Bottom line

Librarian is cheap and fundamentally recoverable: one container, one SQLite file, nightly integrity-checked snapshots, shallow health, explicit readiness, and no mandatory SaaS. The confirmed shelf-health timeout and heavy Sorting DOM show that current scale is exposing synchronous aggregate and rendering costs (PERF-002, PERF-008). The larger reliability weakness is observability: step status exists, but route latency, event-loop delay, endpoint failures, and alert thresholds do not support a 15-minute diagnosis (PERF-007). Fix slow owner surfaces and local instrumentation first. Protect online backups, readiness semantics, bounded Hall/Review contracts, and fail-soft optional integrations.

## 2. Key conclusions

1. **The confirmed failure is Maintain, not SQLite generally.** Shelf health synchronously performs permission inspection and several catalog counts (`librarian/web/routers/maintain.py:116-130`) and exceeded the run timeout (PERF-002).
2. **Sorting is bounded server-side but still expensive in the browser.** `/api/review` defaults to 25 with cursor/reason filters (`librarian/web/routers/review.py:31-48`), yet the live accessibility snapshot exceeded 1,000 nodes. Initial DOM and repeated card complexity remain costly (PERF-008).
3. **Backups are real, local, and integrity-aware.** The poller runs backup when due (`librarian/poller.py:463-469`); runbook states 7 daily/4 weekly snapshots and `PRAGMA integrity_check` (`docs/ops/AUTOMAT.md:153-180`). Restore practice—not backup existence—is the gap.
4. **Health/readiness separation is correct.** Public `/api/health` is liveness only; readiness performs `SELECT 1` and requires poller activity (`librarian/web/status.py:67-76`). Do not enrich liveness.
5. **Frontend baseline is not measured enough.** No Lighthouse trace was captured in this run, so LCP/INP/CLS claims remain unproven (PERF-003). Establish repeatable budgets before optimization.
6. **Large PDF/comic reading remains a known stress path.** PDF.js and Foliate are first-party dependencies (`frontend/package.json:18-24`), but no 400MB stress artifact was measured (PERF-004).
7. **Cost drivers are operator-controlled.** LLM calls, indexer requests, disk/media, and CPU are the main costs; there is no analytics bill. Call counts and budget hints should be visible, not exported (PERF-006).
8. **Polling is disciplined in backend status but aggressive in some UI loops.** Maintain polls active jobs at 700ms and jobs status every 30s (`MaintainPage.jsx:180-207,383-539`). Verify visibility pause and backoff before adding more loops (PERF-009).

## 3. Foundations challenged

| Assumption | Evidence for | Evidence against | Verdict | Cost | Rationale |
|---|---|---|---|---|---|
| One box is enough | Household scale, low fixed cost | One process/failure domain | Keep | XL | Measure contention before splitting. |
| SQLite is the bottleneck | 10.8k works | Hall/Review bounds work; shelf-health composition timed out | Investigate endpoint, keep DB | M | Query/caching evidence precedes migration. |
| Client can render all work | 25-item server page | 1,000+ snapshot nodes | Change | M | Render fewer details; window only if needed. |
| LLM is optional | Shelves work without it | Cost opaque | Keep; expose budget | S | Visibility, not vendor lock-in. |
| Health proves readiness | Process-up is reliable | It intentionally ignores DB | Keep split | S | Liveness must not restart a merely busy app. |
| Fast LAN means fast UI | likely repeat cache | no Lighthouse/CPU profile | Investigate | S | Establish budgets first. |

## 4. If we built it today

We would keep one container and add an in-memory/local runtime ledger: per-route count/error/p50/p95, active job age, poller heartbeat age, backup age, event-loop delay, and LLM/indexer call totals. Expensive diagnostics would return a cached snapshot immediately and refresh asynchronously. Browser routes would have explicit initial-DOM and bundle budgets. Restore drills would be scheduled operational work.

The gap is small-to-moderate. Poller status, backup timestamps, progress JSON, readiness, cursor Review, and capped Hall already exist. Prometheus, hosted APM, Redis, and a second worker are rejected for now: they add components before local signals prove need.

## 5. Findings by surface

**Public.** Shallow health and static SPA delivery minimize dependencies. Lighthouse was not run. **Grade: B.** IDs: PERF-003.

**Consumer.** Hall rails are capped at 18 (`hall.py:45-68`). Large PDF/comic first-page behavior is under-tested (PERF-004). **Grade: B-.**

**Owner.** Confirmed shelf-health timeout and heavy Sorting DOM are current scale failures (PERF-002, PERF-008). **Grade: C+.**

**Admin/Ops.** Backup and poller step status are strong; route-level telemetry and practiced restore are thin (PERF-007, PERF-009). **Grade: B-.**

## 6. Findings by theme

**Frontend:** establish Lighthouse and DOM budgets; reduce initial Sorting details. **Backend:** cache aggregates and profile queries, not frameworks. **Reliability:** protect backup/readiness and practice restore. **Observability:** local structured metrics must answer “which route/job?” in 15 minutes. **Cost:** show counts/budgets for optional providers.

## 7. Stop doing

- Stop computing heavy owner diagnostics synchronously on page open (PERF-002).
- Stop adding UI poll loops without visibility pause/backoff (PERF-009).
- Stop treating a liveness 200 as database/poller readiness.
- Do not claim performance wins without repeatable Lighthouse/LAN samples (PERF-003).
- Do not add hosted APM or a second process before local metrics prove need (PERF-007).

## 8. Strengths worth protecting

- Nightly online snapshots, integrity check, retention, and `0600`/`0700` permissions.
- Shallow `/api/health` and explicit readiness.
- Hall 18-item rails and Review 25-item cursor page.
- Poller step isolation and last-run/error fields (`poller.py:259-368`).
- Optional integration failure does not take down shelves.

## 9. Risks of inaction

Maintain becomes an unreliable operational surface, so owners return to SSH/log guessing. Sorting remains visually and assistively expensive even when the API is bounded. Poller or integration stalls take longer than 15 minutes to isolate. A backup exists but an unpracticed restore fails during the one incident that matters. Optional LLM/indexer use grows without an owner-visible budget.

## 10. Recommended direction

**Now:** cache/async shelf health; reduce Sorting initial DOM; establish benchmark scripts (PERF-002, PERF-008, PERF-003). **Next:** local structured route/job metrics, visibility-aware polling, and large-document stress tests (PERF-007, PERF-009, PERF-004). **Later:** expose provider call/cost hints and reconsider topology only if SLOs repeatedly fail (PERF-006).

## 11. Scorecard

| Surface | Speed | Reliability | Observability | Cost | Overall |
|---|---:|---:|---:|---:|---:|
| Public | 4 | 4 | 2 | 5 | 4 |
| Consumer | 3 | 4 | 2 | 4 | 3 |
| Owner | 2 | 3 | 2 | 4 | 3 |
| Admin/Ops | 3 | 4 | 3 | 4 | 3 |

## Proposed SLOs

| Journey | SLI and target | Window / budget |
|---|---|---|
| Process liveness | `/api/health` p99 <200ms; 99.9% | 30 days; ≤43m error budget |
| Ready for work | `/api/ready` p99 <500ms; 99.5% | 30 days; ≤3h36m |
| Hall usable | response p95 <500ms; usable paint p95 <2s LAN | weekly |
| Search local | p95 <750ms at 10.8k works | weekly |
| Sorting first page | API p95 <1s; interactive p95 <2s; initial focusables <100 | weekly |
| Maintain shell | shell usable <1s even if cards stale | weekly |
| Shelf health | cached p95 <2s; refresh <60s | weekly |
| Queue confirm | accepted response p95 <1s; no duplicate SAB sends | weekly |
| Background jobs | heartbeat age <2× interval; silent death 0 | continuous |
| Backup | ≥1 successful integrity-checked snapshot /24h | daily |
| Restore | successful drill ≤60 minutes | annually and before risky migration |

# Part B — Detailed findings

## 12. Scope & method

Reviewed the [platform map](00_2026-11-04_platform-map.md), current review/backlog, Automat backup/deploy runbook, package files, and indexed Hall/Review/Maintain/poller/status/frontend source. Used supplied confirmed timeout/live scale. No Lighthouse, bundle build, database query plan, host CPU/disk profile, PDF stress run, or restore was performed; those remain explicit gaps.

## 13. Strengths

### PERF-001: Protect nightly backup and readiness

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Admin |
| Persona(s) | Owner, maintainer |
| Category | Reliability |
| Severity | High |
| Impact | 5 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 15 |
| Verdict | Protect |
| Dependencies | OPS-008 |
| Labels | backup, readiness |

**Evidence:** `librarian/poller.py:463-469`; `librarian/web/status.py:27-76`; `docs/ops/AUTOMAT.md:153-180`.

**Current state:** nightly due check, retained integrity-checked snapshots, visible last backup, and DB+poller readiness. **Root cause:** durability was designed into the poller.

**Recommendation:** Keep behavior and permissions; add restore drill evidence, not another backup mechanism.

**Rationale:** Local backup fits privacy and deployment. Cloud upload is optional owner infrastructure, not a default.

**User story:** As an owner, I want a recent valid snapshot and honest readiness.

**Acceptance criteria:** [ ] snapshot/retention/integrity tests stay green. [ ] health remains shallow.

**Success metric:** Backup <24h; annual restore succeeds.

**Validation:** inspect timestamps, integrity check, clone restore.

### PERF-005: Protect fail-soft optional integrations

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | All |
| Category | Reliability |
| Severity | Medium |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 8 |
| Verdict | Protect |
| Dependencies | — |
| Labels | llm, indexer |

**Evidence:** `docs/HELP.md:20-27`; poller catches step exceptions and records only that step (`librarian/poller.py:346-368`).

**Current state:** provider/rate-limit failures do not remove shelf access. **Root cause:** optional integrations are isolated.

**Recommendation:** Keep per-step failure isolation and honest empty/error copy.

**Rationale:** Retrying forever or failing the page would turn an optional cost into an outage.

**User story:** As a reader, I want owned shelves to work when providers fail.

**Acceptance criteria:** [ ] provider failure leaves Hall/Search local usable. [ ] poller records last error.

**Success metric:** Zero core-shelf outages caused by optional providers.

**Validation:** mocked provider failures.

## 14. Weaknesses

### PERF-002: Make shelf health a cached asynchronous snapshot

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Owner |
| Category | Latency |
| Severity | High |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 4.0 |
| Verdict | Fix |
| Dependencies | ARCH-002 |
| Labels | maintain, cache |

**Evidence:** live timeout at 15–20s; synchronous report/count composition at `librarian/web/routers/maintain.py:116-130`.

**Current state:** one diagnostic can outlive the page request. **Root cause:** filesystem permission scan and counts execute on demand.

**Recommendation:** return last snapshot with `generated_at/stale/refreshing`; refresh off-request at most every 15 minutes or after relevant jobs; independently time subchecks.

**Rationale:** Cache preserves useful weather without blocking Maintain. Raising timeout hides the defect. Now because failure is confirmed.

**User story:** As an owner, I want Maintain to open even while shelf inspection runs.

**Acceptance criteria:** [ ] shell <1s. [ ] snapshot response <2s. [ ] refresh <60s or named failed subcheck.

**Success metric:** shelf-health p95 <2s.

**Validation:** cold/warm LAN timing at 10.8k works.

### PERF-008: Reduce Sorting initial DOM and render cost

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Owner, assistive-tech user |
| Category | Frontend performance |
| Severity | High |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 4.0 |
| Verdict | Fix |
| Dependencies | A11Y-005 |
| Labels | sorting, dom |

**Evidence:** live snapshot >1,000 nodes; server already defaults to 25 and cursor (`review.py:31-48`).

**Current state:** page count is bounded, card detail is still heavy. **Root cause:** every slip renders controls/details eagerly.

**Recommendation:** initially render summary/actions; lazy-mount details/candidates; target <100 focusables. Use windowing only if simplified cards still miss INP.

**Rationale:** Simplification preserves semantic DOM better than immediate virtualization. Now because it harms both speed and accessibility.

**User story:** As an owner, I want Sorting responsive and scannable.

**Acceptance criteria:** [ ] initial focusables <100. [ ] filter update announced. [ ] no lost keyboard position.

**Success metric:** interactive p95 <2s; INP <200ms on reference laptop.

**Validation:** browser profile, axe, VoiceOver script.

### PERF-003: Establish repeatable frontend budgets

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Maintainer, mobile reader |
| Category | Process |
| Severity | Medium |
| Impact | 2 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 2.0 |
| Verdict | Fix |
| Dependencies | — |
| Labels | lighthouse |

**Evidence:** no Lighthouse run/artifact in this review; Vite 5 build exists (`frontend/package.json:6-17`).

**Current state:** frontend performance is inferred. **Root cause:** no release budget artifact.

**Recommendation:** Lighthouse Hall/Search/Sorting at desktop and 390px; store LCP/INP/CLS, transfer and entry chunk; fail only on material regression after baseline.

**Rationale:** Measurement before optimization. Now/Next because it validates PERF-008 and avoids cargo-cult splitting.

**User story:** As a maintainer, I want comparable release metrics.

**Acceptance criteria:** [ ] reproducible profile. [ ] baseline committed to review artifact/process. [ ] thresholds documented.

**Success metric:** no unexplained >10% regression.

**Validation:** repeat three runs and use median.

### PERF-004: Stress-test the large-document path

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Reader |
| Category | Reader |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Likely |
| Priority score | 1.6 |
| Verdict | Fix |
| Dependencies | test fixture |
| Labels | pdf, memory |

**Evidence:** `pdfjs-dist` and `foliate-js` dependencies at `frontend/package.json:18-24`; no stress result this run.

**Current state:** progressive reader exists; memory/first-page limits are unproven. **Root cause:** ordinary fixtures underrepresent household media.

**Recommendation:** add 100/400MB PDF/CBZ fixtures outside git or generated; measure first page, memory, cancellation, range behavior.

**Rationale:** Large media can crash a tablet. Full pre-conversion was rejected because it increases storage and wait. Next after owner timeout fixes.

**User story:** As a reader, I want page one without loading the whole book.

**Acceptance criteria:** [ ] page one <5s LAN. [ ] cancellation releases work. [ ] failure offers download.

**Success metric:** no tab crash at 400MB.

**Validation:** device profile and memory trace.

### PERF-007: Add local structured observability

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Maintainer |
| Category | Observability |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 2.0 |
| Verdict | Fix |
| Dependencies | GRO-004 shares rollup mechanics |
| Labels | logs, latency |

**Evidence:** poller exposes step last run/error (`poller.py:259-281`); status only exposes version, backup, poller alive (`status.py:53-64`); no route histogram endpoint is evidenced.

**Current state:** jobs are inspectable; request incidents require log guessing. **Root cause:** operational state grew before request telemetry.

**Recommendation:** owner-only runtime endpoint and structured minute log: route template, status class, duration bucket, active jobs, heartbeat age, backup age, event-loop delay. No query/path/user data.

**Rationale:** Enough for 15-minute diagnosis without hosted APM. Do next because it should measure the fixes, not block them.

**User story:** As a maintainer, I want to identify the slow route/job without SSH archaeology.

**Acceptance criteria:** [ ] p50/p95/error rate. [ ] owner-only. [ ] no sensitive values.

**Success metric:** diagnose staged slowdown in <15 minutes.

**Validation:** fault injection and redaction test.

### PERF-009: Make UI polling visibility-aware

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Owner |
| Category | Reliability/cost |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Suspected |
| Priority score | 1.6 |
| Verdict | Investigate |
| Dependencies | ARCH-008 |
| Labels | polling, queue |

**Evidence:** active Maintain loops poll at 700ms and status at 30s (`MaintainPage.jsx:180-207,383-539`); current run did not prove hidden-tab behavior for all loops.

**Current state:** timely progress, potentially unnecessary hidden-tab traffic. **Root cause:** each workflow owns a timer.

**Recommendation:** shared hook pauses when hidden, wakes immediately on visible/focus, and backs off 0.7→2→5s after no change.

**Rationale:** Reduces CPU/requests and centralizes race handling. Investigate first because some shared hook behavior may already exist.

**User story:** As an owner, I want progress fresh when watching without background churn.

**Acceptance criteria:** [ ] no polling while hidden. [ ] immediate wake. [ ] one in-flight request/job.

**Success metric:** hidden-tab progress requests approach zero.

**Validation:** browser network trace.

## 15. Opportunities

### PERF-006: Show provider usage and cost hints

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Owner |
| Persona(s) | Owner |
| Category | Cost |
| Severity | Low |
| Impact | 2 |
| Effort | S |
| Confidence | Likely |
| Priority score | 1.0 |
| Verdict | Add |
| Dependencies | PERF-007 |
| Labels | llm, indexer |

**Evidence:** optional BYO providers described at `docs/HELP.md:20-27`; poller/indexer status already reaches Maintain.

**Current state:** owner sees failures, not monthly usage. **Root cause:** integration observability is operational, not budget-oriented.

**Recommendation:** show monthly LLM calls/tokens when known, indexer requests, and configurable warning thresholds; never invent dollars without provider pricing.

**Rationale:** Makes optional cost governable. Later because latency/reliability are more urgent.

**User story:** As an owner, I want usage hints before a provider bill surprises me.

**Acceptance criteria:** [ ] counts local. [ ] estimates labeled. [ ] warning configurable.

**Success metric:** no >50% unexplained monthly jump.

**Validation:** fake usage rows.

## 16. Remediation plan

| Horizon | ID | Work | Effort | Owner | Dependencies |
|---|---|---|---|---|---|
| Now | PERF-002 | Cached async shelf-health | M | BE | ARCH-002 |
| Now | PERF-008 | Reduce Sorting initial DOM | M | FE | A11Y-005 |
| Now | PERF-003 | Baseline Lighthouse/DOM budgets | S | FE/SRE | — |
| Next | PERF-007 | Runtime metrics and structured logs | M | BE | — |
| Next | PERF-009 | Shared visibility-aware polling | M | FE | ARCH-008 |
| Next | PERF-004 | Large-document stress suite | M | FE | fixture |
| Later | PERF-006 | Provider usage/cost hints | S | BE/FE | PERF-007 |

## 17. Quick wins

Return stale shelf-health immediately, expose `generated_at`, add timing around its subchecks, pause hidden polling, and document the SLO table.

## 18. Open questions

1. Which shelf-health subcheck consumed 20s?
2. What are current Hall/Search/Sorting LCP/INP/CLS and entry sizes?
3. Does SAB/network latency dominate queue tick at ~80 jobs?
4. What provider usage fields are reliable enough to show?

## Self-check

- [x] Full Part A and four surfaces.
- [x] PERF-002/003/004/006/007/008/009 preserved in full format.
- [x] Core-journey SLOs proposed.
- [x] Alternatives, evidence limits, and sequencing stated.
