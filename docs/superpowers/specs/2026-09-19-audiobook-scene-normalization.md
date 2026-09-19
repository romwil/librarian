# Audiobook scene-normalization (2026-09-19)

Authoritative parsing contract for Usenet / dump filenames before Audnexus ASIN match.
Implementation: `librarian/audiobook_normalize.py`. Golden fixtures:
`tests/fixtures/audiobook/scene_normalization.json` (≥15 cases).

## Goal

Turn noisy release names into stable tokens: **author**, **title**, **narrator**,
**series_name**, **series_index**, **year**, **asin**, plus scrubbed noise flags.
Never invent an ASIN. Never route spoken-word into `music_root`.

## Delimiters

Split and tidy with the same spirit as `tidy_title` / `_DOT_GROUP`:

1. Replace `.` `_` `-` runs with spaces (keep hyphenated proper names when bounded by letters).
2. Prefer `Author - Title` when a spaced hyphen separator is present.
3. Bracket groups `[…]` `(…)` and yEnc counters `6/8` / `[6/8]` are **noise containers** —
   strip their contents when they match the noise dictionary or part counters; otherwise keep
   narrator / series hints found inside.

## Noise dictionary (case-insensitive)

Strip these tokens wherever they appear as whole words (dots/underscores already normalized):

| Class | Tokens |
|-------|--------|
| Format | `audiobook`, `audio book`, `m4b`, `mp3`, `flac`, `m4a`, `aac`, `ogg`, `opus` |
| Edition | `unabridged`, `abridged`, `retail`, `proper`, `repack`, `webrip`, `web-rip` |
| Scene / group | trailing `-GROUP`, `eBook-GROUP`-style tails already handled elsewhere; also `VBR`, `CBR` (bitrate), `64k`, `128k`, `64kbps`, `128kbps` |
| Multipart | `part N`, `cd N`, `disc N`, `disk N`, bare `N/M` counters |
| Junk | `nfo`, `sample`, `proof`, `par2` |

Numeric bit-rate / sample-rate bands (`\b\d{2,3}\s?k(?:bps)?\b`, `\b\d{2,3}\s?kb\/?s\b`) are noise.

## Narrator isolation

Narrator is **not** the author. Detect with (priority order):

1. `Narrated by X` / `Read by X` / `Narrator: X`
2. Trailing `by X` **only when** author was already split via `Author - Title` and `X` differs
3. Parenthetical `(Narrated by X)` / `(read by X)`

Store as `narrator`. Do not overwrite `author` with narrator.

## Series / index

Patterns (after noise scrub):

- `Title Book N` / `Title Bk N` → series from preceding words, index `N`
- `Title (#N)` / `Title #N` when clearly a series ordinal (1–99), not a track number
- `Series Name TT-NN` / `Series Name 01` with author already known — prefer explicit series tokens
  from Audnexus over filename guesses at match time

Standalone titles leave `series_name` / `series_index` empty.

## ASIN extraction

Accept Amazon/Audible ASINs: `\b(B0[A-Z0-9]{8}|[0-9]{10})\b` when the 10-digit form is not a
valid ISBN-10 check digit **or** appears next to `asin` / `audible`. Prefer `B0…` forms.
Never mint an ASIN from title text alone.

## Confidence inputs (for Audnexus scorer)

Normalize feeds these signals into `librarian/audnexus.py` scoring:

| Signal | Weight idea |
|--------|-------------|
| Exact ASIN hit | 1.0 (auto) |
| Title token Jaccard | strong |
| Author token Jaccard | strong |
| Narrator match (when both sides have one) | medium |
| Series name + index | medium |
| Year proximity (±1) | weak |
| Duration / chapter count (when known later) | weak, Phase 2 |

### Bands (locked)

| Score | Action |
|-------|--------|
| ≥ 0.85 | Auto-organize; fill identity from Audnexus; remux eligible |
| 0.65–0.84 | Review reason `audnexus_ambiguous` — show top candidates; **no remux** |
| < 0.65 | Review reason `audnexus_unmatched`; **no remux** |

## Downstream layout (Phase 2)

After a resolved match, shelf path:

`{Author}/{Series}/{Index} - {Title} ({Year})/{Title}.m4b`

Standalone omits `{Series}/` and uses `{Author}/{Title} ({Year})/{Title}.m4b`.

## Out of scope

- Comic / magazine / music parse paths
- Hardcover / Open Library as tier-1 for `kind=audiobook`
- Promote to `music_root` / Plexamp
