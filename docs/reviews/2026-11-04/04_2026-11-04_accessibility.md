# 04 · Accessibility & Inclusive Design — Librarian — run 2026-11-04

**Target:** WCAG 2.2 AA · Automat `http://10.10.1.202:8793` · image **1.0.10 / 480eff0** · owner session · Lights Down
**Evidence base:** live accessibility snapshots for Hall/Search/Sorting; `AppChrome.jsx`, `ReviewPage.jsx`, `HoldSlipCard.jsx`, `TypeaheadField.jsx`, `ProfileMenu.jsx`, `useModal.js`, `tokens.css`, `e2e/axe.spec.ts`; [platform map](00_2026-11-04_platform-map.md).
**Companion files:** [platform map](00_2026-11-04_platform-map.md) · [run status and handoff](_status.md)
**Limit:** no live axe, VoiceOver, NVDA, 200% zoom, or screenshot capture completed. Automated checks catch only a fraction of accessibility barriers. **Grade: B.**

# Part A — Conclusions & findings

## 1. Bottom line

Librarian has unusually strong accessibility foundations for a private household SPA: a first-focus skip link, one shell-owned main landmark, explicit focus rings, semantic combobox/listbox search, labelled filter groups, reduced-motion support, a reusable modal focus trap, and mocked axe coverage in both themes (A11Y-001, A11Y-002, A11Y-003, A11Y-010, A11Y-012). The largest current barrier is Sorting at real scale: the live page exposed 1,021 accessibility refs and 633 interactive refs for 27 slips, with repeated help buttons, controls, and forms that make sequential navigation impractical even though individual controls are named (A11Y-005). The most important fix is a semantic master-detail or one-expanded-slip model with announced selection/filter changes—not blind virtualization that removes context. The most important patterns to protect are shell-level bypass/focus contracts and the fully keyboard-operable Search combobox. WCAG 2.2 AA confidence remains **Suspected** until live axe and manual assistive-technology checks are completed (A11Y-008).

## 2. Key conclusions

1. **The global keyboard foundation is correct and testable.** `AppChrome.jsx:76-78` puts “Skip to content” before the top bar and `:133-135` owns `<main id="main" tabIndex={-1}>`; `tokens.css:227-253` provides 3px focus and reveals the skip link. This is the right single-owner shell model and should be protected from page-level duplicate landmarks (A11Y-001).

2. **Search implements the expected ARIA combobox interaction rather than only styling a popup.** `TypeaheadField.jsx:80-157` exposes expanded state, controls, active descendant, listbox/options, selection, arrow navigation, Escape, and Enter. The remaining issue is accessible result quality: verbatim filename-like labels are cognitively noisy and can create ambiguous spoken options (A11Y-002, A11Y-006).

3. **Sorting is semantically rich but operationally overwhelming.** Groups are labelled by headings, controls have names, and rows report busy state. Yet the live snapshot found 633 interactive nodes, and each expanded slip may contain repeated “About” buttons plus seven fields and actions (`HoldSlipCard.jsx:350-445`). Good local semantics do not compensate for a prohibitively long focus order (A11Y-005).

4. **Status and recovery patterns are mature but inconsistent at group/filter boundaries.** Sorting uses status roles, busy states, progress labels, warm loading, empty copy, and Undo (`ReviewPage.jsx:810-1029`). Filter buttons do not expose `aria-pressed`, and the count/status change is not explicitly tied to the filter result. Announce “Low confidence, 22 slips” without re-reading the whole page (A11Y-003, A11Y-004).

5. **Dialog accessibility has a real shared implementation, but not every dialog is proven to use it.** `useModal.js:25-87` moves focus in, traps Tab, handles Escape, and restores the opener. ConfirmDialog and several overlays use it; ProfileMenu declares `role="dialog"` but relies on an anchored-popover hook and was not shown to trap or deliberately behave as a nonmodal popover (A11Y-007, A11Y-010).

6. **The dual-theme contrast baseline is strong on declared pairs.** Text/background, muted/background, accent text/fill, focus/background, and success/background calculate above AA from `tokens.css:4-35,99-163`. This does not prove every computed element; live axe in both themes is still required, especially chips, disabled states, color-mix surfaces, and transient animation frames (A11Y-008, A11Y-009).

7. **Motion and personalization are accessibility features, not decoration.** Reduced-motion blocks exist, the Library card offers theme and text-size controls, and the 44px tap target is tokenized. The product should centralize reduced-motion behavior and test 200%/text spacing rather than assuming rem units guarantee reflow (A11Y-009, A11Y-011).

8. **The preventive test layer is materially better than the original draft stated.** `e2e/axe.spec.ts` already runs login/join/reset, Hall, Search, Work, Sorting, Settings, Library card, dialogs, and Hall/Sorting at 320px; the main theme loop covers Lights Up and Lights Down (`:120-369`). The gap is live owner data, deeper Sorting states, semantic/focus assertions, and manual AT—not absence of axe (A11Y-008, A11Y-012).

## 3. Foundations challenged

| Assumption | Evidence for | Evidence against | Verdict | Cost | Rationale |
|---|---|---|---|---|---|
| Custom reading-room UI can meet AA | Semantic shell/search/modal patterns; token contrast | Bespoke components require discipline | **Keep + gate** | M ongoing | No framework guarantees accessibility; current primitives are a sound base (A11Y-001, 002, 010, 012). |
| Rendering every Sorting slip improves access | All records are present; browser Find works | 633 interactive nodes, repeated field names, exhausting focus order | **Change** | M | Use semantic master-detail with list position and selection announcements (A11Y-005). |
| Visual chip state is enough | `.is-on` shows selection | Sorting reason buttons lack `aria-pressed` | **Change** | XS | State must be programmatic (A11Y-003). |
| Lights Down is accessible because tokens pass | Declared text pairs are high contrast | Computed color-mix/disabled/transient states unmeasured | **Investigate** | S | Token math is necessary, not sufficient (A11Y-008, 009). |
| 44px controls plus responsive CSS proves mobile | `--tap-min`; 320px axe routes | Axe does not test overlap/reflow/reading order | **Investigate** | M | Manual 320/390 and 200% zoom remain required (A11Y-011). |
| `role="dialog"` is appropriate for Library card | It labels a rich popup | Nonmodal anchored popup may not trap focus; dialog semantics imply modality | **Change/clarify** | S | Use menu/popover semantics or the shared modal contract (A11Y-007). |
| Keyboard shortcuts are inclusive by default | j/k/x reduce effort and ignore text fields | Discovery and conflict with AT browse keys are untested | **Keep optional** | S | Default availability is fine if documented and never required (A11Y-004). |
| Axe green means AA | Broad mocked route matrix | No live run/manual SR; automation misses cognition and workflows | **Reject** | — | AA confidence remains Suspected (A11Y-008). |
| Text-size preference solves low vision | Immediate control; rem-based system | User must discover it; 10–11px literals remain | **Keep + raise floor** | S | Preference supplements, not replaces, readable defaults (A11Y-009). |

## 4. If we built it today

One app shell would own skip link, top navigation, exactly one `<main>`, route-title announcement, and focus restoration. Every overlay would be either a nonmodal popover with menu/list semantics or a modal Dialog built on `useModal`; no hybrid `role="dialog"` popovers. Search would retain the current ARIA combobox implementation.

Sorting would be a labelled two-region workspace: a grouped `listbox` or ordinary list of slip buttons/links, and one active inspector region whose heading names the selected slip. The row would announce “3 of 22, The Heist, Path is not clear, recommended Apply.” Selection would move the inspector heading into the virtual cursor order without unexpectedly stealing keyboard focus. Filter changes would announce reason and result count. Destructive group actions would open a focus-trapped dialog naming scope and count.

The gap is moderate and worth closing. The shell, focus trap, controls, copy, and tests already exist. The work is reducing repeated DOM, clarifying state semantics, extending assertions, and completing manual AT/reflow verification—not rebuilding the frontend.

## 5. Findings by surface

**Public.** Login, join, and reset use real main landmarks and labelled fields; mocked axe includes token/no-token and 320px join. Live unauthenticated screen-reader narration and error recovery were not tested. **Grade B+.** IDs: A11Y-001, A11Y-008, A11Y-012.

**Consumer.** Hall/Search have the strongest semantics: skip link, landmarks, keyboard shortcut, combobox/listbox, kind controls, dialogs, and work route tests. Suggestion label quality and full reader media/caption behavior remain unreviewed. **Grade B+.** IDs: A11Y-001, A11Y-002, A11Y-006, A11Y-009, A11Y-010.

**Owner.** Sorting’s individual controls are named and grouped, but scale makes sequential navigation unreasonable. Quiet-hours and bulk controls extend the focus order before slips. This is the priority surface. **Grade C+.** IDs: A11Y-003, A11Y-004, A11Y-005, A11Y-007, A11Y-011.

**Admin.** Settings/People/Maintain share the shell and dialogs; mocked axe covers Settings, Library card, invite, purge, and password. Dense tables, live Maintain hydration, and role-specific navigation were not manually inspected. **Grade B.** IDs: A11Y-007, A11Y-008, A11Y-011, A11Y-012.

## 6. Findings by theme

**Keyboard/focus.** Best: skip link, 3px global focus ring, `/`, Escape, j/k/x, and modal focus trap. Worst: enormous Sorting focus order and unproven ProfileMenu dialog behavior. Direction: one active inspector and a single overlay contract (A11Y-001, 004, 005, 007, 010).

**Semantics/landmarks.** Best: shell-owned main and labelled Sorting groups. Worst: filter selection is visual but not programmatic; repeated “About X” controls dominate spoken navigation. Direction: `aria-pressed`, concise names, list position, and region labelling (A11Y-003, 005).

**Forms/status.** Best: visible labels, FieldHelp, `aria-busy`, role=status, progress labels, Undo. Worst: repeated forms and unclear linkage between filter changes and results. Direction: one form, persistent draft status, polite count announcement (A11Y-003, 005).

**Contrast/color.** Declared pairs pass strongly; color-only status usage was not fully audited live. Direction: automated token test plus live axe/manual checks in both themes; text/icon/status redundancy (A11Y-008, 009).

**Motion/reflow.** Reduced-motion code and 320px axe tests exist. Zoom, text spacing, actual overlap, and long paths remain unproven. Direction: authored 320/390/768 + 200% + text-spacing checks (A11Y-011).

**Cognitive/plain language.** “Sorting,” “slip,” and four-word reasons are strong when explained. Filename-like Search labels and dozens of repeated controls raise memory load. Direction: plain title/author/kind labels and progressive disclosure (A11Y-005, 006).

**Preventive.** Axe coverage is broad and should be protected. Add semantic/focus assertions and live/manual release gates rather than claiming automation proves AA (A11Y-008, 012).

## 7. Stop doing

- Stop mounting every slip’s complete editor in one document (A11Y-005).
- Stop expressing filter selection only through `.is-on` (A11Y-003).
- Stop declaring popup content a dialog without choosing modal or nonmodal behavior (A11Y-007).
- Stop treating mocked axe as a live WCAG certification (A11Y-008).
- Stop relying on color or lamp/weather metaphors without text and icon/state names (A11Y-006).
- Stop using text-size preference as justification for sub-12px meaningful copy (A11Y-009).

## 8. Strengths worth protecting

- First-focus skip link and shell-owned main (A11Y-001).
- Search combobox/listbox keyboard contract (A11Y-002).
- Visible, high-contrast focus ring in both themes (A11Y-009).
- Shared modal focus trap with restoration (A11Y-010).
- Reduced-motion support, text-size preference, and 44px target token (A11Y-009, A11Y-011).
- Two-theme mocked axe matrix and semantic locators (A11Y-012).
- Sorting’s headings, status messages, busy states, Undo, and explanatory copy (A11Y-004, A11Y-005).

## 9. Risks of inaction

As Sorting grows, blind and keyboard-only owners will abandon triage because reaching the tenth slip requires navigating hundreds of controls. A visual filter can report one group while assistive technology has no programmatic selected state. Hybrid popovers may strand or leak focus as more controls are added. A green mocked axe suite may create false confidence while live data, animations, long paths, and manual workflows remain untested. Low-vision users will rely on an undiscoverable text-size slider to compensate for defaults. These are exclusion risks in the same household, not abstract compliance issues.

## 10. Recommended direction

**Now:** add `aria-pressed` and polite filter counts; document optional shortcuts; audit ProfileMenu semantics; add token contrast tests; complete live axe in both themes without changing the **Suspected** confidence until it runs. **Next:** ship one-active-slip/master-detail Sorting with stable heading/list semantics; add focus and overlay restoration tests; perform 320/390/200%/text-spacing QA. **Later:** manual VoiceOver and NVDA scripted journeys for Foyer → Hall → Search → Work and owner Desk → Sorting → Apply/Skip.

Ninety-day success: fewer than 100 initial focusable nodes on 27-slip Sorting; every filter exposes state and announces count; every overlay has tested focus entry/Escape/return; zero serious/critical axe violations on the mocked matrix and live sampled routes; all four scripted journeys complete with VoiceOver; no two-axis page scrolling at 320px or 200% zoom.

## 11. Scorecard

| Surface | Keyboard | Screen reader | Forms/status | Contrast | Reflow | Cognitive | Overall |
|---|---:|---:|---:|---:|---:|---:|---:|
| Public | 4 | 4 | 4 | 4 | 3 | 4 | **3.8** |
| Consumer | 4 | 4 | 4 | 4 | 3 | 3 | **3.7** |
| Owner | 2 | 2 | 4 | 4 | 2 | 2 | **2.7** |
| Admin | 3 | 3 | 4 | 4 | 3 | 3 | **3.3** |

Scores are evidence-weighted; no surface receives 5 without manual AT and live reflow proof.

## Expected screen-reader narration

**Search today:** “Search, combobox, collapsed.” After typing: “Search, combobox, expanded, Born In Fire shelf, option 1 of …” The control mechanics are correct; proposed label is “Born In Fire, [author], Book, on shelf” (A11Y-002, A11Y-006).

**Sorting today:** “Sorting, heading level 1. 27 slips, status. Filter by reason, group. All 27, button. Low confidence 22, button…” then Quiet hours and bulk controls, followed by hundreds of repeated controls. Proposed: “Low confidence, pressed, 22 slips” and “Low confidence slips, list, 22 items. Fortunate Son, item 1 of 22, Path is not clear, recommended Request new version” (A11Y-003, A11Y-005).

# Part B — Detailed findings

## 12. Scope & method

The live pass used accessibility snapshots, not screenshots: Hall/Search and a full Sorting snapshot (1,021 refs; 633 interactive). Code review covered shell, typeahead, Sorting, slips, overlays, tokens, and axe specs. Contrast ratios were calculated from token values, not every computed usage. Not done: live axe on Automat, VoiceOver/NVDA, keyboard execution of all actions, 200% zoom, WCAG text-spacing override, captions/readers, low-bandwidth throttling, reader/op role sessions. A11Y-008 therefore remains **Suspected**.

## 13. Strengths

### A11Y-001: Protect the skip-link and single-main shell contract

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | Keyboard-only, screen-reader user |
| Category | Bypass blocks / landmarks |
| Severity | High |
| Impact | 5 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 15.0 |
| Verdict | Protect |
| Dependencies | none |
| Labels | wcag-2.4.1, wcag-1.3.1, shell |

**Evidence:** `frontend/src/components/AppChrome.jsx:76-78,133-135`; `frontend/src/styles/tokens.css:227-253`; live Sorting snapshot begins “Skip to content.”

**Current state:** First Tab can bypass chrome to a focusable main. **Root cause:** the shell, not each page, owns the contract.

**Recommendation:** Keep exactly one `#main` per route and the skip link before navigation. Add an e2e assertion that activation moves focus to main.

**Rationale:** Page-owned landmarks were rejected because they drift to zero/two. Protect now as owner layouts are reworked.

**User story:** As a keyboard user, I want to skip repeated navigation on every route.

**Acceptance criteria:**
- [ ] First Tab exposes “Skip to content.”
- [ ] Activation focuses exactly one main.
- [ ] No nested page main is introduced.

**Success metric:** two key presses or fewer from load to main.

**Validation:** semantic Playwright assertion on public/consumer/owner routes.

### A11Y-002: Protect the Search combobox keyboard contract

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Consumer |
| Persona(s) | Screen-reader, keyboard-only reader |
| Category | Name/role/value; keyboard |
| Severity | High |
| Impact | 5 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 7.5 |
| Verdict | Protect |
| Dependencies | A11Y-006 |
| Labels | wcag-4.1.2, combobox, search |

**Evidence:** `frontend/src/components/TypeaheadField.jsx:80-157` uses combobox/listbox/options, `aria-expanded`, controls, active descendant, selected state, arrows, Escape, Enter.

**Current state:** The custom typeahead follows the standard interaction. **Root cause:** semantics and keyboard behavior were implemented together.

**Recommendation:** Preserve behavior and add spoken-label quality under A11Y-006; announce loading only if latency is perceptible.

**Rationale:** A native datalist was rejected because it cannot express rich metadata consistently; a visual-only popup was rejected as inaccessible. Protect during label refactor.

**User story:** As a screen-reader user, I want to review and select suggestions without leaving the field.

**Acceptance criteria:**
- [ ] Active descendant tracks the highlighted option.
- [ ] Escape closes without clearing typed value.
- [ ] Enter selects active option or submits when closed.

**Success metric:** manual SR user selects a known title without pointer help.

**Validation:** component tests plus VoiceOver/NVDA.

### A11Y-009: Protect theme, text-size, focus, and reduced-motion foundations

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | Low-vision, older, motion-sensitive user |
| Category | Perceivable/personalization |
| Severity | High |
| Impact | 5 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 7.5 |
| Verdict | Protect |
| Dependencies | A11Y-008 |
| Labels | wcag-1.4.3, wcag-2.4.7, motion |

**Evidence:** `tokens.css:4-35,99-163` theme pairs; `:227-253` focus; `ProfileMenu.jsx:110-149` radio theme and labelled text-size range; reduced-motion blocks include `motion.css:420`.

**Current state:** Users can change theme and enlarge rem-based UI; focus is visible. **Root cause:** accessibility preferences are first-class user settings.

**Recommendation:** Keep controls immediate; add token contrast tests and central reduced-motion duration aliases. Raise meaningful text floor rather than relying on enlargement.

**Rationale:** Browser-only zoom was rejected as the sole answer; app preferences help household users but do not waive readable defaults. Protect now during token consolidation.

**User story:** As a low-vision reader, I want readable focus and scalable text in either theme.

**Acceptance criteria:**
- [ ] Focus indicator maintains ≥3:1 adjacent contrast.
- [ ] Text size persists and reflows.
- [ ] Reduced motion removes loops/transforms without hiding status.

**Success metric:** zero token contrast regressions and all core tasks at 200% zoom.

**Validation:** token test, zoom/text-spacing checks, reduced-motion capture.

### A11Y-010: Protect the shared modal focus lifecycle

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | Keyboard-only, screen-reader user |
| Category | Focus management |
| Severity | High |
| Impact | 5 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 7.5 |
| Verdict | Protect |
| Dependencies | A11Y-007 |
| Labels | wcag-2.4.3, wcag-2.1.2, dialogs |

**Evidence:** `frontend/src/hooks/useModal.js:25-87` records opener, focuses heading/control, traps Tab, handles Escape, restores focus; `e2e/axe.spec.ts:239-354` opens multiple overlays.

**Current state:** A reusable correct focus lifecycle exists. **Root cause:** overlay behavior was centralized.

**Recommendation:** Every modal dialog uses the hook; add a source/test guard and focus restoration assertions.

**Rationale:** Per-dialog key handlers were rejected because they drift. Protect now while ProfileMenu semantics are clarified.

**User story:** As a keyboard user, I want focus contained in a modal and returned to its opener.

**Acceptance criteria:**
- [ ] Modal focus enters a named heading/control.
- [ ] Tab cycles; Escape closes; opener regains focus.
- [ ] No focusable content remains under `aria-hidden`.

**Success metric:** 100% overlay focus contract coverage.

**Validation:** keyboard e2e for every overlay family.

## 14. Weaknesses

### A11Y-005: Reduce Sorting’s accessibility-tree and focus-order load

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Screen-reader, keyboard-only, cognitive-load user |
| Category | Operability / cognitive |
| Severity | High |
| Impact | 5 |
| Effort | L |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | A11Y-003, A11Y-004 |
| Labels | sorting, focus-order, wcag-2.4.3 |

**Evidence:** Live `/review`: 1,021 refs/633 interactive for 27 slips. `HoldSlipCard.jsx:57-445` can render repeated explanation, actions, seven fields, Apply/Skip per slip.

**Current state:** Every control has local meaning, but reaching later slips is exhausting. **Root cause:** each row owns a full editor and help/actions.

**Recommendation:** Render grouped rows plus one active inspector; announce selection and list position. If virtualizing, retain group heading/count and expose total/position. Do not move focus on every arrow selection unless in an explicit composite widget.

**Rationale:** Pagination was rejected because it fragments batches; CSS hiding was rejected because hidden/mounted semantics can remain; blind virtualization was rejected because it can destroy SR context. Fix now before backlog growth.

**User story:** As a screen-reader owner, I want to choose a slip from a concise list and edit it in one predictable region.

**Acceptance criteria:**
- [ ] Fewer than 100 initial focusable nodes for 27 slips.
- [ ] Exactly one inspector form is mounted.
- [ ] Row name includes title, reason, recommendation, and position.
- [ ] Group/filter context remains announced.

**Success metric:** SR user reaches and edits slip 20 in under one minute.

**Validation:** tree count, keyboard path, VoiceOver/NVDA scripted test.

### A11Y-003: Expose Sorting filter selection programmatically

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Screen-reader user |
| Category | Name/role/value |
| Severity | Medium |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 8.0 |
| Verdict | Fix |
| Dependencies | none |
| Labels | wcag-4.1.2, filters, quick-win |

**Evidence:** `ReviewPage.jsx:819-838` uses buttons and `.is-on` but no `aria-pressed`; live snapshot lists “All 27” and reason buttons without pressed state.

**Current state:** Selection is visible only. **Root cause:** chips were styled as buttons without toggle semantics.

**Recommendation:** Set `aria-pressed` on every reason filter and include normalized label/count. Keep the group label “Filter by reason.”

**Rationale:** Tabs were rejected because filters do not switch panels; radio was rejected because button toggle semantics already fit and allow All. Fix now because it is XS and affects every SR Sorting visit.

**User story:** As a screen-reader owner, I want to hear which reason filter is active.

**Acceptance criteria:**
- [ ] Exactly one filter is pressed.
- [ ] All is pressed when no reason is selected.
- [ ] Accessible names contain human labels and counts.

**Success metric:** axe/manual state audit reports no ambiguous selected filter.

**Validation:** Testing Library and live snapshot.

### A11Y-004: Announce filter, shortcut, progress, and undo changes consistently

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Screen-reader, keyboard-only user |
| Category | Status messages |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Likely |
| Priority score | 2.4 |
| Verdict | Fix |
| Dependencies | A11Y-003 |
| Labels | wcag-4.1.3, sorting, shortcuts |

**Evidence:** `ReviewPage.jsx:813-818` count has `role="status"`; `:852-875` Undo status; `:949-1010` labelled progress. Filter fetch timing and j/k selection announcements were not manually heard.

**Current state:** Status infrastructure exists, but the result of filter/keyboard navigation may not be concise or deterministic. **Root cause:** messages were added per feature.

**Recommendation:** One polite desk announcer emits “Low confidence, 22 slips,” “Selected 2 of 22, Title,” and action completion. Never announce every progress poll.

**Rationale:** Multiple live regions were rejected because they compete; assertive announcements were rejected except destructive failure. Fix next to filter semantics.

**User story:** As a screen-reader owner, I want concise confirmation when the desk changes.

**Acceptance criteria:**
- [ ] Filter and selected-row changes announce once.
- [ ] Polling announces meaningful phase/terminal changes only.
- [ ] Undo availability and completion are announced.

**Success metric:** no duplicate announcement in a scripted SR recording.

**Validation:** fake-timer component tests and manual SR.

### A11Y-007: Resolve the Library card’s dialog/popover semantics

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Keyboard-only, screen-reader user |
| Category | ARIA/focus |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Likely |
| Priority score | 2.4 |
| Verdict | Fix |
| Dependencies | A11Y-010 |
| Labels | dialog, popover, wcag-4.1.2 |

**Evidence:** `ProfileMenu.jsx:79-103` trigger uses `aria-haspopup="dialog"` and panel `role="dialog"`; it relies on `useAnchoredPopover`, not the reviewed `useModal`.

**Current state:** Escape/outside dismissal likely works; modality, focus containment, and initial/return focus were not proven. **Root cause:** a rich anchored card was labelled as a dialog without adopting the dialog lifecycle.

**Recommendation:** Prefer nonmodal `popover`/region with heading and natural Tab order if background remains operable; otherwise use `useModal`, `aria-modal`, focus trap, and restoration. Do not keep hybrid semantics.

**Rationale:** `menu` was rejected because sliders/radio theme controls are not menuitems. Fix now as the panel accumulates settings.

**User story:** As a keyboard user, I want Library card focus behavior to match what assistive technology announces.

**Acceptance criteria:**
- [ ] Chosen role matches modal behavior.
- [ ] Escape closes and trigger regains focus.
- [ ] Focus order reaches every control once.

**Success metric:** no focus escape/stranding in keyboard test.

**Validation:** role-specific e2e plus VoiceOver.

### A11Y-006: Remove color-only and filename-like cognitive signals

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer, Owner |
| Persona(s) | Color-vision, screen-reader, non-native-language user |
| Category | Use of color / cognitive |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Likely |
| Priority score | 1.6 |
| Verdict | Fix |
| Dependencies | A11Y-002 |
| Labels | wcag-1.4.1, plain-language, search |

**Evidence:** Live typeahead included filename-like labels; `TypeaheadField.jsx:152-155` only adds generic “shelf.” Platform map notes lamp/weather/job metaphors; complete color-only audit was not performed.

**Current state:** Most statuses have words, but label quality and all icon/color redundancies are not proven. **Root cause:** storage/provider strings and visual metaphor can leak into user-facing names.

**Recommendation:** Search options announce Title, Author, Kind, Owned. Every status uses text plus optional icon/color; lamp/weather never carries state alone.

**Rationale:** Tooltips were rejected because they do not help touch/SR users; removing color was rejected because redundancy is preferable. Fix during typeahead and token work.

**User story:** As a color-blind reader, I want every state named in text.

**Acceptance criteria:**
- [ ] No state relies only on hue.
- [ ] Typeahead names are canonical and deduplicated.
- [ ] Icons have names or are hidden when text duplicates them.

**Success metric:** manual monochrome audit preserves all meanings.

**Validation:** monochrome screenshot/manual audit and accessible-name tests.

### A11Y-008: Complete live axe and manual AA verification

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | All disabled users |
| Category | Verification |
| Severity | High |
| Impact | 5 |
| Effort | M |
| Confidence | **Suspected** |
| Priority score | 2.5 |
| Verdict | Fix |
| Dependencies | A11Y-005, A11Y-007 |
| Labels | live-axe, manual-at, wcag-aa, suspected |

**Evidence:** No live axe/VoiceOver/NVDA run completed in this pass. `e2e/axe.spec.ts:120-369` proves mocked coverage, not live Automat data or manual task success.

**Current state:** CI prevention exists; production confidence is incomplete. **Root cause:** live browser capture/tool timeouts and absence of manual AT execution.

**Recommendation:** Run axe read-only on Login, Hall, Search, Work, Sorting, Settings, Card in both themes; then execute four manual keyboard/SR journeys and 200% zoom/text-spacing. Keep AA confidence Suspected until recorded.

**Rationale:** Lighthouse-only was rejected as shallower than existing axe; automation-only was rejected because it misses focus order, cognition, and announcements. Do now before claiming conformance.

**User story:** As a disabled household member, I want accessibility claims proven on the same live-scale app I use.

**Acceptance criteria:**
- [ ] Live axe results recorded by route/theme.
- [ ] Serious/critical violations are zero or ticketed with owner/date.
- [ ] VoiceOver and NVDA scripts record task completion and barriers.
- [ ] 320px/200%/text-spacing results recorded.

**Success metric:** evidence-backed AA statement replaces Suspected.

**Validation:** stored run artifacts and finding updates.

### A11Y-011: Prove reflow, target size, loading, and long-content behavior

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Low-vision, mobile, motor user |
| Category | Reflow / target size |
| Severity | Medium |
| Impact | 4 |
| Effort | M |
| Confidence | Suspected |
| Priority score | 1.3 |
| Verdict | Fix |
| Dependencies | A11Y-008 |
| Labels | wcag-1.4.10, wcag-2.5.8, reflow |

**Evidence:** `tokens.css:96` defines 44px target; `e2e/axe.spec.ts:155-160,355-369` visits 320px. Maintain initially produced an empty snapshot during recon before hydration; long live paths exist in Sorting.

**Current state:** code intent is strong; visual reflow/loading focus order is not proven. **Root cause:** axe is asked to stand in for layout and zoom testing.

**Recommendation:** Test 320px, 390px, 768px, 200% zoom, WCAG text spacing, long titles/paths, loading-to-content focus stability, and sticky controls.

**Rationale:** Screenshot-only checks were rejected because focus/order matter; unit CSS checks were rejected because they cannot detect overlap. Do next to the Sorting redesign.

**User story:** As a low-vision owner, I want enlarged Sorting to remain one-dimensional and operable.

**Acceptance criteria:**
- [ ] No two-axis page scrolling at 320px/200%.
- [ ] Targets meet 24px minimum and primary controls target 44px.
- [ ] Hydration does not drop focused content.
- [ ] Long paths wrap without obscuring controls.

**Success metric:** all authored layout tasks pass at five display conditions.

**Validation:** Playwright geometry plus manual zoom.

## 15. Opportunities

### A11Y-012: Extend the existing axe matrix with semantic contracts

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Cross-cutting |
| Persona(s) | All assistive-technology users |
| Category | Prevention |
| Severity | High |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 4.0 |
| Verdict | Add |
| Dependencies | A11Y-003, A11Y-005, A11Y-007 |
| Labels | axe, playwright, ci |

**Evidence:** `e2e/axe.spec.ts:120-369` covers public and owner routes, both themes, overlays, and 320px; `assertAxe` currently expects zero violations (`:43-52`).

**Current state:** Broad automated baseline exists. **Root cause of gap:** axe cannot assert focus restoration, filter state, focusable-node budget, or master-detail narration.

**Recommendation:** Keep axe and add assertions for exactly one main, skip activation, pressed filters, overlay focus return, initial Sorting focusables <100, and no horizontal overflow.

**Rationale:** Replacing axe was rejected; it is valuable. Add behavioral contracts now so the upcoming redesign cannot be “axe green, unusable.”

**User story:** As a maintainer, I want CI to catch semantic regressions before a household member does.

**Acceptance criteria:**
- [ ] Both themes retain zero axe violations in existing routes.
- [ ] Semantic/focus/layout contracts run in Playwright.
- [ ] Sorting fixture includes grouped, busy, error, and destructive-dialog states.

**Success metric:** zero escaped core-chrome accessibility regressions for a quarter.

**Validation:** deliberate regression proves each assertion fails.

## 16. Remediation plan

| Horizon | ID | Title | Effort | Owner | Dependencies |
|---|---|---|---|---|---|
| Now | A11Y-003 | Pressed state for reason filters | XS | Frontend | none |
| Now | A11Y-004 | Unified desk announcements | S | Frontend | A11Y-003 |
| Now | A11Y-007 | Resolve Library card semantics | S | Frontend | A11Y-010 |
| Now | A11Y-008 | Live axe/manual verification | M | QA + a11y | current build |
| Next | A11Y-005 | One active Sorting inspector | L | Product + frontend | A11Y-003/004 |
| Next | A11Y-011 | Reflow/zoom/target proof | M | QA | A11Y-008 |
| Next | A11Y-012 | Semantic CI contracts | M | Frontend QA | A11Y-003/005/007 |
| Later | A11Y-006 | Full non-color/plain-language audit | M | Content + design | typeahead work |

Quick semantic fixes and verification precede the structural Sorting change. CI contracts land with the redesign so they capture the intended behavior, not the old 633-control document.

## 17. Quick wins

- Add `aria-pressed` to Sorting reason filters (A11Y-003).
- Add one polite filter/count announcement (A11Y-004).
- Assert skip-link focus and exactly one main (A11Y-001, A11Y-012).
- Decide ProfileMenu modal vs nonmodal semantics (A11Y-007).
- Add token contrast calculations to unit tests (A11Y-009).

## 18. Open questions

- Should Sorting rows be ordinary links/buttons plus an inspector, or a composite listbox? Prefer ordinary controls unless arrow-key behavior is deliberately specified.
- Does the op role have a different focus order or hidden controls than owner?
- Do EPUB/PDF/CBZ readers expose headings, page progress, and caption/alt equivalents? Not reviewed.
- Which live routes can be safely axe-scanned without triggering actions? The listed routes are read-only.
- Who owns the manual VoiceOver/NVDA release gate and evidence retention?

## Phase 6 self-check

- [x] Full Part A, all surfaces/themes, scorecard, narration, stop/protect/risks/direction.
- [x] IDs A11Y-001 through A11Y-012 preserved and unique.
- [x] A11Y-008 AA confidence remains **Suspected** pending live axe/manual AT.
- [x] Every finding has full format, evidence, alternatives, why now, criteria, metric, validation.
- [x] Existing axe coverage is accurately described; automation limits are explicit.
- [x] No unsupported screenshot claim and no application code or sibling review file modified.
