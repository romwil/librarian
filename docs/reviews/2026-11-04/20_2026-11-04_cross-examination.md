# 20 · Cross-examination — run 2026-11-04

Each department read Part A and top findings from peers after Batches 1–5. Image truth: Automat **1.0.10** / **480eff0**. Checkout HEAD `fced2be` may differ from the image; no material product drift was flagged for the resolutions below. Companion: [`00_2026-11-04_platform-map.md`](00_2026-11-04_platform-map.md) · [`21_2026-11-04_red-team.md`](21_2026-11-04_red-team.md) · [`30_2026-11-04_executive-summary-and-roadmap.md`](30_2026-11-04_executive-summary-and-roadmap.md) · [`31_2026-11-04_big-decisions.md`](31_2026-11-04_big-decisions.md) · [`2026-11-04_backlog.csv`](2026-11-04_backlog.csv).

Live evidence used across peers: Hall kind chips (Books 10762 / Music 97 / …); Sorting **All 27** with **low confidence 22**; Sorting a11y snapshot ~**1021** refs / **633** interactive; Maintain morning desk (Sorting 27 + **5541** unshelved shells); House pulse and indexer lanterns on `/maintain`.

---

## Product (`01_2026-11-04_product-strategy.md`)

**Conflicts.** UX Desk consolidation (**UX-001** in [`02_2026-11-04_ux-experience.md`](02_2026-11-04_ux-experience.md)) can starve Sorting triage (**PRD-003**) if treated as a rewrite. **Resolution:** triage and Downloads density first; Desk IA is **BD-2** Later ([`31_`](31_2026-11-04_big-decisions.md)). Visual denser Desk (**VIS-003** in [`03_2026-11-04_visual-design.md`](03_2026-11-04_visual-design.md)) must not leak Hall chrome materials into a grabber aesthetic — density only inside Desk routes.

**Reinforcements.** **PRD-003** ↔ **UX-002** / **UX-005** ↔ **PERF-008** ([`09_2026-11-04_performance-reliability-cost.md`](09_2026-11-04_performance-reliability-cost.md)) ↔ **A11Y-005** ([`04_2026-11-04_accessibility.md`](04_2026-11-04_accessibility.md)) ↔ **OPS-003** ([`10_2026-11-04_operations-support.md`](10_2026-11-04_operations-support.md)) — one owner-desk toil root cause. **PRD-010** ↔ **SEC-001**/confirm authz ([`06_2026-11-04_security.md`](06_2026-11-04_security.md)). **PRD-011** ↔ **OPS-003** queue volume. Maintain already ships “Tend these…” (**PRD-009** adjacency) — Hall card should deep-link, not fork a third morning narrative.

**Blind spots.** Music first-tier cost vs Promote complexity underweighted relative to 10k books (**BD-4**). Unshelved shells **5541** can dwarf Sorting 27 if “desk calm” is undefined (**BD-3**).

**Re-ranking.** **PRD-011** Downloads density ≥ **PRD-007** named shelves for Now. Shells purge safety stays tied to **UX-005**.

---

## UX (`02_2026-11-04_ux-experience.md`)

**Conflicts.** VIS denser Desk (**VIS-003**) vs calm Hall — resolve: denser spacing only on `/queue`, `/review`, `/maintain`. Architecture pagination (**ARCH-002** in [`08_2026-11-04_architecture.md`](08_2026-11-04_architecture.md)) may change Sorting interaction model — keep j/k focus retention (**UX-003** / **A11Y-004**).

**Reinforcements.** **UX-005** Purge confirm ↔ Maintain **Purge shells (5541)** destructive scale ↔ SEC Apply-jail spirit. **UX-011** Quiet hours off primary Sorting ↔ **VIS-003**. **UX-007** mobile ↔ A11Y reflow.

**Blind spots.** Reader-role chrome not walked live (owner-only session). Discover empty and foyer unauthenticated screenshots still thin.

**Re-ranking.** **UX-005** before **UX-001**. **UX-002** reason-chip defaults before Desk menu.

---

## Visual (`03_2026-11-04_visual-design.md`)

**Conflicts.** None hard with security/privacy. Tabular nums (**VIS-007**) must not wait on a token redesign.

**Reinforcements.** **VIS-003** ↔ **UX-011** Quiet hours demotion. Token freeze ↔ lexicon/GRO copy consistency (**GRO-006** in [`05_2026-11-04_growth-content-analytics.md`](05_2026-11-04_growth-content-analytics.md)).

**Blind spots.** Lights Up Sorting not PNG-verified (screenshot MCP timeouts) — polish claims stay **Likely** per red team.

**Re-ranking.** Keep **VIS-003** / **VIS-007** in Now with UX triage chrome; **VIS-006** inventory Later.

---

## Accessibility (`04_2026-11-04_accessibility.md`)

**Conflicts.** Virtualization (**A11Y-005**) vs full-list keyboard j/k (**UX-003**) — resolve: virtualize with focused-item retention and filter-change live regions. Do not ship windowing that drops keyboard mode.

**Reinforcements.** **A11Y-005** ↔ **PERF-008** ↔ **ARCH-002**. Skip/combobox strengths ↔ UX Hall protect.

**Blind spots.** Live axe on `:8793` still outstanding (**A11Y-008**) — do not treat WCAG AA as Confirmed. SR hardware pass not run.

**Re-ranking.** **A11Y-008** process evidence before celebrating grade; virtualize after or with PERF windowing, not as pure a11y-only rewrite.

---

## Growth (`05_2026-11-04_growth-content-analytics.md`)

**Conflicts.** Event plan (**GRO-004**) vs PRIV minimize ([`07_2026-11-04_privacy-compliance.md`](07_2026-11-04_privacy-compliance.md)) — resolve: **first-party house pulse only**, no SaaS analytics SDK. Align with Maintain House pulse copy (“Nothing leaves the house”).

**Reinforcements.** **GRO-002**/lexicon ↔ UX/VIS/PRD. OPDS (**GRO-005**) ↔ consumer distribution without public growth.

**Blind spots.** Invite conversion unmeasured (invites n=0). No on-box confirm_download chart yet.

**Re-ranking.** **GRO-004** after **PRIV-003** LLM disclosure. **GRO-006** string pass can ship Now as XS–S.

---

## Security (`06_2026-11-04_security.md`)

**Conflicts.** MFA (**SEC-009**) adds foyer friction — Later, gated by **BD-5** after **BD-1**. Trust-proxy misconfig could fight UX vip login — document with OPS.

**Reinforcements.** **SEC-006** bind ↔ OPS firewall / CF Access notes ↔ **BD-1**. **SEC-003** Origin+X-Librarian ↔ SPA `frontend/src/api.js` header. Confirm-before-SAB authz ↔ **PRD-010**.

**Blind spots.** Dependency CVEs not scanned (**SEC-008**). Cloudflare Access policies not exported/verified in this review — treated as owner-reported ops evidence.

**Re-ranking.** **SEC-006** remains Critical Accepted with an explicit BD; do not pretend CF Access closes S3.

---

## Privacy (`07_2026-11-04_privacy-compliance.md`)

**Conflicts.** GRO events vs data minimization — resolved under Growth (first-party only). LLM chase features must not ship disclosure-free.

**Reinforcements.** **PRIV-003** ↔ Settings/HELP ↔ GRO honesty. **PRIV-004** backups ↔ **OPS-008** restore drills. **PRIV-010**/health lean disclosure ↔ SEC handshake.

**Blind spots.** Cross-reader progress isolation (**PRIV-007**) still Suspected without multi-reader live proof. Export completeness (**PRIV-002**) needs field checklist against code.

**Re-ranking.** **PRIV-003** into Now ahead of chase growth. **PRIV-004** with backup ACL Next.

---

## Architecture (`08_2026-11-04_architecture.md`)

**Conflicts.** Worker split (**ARCH-003**) vs ops simplicity of single process — defer; document kill criterion instead (**BD-3** adjacency / red-team SQLite cow). TS rewrite (**ARCH-004**) vs velocity — reject big-bang.

**Reinforcements.** **ARCH-002** ↔ **PERF-002** / **PERF-008**. Hotspot splits (**ARCH-008**) ↔ Sorting/Maintain module size.

**Blind spots.** Exact slow SQL not EXPLAIN’d this run. Payload caps not measured with chrome Network panel numbers.

**Re-ranking.** Caps/pagination/indexes before new services or worker extraction.

---

## Performance (`09_2026-11-04_performance-reliability-cost.md`)

**Conflicts.** None with security headers/CSP. Lighthouse gap (**PERF-003**) vs VIS polish claims — both need artifacts.

**Reinforcements.** **PERF-002** Maintain shelf-health timeout ↔ **ARCH-002** ↔ Maintain morning desk usefulness. **PERF-008** ↔ **A11Y-005**. Backups strength ↔ OPS/PRIV.

**Blind spots.** No Lighthouse LCP numbers. Queue tick cost under ~80 jobs Suspected (**PERF-009**).

**Re-ranking.** **PERF-002** co-equal with Sorting virtualize for Now.

---

## Operations (`10_2026-11-04_operations-support.md`)

**Conflicts.** None that invert product Protects. Impersonation absence is correct (SEC/PRIV) even if support is slower.

**Reinforcements.** **OPS-003** ↔ PRD/UX Sorting-Downloads Now list. **OPS-004** runbooks ↔ SECURITY.md / AUTOMAT.md. **OPS-008** ↔ **PRIV-004**. Maintain Purge shells 5541 is an ops load driver equal to Sorting 27.

**Blind spots.** No ticket system metrics — toil inferred from live counts. Reader self-serve FAQ still thin (**OPS-010**).

**Re-ranking.** Weekly checklist (**OPS-001**) and FAQ (**OPS-010**) Now as enablement while engineering clears piles.

---

## Board-level synthesis of conflicts

| Tension | Resolution | BD / epic |
|---|---|---|
| Desk IA rewrite vs triage | Triage first | BD-2 Later |
| Virtualize vs keyboard Sorting | Virtualize + focus retain | Scale lists |
| House pulse vs no trackers | First-party only | Household pulse |
| CF Access vs S3 Accepted | Document edge; don’t close Critical | BD-1 |
| Auto-file vs UI pile | Metric first; hybrid experiment later | BD-3 |
| MFA vs foyer calm | After edge posture | BD-5 |
| Auto-confirm temptation | Explicit Reject | BD-6 |
