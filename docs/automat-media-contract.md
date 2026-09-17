# Automat media contract

Household layout for Librarian (`:8793`) and Smart Map (`:8790`) on the shared `/data` mount (`/mnt/user/data`). This is written truth for paths, filenames, tags, and inbox boundaries. It is **not** a shared Python package — do not extract `automat-media`.

**This product (Librarian):** organizes Usenet / watch payloads into `library/incoming-music`, **Promote**s whole album folders into `music_root`, and is the only writer of `library/audiobooks` (plus books / magazines / comics under `library/`). It does not write `YouTubeLibrary` or use `YouTubeDownload` as `watch_root`.

Sibling copy: Smart Map `docs/automat-media-contract.md` (same standards).

## Paths and ownership

| Path | Owner | Layout |
|------|--------|--------|
| `/data/media/library/incoming-music` | Librarian | `{Artist}/{Album}/` then **Promote** the whole folder to `music_root` |
| `/data/media/music` | Shared filesystem: Librarian album Promote + Smart Map YouTube/inbox audio confirm | `{Artist}/{Album}/` — **never audiobooks** |
| `/data/media/library/audiobooks` | Librarian only | `{Author}/{Title}/` |
| `/data/media/library/books` | Librarian only | `{Author}/{Title}/` |
| `/data/media/library/magazines` | Librarian only | `{Series\|Title}/{YYYY-MM}/` |
| `/data/media/library/comics` | Librarian only | `{Series}/{Issue}/` |
| `/data/media/YouTubeLibrary` | Smart Map only | existing channel/title layout |
| `/data/media/YouTubeDownload` | Smart Map inbox | Librarian `watch_root` must not be this or library roots |

`/data/media/music` is a **shared filesystem**, not a shared workflow. Librarian owns Usenet-sourced album folders (incoming → Promote). Smart Map owns YouTubeDownload-sourced tracks (operator confirm → move). Neither app calls the Plex API; Plex scans these folders.

Legacy flat roots (`/data/media/books`, `/data/media/audiobooks`, `/data/media/incoming-music`, …) may still exist on disk during cutover. New defaults and Settings point at `library/*`. Operator migrate: [ops/LIBRARY_MIGRATE.md](ops/LIBRARY_MIGRATE.md).

## Filename rule (locked)

Preserve the **original filename** inside `{Artist}/{Album}/`.

Smart Map (and Librarian single-track join) may use `{NN} - {Title}{ext}` **only when a trustworthy track number and title tag exist**; otherwise keep the source name. Do not rename to a Usenet dump. Sanitize path parts (no `/`, no trailing dots). `NN` is zero-padded to two digits.

Trustworthy means **embedded tags** (or an operator-supplied tag dict), not filename parse, not a YouTube playlist index.

## Tag precedence

embedded tags > sidecar (`.info.json` / OPF / ComicInfo) > folder name > filename parse.

Librarian never invents an ISBN or MusicBrainz id. Smart Map never invents TMDB/TVDB ids into filesystem metadata.

## Spoken-word

`.m4b`, or `audiobook` / `unabridged` in the name → **not** Plex Music. Librarian routes those to `audiobooks_root` under `library/`. Smart Map keeps `.m4b` out of `AUDIO_EXTENSIONS` so it cannot be classified as music.

## Inbox boundaries

Smart Map `browse_root` ≠ Librarian `books_root` / `comics_root` / `audiobooks_root` / `incoming_music_root` / `music_root` / `watch_root`.

Librarian ingest already forbids watching library roots and SAB complete. `watch_root` must also not be `YouTubeDownload` or `YouTubeLibrary`.

## Fail-closed IDs

| App | Must not invent |
|-----|-----------------|
| Librarian | ISBN, MusicBrainz id (MBID) |
| Smart Map | TMDB / TVDB ids in NFO or other filesystem metadata |

LLM assist may fill titles; it does not mint catalog ids that were not in evidence.

## Who writes here

| Writer | Writes | Does not write |
|--------|--------|----------------|
| Librarian | `library/incoming-music` (organize), `music` (Promote whole album), `library/audiobooks`, `library/books` / magazines / comics | `YouTubeLibrary`, `YouTubeDownload` |
| Smart Map | `YouTubeDownload` (inbox read + move-out on confirm), `YouTubeLibrary` (video publish), `music` (per-file confirm) | `library/incoming-music`, `library/audiobooks`, `library/books` / comics / magazines |

Do not merge the two apps. Do not share NZBFinder/SAB or Smart Map’s TV/movie/YouTube video pipeline.
