# 03 · Design Director — Librarian — run 2026-11-04

**Reviewed:** Automat `http://10.10.1.202:8793` · image **1.0.10 / 480eff0** · owner session · Lights Down
**Evidence base:** live Hall/Search/Sorting accessibility snapshots; `frontend/src/styles/tokens.css`, `chrome.css`, `owner.css`, `stacks.css`, `work.css`, `reader.css`; chrome and Sorting components; [platform map](00_2026-11-04_platform-map.md).
**Companion files:** [platform map](00_2026-11-04_platform-map.md) · [run status and handoff](_status.md)
**Constraint:** screenshot capture timed out, so composition judgments use live structure and code, not invented pixel measurements. **Grade: B+.**

# Part A — Conclusions & findings

## 1. Bottom line

Librarian has a real visual identity: Literata display type, Source Sans 3 UI type, warm paper by day, lamp/brass/leather by night, and covers treated as media rather than generic SaaS cards. Its token architecture is substantially healthier than the thin draft implied—two themes, semantic aliases, type/space/radius scales, tap and layout contracts, focus treatment, and self-hosted fonts are all centralized in `tokens.css` (VIS-001, VIS-002). The single most important fix is to finish the system beyond its core tokens: owner pages still combine chips, settings, bulk actions, progress, and repeated forms with weak elevation/state hierarchy, while raw sizes, shadows, and z-index values remain scattered (VIS-003, VIS-006). The most important thing to protect is the Lights Down reading-room soul and the disciplined separation of paper, ink, gilt, accent fill, and accent text (VIS-001, VIS-002). Grade **B+**: distinctive and coherent at the reader layer, one component/consolidation pass short of feeling equally deliberate at owner scale.

## 2. Key conclusions

1. **The identity is mature enough to protect, not redesign.** `tokens.css:46-58` defines Literata, Source Sans 3, IBM Plex Mono, and a compact type ramp; `:99-129` defines the night-library palette. Hall’s search/rails and work hero use that editorial vocabulary. A neutral component-library reskin would reduce differentiation without solving the real issue—owner hierarchy (VIS-001, VIS-002).

2. **The token system is broad but incomplete.** Color, typography, spacing, radius, motion shorthand, tap size, peek, rails, hero search, top bar, and reading width are tokens (`tokens.css:46-96`). Elevation, z-index, semantic warning/info, motion tiers, and breakpoints are not. The styles sampled contain hand-written shadows and z values from 1 to 1000, plus 390/640/720 breakpoints. Finish aliases before adding more surfaces (VIS-006).

3. **Lights Up and Lights Down are one product, not a default plus novelty mode.** The same semantic names switch at `tokens.css:99-163`, and the focus/ink contracts survive both. The night theme uses gilt as both material and readable text; the day theme intentionally uses darker `--gilt-text`. Preserve both, but formalize contrast tests for semantic pairs (VIS-001, VIS-002).

4. **Owner density is functional but visually undifferentiated.** The live Sorting tree begins with five reason chips, shortcuts, Quiet hours, Purge, model checks, group actions, then repeated slip controls. Code places those layers sequentially (`ReviewPage.jsx:810-1054`). The problem is not “too much information”; it is that filters, configuration, destructive tools, progress, and record editing share similar visual weight (VIS-003).

5. **Typography carries the brand at display scale and becomes too small at utility scale.** Base is 15px, `--text-xs` is 12px, and the global kicker is hard-coded to 11px with 0.16em tracking (`tokens.css:50-58,216-225`). Owner/stacks styles contain additional 10–13px literals. Keep the typefaces, raise the utility floor to 12px, and reserve 11px uppercase only for non-essential decorative eyebrows (VIS-004).

6. **The component system exists as conventions, not primitives.** `.cta`, `.chip`, `.card`, `.field`, `.seal`, dialog patterns, and progress blocks recur, but ownership is distributed across global partials and feature components. Sorting alone combines generic chips, group-motion chips, CTA variants, FieldHelp, ThinkingButton, and nested details. Consolidation should name the stable variants and their state matrix rather than importing a new framework (VIS-005).

7. **Motion intent is good; the implementation needs tiers.** A global `--motion: 200ms ease`, 280ms theme transition, and multiple reduced-motion blocks show awareness (`tokens.css:73,166-172`; `motion.css:420`). A single shorthand cannot distinguish hover, disclosure, sheet, and ambient effects. Introduce fast/base/slow and easing aliases, then map every animation to them (VIS-007).

8. **Incremental migration is credible because the architecture is already variable-driven.** Most proposed tokens can land as aliases with no visual change, followed by owner page and shared-control migrations. No big-bang redesign or CSS framework replacement is justified (VIS-008).

## 3. Foundations challenged

| Assumption | Evidence for | Evidence against | Verdict | Cost | Rationale |
|---|---|---|---|---|---|
| Reading-room, not generic admin, is the brand | Literata/Source Sans; paper/lamp/leather/gilt; cover-first rails | Owner pages can resemble a dense form console | **Keep** | — | Bring Desk into the room; do not make Hall look like admin (VIS-002, VIS-003). |
| Two named themes should remain | Full token swap; user preference; strong day/night contexts | Every pair doubles QA | **Keep** | S ongoing | The use contexts are real and the implementation is centralized. Add automated pair tests (VIS-001). |
| 15px base is sufficient because text size exists | User can enlarge; compact owner UI | 12px/11px utility text affects older users before they find the control | **Change** | S | Raise default to 16px or utility floor to 12px; preserve scaling (VIS-004). |
| Plain CSS partials scale | Low runtime cost; brand-specific art direction | Shared states and elevations remain implicit | **Keep CSS, add primitives** | M | Framework migration is cost without benefit; component contracts solve drift (VIS-005, VIS-006). |
| One accent can cover brand and status | Calm palette; less dashboard color | Danger/success exist; warning/info are absent | **Change semantics** | S | Add status roles without adding a second brand accent (VIS-006). |
| 44px minimum applies everywhere | `--tap-min:44px`; touch safety | Dense owner rows tempt smaller controls | **Keep/enforce** | S | Density should come from spacing and disclosure, not tiny targets. |
| Peek and rail dimensions are global contracts | Tokens provide exact dimensions | Some media kinds need distinct aspect ratios | **Keep** | — | Existing tokens already separate books, magazines, comics, audio (VIS-001). |
| “Admin” should use the same density as consumer | One product language | Sorting has 633 interactive refs and repeated forms | **Change density, keep materials** | M | Add a compact density scale for Desk only (VIS-003). |
| Global 200ms ease is enough | Coherent baseline | Ambient, hover, sheet, and theme need different timing | **Change** | S | Three tiers reduce one-offs and improve reduced-motion behavior (VIS-007). |

## 4. If we built it today

I would keep the exact art direction, plain CSS, and one-attribute theme architecture. I would begin with a complete token file: primitive neutral/material colors, semantic surface/text/action/status aliases, a 1.2 typography scale, a 4px spacing scale, four radii, four elevations, a documented z-index ladder, three motion tiers, and four breakpoints. Then I would build twelve shared components—Button, IconButton, Chip, Badge, Field, Select, Card, SlipRow, Dialog, Popover, Progress, EmptyState—with a design gallery rendered in both themes and compact/comfortable density.

Reader pages would remain spacious and editorial. Desk pages would use the same paper/leather/gilt materials but reduce vertical spacing one token step, use tabular figures, and reserve raised surfaces for the active task. The gap is moderate: variables, classes, and reusable React helpers already exist. Closing it is worth it because the owner backlog will grow; replacing CSS or redesigning Hall is not.

## 5. Findings by surface

**Public.** The foyer’s constrained glass-card width, 44px controls, warm contrast, and limited action hierarchy are appropriately calm. It earns attention without pretending this private tool has a marketing site. **Grade A-.** IDs: VIS-001, VIS-002, VIS-005.

**Consumer.** Hall, Search, rails, peek, and work hero carry the brand best. Covers have explicit aspect contracts, titles use Literata selectively, and reader chrome stays quiet. Utility labels and typeahead metadata occasionally drop too small; component states should be documented rather than inferred. **Grade A-.** IDs: VIS-001, VIS-002, VIS-004, VIS-005.

**Owner.** Sorting uses the same palette and type, but the sequence of chips, settings, dangerous actions, progress, grouped cards, and fields lacks a clear visual grammar. The desk should become compact, not cramped: one active raised inspector, low-elevation rows, one primary action per scope, destructive actions separated. **Grade B-.** IDs: VIS-003, VIS-004, VIS-005, VIS-006.

**Admin.** Settings, People, Maintain, Downloads, and Sorting are the admin surface. Their shared classes create family resemblance, but no specimen or state inventory prevents drift. **Grade B.** IDs: VIS-003, VIS-005, VIS-006, VIS-008.

## 6. Findings by theme

**Color.** Best: distinct material/semantic roles and fill/text split. Worst: missing warning/info and reliance on `color-mix()` without a documented semantic pair matrix. Direction: preserve palette; add roles and contrast tests (VIS-001, VIS-006).

**Typography.** Best: Literata display + Source Sans 3 body + IBM Plex Mono for paths. Worst: 10–11px literals and uppercase kickers. Direction: use the specimen below, minimum 12px informational text, tabular figures on all counts (VIS-004).

**Layout/composition.** Best: `--reading-column-max`, exact rail ratios, peek width, and hero search max. Worst: owner hierarchy is a sequence rather than a composition. Direction: Desk grid with toolbar, groups, and one inspector (VIS-003).

**Components.** Best: shared `ThinkingButton`, FieldHelp, useModal, chip/card/field conventions. Worst: state variants live in callers and partials. Direction: named primitives and one state table (VIS-005).

**Iconography.** The reviewed surface favors text labels and CSS material motifs, which avoids an inconsistent icon zoo. Protect explicit labels; if icons expand, use one 20px/1.75px-stroke set and never icon-only destructive actions.

**Motion.** Best: reduced-motion support and calm 200ms baseline. Worst: one token for unlike motions and a 280ms root theme transition. Direction: fast/base/slow plus reduced-motion aliases (VIS-007).

**Polish.** Live structural evidence shows no missing theme or broken hierarchy, but screenshot timeout prevents pixel-level alignment claims. The primary polish debt is systematic: utility type floor, elevation, action hierarchy, and compact density.

## 7. Stop doing

- Stop adding raw shadows, z-index values, durations, and breakpoint widths outside tokens (VIS-006, VIS-007).
- Stop using 10–11px for meaningful status or action labels (VIS-004).
- Stop making filters, configuration, primary actions, and destructive actions equally prominent (VIS-003).
- Stop introducing new chip/button/card families without mapping them to the target variants (VIS-005).
- Stop treating owner density as permission to violate 44px target size.
- Stop planning a visual “refresh”; finish the existing system instead (VIS-008).

## 8. Strengths worth protecting

- Paper/lamp/leather/gilt material language and both themes (VIS-001, VIS-002).
- Literata, Source Sans 3, IBM Plex Mono, self-hosted (VIS-002, VIS-004).
- Accent fill/text separation and 3px focus ring (VIS-001).
- Cover and media aspect contracts, peek width, reading column, and hero search dimensions (VIS-001).
- Cards as content containers rather than every section becoming a floating SaaS tile.
- Reduced-motion intent and calm transitions (VIS-007).

## 9. Risks of inaction

In 6–12 months, every new owner feature will add another local card/chip/toolbar variant and another arbitrary elevation. Lights Up/Down will still work, but visual QA will become a manual audit because semantic roles are undocumented. Sorting will look increasingly like a form generator rather than a reading-room desk. Small utility text will undermine the text-size preference by making “Default” inadequate. A later redesign will appear necessary even though the actual need is a finite token and primitive migration.

## 10. Recommended direction

**Now:** land complete tokens as aliases, enforce a 12px utility floor, add tabular numerals, separate destructive Desk actions, and publish component state contracts. **Next:** migrate Sorting, Downloads, and Settings to shared Button/Chip/Field/Card/Progress variants and one active-inspector composition. **Later:** add a design gallery, visual regression snapshots in both themes/densities, and lint gates for raw values.

Ninety-day targets: zero new raw colors/shadows/z values outside approved files; all Sorting/Downloads actions mapped to five button variants; all counts tabular; no meaningful text below 12px; both themes pass contrast checks; five key screens have stable before/after screenshots.

## 11. Scorecard

| Surface | Brand | Color | Type | Layout | Components | Motion | Overall |
|---|---:|---:|---:|---:|---:|---:|---:|
| Public | 5 | 5 | 4 | 4 | 4 | 4 | **4.3** |
| Consumer | 5 | 5 | 4 | 4 | 4 | 4 | **4.3** |
| Owner | 4 | 4 | 3 | 3 | 3 | 4 | **3.5** |
| Admin | 4 | 4 | 3 | 3 | 3 | 4 | **3.5** |

# Part B — System specification

## 12. Scope & method

Code-first audit of the central token file and the style partials governing chrome, Hall/stacks, work detail, reader, and owner surfaces; live structural review of Hall, Search, and Sorting. The live Sorting tree contained 1,021 refs/633 interactive refs. Not completed: screenshot capture, computed-style census of every declaration, live Lights Up walkthrough, 390px pixel inspection, email/OPDS rendering. Contrast ratios below are calculated from declared hex pairs using WCAG relative luminance; usage still requires live axe/manual verification.

## 12.1 Current token inventory

| Dimension | Current evidence | Assessment |
|---|---|---|
| Theme colors | 28+ semantic/material variables per theme (`tokens.css:4-35,99-163`) | Strong; add warning/info and disabled roles |
| Families | Literata, Source Sans 3, IBM Plex Mono (`:46-49`) | Protect |
| Type sizes | 0.75–1.75rem, 15px base (`:50-58`) | Coherent; utility floor issue |
| Spacing | 4, 8, 12, 16, 20, 24, 32, 48 (`:61-68`) | Strong 4px scale |
| Radius | 6, 8, 12 (`:70-72`) | Add round/pill alias |
| Motion | one `200ms ease` token; root 280ms (`:73,166-172`) | Incomplete |
| Layout | gutter, peek, rail ratios, hero, top bar, reading width, tap 44 (`:69,76-96`) | Excellent |
| Elevation | raw shadows in partials | Missing system |
| Z-index | raw 1–1000 values in sampled partials | Missing ladder |
| Breakpoints | repeated 390/640/720 widths | Missing named policy |

## 12.2 Proposed design tokens

| Group | Token | Value | Purpose |
|---|---|---:|---|
| Surface | `--color-canvas` | `var(--bg)` | page |
| Surface | `--color-panel` | `var(--surface)` | grouped content |
| Surface | `--color-raised` | `var(--surface-raised)` | active inspector/dialog |
| Text | `--color-text` | `var(--text)` | body/headings |
| Text | `--color-muted` | `var(--muted)` | secondary copy |
| Action | `--color-action` | `var(--accent)` | primary fill |
| Action | `--color-on-action` | `var(--accent-text)` | text on primary |
| Action | `--color-link` | `var(--gilt-text)` | inline link/secondary accent |
| Status | `--color-success` | `var(--success)` | successful state |
| Status | `--color-warning` | Up `#7a4b00`; Down `#e8b75a` | needs attention |
| Status | `--color-danger` | `var(--danger)` | destructive/error |
| Status | `--color-info` | Up `#315f68`; Down `#83bac2` | informational |
| Type | `--font-display/body/mono` | existing | family contracts |
| Type | `--type-0..7` | 0.75, .875, 1, 1.125, 1.25, 1.5, 2, 3rem | 1.2-ish scale |
| Leading | `--leading-tight/body-loose` | 1.2 / 1.5 / 1.7 | usage tiers |
| Space | `--space-0..8` | 0,4,8,12,16,20,24,32,48px | existing plus zero |
| Radius | `--radius-sm/md/lg/round` | 6/8/12/999px | named shape |
| Elevation | `--shadow-1` | `0 1px 2px rgb(0 0 0/.14)` | row/popover |
| Elevation | `--shadow-2` | `0 8px 24px rgb(0 0 0/.24)` | inspector/menu |
| Elevation | `--shadow-3` | `0 24px 64px rgb(0 0 0/.38)` | dialog |
| Motion | `--duration-fast/base/slow` | 120/200/320ms | hover/disclosure/sheet |
| Motion | `--ease-standard/emphasized` | `cubic-bezier(.2,0,0,1)` / `cubic-bezier(.2,0,0,1.2)` | predictable motion |
| Z | `--z-base/sticky/menu/sheet/modal/toast` | 0/10/100/200/300/400 | layering |
| Breakpoints | policy | 390/640/720/1024px | phone/large phone/nav/desktop |
| Density | `--control-h` | 44px comfortable; 40px compact desktop only | controls |

### Contrast pairs

| Pair | Lights Up | Lights Down | WCAG target | Verdict |
|---|---:|---:|---:|---|
| text / bg | ~15.3:1 | ~16.4:1 | 4.5 | AAA |
| muted / bg | ~9.1:1 | ~8.1:1 | 4.5 | AAA |
| gilt-text / bg | ~5.3:1 | ~10.2:1 | 4.5 | AA+ |
| accent-text / accent | ~7.4:1 | ~7.0:1 | 4.5 | AA+ |
| focus-ring / bg | ~6.5:1 | ~9.4:1 | 3.0 UI | Pass |
| success / bg | ~5.7:1 | ~6.8:1 | 4.5 | AA |

Ratios are approximate from declared values and must be encoded in a token test. `--border` is decorative; interactive boundaries use `--control-border` and must remain ≥3:1.

### Ready-to-paste CSS proposal

```css
:root {
  --color-canvas: var(--bg);
  --color-panel: var(--surface);
  --color-panel-muted: var(--surface-2);
  --color-raised: var(--surface-raised);
  --color-text: var(--text);
  --color-muted: var(--muted);
  --color-action: var(--accent);
  --color-on-action: var(--accent-text);
  --color-link: var(--gilt-text);
  --color-success: var(--success);
  --color-warning: #7a4b00;
  --color-danger: var(--danger);
  --color-info: #315f68;

  --type-0: 0.75rem;
  --type-1: 0.875rem;
  --type-2: 1rem;
  --type-3: 1.125rem;
  --type-4: 1.25rem;
  --type-5: 1.5rem;
  --type-6: 2rem;
  --type-7: 3rem;
  --leading-tight: 1.2;
  --leading-body: 1.5;
  --leading-loose: 1.7;

  --space-0: 0;
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-round: 999px;
  --shadow-1: 0 1px 2px rgb(0 0 0 / 0.14);
  --shadow-2: 0 8px 24px rgb(0 0 0 / 0.24);
  --shadow-3: 0 24px 64px rgb(0 0 0 / 0.38);

  --duration-fast: 120ms;
  --duration-base: 200ms;
  --duration-slow: 320ms;
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);
  --ease-emphasized: cubic-bezier(0.2, 0, 0, 1.2);
  --motion-fast: var(--duration-fast) var(--ease-standard);
  --motion-base: var(--duration-base) var(--ease-standard);
  --motion-slow: var(--duration-slow) var(--ease-emphasized);

  --z-base: 0;
  --z-sticky: 10;
  --z-menu: 100;
  --z-sheet: 200;
  --z-modal: 300;
  --z-toast: 400;
  --control-h: var(--tap-min);
}

[data-theme="lights-down"] {
  --color-warning: #e8b75a;
  --color-info: #83bac2;
}

[data-density="compact"] {
  --space-control-y: var(--space-2);
  --space-section: var(--space-4);
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --duration-fast: 0ms;
    --duration-base: 0ms;
    --duration-slow: 0ms;
  }
}
```

CSS custom properties cannot hold media-query conditions portably; keep 390/640/720/1024 as a documented breakpoint policy or adopt `@custom-media` only with build-tool support.

## 12.3 Typography specimen

| Level | Family | Size | Weight | Line height | Tracking | Usage |
|---|---|---:|---:|---:|---:|---|
| Display | Literata | clamp(2.5rem,7vw,5.25rem) | 600 | 1.05 | -0.03em | work hero only |
| H1 | Literata | clamp(2rem,5vw,3rem) | 600 | 1.12 | -0.025em | page title |
| H2 | Literata | 2rem | 600 | 1.18 | -0.02em | major section/rail group |
| H3 | Literata | 1.5rem | 600 | 1.25 | -0.01em | card/group title |
| H4 | Source Sans 3 | 1.25rem | 650 | 1.3 | 0 | subsection |
| H5 | Source Sans 3 | 1.125rem | 650 | 1.35 | 0 | dense panel |
| H6 | Source Sans 3 | 1rem | 700 | 1.4 | 0.01em | local heading |
| Body | Source Sans 3 | 1rem | 400 | 1.55 | 0 | prose/UI |
| Body small | Source Sans 3 | .875rem | 400 | 1.45 | 0 | secondary UI |
| Caption | Source Sans 3 | .75rem | 500 | 1.4 | .01em | non-essential metadata |
| Label | Source Sans 3 | .875rem | 650 | 1.2 | .01em | fields/buttons/chips |
| Kicker | Source Sans 3 | .75rem | 700 | 1.2 | .12em | decorative eyebrow only |
| Code/path | IBM Plex Mono | .8125rem | 400 | 1.5 | 0 | paths/IDs |
| Count/data | Source Sans 3 | .875–1rem | 650 | 1.2 | 0 | `tabular-nums` |

Rules: no meaningful text below 12px; Literata only at 18px+; line length 45–75 characters; all desk counts use tabular figures; uppercase is never used for sentences or error copy.

## 12.4 Component consolidation

| Current patterns | Target component | Target variants/states |
|---|---|---|
| `.cta`, ghost, outline, compact, recommended classes | `Button` | primary, secondary, quiet, danger, link; default/hover/focus/pressed/disabled/loading |
| icon-ish close/help/menu buttons | `IconButton` | neutral/danger; always named; 44px target |
| `.chip`, `.is-on`, group motion, theme chips | `Chip` | filter (`aria-pressed`), status, removable |
| inbox/sorting/count seals | `Badge` | neutral, attention, danger; tabular |
| `.field`, FieldLabel, FieldHelp, PasswordField | `Field` | text/select/time/range; help/error/disabled |
| `.card`, ticket, hold-slip | `Card` + `SlipRow` | flat/grouped/raised; active/busy/error |
| ConfirmDialog and modal families | `Dialog` | confirm/danger/info; mandatory focus trap |
| Profile menu/popovers | `Popover` | anchored/menu/dialog semantics chosen explicitly |
| JobProgress and local progress blocks | `Progress` | determinate/indeterminate; polite status |
| empty lamp variants | `EmptyState` | icon/title/body/action |

One primary action per scope: page, group, active record, or dialog. Danger never shares the primary fill. Loading preserves button width and label context.

## 12.5 Before/after — five key screens

### Hall

**Before:** brand/top nav; hero search; kind chips; Continue/Recent/Favorites/Noted rails. **After:** preserve composition; normalize suggestion labels and make rail heading/action alignment use the type/space tokens.

```text
BEFORE/AFTER (structure retained)
[Librarian] [Hall Stacks Search Favorites Wanted]          [Inbox] [Card]
                     HALL
        [ Search title, author, series…             ]
      [Books 10762] [Music 97] [Audio 74] [Mag 17] [Comics 14]
Continue reading  ───────────────────────────────────────────────
[cover] [cover] [cover] ...
```

### Search

**Before:** search field, kind chips, More ways, local results/Discover. **After:** one raised results surface only when results exist; filter chips use one component; labels use Title · Author · Kind; empty/loading states retain the same vertical anchor.

```text
[ Search __________________________________________ ] [Search]
[All] [Book] [Magazine] [Comic] [Audiobook] [Music]
Owned shelves (12)                     [More ways to search]
────────────────────────────────────────────────────────────
Title                                Author              Kind
```

### Sorting

**Before:** chips → shortcuts → Quiet hours → bulk tools → groups → repeated editors. **After:** sticky Desk toolbar, grouped row pane, one raised inspector; danger inside Desk actions.

```text
BEFORE                         AFTER
[chips]                        [All 27][Low 22][Audio 2]  [Desk actions ▾]
[shortcuts]                    ┌──────── rows ────────┬──── active slip ────┐
[quiet hours]                  │ Low confidence 22    │ Fortunate Son       │
[purge][model][trusted]        │ Title · reason · CTA │ What this means…    │
[group card + full forms]      │ Title · reason · CTA │ proposed fields     │
                               │ ...                  │ [Apply] [Skip]      │
                               └──────────────────────┴─────────────────────┘
```

### Downloads

**Before:** job cards mix status and actions. **After:** use SlipRow, job-word badge, title, age/source, and one action; confirm dialog owns consequence copy.

```text
ASKED  Dune — Frank Herbert       asked 12m ago       [Confirm]
ON THE WAY  The Left Hand…       68% · 4m remaining  [Details]
NEEDS YOU  Issue 149             unpack stalled      [Open Sorting]
```

### Foyer

**Before:** dark glass card with Name, Password, Enter, invite paste. **After:** preserve; apply Field/Button primitives, keep one primary Enter, and make invite a clearly secondary disclosure.

```text
THE READING ROOM
Librarian keeps this household's shelves together.
Name      [________________________]
Password  [____________________][show]
[ Enter ]
Have an invite? [Paste invitation]
```

## 12.6 Migration path

1. **Alias phase, no visual change:** add semantic, elevation, z, motion, and density tokens; map existing values.
2. **Guardrail phase:** lint new raw colors/shadows/z/durations; token contrast unit test.
3. **Primitive phase:** implement Button, Chip, Field, Badge, Card/SlipRow, Dialog; document all states.
4. **Owner pilot:** migrate Sorting toolbar and one slip inspector; screenshot both themes at 1440/768/390.
5. **Adjacent desks:** Downloads, Maintain attention, Settings.
6. **Reader polish:** Search and foyer; Hall only for shared primitive adoption.
7. **Cleanup:** delete dead variants and aliases only after no callers remain.

Rollback is per surface because old classes remain during migration. Do not change theme palette, IA, and component implementation in one release.

# Part B — Detailed findings

## 13. Strengths

### VIS-001: Protect the semantic token and layout-contract foundation

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | All; low-vision reader; maintainer |
| Category | Design system |
| Severity | High |
| Impact | 5 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 7.5 |
| Verdict | Protect |
| Dependencies | basis for VIS-003–008 |
| Labels | tokens, themes, layout |

**Evidence:** `frontend/src/styles/tokens.css:4-96` centralizes surfaces, text, material roles, families, scale, spacing, radius, motion, peek/rail/hero/topbar/reading/tap contracts; `:99-163` swaps themes.

**Current state:** A single source controls the product’s visual foundation. **Root cause:** design decisions were encoded as semantic variables rather than copied values.

**Recommendation:** Keep names and values unless contrast testing requires a change. Add the proposal as aliases first and a token contrast test.

**Rationale:** Replacing tokens with utilities or CSS-in-JS was rejected: it adds migration cost and loses clear theme semantics. Protect now because consolidation can tempt renaming churn.

**User story:** As a household member, I want every surface to honor my theme and text size.

**Acceptance criteria:**
- [ ] New surfaces use semantic tokens.
- [ ] Both themes retain layout contracts.
- [ ] Token pair tests enforce text/UI contrast.

**Success metric:** zero theme-specific raw colors in new feature CSS.

**Validation:** token unit test and two-theme visual regression.

### VIS-002: Protect the reading-room identity

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Public, Consumer, Owner |
| Persona(s) | All household members |
| Category | Brand |
| Severity | High |
| Impact | 5 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 15.0 |
| Verdict | Protect |
| Dependencies | VIS-001 |
| Labels | brand, typography, lights-down |

**Evidence:** `tokens.css:46-49` family choices; `:99-129` night palette; live Lights Down Hall/Search/Sorting; platform map describes reading-room soul.

**Current state:** Librarian looks like a private library rather than Calibre or an Arr dashboard. **Root cause:** consistent materials, editorial serif, and cover-first composition.

**Recommendation:** Keep fonts, lamp/brass/leather vocabulary, one rust/brass action family, and calm Hall. No purple glow, neon status palette, or neutral SaaS reskin.

**Rationale:** A “modern refresh” was rejected because the brand is already distinctive. Protect now while owner density is changed so the Desk does not become a separate product.

**User story:** As a reader, I want the library to feel calm enough to browse at night.

**Acceptance criteria:**
- [ ] Before/after screens retain both themes and family pairing.
- [ ] Owner compact density uses the same materials.
- [ ] No new brand accent is introduced.

**Success metric:** visual regression and qualitative review retain recognizable Librarian identity.

**Validation:** five-screen, two-theme design review.

## 14. Weaknesses

### VIS-003: Establish hierarchy for owner-dense desks

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner, Admin |
| Persona(s) | Established owner, op |
| Category | Layout and hierarchy |
| Severity | High |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 4.0 |
| Verdict | Fix |
| Dependencies | VIS-005, UX-001/UX-005 context only |
| Labels | sorting, density, hierarchy |

**Evidence:** Live `/review` sequence and 633 interactive refs; `ReviewPage.jsx:810-1054` renders filters, shortcut, Quiet hours, bulk actions/progress, groups, and cards in one flow.

**Current state:** Many useful controls share similar emphasis. **Root cause:** feature-local additions were stacked instead of composed into toolbar/list/inspector regions.

**Recommendation:** Adopt the Sorting before/after: compact toolbar; danger disclosure; low-elevation grouped rows; one `--shadow-2` active inspector; one primary per scope.

**Rationale:** Simply reducing spacing was rejected because hierarchy stays flat; hiding functionality was rejected because owner work is real. Fix now before additional reason/action families arrive.

**User story:** As an owner, I want my eye to land on the current group and slip, not every possible action.

**Acceptance criteria:**
- [ ] Filters, Desk actions, rows, and inspector are visually distinct regions.
- [ ] At most one primary action per scope.
- [ ] Danger is never styled as primary.
- [ ] Compact mode retains 44px touch targets at touch breakpoints.

**Success metric:** five-second test participants identify current task and next action at ≥90%.

**Validation:** screenshot comparison and task-based design critique.

### VIS-004: Raise the meaningful-text floor

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Older/low-vision user, owner |
| Category | Typography |
| Severity | Medium |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 4.0 |
| Verdict | Fix |
| Dependencies | VIS-001 |
| Labels | typography, readability |

**Evidence:** `tokens.css:50-58` uses 15px base/12px xs; `:216-225` sets kicker to 11px. Sampled `stacks.css`, `owner.css`, and `chrome.css` contain 10px/11px/13px literals.

**Current state:** Display typography is strong; dense metadata can become materially smaller than body copy. **Root cause:** utility text was compressed piecemeal.

**Recommendation:** Use the specimen; meaningful minimum 12px, labels 14px, body 16px. Keep 11px only for decorative kicker text that duplicates a heading.

**Rationale:** Making “Large” the default was rejected because it changes all layout; removing compact text was rejected because metadata needs hierarchy. Fix now before component primitives freeze the old values.

**User story:** As an older reader, I want status and controls readable at Default text size.

**Acceptance criteria:**
- [ ] No action/status/error text computes below 12px.
- [ ] Labels compute at least 14px.
- [ ] 200% zoom does not clip owner controls.

**Success metric:** zero meaningful nodes below 12px in five-screen computed-style audit.

**Validation:** CDP style census and zoom QA.

### VIS-006: Complete elevation, status, layer, and breakpoint tokens

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Maintainer, all users |
| Category | Design system |
| Severity | Medium |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 2.7 |
| Verdict | Fix |
| Dependencies | VIS-001 |
| Labels | tokens, elevation, layering |

**Evidence:** `tokens.css:4-96` has no shadow/z/breakpoint/warning/info scale. Sampled partials use raw shadows and z-index values including 1, 20, 30, 40, 50, 80, 100, 110, 200, 250, 300, 1000 and breakpoints 390/640/720.

**Current state:** Core identity is tokenized; spatial layering and statuses are conventions. **Root cause:** tokens were added around page needs, not as a complete system.

**Recommendation:** Add the exact proposed aliases and forbid new raw values outside token/media files.

**Rationale:** A CSS framework was rejected; it would not decide Librarian’s semantic roles. Fix now because primitives require stable foundations.

**User story:** As a maintainer, I want menus, dialogs, and statuses to use predictable layers and colors.

**Acceptance criteria:**
- [ ] New CSS uses named elevation/z/status/motion tokens.
- [ ] Warning and info pairs pass AA.
- [ ] Breakpoint policy is documented and tested.

**Success metric:** zero new distinct shadow/z/breakpoint values for 90 days.

**Validation:** stylelint/custom audit.

## 15. Opportunities

### VIS-005: Create a documented primitive and state layer

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Cross-cutting |
| Persona(s) | All users, maintainer |
| Category | Components |
| Severity | High |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 4.0 |
| Verdict | Add |
| Dependencies | VIS-006 |
| Labels | components, state-matrix |

**Evidence:** Repeated `.cta`, `.chip`, `.card`, `.field`; `ThinkingButton`, FieldHelp, ConfirmDialog/useModal; Sorting combines many local variants (`HoldSlipCard.jsx:57-445`).

**Current state:** Good patterns exist but adoption and states are implicit. **Root cause:** no design gallery or component contract.

**Recommendation:** Build the consolidation table’s primitives, render default/hover/focus/active/disabled/loading/error/selected in both themes, and screenshot-test them.

**Rationale:** Adopting an external library was rejected because matching the brand would require restyling anyway. Add now so owner redesign does not create a second variant generation.

**User story:** As a user, I want the same visual treatment to mean the same action everywhere.

**Acceptance criteria:**
- [ ] Five button and three chip variants cover audited uses.
- [ ] All states exist in both themes.
- [ ] Dialog/popover semantics are part of component contracts.

**Success metric:** 80% of five key screens use target primitives in 90 days.

**Validation:** design gallery and source usage audit.

### VIS-007: Introduce motion tiers and one reduced-motion contract

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Cross-cutting |
| Persona(s) | Motion-sensitive user, all |
| Category | Motion |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Add |
| Dependencies | VIS-006 |
| Labels | motion, reduced-motion |

**Evidence:** `tokens.css:73` one 200ms token; `:166-172` 280ms root transition; `motion.css:420` reduced-motion block; other partials have local blocks.

**Current state:** Motion is calm but timing and reduction are distributed. **Root cause:** feature-specific animation rules.

**Recommendation:** Use 120/200/320ms tiers and zero them through token overrides under reduced motion; ambient effects may retain static presence.

**Rationale:** Removing all motion was rejected because transitions clarify state; per-feature media blocks were rejected because coverage drifts. Add now alongside token completion.

**User story:** As a motion-sensitive reader, I want state changes without sweeping or pulsing animation.

**Acceptance criteria:**
- [ ] Every animation/transition uses a duration token.
- [ ] Reduced motion removes transform/looping effects.
- [ ] Focus and status changes remain perceivable.

**Success metric:** zero unclassified animation durations.

**Validation:** source audit and reduced-motion visual test.

### VIS-008: Migrate incrementally with visual gates

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Cross-cutting |
| Persona(s) | Maintainer, all users |
| Category | Migration |
| Severity | Medium |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 2.7 |
| Verdict | Add |
| Dependencies | VIS-001, VIS-005, VIS-006 |
| Labels | migration, visual-regression |

**Evidence:** Existing variable architecture permits aliases; five key screens and two themes are identifiable; mocked e2e already visits Hall/Search/Work/Sorting/Settings in both themes (`e2e/axe.spec.ts:162-229`).

**Current state:** Migration can be surface-based, but no visual specimen/regression gate was confirmed. **Root cause:** tests focus semantics/axe, not appearance.

**Recommendation:** Follow §12.6 and add stable screenshots after motion settles. Roll out owner-first; keep old classes until each surface is green.

**Rationale:** Big-bang redesign was rejected due regression risk; never-migrate was rejected because drift compounds. Start now with aliases and one pilot.

**User story:** As a household member, I want system improvements without a disorienting redesign.

**Acceptance criteria:**
- [ ] Each migrated surface has before/after captures at 1440/768/390 in both themes.
- [ ] Rollback is possible per surface.
- [ ] Dead variants are removed only after usage reaches zero.

**Success metric:** no theme/route rollback during staged migration.

**Validation:** visual diff review and class usage audit.

## 16. Remediation plan

| Horizon | ID | Title | Effort | Owner | Dependencies |
|---|---|---|---|---|---|
| Now | VIS-004 | Meaningful text floor | S | Design + frontend | VIS-001 |
| Now | VIS-006 | Complete system tokens | M | Design systems | VIS-001 |
| Now | VIS-007 | Motion tiers | S | Frontend | VIS-006 |
| Next | VIS-005 | Primitive/state layer | M | Design systems | VIS-006 |
| Next | VIS-003 | Sorting hierarchy pilot | M | Product design + frontend | VIS-005 |
| Next | VIS-008 | Visual migration gates | M | QA + design | VIS-005 |
| Later | VIS-008 | Migrate Downloads/Settings/Hall shared controls | L | Frontend | pilot |

Aliases and tests land first, primitives second, Sorting pilot third. That order prevents redesigning the desk on another generation of one-off values.

## 17. Quick wins

- Add `font-variant-numeric: tabular-nums` to every badge/count.
- Replace the 11px global kicker with 12px.
- Add warning/info/elevation/z/motion aliases without visual change.
- Move destructive Desk actions into a danger disclosure.
- Publish Button/Chip state names before implementation.

## 18. Open questions

- Should default base rise from 15px to 16px, or should only utility tokens rise?
- Is compact density owner-controlled or route-owned? Recommendation: route-owned, never below touch minimum on touch devices.
- Which visual-regression tool belongs in the existing Playwright setup?
- Does the accent pair need a separate `--gilt-text` alias in every component, or should `--color-link` become canonical?

## Appendix A — Component state specimen

This is the minimum state inventory for the proposed design gallery. The gallery is an implementation contract, not a mood board: every row renders in Lights Up, Lights Down, comfortable density, and Desk compact density.

### Button

| Variant | Default | Hover | Focus | Active | Disabled | Loading |
|---|---|---|---|---|---|---|
| Primary | accent fill + accent text | 8% ink mix | 3px focus ring | 4% darker fill | muted surface/text; no opacity-only label | stable width; spinner + present-tense label |
| Secondary | raised surface + control border | accent-soft surface | 3px ring | surface-2 | muted border/text | stable width |
| Quiet | transparent + text | menu-hover | 3px ring | accent-soft | muted text | stable width |
| Danger | danger-soft + danger text | stronger danger mix | 3px danger/focus dual ring | stronger danger surface | muted | “Deleting…”; cannot double-submit |
| Link | underlined text | thicker underline | 3px ring | text | muted | not used for async work |

Rules: one Primary per visual scope; Danger never inherits Primary; icon-only buttons use `IconButton`; a disabled button still preserves readable contrast; loading does not replace the accessible name with “spinner.”

### Chip and Badge

| Component | State | Visual contract | Semantic contract |
|---|---|---|---|
| FilterChip | off | transparent/low surface, control border | `aria-pressed=false` |
| FilterChip | on | accent-soft, accent-ink, stronger border | `aria-pressed=true` |
| FilterChip | focus | 3px ring outside border | focus visible |
| StatusChip | neutral | surface-2 + text | text names state |
| StatusChip | attention | warning-soft + warning text/icon | never hue-only |
| Badge | count | fixed-height compact capsule | tabular figures; concise name |
| Badge | overflow | “99+” | accessible name uses exact count if known |

### Field

| State | Border | Label/help | Message |
|---|---|---|---|
| Default | control-border | visible label | optional persistent hint |
| Hover | text/control mix | unchanged | unchanged |
| Focus | focus ring + control border | label remains | no layout jump |
| Filled | control-border | visible label | value never substitutes for label |
| Invalid | danger border | label remains | text + icon; `aria-describedby` |
| Disabled | border + muted surface | readable muted label | reason when non-obvious |
| Busy | ordinary field disabled only when necessary | label remains | polite status outside field |

### Card, row, and inspector

| Variant | Surface | Elevation | Use |
|---|---|---|---|
| Flat row | transparent/panel | none | lists and grouped slips |
| Group card | panel | border only | reason section |
| Raised card | raised | shadow-1 | menu/popover or selected subpanel |
| Active inspector | raised | shadow-2 | one selected Sorting record |
| Dialog | raised | shadow-3 | blocking confirmation |

Do not stack raised cards inside raised cards. Selection uses border/surface plus text, not shadow alone. Busy and error states preserve dimensions so the Desk does not jump.

### Dialog and Popover

| Property | Dialog | Popover |
|---|---|---|
| Blocks background | yes | no |
| Focus trap | yes | no; logical Tab order |
| Escape | closes | closes |
| Outside click | policy by risk; never destructive confirmation | closes |
| Initial focus | heading or safest action | first logical control only when opened by keyboard |
| Return focus | opener | opener |
| Elevation | shadow-3 | shadow-2 |

This distinction is visually important as well as semantic: a dialog gets a veil and centered/edge sheet composition; a popover remains anchored to its trigger without a full-screen veil.

## Appendix B — Exact screen-level acceptance

### Hall acceptance

- The Hall h1, search, kind filters, and first non-empty rail fit in the first 900px of a 1440×900 viewport.
- Search remains the highest-contrast action; no owner badge uses a larger visual mass.
- Rail covers retain token aspect ratios; title wraps to two lines, metadata to one.
- Empty rails are omitted or replaced by one action-oriented empty state, never blank carousels.
- At 390px, one full cover plus a meaningful preview of the next communicates horizontal scroll.

### Search acceptance

- Search input and submit form one group; submit is the only Primary in that group.
- Filter chips wrap without changing reading order.
- Local ownership is visible through text/icon, not a color band alone.
- Loading, empty, error, and results preserve the same top anchor to prevent layout disorientation.
- Long author/title pairs wrap without pushing action controls outside the row.

### Sorting acceptance

- Reason filters and current count occupy one toolbar line at desktop and a wrapped region at narrow widths.
- “Desk actions” contains destructive/bulk actions; no danger control sits beside routine filters.
- Group headings remain Literata or strong body type at ≥18px; row metadata remains Source Sans 3 ≥12px.
- One selected row and its inspector have redundant selection cues: border, surface, and heading.
- Counts, percentages, and times use tabular figures.
- At 768px, inspector becomes a sheet or follows the list; at 390px, it is a full-width route-like panel with a clear Back to group action.

### Downloads acceptance

- Job word is first and textual: Asked, On the way, Arrived, Needs you, Failed.
- Progress color never replaces a numeric/text status.
- A routine row has one action; secondary detail sits under disclosure.
- Confirm dialog names destination and count; destructive/cost-bearing consequences are plain language.
- Row height is stable when progress updates.

### Foyer acceptance

- Foyer uses one Primary (“Enter”); invite and reset are links/disclosures.
- Labels stay visible above fields; placeholders are examples only.
- Browser autofill colors are theme-safe and retain text contrast.
- Error copy appears adjacent to the form summary and associates with fields.
- At 320px and 200% zoom, no horizontal scroll or clipped primary action.

## Appendix C — Visual QA capture matrix

| Screen/state | 1440 | 768 | 390 | Lights Up | Lights Down | Reduced motion |
|---|---:|---:|---:|---:|---:|---:|
| Foyer default/error | ✓ | — | ✓ | ✓ | ✓ | ✓ |
| Hall populated/empty/loading | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Search idle/results/empty/error | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Sorting 27/filter/inspector/dialog | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Downloads five job states | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Work peek/full page | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Settings long form | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

Capture after finite animations settle. Also capture the first reduced-motion frame so a token transition cannot hide text. Visual diffs require human review for intentional cover/content changes; mask cover imagery, never controls or text.

## Appendix D — Governance

- Token additions require purpose, both-theme values, contrast row, and one usage example.
- New component variants require a state that cannot be expressed by an existing variant; “this page looks different” is not sufficient.
- New z-index values require placement in the six-step ladder.
- New breakpoints require evidence that the documented four cannot express the layout.
- New motion requires reduced-motion behavior in the same change.
- Owner compact density may reduce whitespace one step; it may not reduce meaningful text below 12px or touch targets below the platform contract.
- Quarterly, delete aliases and variants with zero source call sites; never retain them “just in case.”

## Phase 6 self-check

- [x] Full Part A, all surfaces/themes, scorecard, stop/protect/risks/direction.
- [x] IDs VIS-001 through VIS-008 preserved and unique; no new ID introduced.
- [x] Complete token table and ready-to-paste CSS included.
- [x] Typography specimen, component consolidation, five before/after screens, and incremental migration included.
- [x] Every finding has full format, file/live evidence, alternatives, and why now.
- [x] Screenshot limitation stated; no unsupported pixel claim.
- [x] No application code or sibling review file modified.
