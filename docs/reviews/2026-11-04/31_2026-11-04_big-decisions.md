# 31 · Big decisions — run 2026-11-04

These are leadership calls. They are not tickets. Each one blocks a slice of [`2026-11-04_backlog.csv`](2026-11-04_backlog.csv) where `DecisionRequired=yes`. Waiting without recording a choice is option **Do nothing** on each ADR.

**Commit / image reviewed:** Automat image **1.0.10** / **480eff0** (`docker exec librarian cat /app/.build-info`). Checkout HEAD during enrichment: `fced2be` (flagged in [`_status.md`](_status.md); no material product drift vs image for these calls).

**Companion files:** [`00_2026-11-04_platform-map.md`](00_2026-11-04_platform-map.md) · [`20_2026-11-04_cross-examination.md`](20_2026-11-04_cross-examination.md) · [`21_2026-11-04_red-team.md`](21_2026-11-04_red-team.md) · [`30_2026-11-04_executive-summary-and-roadmap.md`](30_2026-11-04_executive-summary-and-roadmap.md) · [`2026-11-04_backlog.csv`](2026-11-04_backlog.csv)

**Red team → BD map:** The three leadership questions in [`21_2026-11-04_red-team.md`](21_2026-11-04_red-team.md) are answered here as **BD-3** (Sorting open-count / metric ownership), **BD-1** (Hub reverse-proxy exit vs permanent LAN + CF Access posture), and **BD-4** (music first-tier). Cross-examination Desk-IA timing lands as **BD-2**. MFA sequencing is **BD-5**. Confirm-before-SAB auto-confirm temptation is **BD-6** (explicit Reject).

**CSV** `DecisionRequired` **contract:** Only rows that list a `BD-N` in Dependencies (or are named in a **Blocks** list below) may set `DecisionRequired=yes`. Today that is **SEC-006 → BD-1**, **PRD-012 / UX-001 → BD-2**, **SEC-009 → BD-5**. BD-3 / BD-4 / BD-6 are strategic calls that gate *new work* and sequencing; they do not orphan CSV IDs. If a later CSV row cites a BD that was never written, remap it in this intro the way Oct 28-2 remapped BD-06–09.

**Decision owner for all six:** the maintainer. **Default deadline:** before the next Automat `./docker-run.sh` promote that claims the Now roadmap, and in any case within **14 days** of accepting [`30_`](30_2026-11-04_executive-summary-and-roadmap.md). Record **Decided.** under each ADR; do not invent decisions in this rewrite.

---

## BD-1 · Who/what is the lasting exposure posture — Hub reverse-proxy-only, Automat CF Access as the edge, or permanent bare LAN bind?

**Context.** `docs/SECURITY.md` **S3** remains **Accepted**: the container listens on `0.0.0.0:8793` so any host interface (and accidental WAN map) can reach the control plane. The written product exit is **Hub reverse-proxy-only** — when Hub `romwil/librarian` is the ship path, TLS on a reverse proxy you control is the only published way in, with `LIBRARIAN_TRUST_PROXY_HEADERS=1` only on that hop. Hub publish for this kit is still **deferred** ([`00_2026-11-04_platform-map.md`](00_2026-11-04_platform-map.md), sacred cow 16; Automat playbook). On this household, the owner already reaches the app via `**librarian.automat.vip`** (Cloudflare Access / Workspace gate + TLS) while guest Wi‑Fi sits on a **separate VLAN** that cannot route to `10.10.x.x`. Live LAN truth for agents remains `http://10.10.1.202:8793` ([`_status.md`](_status.md)). Security finding **SEC-006** in [`06_2026-11-04_security.md`](06_2026-11-04_security.md) tracks the Accepted bind; privacy and ops treat vip Origin allowlisting (`PUBLIC_BASE_URL` / `LIBRARIAN_PUBLIC_ORIGINS`, cow 22) as already required for CF Tunnel login in 1.0.10. Tickets cannot settle whether “Accepted forever with CF Access” is the product story or whether Hub exit must still ship — that is a leadership posture call, and the red team asked it explicitly ([`21_`](21_2026-11-04_red-team.md)).

**Options.**

1. **Do nothing.** Leave S3 Accepted, Hub deferred, and rely on tribal knowledge that vip + VLAN exist. Firewall checks stay ad hoc. New CA/Unraid installers still get a bare bind story with no published TLS path.
2. **Automat-edge as the lasting posture (document + harden CF Access).** Keep container bind unchanged. Treat Cloudflare Access (or equivalent) + guest VLAN + Origin allowlist + opt-in proxy trust as the **household production edge**. Write the Automat firewall / Access checklist into ops docs; schedule Hub only if public CA installers become a goal. Optional follow-ups: Access policy least-privilege (who can hit the app), Tunnel not bypassable to bare `:8793` from WAN, confirm `LIBRARIAN_TRUST_PROXY_HEADERS` only on the Tunnel hop, periodic Access audit log glance.
3. **Ship Hub reverse-proxy-only within two quarters.** Resume Hub `romwil/librarian` + CA proof so the *product* exit matches SECURITY.md. Automat CF Access can remain the house’s edge, but the kit story stops saying “LAN-trusted forever.”
4. **Change default bind to LAN interface only.** Reduces accidental WAN exposure for naive templates; breaks some Unraid “publish all interfaces” habits and does not replace TLS or Access.

**Recommendation.** **Option 2 now** for this household and this kit’s deferred-Hub reality; **revisit option 3** when (and only when) public CA installers are an active milestone. Do not choose option 4 unless Unraid template users are the primary victim and Hub remains years out. Option 1 is honest only if the maintainer accepts that SECURITY.md’s Hub exit sentence is aspirational — record that explicitly if chosen.

**Trade-offs.** Option 2 makes Automat’s CF Access first-class ops truth and avoids inventing Hub release machinery before the kit is ready; it does **not** help a random CA user who port-forwards 8793. Option 3 pays L release cost for a story installers need. Option 4 surprises Docker templates without solving auth or TLS. Doing nothing keeps SEC-006 as a permanent Critical Accepted without a written household edge.

**Cost.** Option 2 = **S** (docs + Access checklist + verify Origin allowlist / Tunnel / VLAN once). Option 3 = **L** (Hub publish, Path B proof, rollout script — none active for Librarian today). Option 4 = **M** with support fallout.

**Reversibility.** High for option 2 documentation. Medium for Hub once CA users depend on it. Bind changes are medium (template + support).

**Deadline.** **2026-12-15** (or before any intentional WAN/vip expansion). **Blocks:** SEC-006 (`DecisionRequired=yes`); sequences SEC-009 / **BD-5** (MFA after edge story is clear); informs OPS firewall notes in [`10_2026-11-04_operations-support.md`](10_2026-11-04_operations-support.md).

**CF Access hardening notes (for option 2 — review, not a separate BD).** Prefer: (a) Access application covers the vip hostname with Workspace IdP; (b) no WAN DNAT to `10.10.1.202:8793`; (c) guest VLAN cannot route to the library VLAN; (d) `PUBLIC_BASE_URL` / `LIBRARIAN_PUBLIC_ORIGINS` include the vip; (e) `LIBRARIAN_TRUST_PROXY_HEADERS=1` only behind the Tunnel/proxy you control, never on a laptop SSH tunnel; (f) confirm sibling CSRF posture (`Origin` + `X-Librarian: 1`) still holds through the proxy; (g) Access session length and admin bypass paths are intentional. Do not treat vip CDN as version truth — agents keep reading LAN `:8793` / `.build-info`.

WR: The platform is accessed via [librarian.automat.vip](http://librarian.automat.vip) which provides ssl and cloudflare protection - it is gated by Workspace auth. the guest network is a separate vlan here and only private ips can get to the 10.10.x.x address. can you review the cloudflare configurations around this route and recommend any additional recommendations for this item?

*(Maintainer note captured; option space above incorporates CF Access as a first-class edge. Formal **Decided.** still awaits WR.)*

**Status.** Proposed.

WR: Decided Option 2

---

## BD-2 · Should owner desk IA consolidate under one Desk, or educate-in-place while triage ships?

**Context.** Live owner chrome exposes **Downloads**, **Sorting 27**, and **Maintain** as peer destinations beside reader nav ([`00_`](00_2026-11-04_platform-map.md) walkthrough; Maintain morning desk already says “Tend these…” with Sorting + unshelved shells). Product (**PRD-012** in [`01_2026-11-04_product-strategy.md`](01_2026-11-04_product-strategy.md)) and UX (**UX-001** in [`02_2026-11-04_ux-experience.md`](02_2026-11-04_ux-experience.md)) both name noun sprawl as learning cost for new owners. Cross-examination resolves the conflict with Sorting triage (**PRD-003**, **UX-002**, **OPS-003**): **triage UX first; Desk IA as Later** ([`20_2026-11-04_cross-examination.md`](20_2026-11-04_cross-examination.md)). Red team flags full Desk rewrite before triage defaults as expensive low-yield ([`21_`](21_2026-11-04_red-team.md)). Tickets can ship filters and confirms; they cannot decide whether primary nav should collapse without a product call.

**Options.**

1. **Do nothing.** Keep three top-level owner nouns forever; rely on HELP and Maintain morning desk copy.
2. **Educate-in-place now; group later.** Ship HELP checklist + Sorting/Downloads actionable defaults; leave nav alone until Sorting steady-state metric moves (see BD-3). Then consider a Desk menu with a single badge.
3. **Group under Desk menu soon (badge).** One primary ops entry; Confirm | Sorting | Tend tabs inside. Touches chrome, a11y, e2e.
4. **Full single-page Desk rewrite.** Merge surfaces into one SPA route. Highest learning reset; largest regression surface.

**Recommendation.** **Option 2 now.** Explicitly reject option 4 this quarter. Option 3 is the candidate **after** Sorting open-count is habitually under the BD-3 threshold (or after 30 days of triage metrics). Option 1 is acceptable only if the maintainer will not invite new owners soon.

**Trade-offs.** Educate-in-place preserves e2e and lexicon muscle memory while the Now list clears slips. Early Desk grouping (option 3) helps new owners but competes with PERF/A11Y virtualization work on the same chrome. A full rewrite burns the quarter the board already assigned to toil.

**Cost.** Option 2 = **S** (HELP + defaults). Option 3 = **M**. Option 4 = **XL**.

**Reversibility.** High for copy/defaults. Medium for nav grouping (habits + Playwright). Low for a merged route without a long feature flag.

**Deadline.** Revisit **30 days after triage defaults ship**, or when Sorting median open < 5 for two weeks (BD-3). **Blocks:** PRD-012, UX-001 (`DecisionRequired=yes`); does **not** block PRD-003 / UX-005 / OPS-003 Now work.

**Status.** Proposed.

WR: option 2 with 4 in the  future

---

## BD-3 · What Sorting open-count is unacceptable after 30 days of triage — and who owns the metric?

**Context.** Live Sorting shows **All 27** with reason chips (**low confidence 22**, audnexus unmatched 2, unknown identity 2) and a ~**1021**-ref DOM ([browser snapshot `/review](http://10.10.1.202:8793/review)`). Maintain morning desk also surfaces **5541 unshelved shells** beside Sorting — a second pile that can dwarf slips if “desk calm” is undefined. Product’s success line is median open slips **< 5** in 90 days (**PRD-003**); red team asked for a sharper **30-day unacceptable** threshold and a named owner ([`21_`](21_2026-11-04_red-team.md)). The bolder alternative is stricter auto-organize so Sorting is empty by construction (**BD-3’s sister temptation** is BD options below overlapping BD historically labeled “stricter auto-file” — kept here as the metric call; auto-file experiment remains option space). Without a number, “Owner Desk calm” epics cannot fail.

**Options.**

1. **Do nothing.** Keep “< 5 in 90 days” aspirational; no weekly owner; shells count ignored.
2. **UI/triage-only SLO.** Owner (maintainer) owns weekly Sorting open count. **Unacceptable after 30 days of Now triage:** median daily open **> 15** (or never below 20 for 7 consecutive days). Shells get a separate Maintain purge ritual, not the same SLO.
3. **Raise auto-file confidence + measure mis-shelve rate** so open slips trend toward <1% of jobs (red-team bold option). Sorting UI still improves, but the bet is identify quality.
4. **Hybrid.** ISBN-strong books auto-file behind an owner toggle; audio/comics stay Sorting-first; SLO as in option 2 for the remaining pile.

**Recommendation.** **Option 2 for the metric and ownership now**; run **option 4 as a measured experiment** only after baseline triage defaults exist (do not flip auto-file in the same week as virtualization). Option 3 alone is too bold without mis-shelve instrumentation (GRO house pulse / PERF). Option 1 fails the red-team question.

**Trade-offs.** A numeric SLO creates a honest fail if toil returns; it also pressures purge-shells (5541) to stay out of the Sorting badge narrative. Auto-file upside is product identity at scale; downside is silent wrong shelves and household trust loss (ties to BD-6 spirit).

**Cost.** Option 2 = **XS** (write the number + who checks Maintain/Sorting weekly). Option 4 experiment = **M** with undo/telemetry. Option 3 = **L** identify work.

**Reversibility.** Metric choice is high. Auto-file toggle should be reversible; untoggle does not unshelve bad moves without undo tooling.

**Deadline.** **Record the number within 7 days** of accepting the roadmap; evaluate at **+30 days**. **Blocks:** framing of PRD-003 / OPS-003 success; gates whether BD-2 option 3 is allowed; informs ARCH/PERF pagination priority if DOM weight blocks triage (**A11Y-005**, **PERF-008** in [`04_`](04_2026-11-04_accessibility.md) / [`09_`](09_2026-11-04_performance-reliability-cost.md)).

**Status.** Proposed.

WR: 2

---

## BD-4 · Is music first-tier on Hall strategic, or should Hall demote it until Promote UX is excellent?

**Context.** Live Hall kind chips show **Books · 10762** vs **Music · 97** ([`00_`](00_2026-11-04_platform-map.md)). Sacred cow 14 stages music in incoming → **Promote** to `music_root` for Plexamp; audiobooks must never land in music_root. Product kept music first-tier with a light challenge (**PRD** foundations); red team called that possible nostalgia for the Automat media contract rather than reader JTBD ([`21_`](21_2026-11-04_red-team.md)). Cross-ex listed music cost as a Product blind spot ([`20_`](20_2026-11-04_cross-examination.md)). Tickets can polish Promote copy; they cannot demote a Hall chip without a product call.

**Options.**

1. **Do nothing / keep first-tier.** Music stays a Hall chip and Search kind equal to books.
2. **Demote to Stacks/Search-only.** Hall chips emphasize books/audio/comics/magazines; music reachable from Stacks or Library card.
3. **Remove first-tier until Promote UX passes a support bar.** Music ingest remains; Hall stops advertising it until Promote error rate / owner FAQ load is low.
4. **Keep chips; invest in Promote UX this quarter.** Explicitly accept music JTBD as strategic for Automat.

**Recommendation.** **Option 1 (keep) pending a Promote support review**, with a **revisit date**. Do not remove in this release. If Promote/support load is high after named-shelf and Sorting Now work, prefer option 2 over option 3 (so power users still find music without a Hall chip tax on every reader).

**Trade-offs.** Keeping first-tier matches Automat’s media contract and Plexamp path; it spends owner education and Sorting/identify edge cases on a small catalog slice. Demoting clarifies Hall as a reading room; it may feel like a regression to the household that already promotes albums.

**Cost.** Keep = **XS**. Demote chip = **S** (chrome + HELP). Promote UX investment = **M**.

**Reversibility.** High for chip placement. Remove-from-product would be L and is not recommended.

**Deadline.** **2027-01-15** revisit (or earlier if Promote generates repeat SSH/FAQ). Does not block Now Sorting work. **Blocks:** new music-first features and any “Hall marketing” of Promote until revisit.

**Status.** Proposed.

WR: 2

---

## BD-5 · Optional owner MFA — none, optional TOTP, or required?

**Context.** Local password is the only auth method on live Automat (`auth_methods: ["local"]`). Security lists optional owner MFA as **SEC-009** ([`06_`](06_2026-11-04_security.md)). Foyer UX and invite-only join are strengths; MFA before a clear edge story (BD-1) adds friction for little WAN benefit if bare `:8793` is not the published path. Cross-ex: MFA Later only ([`20_`](20_2026-11-04_cross-examination.md)). Red team lists MFA-before-proxy as expensive low-yield ([`21_`](21_2026-11-04_red-team.md)).

**Options.**

1. **Do nothing / none this year.** Passwords + session revoke + rate limits remain the story.
2. **Optional TOTP for owner** after BD-1 edge posture is written (CF Access and/or Hub proxy). Members stay password-only unless asked later.
3. **Required MFA for owner** (and maybe op) whenever vip/WAN is in use.

**Recommendation.** **Option 1 until BD-1 is Decided.** Then **option 2** if the lasting edge still allows password phishing to matter *inside* Access (defense in depth) or if LAN-only neighbors are in scope. Reject option 3 for a household kit unless threat model upgrades to hostile WAN without Access.

**Trade-offs.** Optional TOTP helps stolen-password cases on LAN; it costs recovery UX and support. Required MFA punishes the maintainer’s own foyer for a threat CF Access may already bound. Doing nothing is coherent with invite-only + Access if BD-1 option 2 sticks.

**Cost.** Option 2 = **L** (enroll, challenge, recovery codes, e2e). Option 3 adds support L.

**Reversibility.** Medium — once members expect MFA, removing it feels like a downgrade.

**Deadline.** **Post BD-1**, or **2027-Q1** if BD-1 stays Proposed. **Blocks:** SEC-009 (`DecisionRequired=yes`).

**Status.** Proposed.

WR: vip/WAN is behind Cloudlare and Workspace challenge layer

---

## BD-6 · Should trusted ops ever auto-confirm Asked slips into SAB after Ask the house?

**Context.** Sacred cow: **confirm-before-SAB** — readers Ask the house; owners/ops confirm on Downloads; Search/Discover never silent-grab ([`00_`](00_2026-11-04_platform-map.md) cows 3–4; **PRD-010** protect). Red team noted the board correctly Protect’d this cow but did not explicitly reject a tempting carve-out: auto-confirm for muted-healthy indexers or trusted ops ([`21_`](21_2026-11-04_red-team.md)). Without an explicit Reject, a future “speed” ticket can reopen household trust.

**Options.**

1. **Do nothing (implicit keep).** Leave the cow in HELP without a recorded Reject of auto-confirm.
2. **Allow op auto-confirm** for known-good indexer hosts / muted-healthy lanterns (Maintain scorecard) after Ask.
3. **Reject forever** — every SAB send remains an explicit confirm (bulk confirm UX may still exist; automation of the decision does not).

**Recommendation.** **Option 3 — Reject.** Improve Downloads density and digests (**PRD-011**, **OPS-003**) instead. Bulk *human* confirm with clear counts is fine; silent or policy-automatic confirm is not.

**Trade-offs.** Reject preserves the reading-room identity under acquire load. Allowing auto-confirm speeds power ops and risks surprise bandwidth bills, wrong grabs, and “Needs you” meaninglessness. Implicit do-nothing invites the next sprint to “just add a toggle.”

**Cost.** **XS** (record decision; no build). Building auto-confirm would be M and is out of scope if Rejected.

**Reversibility.** Recording Reject is reversible later with a new BD; shipping auto-confirm is harder to unwind socially than technically.

**Deadline.** **Record now** (no build). **Blocks:** any future auto-confirm feature ticket; does not block bulk confirm UX.

**Status.** Proposed — recommendation is Reject (awaiting maintainer **Decided.**).

WR: 2 

---

## Decision log (maintainer)

| BD | Title | Status |
|---|---|---|
| BD-1 | Exposure posture / CF Access vs Hub exit | Proposed (WR note on vip + VLAN captured) |
| BD-2 | Desk IA vs educate-in-place | Proposed |
| BD-3 | Sorting SLO / metric owner / auto-file hybrid | Proposed |
| BD-4 | Music first-tier | Proposed |
| BD-5 | Owner MFA | Proposed |
| BD-6 | Auto-confirm after Ask | Proposed (rec: Reject) |
