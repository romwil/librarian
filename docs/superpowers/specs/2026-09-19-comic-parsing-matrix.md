# Comic parsing matrix (2026-09-19)

Scene-normalization contract for Usenet / dump comic filenames before ComicVine
authority match. Companion to the Spoken Word & Sequential Art PRD (comics track).

**Authority:** ComicVine only (print comics / GNs). Magazines stay on the magazine parse path.
**Shelf container:** clean CBZ + embedded `ComicInfo.xml`. No in-app Guided View reader.

## Tokens

| Token | Meaning | Notes |
|-------|---------|--------|
| `series` | Series / volume display name | After noise scrub; title-case via `tidy_title` |
| `volume_year` | **Volume start year** | ComicVine `start_year`. Beats calendar/release year for disambiguation |
| `issue` | Issue number | Integer or decimal (`18.1`); strip leading zeros for identity; keep decimals |
| `year` | Cover / pub year | From `(YYYY)` or bare year after series; not preferred over `volume_year` for CV volume pick |
| `variant` | Cover / printing marker | `CVR A`, `Cover B`, `FOC`, `2nd Print` — kept in Notes, not in path stem |
| `annual` | Annual flag | `Annual`, `Ann` → issue often `Annual N` or mapped via CV |
| `format` | GN / TPB / HC / OS | One-shots and trade paths use subtitle layout |
| `publisher` | From CV after match | Required for dest path; never invent from group tags |

## Noise dictionary (strip before token extract)

Case-insensitive; dots/underscores/spaces interchangeable.

**Ripper / scene groups:** `Minutemen`, `Megan`, `Empire`, `DCP`, `Glorith`, `Zone-Empire`,
`Digital-Empire`, `ThP`, `dCS`, `GlorTh`, `DarkHorse-Empire`, `Comicbook-Empire`.

**Scan quality / ads:** `c2c`, `c2c-`, `no-ads`, `NoAds`, `Digital`, `HD-WebRip`, `Webrip`,
`(Digital)`, `CBZ`, `CBR`, `PDF` (extension already stripped by stem).

**Archive / dump markers:** `repack`, `proper`, `retail`, `hybrid`, `-HD`, `(HD)`.

**Do not strip:** publisher house names that are also series titles (`Image`, `Marvel` as series
tokens stay when they are the series, not a trailing `-Marvel` group — group form is
`eBook-Group` / `-Minutemen` style at the end).

## Delimiters

Primary separators: `.` `_` `-` and whitespace. Prefer left-to-right greedy series until an
issue / year / volume marker.

Recognized issue markers:

- `#N` / `No. N` / `No N`
- `vN NNN` / `Vol. N NNN` / `Volume N NNN` (volume **number**, not start year)
- `YYYY NNN` (year then zero-padded issue)
- bare zero-padded `0NN` / `NNN` when kind hint is comic

Year markers: `(19xx|20xx)` preferred; bare `19xx|20xx` after series also accepted.

Decimal issues: `#18.1`, `18.INH`, numeric `18.1` only (alpha suffixes → Notes/variant).

## Volume disambiguation (locked)

When ComicVine returns multiple volumes with the same title key:

1. Prefer volume whose `start_year` equals parsed `volume_year` (or sole year token when it
   clearly sits in the volume-year position — e.g. `Moon.Knight.1980.001`).
2. Else prefer `start_year` nearest to but **≤** parsed cover/`year` when only a cover year exists.
3. Else first exact title-key match (legacy thin client behavior) with **low** confidence → Review.

**Never** treat cover year alone as volume start year for multi-decade titles
(Moon Knight 1980 vs 2014 vs 2021, Batman, X-Men, Spider-Man, …).

## Confidence bands (ComicVine)

| Score | Action |
|-------|--------|
| ≥ 0.85 | Auto-organize (after CBZ gate) |
| 0.65–0.84 | Review — `comicvine_ambiguous` with top volume/issue candidates |
| &lt; 0.65 | Review — `comicvine_unmatched` (or keep parse-only low if no key) |

Inputs: title-key equality, `volume_year` hit, issue number present in volume, publisher
agreement when known. Numeric score lives on the match payload; catalog `confidence` stays
`high`/`low` for existing gates (`high` iff score ≥ 0.85 and series+issue filled).

## ComicInfo.xml required nodes

Librarian writes a full schema (empty nodes omitted when blank):

| Node | Source |
|------|--------|
| `Series` | CV volume name / parse series |
| `Number` | Issue (`18.1` allowed) |
| `Volume` | Volume start year (or CV volume number when only that exists) |
| `Title` | Issue title / story name |
| `Summary` | CV description (stripped HTML) |
| `Year` / `Month` / `Day` | Cover date |
| `Writer` / `Penciller` / `Inker` / `Colorist` / `CoverArtist` / `Letterer` | CV credits |
| `Publisher` | CV publisher |
| `PageCount` | Raster page count after remux |
| `Web` | CV site detail URL |
| `Notes` | `indexer guid: …; librarian: cv={volume_id}/{issue_id}; matched={iso}` |

Sidecar `ComicInfo.xml` beside the folder **and** the same XML embedded at the ZIP root of the CBZ.

## Dest layout (locked)

Root: `/data/media/library/comics` (`comics_root`). Librarian sole writer.

- Issues:
  `{Publisher}/{Series} ({VolumeYear})/{Series} v{VolumeYear} #{Issue} ({Year}).cbz`
- GN / TPB / one-shot:
  `{Publisher}/{Series} ({VolumeYear})/{Series} - {Subtitle} ({Year}).cbz`

Fallback when publisher unknown: `Unknown Publisher`. When volume year unknown: omit
`({VolumeYear})` / `v{VolumeYear}` segments and use `{Publisher}/{Series}/…` until Review
fills them (scan still accepts legacy `{Series}/{Issue}/` trees).

## Golden fixtures (≥15)

Inputs are Usenet-style stems (no extension). Expected tokens after normalize.

| # | Input | series | volume_year | issue | year | notes |
|---|-------|--------|-------------|-------|------|-------|
| 1 | `Saga.2012.001.Digital-Empire` | Saga | 2012 | 1 | 2012 | year-as-volume for Image Saga |
| 2 | `Saga.#54.(2022).c2c-Minutemen` | Saga | — | 54 | 2022 | hash+paren year; strip c2c/group |
| 3 | `Moon.Knight.1980.001.Digital` | Moon Knight | 1980 | 1 | 1980 | multi-decade — volume year wins |
| 4 | `Moon.Knight.2014.001.(2014)` | Moon Knight | 2014 | 1 | 2014 | distinct volume from #3 |
| 5 | `Batman.#18.1.(2024).no-ads` | Batman | — | 18.1 | 2024 | decimal issue |
| 6 | `Amazing.Spider-Man.Annual.2023.001` | Amazing Spider-Man | — | Annual 1 | 2023 | annual |
| 7 | `X-Men.v1.094.(1975)` | X-Men | — | 94 | 1975 | vol number ≠ start year |
| 8 | `Watchmen.#01.(1986).Megan` | Watchmen | — | 1 | 1986 | zero-pad issue → `1` |
| 9 | `Sandman.Overture.#1.(2013).CVR.B` | Sandman Overture | — | 1 | 2013 | variant → Notes |
| 10 | `Paper.Girls.001.(2015).Digital-Empire` | Paper Girls | — | 1 | 2015 | padded without hash |
| 11 | `Descender.Vol.01.Tin.Stars.(2015).TPB` | Descender | — | — | 2015 | TPB → format=tpb, subtitle Tin Stars |
| 12 | `Monstress.#18.(2021).HD-WebRip` | Monstress | — | 18 | 2021 | strip HD-WebRip |
| 13 | `The.Walking.Dead.#193.(2019)` | The Walking Dead | — | 193 | 2019 | leading article kept |
| 14 | `Invincible.Compendium.1.(2011)` | Invincible | — | — | 2011 | format=compendium / GN path |
| 15 | `Daredevil.1964.001.Digital-Glorith` | Daredevil | 1964 | 1 | 1964 | volume year + ripper strip |
| 16 | `Ultimate.Spider-Man.2024.001` | Ultimate Spider-Man | 2024 | 1 | 2024 | reboot year as volume |
| 17 | `Something.is.Killing.the.Children.#18.(2022)` | Something is Killing the Children | — | 18 | 2022 | long series name |

Fixture tests live in `tests/test_comic_normalize.py` and must stay value-based (exact token
equality). ComicVine HTTP is mocked in `tests/test_comicvine.py`; SQLite cache is real.

## Out of scope

- React Guided View / in-app ink reader
- ComicVine for magazines
- Writing outside `comics_root`
- Smart Map writing comics
