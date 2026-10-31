# VoiceOver script (1.0)

Owner-run pass for VoiceOver on macOS. Automated Playwright coverage lives in
[`e2e/voiceover.spec.ts`](../../e2e/voiceover.spec.ts) (names and roles on **:8794**).
A physical VoiceOver pass is not required to ship; this script is the ritual to
run when a Mac is at hand.

Target: WCAG 2.2 AA on foyer, Hall, Search, join, Sorting first page, Settings.
Product port **8793** (Automat `http://10.10.1.202:8793` or local). Never 8788 / 8790 / 8791 / 8792.

## Setup

1. System Settings → Accessibility → VoiceOver → On (⌘F5).
2. Rotor: Headings, Links, Form Controls, Landmarks.
3. Use VO-A to read, VO-U for the rotor, Tab / Shift-Tab for focus.

## 1. Login (foyer)

1. Open `/login`. VO should speak the heading **The Reading Room**.
2. Document title is **Sign in · Librarian**.
3. Tab: **Name**, **Password** (with Show password), **Enter**.
4. Submit a wrong password. VO should speak the alert (not a silent fail).
5. **Paste an invite** is a separate form below Enter.

## 2. Join

1. Open `/join` (or paste a token on the foyer). Do not mint a live Automat invite for this pass.
2. Title **Join · Librarian**. Heading **The Reading Room**.
3. With a valid token: **Name**, **Password**, **Enter**. Expiry is spoken as muted text.
4. Without a token: **Invite link** and **Open invite**.

## 3. Open / Read

1. Sign in. Skip to content, then Hall heading.
2. Open a book that can be read in the app.
3. The work heading is the title. The primary button is **Read** (exact name — not **Reading Room**).
4. Activate Read. VO should speak a dialog named with the title (Reading room).
5. Escape / Close returns to the work page.

## 4. Listen

1. Open an audiobook that can be heard in the app.
2. Primary button is **Listen** on the work (not a file-row Listen).
3. Activate that Listen. VO should speak a dialog named with the title (Listening room).
4. Transport controls have names; position uses a value text where present.
5. Close returns to the work page.

## 5. Sorting

1. As owner/op, open **Sorting** (`/review`). Heading, nav, and title all say Sorting.
2. Each slip has a heading. Group actions are a named group.
3. **Delete group** / **Accept the clear ones** open a dialog; Tab stays inside; Escape restores the opener.
4. Typed-count confirms include a labeled field in the tab order.

## Pass / fail

- **Pass:** every control above has a spoken name; focus is visible (`:focus-visible`); overlays do not dump Tab into the Hall behind them.
- **Fail:** unnamed buttons, title not announced, Tab escapes a dialog, skip link missing.

Do not treat confirm-before-download as a legal review. It is a product control: nothing reaches SABnzbd until Queue to SAB is confirmed.
