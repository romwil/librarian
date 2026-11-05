# 30 · Executive summary & roadmap — run 2026-11-04

**Platform:** Librarian on Automat LAN · image **1.0.10** / **480eff0** · Overall grade: **B+** (unchanged after enrichment; evidence deepened, product story not rewritten).

**Companion files:** [`00_2026-11-04_platform-map.md`](00_2026-11-04_platform-map.md) · [`20_2026-11-04_cross-examination.md`](20_2026-11-04_cross-examination.md) · [`21_2026-11-04_red-team.md`](21_2026-11-04_red-team.md) · [`31_2026-11-04_big-decisions.md`](31_2026-11-04_big-decisions.md) · [`2026-11-04_backlog.csv`](2026-11-04_backlog.csv)

---

## Leadership briefing

Librarian is a rare household product that still feels like a **reading room** rather than a download manager. On live Automat, Hall-first chrome, invite-only access, confirm-before-SAB, Origin + `X-Librarian` mutation gates, CSP, and a coherent lexicon are worth protecting — and they are evidenced in code and in the owner session, not only in aspiration ([`01_2026-11-04_product-strategy.md`](01_2026-11-04_product-strategy.md), [`06_2026-11-04_security.md`](06_2026-11-04_security.md)).

That promise is under strain from **owner desk load** and **catalog scale**, not from a confused reader product. Live Sorting shows **27** slips (**low confidence 22** dominant) with a ~**1021**-node accessibility tree; Maintain’s morning desk pairs that with **5541 unshelved shells**, indexer lanterns, and House pulse. Queue volume remains on the order of **~80** jobs. Maintain shelf-health has timed out in this run’s recon ([`09_2026-11-04_performance-reliability-cost.md`](09_2026-11-04_performance-reliability-cost.md), [`08_2026-11-04_architecture.md`](08_2026-11-04_architecture.md)). Cross-cutting root cause: **acquire/identify/catalog volume outrunning exception UX and list performance**.

Security posture is mature for a LAN kit, with one standing Critical **Accepted** bind (`0.0.0.0:8793`, SECURITY.md S3 / **SEC-006**). The household already uses **Cloudflare Access** on `librarian.automat.vip` plus a guest VLAN; that is valuable edge defense and still does not close S3 without a written posture decision (**BD-1** in [`31_`](31_2026-11-04_big-decisions.md)). Privacy is private-by-shape; LLM/outbound metadata needs disclosure (**PRIV-003** in [`07_`](07_2026-11-04_privacy-compliance.md)) before chase features grow.

Strategic direction for two quarters: (1) make owner Desk work scannable and measurable (Sorting steady-state under the **BD-3** threshold; shells handled as an explicit Maintain ritual), (2) bound Hall/Review/Maintain latency and Sorting DOM cost, (3) ship privacy disclosure and first-party house pulse only, (4) decide Hub proxy exit vs CF Access as lasting edge (**BD-1**). Do not open public growth, Arr-style homes, MFA-before-edge, or auto-confirm after Ask (**BD-6** Reject).

---

## Department grades

| Dept | Grade | One-line | File |
|---|---|---|---|
| Product | B+ | Library soul intact; owner loop stressed | [`01_`](01_2026-11-04_product-strategy.md) |
| UX | B | Strong reader; Desk IA debt | [`02_`](02_2026-11-04_ux-experience.md) |
| Visual | B+ | Tokens/soul strong; owner density unfinished | [`03_`](03_2026-11-04_visual-design.md) |
| A11y | B | Intent high; live axe/SR pending (Suspected AA) | [`04_`](04_2026-11-04_accessibility.md) |
| Growth | B | Lexicon strong; metrics blind | [`05_`](05_2026-11-04_growth-content-analytics.md) |
| Security | B+ | Hardened; S3 Accepted + CF edge ops | [`06_`](06_2026-11-04_security.md) |
| Privacy | B | Private-by-shape; disclose LLM | [`07_`](07_2026-11-04_privacy-compliance.md) |
| Architecture | B | Right topology; scale edges at 10k+ | [`08_`](08_2026-11-04_architecture.md) |
| Perf/SRE | B- | Backups good; Maintain timeout + Sorting DOM | [`09_`](09_2026-11-04_performance-reliability-cost.md) |
| Ops | B- | Toil real (27 + 5541 shells); runbooks good | [`10_`](10_2026-11-04_operations-support.md) |

---

## Where experts agree and disagree

**Agree** (see [`20_`](20_2026-11-04_cross-examination.md)): Sorting/Downloads toil is Now; confirm-before-SAB is Protect; first-party metrics only; pagination/virtualization shared across ARCH/PERF/A11Y; cut Arr-home.

**Disagree on timing:** Desk IA rewrite vs triage-first → **triage-first**, Desk as **BD-2**. Stricter auto-organize vs UI pile → metric + hybrid experiment in **BD-3**, not blind Now auto-file. Music keep vs demote → **BD-4**. MFA now vs later → **BD-5** after **BD-1**.

**Red team** ([`21_`](21_2026-11-04_red-team.md)): downgrade AA confidence; treat CF Access as ops evidence not S3 closure; force shells into SLO conversation; Reject auto-confirm (**BD-6**).

---

## Top 15 cross-department priorities

Traceable to [`2026-11-04_backlog.csv`](2026-11-04_backlog.csv) and epics below.

| # | ID(s) | Title | Horizon | Epic | BD? |
|---|---|---|---|---|---|
| 1 | PRD-003, UX-002, OPS-003 | Sorting triage to steady-state (BD-3 number) | Now | Owner Desk calm | BD-3 |
| 2 | PRD-011, OPS-003 | Downloads actionable default | Now | Owner Desk calm | — |
| 3 | UX-005 | Purge/bulk confirm safety (incl. shells) | Now | Owner Desk calm | — |
| 4 | PERF-002, ARCH-002 | Fix shelf-health timeout / cache | Now | Scale lists | — |
| 5 | PERF-008, A11Y-005 | Paginate/virtualize Sorting | Now | Scale lists | — |
| 6 | PRIV-003 | LLM/outbound disclosure | Now | Trust disclosures | — |
| 7 | SEC-006 | Hub/CF edge vs LAN posture | Next/Decision | Trust disclosures | **BD-1** yes |
| 8 | PRD-009 | Owner Hall tend card (deep-link Maintain brief) | Next | Activation polish | — |
| 9 | PRD-007, UX-006 | Named shelves activation | Next | Activation polish | — |
| 10 | GRO-004 | First-party house pulse events | Next | Household pulse | — |
| 11 | A11Y-008 | Live axe Up/Down on LAN | Now | Scale lists | — |
| 12 | UX-001, PRD-012 | Desk IA grouping | Later | Owner Desk calm | **BD-2** yes |
| 13 | OPS-008, PRIV-004 | Backup ACL + restore drill | Next | Trust disclosures | — |
| 14 | VIS-003, UX-011 | Demote Quiet hours on Sorting | Now | Owner Desk calm | — |
| 15 | PRD-008 | Enforce cut list (no Arr-home) | Now | Owner Desk calm | — |

---

## Cut list

Arr-home KPIs; public signup; third-party analytics SDKs; TypeScript rewrite; MFA-before-edge; silent SAB from Discover; trusted auto-confirm after Ask (**BD-6**).

---

## Strengths to protect

| Strength | IDs / evidence |
|---|---|
| Confirm-before-SAB + Ask-the-house | PRD-010, SEC authz |
| Exact public handshake + lean health | SEC-001/002, PRIV |
| Origin + `X-Librarian: 1` | SEC-003, `frontend/src/api.js` |
| CSP / sandboxed media | SEC-004 |
| Lights Down tokens + self-hosted fonts | VIS, tokens.css |
| Hall hero search + peek/work | UX/PRD |
| Sorting reason chips | UX-002, OPS-002 |
| Nightly backups (secrets excluded) | PERF/OPS/PRIV |
| Lexicon / HELP contract | GRO/PRD |
| notes_match What’s New | status / build-info |

---

## Epics

1. **Owner Desk calm** — PRD-003/011/005/008/012, UX-001/002/005/011, OPS-003, VIS-003/007 — Now/Next — success: Sorting under **BD-3** SLO; shells ritual defined  
2. **Scale lists** — ARCH-002/008, PERF-002/008/003, A11Y-005/008/012 — Now — success: Review interactive &lt; 2s; shelf-health p95 &lt; 2s; LAN axe clean on core paths  
3. **Trust disclosures** — PRIV-003/002/004, SEC-006/005/008/009 — Now/Next — success: LLM disclosure visible; BD-1 recorded; backup ACL drill logged  
4. **Household pulse** — GRO-004/006, PERF-007, OPS-001/010 — Next — success: on-box confirm/ask metrics without SaaS  
5. **Activation polish** — PRD-007/009/013, UX-006/010, GRO-005 — Next — success: ≥1 named shelf; Hall tend deep-link; OPDS documented  

---

## Merged roadmap

**Now (0–2w):** Sorting default-to-top-reason; Downloads actionable filter; Purge confirm (slips + shells awareness); shelf-health cache; Sorting virtualize/paginate spike; LAN axe pass; LLM disclosure copy; cut-list memo; record **BD-3** number + owner; record **BD-6** Reject; advance **BD-1** with CF Access checklist.

**Next (2–6w):** Finish virtualization; Hall tend deep-link; named shelves CTA; house pulse events; backup restore drill; Quiet hours secondary; dependency audit cadence; OPDS HELP.

**Later (6w+):** Desk IA if metrics justify (**BD-2**); Hub publish only if CA installers are a milestone (**BD-1** option 3); optional MFA (**BD-5**); auto-file hybrid experiment (**BD-3** option 4); music demotion revisit (**BD-4**).

Items with `DecisionRequired=yes` in the CSV must not be implemented past a reversible spike until the matching BD is **Decided.**
