# Librarian Reading Room — visual handoff

Stitch project **Librarian Reading Room** was not created. After `mcp_auth` reported success, every Stitch call (`list_projects`, `create_project`) still returned **401**: *API keys are not supported by this API. Expected OAuth2 access token*. Reconnect **user-stitch** with Google OAuth in Cursor Settings → Tools & MCP, then regenerate screens from the prompts at the bottom of this file.

Until then, these HTML mockups are the copy source (open on a desktop viewport, then ~390px for the tab bar). They were visually QA’d in-browser: foyer lamp + glass card, Hall hero/rails, search stacks/beyond, opaque 44rem peek, blurred work hero.

| Screen | File |
| --- | --- |
| Index | `mockups/index.html` |
| 1 Login foyer | `mockups/foyer.html` |
| 2 The Hall | `mockups/hall.html` |
| 3 Unified search | `mockups/search.html` |
| 4 Work peek over Hall | `mockups/peek.html` |
| 5 Full work detail | `mockups/work.html` |
| Shared CSS / tokens | `mockups/reading-room.css` |

Do **not** clone Projectionist cinema gold (`#ffb800`, Fraunces + DM Sans marquee). Do **not** clone Calibre (sidebar tree, Windows list, toolbar). Same *structures* as Projectionist: full-bleed hero, clickable chips, horizontal cover rails, peek then full page.

---

## Soul

Night reading room after the house has gone quiet. Brass lamp, paper dust in the cone of light, clothbound spines, gilt stamping. Warm walnut ink — not theater black. Intimate, not cinematic. One type ramp, one cover card, one 200ms motion language.

---

## Tokens (paste into SPA `:root`)

```css
:root {
  /* Color — brass gilt, not cinema #ffb800 */
  --bg: #110d09;
  --surface: #1a1410;
  --surface-2: #231b14;
  --surface-raised: #2a2118;
  --border-subtle: #3a2e22;
  --border: #4a3c2c;
  --text: #f4ead6;
  --muted: #b5a48a;
  --paper: #e8dcc4;
  --gilt: #e4c078;
  --accent: #c9954a;
  --accent-2: #a87838;
  --accent-soft: rgba(201, 149, 74, 0.16);
  --accent-text: #1a1208;
  --lamp: #f0b85a;
  --lamp-glow: rgba(240, 184, 90, 0.22);
  --dust: rgba(232, 220, 196, 0.07);
  --leather: #6b3e2a;
  --danger: #c47a6c;
  --success: #7d9a78;
  --workspace-base: #0e0b08;
  --workspace-wash-a: #2a1c10;
  --workspace-wash-b: #161018;

  /* Type */
  --font-display: "Literata", "Palatino Linotype", Palatino, serif;
  --font-body: "Source Sans 3", "Source Sans Pro", system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, monospace;
  --text-xs: 0.75rem;
  --text-sm: 0.8125rem;
  --text-md: 0.9375rem;
  --text-lg: 1.125rem;
  --text-xl: 1.375rem;
  --text-2xl: 1.75rem;
  --leading-tight: 1.22;
  --leading-body: 1.55;
  --base-font-size: 15px;

  /* Space / radius */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-7: 32px;
  --space-8: 48px;
  --gutter: 24px;          /* 16px on mobile */
  --radius-sm: 6px;
  --radius: 8px;
  --radius-lg: 12px;
  --motion: 200ms ease;

  /* Layout contracts (Projectionist structure) */
  --peek-width: 44rem;                         /* min(44rem, calc(100vw - 1.5rem)) */
  --peek-inset-y: max(1.25rem, 3vh);
  --rail-cover-w: 148px;
  --rail-cover-h: 222px;                       /* 2/3 of 148 */
  --rail-square: 160px;                        /* music + audiobook */
  --rail-gap: 16px;
  --hero-search-max: 42rem;
  --hero-search-h: 3.25rem;
  --glass-card-max: 520px;
  --topbar-h: 64px;
  --reading-column-max: 1200px;
}
```

### Token table

| Token | Hex / value | Use |
| --- | --- | --- |
| `--bg` | `#110d09` | Page ground |
| `--surface` | `#1a1410` | Peek panel, glass card, topbar mix |
| `--surface-2` | `#231b14` | Cover fallback, inset wells |
| `--surface-raised` | `#2a2118` | Search field, chips |
| `--border-subtle` | `#3a2e22` | Topbar rule |
| `--border` | `#4a3c2c` | Peek, fields |
| `--text` | `#f4ead6` | Cream paper body |
| `--muted` | `#b5a48a` | Kickers, captions |
| `--paper` | `#e8dcc4` | Synopsis, subheads |
| `--gilt` | `#e4c078` | Lamp mark, hover, seals |
| `--accent` | `#c9954a` | Primary CTA, chips-on |
| `--accent-2` | `#a87838` | Pressed brass |
| `--accent-text` | `#1a1208` | Text on gilt pills |
| `--lamp` | `#f0b85a` | Foyer shaft + wash |
| `--leather` | `#6b3e2a` | Secondary wash, avatar |
| `--danger` | `#c47a6c` | Review / missing gaps |
| `--success` | `#7d9a78` | Organized / Open chip |
| Display font | **Literata** | Titles, wordmark, cover gilt |
| Body font | **Source Sans 3** | UI, blurbs, fields |
| Label | Source Sans 3 / 11px / 0.12–0.16em / uppercase | Kickers, chips, field labels |

Google Fonts:

```
https://fonts.googleapis.com/css2?family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,600;0,7..72,700;1,7..72,400&family=Source+Sans+3:wght@400;500;600;700&display=swap
```

Page wash (Hall / Search / Work, not foyer):

```css
background:
  radial-gradient(ellipse 90% 55% at 50% -8%, color-mix(in srgb, var(--lamp) 18%, transparent), transparent 58%),
  radial-gradient(ellipse 50% 40% at 100% 0%, color-mix(in srgb, var(--leather) 22%, transparent), transparent 50%),
  linear-gradient(180deg, var(--workspace-base) 0%, var(--bg) 42%);
```

---

## Type ramp

| Role | Size | Weight | Font |
| --- | --- | --- | --- |
| Work hero title | `clamp(2.5rem, 7vw, 5.25rem)` / line 0.95 / tracking -0.03em | 600 | Literata |
| Hall H1 | `clamp(2rem, 5vw, 3.25rem)` | 600 | Literata |
| Peek title | `clamp(1.35rem, 4vw, 1.85rem)` | 600 | Literata |
| Rail H2 | `1.375rem` (`--text-xl`) | 600 | Literata |
| Glass door title | `1.75rem` | 600 | Literata |
| Body / search input | 15px / 1.05rem in hero field | 400 | Source Sans 3 |
| Chip / kicker | 11px, 0.08–0.16em, uppercase | 700 | Source Sans 3 |
| Cover gilt title | ~0.95rem, max 12ch | 600 | Literata |
| ISBN / files | 13px | 400 | IBM Plex Mono |

---

## Motion

| Event | Spec |
| --- | --- |
| Default UI | `200ms ease` |
| Cover hover | `translateY(-4px)` + lamp-tinted shadow, 200ms. One-line title fades in under the card. **Never** a hamburger on the poster. |
| Peek in | 200ms opacity + `translateY(0.75rem)` (Projectionist uses 220ms; we standardize 200ms) |
| Foyer lamp | 28s ease-in-out alternate, scale 1 → 1.04, drift -2% / +1.5% |
| Dust | 40s linear, translateY -8%, mix-blend screen |
| Page-turn (foyer) | 8s breathe; a page that never quite finishes |
| Primary CTA hover | `translateY(-1px)` + slight brightness |
| `prefers-reduced-motion` | **All still.** Foyer becomes static warm gradient + paper grain. Peek appears with no slide. No dust, no lamp drift, no page-turn. |

Focus rings: 2px gilt mix, offset 1–2px. Peek traps focus; Esc / scrim / close returns focus to the cover that opened it.

---

## Layout contracts

Copied from Projectionist Explore + title-detail, with reading-room chrome:

| Piece | Measure |
| --- | --- |
| Peek panel | `width: min(44rem, calc(100vw - 1.5rem))`; `top/bottom: max(1.25rem, 3vh)`; centered (`left: 50%; transform: translateX(-50%)`); z-index 90 over scrim 85 |
| Scrim | `rgba(8, 6, 4, 0.62)` — warmer than Projectionist’s `rgba(0,0,0,0.55)` |
| Portrait cover | **148 × 222** (aspect 2/3). Books, magazines, comics. |
| Square cover | **160 × 160**. Audiobooks, music. |
| Rail | Horizontal scroll, snap start, gap 16px, padding gutter 24px, cover height locked as above |
| Glass login card | `min(520px, 100%)`, padding 32px 24px (`--space-7` / `--space-6`), blur 18px, gilt-soft 1px border |
| Hero search | Max 42rem, height 3.25rem, pill radius 999px, inner lamp ring `0 0 0 6px var(--accent-soft)` |
| Work hero | `min-height: min(72vh, 640px)`; blurred cover full-bleed; dual scrim (up from `--bg`, in from left) |
| Topbar | 64px, blur 14px, sparse |
| Mobile tab bar | Hall / Search / Favorites / You, 64px + safe-area |

**Librarian peek shows the cover.** Projectionist’s `.title-detail-drawer-poster { display: none }` is a cinema leftover — do not copy that hide. Compact peek is cover + title + chips + short blurb + acts.

---

## Component inventory

Build these once; every screen reuses them.

1. **Lamp colophon** — oil-lamp mark (see SVG in mockups). Wordmark “Librarian” in Literata. Not a film sprocket, not a calibre “C”.
2. **Topbar** — mark, Hall, Search (or `/` focus), People/Settings if allowed. Review is an **op/owner bag badge**, not a reader tab.
3. **Glass door** — foyer card (username/password). Join (`/join?token=`) is the **same** card plus a quiet gilt **seal** (“Reader” / “Op”).
4. **Hero search field** — single pill, always on The Hall; same field on the results page.
5. **Kind chips** — Book / Magazine / Comic / Audiobook / Music. Clickable; filter search or jump to area.
6. **Metadata chips** — kind, year, author/artist, genre, format, ISBN, Favorites. All clickable (author → author page later; format → convert menu).
7. **Cover card** — cloth + gilt CSS (or real `cover.jpg`). Hover lift. Progress bar 3px gilt at bottom for Continue. Living status chip for indexer jobs (Request → Queued → Downloading → Organized → Open).
8. **Cover rail** — section kicker optional, Literata H2, optional “See all”, horizontal track.
9. **Peek overlay** — app-wide provider (Projectionist `TitleDetailOverlayProvider` contract). Cover click does **not** navigate. Hall/search scroll stays put.
10. **Primary / outline / ghost CTAs** — gilt fill pill; brass outline; ghost border. Uppercase 0.04em tracking, 14px 28px padding, radius 999.
11. **Advanced search drawer** — `<details>` under the same hero (author, title, ISBN, series, kind, year). Not a second app.
12. **Empty Hall CTA** (owner only) — one beautiful card: “Open the stacks — add an indexer.” No form dump.
13. **Mobile tab bar** — Hall / Search / Favorites / You.
14. **Op/owner pages** — Settings, People, Review, Queue stay in the **same room** (darker lamp, same type). No admin skin.

---

## Screens

### 1. Login foyer (`/login`, also `/join?token=`)

Full viewport. **No household covers** (privacy on the glass door).

Atmosphere layers (bottom → top):

1. Near-black walnut `#0c0907`
2. **Lamp shaft** — conic gradient from top center, warm `#f0b85a` at ~20% opacity, 28s drift
3. Small lamp bulb + glow at ~6% from top
4. **Dust** — sparse 1px cream dots, 40s rise, screen blend
5. **Spine silhouettes** — bottom 28vh, anonymous colored bars, masked to fade up. Not titled.
6. **Unfinished page-turn** — pale paper rhombus, 8s, 12% opacity, lower right
7. **Glass card** — centered, 520px

Card copy:

- Kicker: `HOUSEHOLD LIBRARY`
- Title: `The Reading Room`
- Lede: quiet, one sentence
- Fields: Name, Password
- Primary: `Enter`
- Join only: gilt seal `Reader` or `Op` above the title

Reduced motion: static radial lamp + 7% paper grain overlay, no animations.

### 2. The Hall (post-login default, not Settings)

Sparse topbar. Hero is **only** the search field (large, always there) under a Literata question: “What are you looking for?”

Rails, in order:

| Rail | Who | Cover shape |
| --- | --- | --- |
| Continue | Everyone with progress | Portrait and/or square + progress bar |
| What’s New | Everyone | Mixed kinds |
| Favorites | This user | Mixed |
| Books | Everyone | Portrait |
| Magazines | Everyone | Portrait (issue date as gilt caption) |
| Comics | Everyone | Portrait |
| Audiobooks | Everyone | Square |
| Incoming Music | Op/owner | Square; Promote lives in peek, not a second skin |
| Gaps | Op/owner | Missing cards, `--danger` foil; confirm before SAB |

Empty house: hide empty rails; owner sees a single CTA card instead of the rail stack.

Cover click → peek. Title on hover only (one line). No overflow menus on the poster.

### 3. Unified search (`/search?q=`)

**Never** a separate indexer app. One box, one page.

1. As-you-type: **In the stacks** (FTS5) cover rail/grid immediately.
2. Enter / pause with few or zero local hits: page grows **Beyond the shelves** (NZBFinder). Kind chips infer `70xx` / `7030` / `3030` / music.
3. Local cover → peek (Open / Favorite / Download).
4. Indexer cover → peek with **Request** (op/owner queues SAB; reader’s Request is “asked the house” — same card).
5. After Request, the card becomes a living chip (queued → downloading → organized → **Open**). Queue page is op/owner exceptions only.
6. Advanced is a **drawer under the same hero**.

Dashed gilt outline on beyond-the-shelves covers distinguishes them without a second visual language.

### 4. Work peek

Centered modal over dim Hall/search. Hall **scroll stays put**.

```
[ BOOK                          × ]
[ cover 148×222 ]  Title (Literata)
                   chips (clickable)
                   2–4 line blurb
                   [Open] [Favorite] [Download EPUB]
                   Open full page  ·  ⌘-click keeps peek
```

- Same-tab **Open full page** dismisses peek → `/works/:id`
- ⌘/Ctrl-click keeps peek, new tab
- Esc / scrim / × restores focus to the opening cover
- Indexer peek: primary is **Request** (or living status)
- Reader indexer peek: Request copy = asked the house, same layout

### 5. Full work (`/works/:id`)

Projectionist `TitleDetailPage` structure:

- Sticky topbar with back to Hall
- **Full-bleed hero**: cover duplicated, `blur(42px) saturate(1.15) scale(1.12)`, dual scrim
- Clickable chips, Literata display title (`clamp(2.5rem, 7vw, 5.25rem)`), author · year
- CTA row: Download EPUB (default by kind: CBZ for comics), Favorite, format menu (PDF/MOBI/AZW3/KEPUB on demand)
- Description section, max ~62ch, `--paper`
- Rails: More by this author, On this shelf, Gaps (honest empty + reason, never a junk dump)

---

## Role chrome (same room)

| Role | Hall | Beyond Request | Bag badge | Settings / People |
| --- | --- | --- | --- | --- |
| Reader | Yes | Asked the house | Hidden | Hidden |
| Op | Yes | Queues SAB | Review count | People (invite reader only); no Settings tokens |
| Owner | Yes | Queues SAB | Review count | Everything |

---

## Anti-patterns (fail the review if present)

- Cinema gold `#ffb800`, Fraunces display, “Now Playing”, marquee uppercase wordmarks
- Calibre-style table of filenames as the Hall
- Separate “Grabber” or “Indexer” app chrome
- Hamburger / ⋮ on cover posters
- Peek that navigates away (must overlay)
- Hiding the peek cover
- Anonymous Hall landing on Settings
- Second visual language for join, Review, or Queue
- Mixing audiobook covers into Incoming Music / Plexamp rails

---

## Stitch regeneration prompts (when OAuth works)

Create project title: **Librarian Reading Room**. Design system: dark, customColor `#c9954a`, headline **LITERATA**, body **SOURCE_SANS_3**, roundness **ROUND_EIGHT**, colorMode **DARK**, colorVariant **FIDELITY**, overrideNeutral `#110d09`, overridePrimary `#c9954a`, overrideSecondary `#6b3e2a`, overrideTertiary `#e4c078`.

Then `generate_screen_from_text` DESKTOP, one prompt per screen, including: “Night reading room (lamp, paper dust, gilt). Not Calibre, not a cinema UI. Walnut ink #110d09, brass #c9954a, cream type #f4ead6, Literata display, Source Sans 3 UI. Portrait covers 148×222, square 160. Peek 44rem centered modal.”

1. Login foyer — animated lamp shaft, dust, anonymous spine silhouettes, glass card 520px, no household covers.
2. The Hall — hero search pill 42rem × 3.25rem, rails Continue / What’s New / Favorites / Books / Magazines / Comics / Audiobooks / Incoming Music / Gaps.
3. Search — query “dune”, section In the stacks then Beyond the shelves, kind chips, advanced drawer.
4. Peek — Hall dimmed underneath, 44rem panel, Piranesi cover + chips + Open/Favorite.
5. Work — blurred cover hero 72vh, Piranesi, chips, CTA, More by author rail.
