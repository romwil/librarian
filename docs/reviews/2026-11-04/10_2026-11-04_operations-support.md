# 10 · Operations & Customer Support — Librarian — run 2026-11-04

**Operating model:** owner is household support; maintainer runs Automat · **Live:** `1.0.10 / 480eff0`, Sorting 27, queue ~80 · **Grade: B-**

**Companions:** [Platform map](00_2026-11-04_platform-map.md) · [Growth](05_2026-11-04_growth-content-analytics.md) · [Architecture](08_2026-11-04_architecture.md) · [Performance](09_2026-11-04_performance-reliability-cost.md) · [Backlog](2026-11-04_backlog.csv) · [Automat runbook](../../ops/AUTOMAT.md)

# Part A — Conclusions & findings

## 1. Bottom line

Librarian has real day-two operations: confirm Downloads, clear Sorting, watch indexer weather, verify backup, maintain mappings/permissions, and occasionally recover a failed integration. The product already contains the right primitives—Morning brief, reason-grouped Sorting, safe undo, progress dock, last backup, poller step state, and detailed runbooks. The problem is cumulative toil: 27 Sorting slips and ~80 queue jobs are enough that an owner can no longer infer “what needs me now” from raw lists (OPS-003). Fix actionable defaults and a short recurring checklist first (OPS-001, OPS-003); then reduce config-file and repeat-support work (OPS-005, OPS-010). Protect confirm-before-SAB, backup/restore safety, and no silent impersonation.

## 2. Key conclusions

1. **The owner is the support desk, so owner time is the scarce resource.** There is no ticket organization or staffed admin team. Product operations must be understandable from Maintain, Sorting, Downloads, Settings, and HELP (OPS-001).
2. **The live desks already exceed “glanceable.”** Sorting 27 and queue ~80 are not outages, but they make daily triage a recurring chore. Default views should show actions, not history (OPS-003).
3. **Sorting reason groups are the right automation seam.** `/api/review` supports reason/cursor/limit and bulk-by-reason exists (`librarian/web/routers/review.py:31-48,76-81`). Reduce work by safe group actions, not by hiding the backlog.
4. **Maintain is a strong ops console with a slow-card failure.** Morning brief caps itself at three tend items and jobs status exposes backup/poller/integration state (`maintain.py:138-249`). Shelf-health timeout means one card can undermine confidence in the desk.
5. **Runbooks are unusually concrete.** Automat documents ports, version truth, deploy, backup/restore, permissions, and media roots. The gap is turning them into recurring operator habits (OPS-001, OPS-008).
6. **Config changes should be UI-first but not UI-only.** Secrets and deployment variables appropriately remain in `.env`; routine roots, integrations, and behavior should stay in Settings. The boundary needs a table, not a blanket promise (OPS-005).
7. **Likely support drivers are predictable.** Missing SAB folder mapping, PUID locks, invite redemption, public-origin/proxy configuration, failed provider calls, and job-word confusion already have evidence in HELP/runbooks. Promote the top answers into a compact FAQ (OPS-010).
8. **A restore file is not a restore capability.** Nightly snapshots exist and are protected, but the annual/major-upgrade drill is not evidenced in this review (OPS-008).

## 3. Foundations challenged

| Assumption | Evidence for | Evidence against | Verdict | Cost | Rationale |
|---|---|---|---|---|---|
| Owner does all household ops | Correct scale; role model supports it | Backlogs create recurring toil | Keep model; improve desk | M | Another role/system is unnecessary; action prioritization is not. |
| Raw lists are sufficient | Full detail is available | 27/80 is not glanceable | Change defaults | M | Default to actionable; preserve history via filters. |
| Host `./docker-run.sh` | Authoritative and simple | Host build has weaker rollback than registry | Keep now | S–M | Hub is explicitly deferred. |
| Settings can replace `.env` | Many routine values fit UI | boot/session secrets and deploy trust must be host-controlled | Clarify boundary | S | Avoid false promise and direct file edits. |
| Backup automation is enough | nightly + retention + integrity | no drill evidence | Change practice | S | Recovery must be rehearsed. |
| No status page/support system | One household, LAN truth | owner still needs incident guidance | Keep external absence; improve in-app | S | A SaaS status page adds no value. |
| Full impersonation helps support | would reproduce user state | privacy/audit risk | Remove | — | Prefer role-aware diagnostics and explicit exports. |

## 4. If we built it today

The owner would open one “Today at the desk” feed: failed/stale jobs, unconfirmed reader Asks, oldest Sorting reason groups, backup age, and integration failures. Every item would have one safe action or deep link, age, count, and owner. History would remain available but not lead the page. A one-page weekly checklist would cover backup, queue, Sorting, provider weather, disk/permissions, and update/version truth. Break-glass steps would live in the Automat runbook; common household fixes would live in a five-answer FAQ.

The gap is small-to-moderate because Morning brief, status dock, grouped Sorting, backup state, and runbooks already exist. A ticketing system, external status page, or full impersonation is not justified. Better defaults and practiced recovery are.

## 5. Findings by surface

**Public.** Login/invite issues are household support moments; public proxy/origin mistakes are documented in the maintainer runbook. No external status page is needed. **Grade: B.** IDs: OPS-010.

**Consumer.** Readers can Ask, see job words, receive notices, and use Library card. They should not see SAB filenames or operator controls. **Grade: B+.**

**Owner.** Strong tools, excessive list volume, and no compact recurring checklist. **Grade: C+.** IDs: OPS-001, OPS-003, OPS-005, OPS-008.

**Admin/Ops.** Deploy/version/backup documentation is strong; support intake remains maintainer-shaped and restoration is unpracticed. **Grade: B.** IDs: OPS-008, OPS-010.

## 6. Findings by theme

**Owner maintenance:** best—Morning brief capped at three; worst—raw 27/80 backlogs. **Admin tooling:** best—reason filters, bulk actions, progress and safe undo; worst—slow shelf health and scattered config boundary. **Support load:** predictable and documentable. **Manual toil:** direct `.env`/settings edits and SSH logs should be break-glass. **Communication:** glossary/job words are strong; FAQ should be shorter. **Escalation:** confirmation and snapshots are right; avoid impersonation.

## 7. Stop doing

- Stop opening Downloads/Sorting on historical rows by default (OPS-003).
- Stop treating “backup exists” as equivalent to “restore is ready” (OPS-008).
- Stop telling owners to edit `settings.json` for routine configuration (OPS-005).
- Stop duplicating troubleshooting prose across HELP and Automat; link authoritative procedures (OPS-010).
- Do not add full session impersonation or a SaaS support stack.
- Do not promote Hub rollout as current truth.

## 8. Strengths worth protecting

- Confirm-before-SAB and role-specific Ask/Get language.
- Sorting reason filters, cursor pagination, bulk-by-reason, and safe undo.
- Maintain Morning brief’s three-item cap (`maintain.py:138-189`).
- Poller last-run/error, progress persistence, and stalled-job recovery.
- Nightly integrity-checked snapshots and documented stop/swap/restart restore.
- LAN/image stamp as version truth and `./docker-run.sh` as deploy truth.

## 9. Risks of inaction

The owner starts ignoring badges because too much history looks urgent. Failed/old jobs bury reader Asks; Sorting ages without an explicit service level. Routine settings drift back to file edits and SSH. The first real restore becomes an improvised procedure under pressure. Repeated SAB mapping, permission, invite, and proxy questions consume maintainer time even though answers already exist.

## 10. Recommended direction

**Now:** ship the weekly checklist and actionable queue/Sorting defaults; publish the top-five FAQ (OPS-001, OPS-003, OPS-010). **Next:** formalize Settings-vs-env ownership and conduct/record a restore drill (OPS-005, OPS-008). **Later:** add a redacted “copy support info” bundle only if field issue volume justifies it.

Ninety-day success: weekly desk time <10 minutes when healthy; actionable queue is the default; median open Sorting count <5 or every older item has an explicit reason/owner; backup <24h; one restore drill <60 minutes; top repeat questions answered without SSH.

## 11. Scorecard

| Surface | Self-service | Admin tooling | Recovery | Toil | Communication | Overall |
|---|---:|---:|---:|---:|---:|---:|
| Public | 3 | — | 3 | — | 4 | 3 |
| Consumer | 4 | — | 3 | — | 4 | 4 |
| Owner | 3 | 4 | 3 | 2 | 4 | 3 |
| Admin/Ops | 3 | 4 | 4 | 3 | 4 | 4 |

## Owner toil inventory

| Task | Frequency | Current path / evidence | Current burden | Target |
|---|---|---|---|---|
| Confirm reader Asks | Daily/ad hoc | Downloads; queue ~80 | history competes with action | actionable default; p50 decision <30s |
| Resolve Sorting | Daily/weekly | `/review`; 27 open | inspect cards/reasons | grouped oldest-first; <5 open median |
| Check jobs/poller | Weekly/incident | Maintain status, 30s refresh | scan many rows | exceptions first; healthy collapsed |
| Check shelf permissions | Weekly/incident | shelf-health; confirmed timeout | may not return | cached snapshot <2s |
| Verify backup | Weekly | Maintain + status | timestamp check | automatic warning >24h |
| Restore | Annual/incident | stop/swap/restart runbook | unpracticed | clone drill <60m |
| Configure integration | Rare | Settings or `.env` | boundary unclear | ownership table |
| Fix SAB mapping | Incident | Sorting + HELP | path diagnosis | FAQ + exact validation |
| Fix PUID locks | Incident | Maintain/HELP/runbook | host command required | keep break-glass, show exact root |
| Deploy | Release | kit sync + `./docker-run.sh` | manual but bounded | retain single path |

## Weekly operator checklist

- [ ] Confirm image truth: `/app/.build-info` matches intended release; do not use VIP as version truth.
- [ ] Maintain shows poller alive and no step with a stale heartbeat or repeated last error.
- [ ] Last integrity-checked backup is less than 24 hours old.
- [ ] Downloads actionable view has no reader Ask older than 48 hours.
- [ ] Sorting: review oldest reason group; aim for fewer than five open or record why each remains.
- [ ] Find lanterns: mute only a failing host; do not delete configuration during a transient outage.
- [ ] Disk and shelf permissions have no new locked root; use the documented PUID/GID fix, never `777`.
- [ ] Scan/enrich/ingest jobs are completed or have an explicit recovery action.
- [ ] Review release notes and relevant security/update notices.
- [ ] Monthly: copy secrets/config separately from database snapshots. Annually: run the restore drill on a clone.

# Part B — Detailed findings

## 12. Scope & method

Reviewed the [platform map](00_2026-11-04_platform-map.md), prior review/backlog, HELP, Automat runbook, Hall/Review/Maintain/poller/status source, and supplied live scale. No destructive action, deployment, restore, settings save, invite, or member operation was performed. No support-ticket corpus exists; load drivers are evidence-based inference.

## 13. Strengths

### OPS-002: Protect reason-led Sorting and safe group actions

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Owner |
| Persona(s) | Owner, op |
| Category | Admin tooling |
| Severity | High |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 12 |
| Verdict | Protect |
| Dependencies | OPS-003 |
| Labels | sorting, safety |

**Evidence:** `librarian/web/routers/review.py:31-48,56-81,102-144`; `docs/HELP.md:70-86`.

**Current state:** owner can filter/paginate, undo, and apply safe reason-group actions. **Root cause:** Sorting is modeled as a desk, not raw filesystem surgery.

**Recommendation:** Preserve reason and undo semantics while changing defaults.

**Rationale:** Automation should reduce toil without hiding cause or deleting files.

**User story:** As an owner, I want safe group actions with an undo path.

**Acceptance criteria:** [ ] bulk preview/count. [ ] no file deletion without explicit protected flow. [ ] undo remains visible.

**Success metric:** reduced time per resolved slip with zero accidental loss.

**Validation:** targeted API/e2e tests.

### OPS-004: Protect runbooks and deployment truth

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Admin |
| Persona(s) | Maintainer |
| Category | Operations |
| Severity | High |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 12 |
| Verdict | Protect |
| Dependencies | OPS-008 |
| Labels | runbook, deploy |

**Evidence:** `docs/ops/AUTOMAT.md:10-29,50-87,130-180,190-217`.

**Current state:** ports, version truth, deploy, backup/restore, media roots, and permissions are explicit. **Root cause:** maintainer LAN practices were codified.

**Recommendation:** Keep one authoritative runbook; link rather than duplicate.

**Rationale:** One tested procedure beats several stale summaries. Hub-first is not current Librarian truth.

**User story:** As a maintainer, I want one procedure that protects sibling apps and data.

**Acceptance criteria:** [ ] deploy remains `./docker-run.sh`. [ ] restore steps tested annually.

**Success metric:** no wrong-port or wrong-version incidents.

**Validation:** runbook drill.

## 14. Weaknesses

### OPS-003: Default Downloads and Sorting to actionable work

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Owner, op |
| Category | Toil |
| Severity | High |
| Impact | 5 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 5.0 |
| Verdict | Fix |
| Dependencies | PRD-003 |
| Labels | queue, sorting |

**Evidence:** live Sorting 27 and queue ~80; Review already supports reason/cursor/25 limit (`review.py:31-48`); HELP defines actionable job states (`docs/HELP.md:55-68`).

**Current state:** action and history compete for attention. **Root cause:** list defaults optimize completeness, not owner time.

**Recommendation:** Downloads default to Asked + Failed/Needs-you requiring action; terminal history behind filters. Sorting defaults oldest-first, grouped by reason, with safe bulk suggestions.

**Rationale:** This reduces daily work without deleting history. Auto-confirm was rejected because confirm-before-SAB is a product safety rule. Now because live volume is already material.

**User story:** As an owner, I want to see only decisions awaiting me.

**Acceptance criteria:** [ ] reader Asks first. [ ] terminal history one click away. [ ] reason counts accurate. [ ] no auto-SAB.

**Success metric:** weekly ops time down; confirm p50 <30s; median Sorting <5.

**Validation:** seeded mixed-state Playwright journey.

### OPS-001: Publish a weekly owner checklist

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Owner |
| Category | Enablement |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | OPS-003 |
| Labels | checklist |

**Evidence:** Maintain exposes morning brief/jobs/backup (`maintain.py:138-249`); operations are currently spread through HELP and Automat.

**Current state:** tools exist, cadence is implicit. **Root cause:** docs teach features, not recurring stewardship.

**Recommendation:** put the checklist above in owner HELP and link it from Maintain; auto-check only server-verifiable items.

**Rationale:** A short ritual prevents silent backlog and backup drift. A new dashboard is unnecessary; use current Maintain.

**User story:** As an owner, I want a ten-minute weekly pass.

**Acceptance criteria:** [ ] ≤10 weekly items. [ ] each links to action/evidence. [ ] no false manual completion for backup/poller.

**Success metric:** checklist used for four weeks; healthy pass <10m.

**Validation:** owner dry run.

### OPS-005: Define Settings versus host configuration ownership

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Owner, maintainer |
| Category | Toil |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Likely |
| Priority score | 2.4 |
| Verdict | Fix |
| Dependencies | — |
| Labels | settings, env |

**Evidence:** secrets live in `.env` or `/config/settings.json`; Automat requires owner/session secret and uses Settings for many integrations (`docs/ops/AUTOMAT.md:88-128`).

**Current state:** routine and break-glass configuration can be confused. **Root cause:** install-time and runtime settings share concepts.

**Recommendation:** ownership table: session/owner boot secret, proxy trust, PUID/PGID, TZ = host; library roots, integration URLs/tokens, quiet hours = Settings with env override clearly labeled.

**Rationale:** UI-first reduces SSH, but forcing deployment secrets into UI weakens recovery/security. Do next after immediate toil defaults.

**User story:** As an owner, I want to know where each setting belongs.

**Acceptance criteria:** [ ] one source-of-truth table. [ ] UI shows env-managed read-only state. [ ] no routine direct JSON edits.

**Success metric:** fewer config-file edits and duplicate-value incidents.

**Validation:** fresh-install and upgrade walkthrough.

### OPS-008: Practice and record backup restoration

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Owner, maintainer |
| Category | Reliability |
| Severity | Medium |
| Impact | 4 |
| Effort | S |
| Confidence | Suspected |
| Priority score | 2.67 |
| Verdict | Fix |
| Dependencies | PRIV-004 |
| Labels | backup, restore |

**Evidence:** restore procedure at `docs/ops/AUTOMAT.md:153-185`; status finds newest snapshot (`librarian/web/status.py:27-50`); no drill record reviewed.

**Current state:** backups are automated; recovery confidence is documentary. **Root cause:** restore is rare and easy to postpone.

**Recommendation:** annual and pre-major-migration clone drill: stop clone, swap DB, clear WAL/SHM, boot, ready check, sample shelves, record date/duration/snapshot.

**Rationale:** Testing the exact local procedure is higher value than another backup copy. Next because current backups reduce immediate risk.

**User story:** As an owner, I want proof a snapshot restores before an incident.

**Acceptance criteria:** [ ] drill uses clone, never live first. [ ] completes <60m. [ ] secrets/config handled separately.

**Success metric:** current-year successful drill.

**Validation:** signed drill log and screenshots/count checks.

### OPS-010: Create a five-answer support FAQ

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Owner, reader |
| Category | Support |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Likely |
| Priority score | 2.4 |
| Verdict | Fix |
| Dependencies | OPS-005 |
| Labels | faq |

**Evidence:** SAB mapping and PUID guidance at `docs/HELP.md:70-105`; proxy/origin at `docs/ops/AUTOMAT.md:33-47`; invite and job words throughout HELP.

**Current state:** answers exist but are distributed. **Root cause:** docs grew by capability rather than ticket frequency.

**Recommendation:** FAQ: invite/login; Asked vs On the way vs Needs you vs Failed; missing folder/SAB root; shelf locked/PUID; LAN vs VIP/version/proxy. Each answer ends with one action and link.

**Rationale:** Most likely tickets are already known. A helpdesk product is overkill; a compact index is now justified.

**User story:** As an owner, I want the likely fix in under a minute.

**Acceptance criteria:** [ ] five answers. [ ] canonical terms. [ ] no duplicated secret values/commands outside runbook.

**Success metric:** repeat questions resolved without SSH/escalation.

**Validation:** scenario-based doc test.

## 15. Opportunities

### OPS-006: Protect owner-issued reset without impersonation

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Admin |
| Persona(s) | Owner, reader |
| Category | Escalation |
| Severity | Medium |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 8 |
| Verdict | Protect |
| Dependencies | — |
| Labels | recovery, privacy |

**Evidence:** client exposes issue-reset and sign-out-everywhere (`frontend/src/api.js:46-65`); no view-as route is evidenced.

**Current state:** owner can recover access without silently entering a member session. **Root cause:** household support favors explicit account actions.

**Recommendation:** Protect; add audit/support context rather than impersonation.

**Rationale:** Full impersonation answers some questions by exposing private activity. Narrow diagnostics are safer.

**User story:** As a member, I want support without the owner silently becoming me.

**Acceptance criteria:** [ ] reset/revoke explicit and audited. [ ] no session impersonation.

**Success metric:** zero unaudited view-as events.

**Validation:** route/audit review.

## 16. Remediation plan

| Horizon | ID | Work | Effort | Owner | Dependencies |
|---|---|---|---|---|---|
| Now | OPS-003 | Actionable queue/Sorting defaults | M | Product + FE/BE | — |
| Now | OPS-001 | Weekly checklist in HELP/Maintain | S | Ops + content | OPS-003 |
| Now | OPS-010 | Top-five FAQ | S | Support/content | — |
| Next | OPS-005 | Settings/env ownership table | S | Maintainer | — |
| Next | OPS-008 | Clone restore drill and record | S | Maintainer | PRIV-004 |
| Later | — | Redacted support bundle if issue volume warrants | M | Maintainer | telemetry |

## 17. Quick wins

Make Asked/Failed/Needs-you the queue default, add “oldest waiting” to Morning brief, link the checklist, and publish the five-answer FAQ.

## 18. Open questions

1. What percentage of ~80 jobs are terminal history versus actionable?
2. Which Sorting reasons account for the 27 slips?
3. Who besides the owner has Automat SSH and restore authority?
4. Where should restore-drill evidence live without creating another stale runbook?

## Self-check

- [x] Full Part A and four surfaces.
- [x] OPS-001/003/005/008/010 preserved in full format.
- [x] Toil inventory and weekly checklist included.
- [x] Alternatives, evidence limits, and sequencing stated.
