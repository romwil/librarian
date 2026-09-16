# Help

Librarian is a private **reading room** for the books, magazines, comics, audiobooks, and incoming music the household already owns — and a quiet door to request what’s missing.

## Library vs Search vs Find

**Library** is the product: The Hall, work pages, Favorites, Continue, and the area rails. It is what is already on the shelves.

**Search** looks only at those local shelves. The hero on The Hall and `/search` never hunt the rest of the world.

**Find** is not a top-level tab. After Search results (including no hits), **Find beyond the shelves** opens Find with your query (and kind, plus the kind-appropriate fields — author/title/ISBN, series/issue, or artist/album) already filled in, then looks outside the house. With no query, Find shows **Discover**: trending indexer category feeds for the kind chip you picked. Owners and ops Request from Find; that is where queue chips and gap **confirm** live. Extra Newznab hosts join NZBFinder on Find only — Search stays on the local stacks.

## Find extras

Find can query more than NZBFinder. Extra Newznab v2 hosts live in Settings; results show a muted host name. If one host fails, the others still appear.

**Discover** reads each host’s capabilities category tree (comics `7030`, magazines `7010`, other books `70xx`, audiobooks `3030`, music `3010`/`3040`/`3999`, and real subcats the indexer lists). Latest-in-category uses category RSS (`/rss/category?id=` on NZBFinder, then classic `/rss?t=` or `/api?t=search&cat=`). NZBFinder v2 search needs a real query, so Discover does not call empty-query v2. It does not scrape HTML and does not auto-queue SAB.

Owners can turn on **Show categories** in Settings. Then Discover and fielded Find also offer Movies, TV, and XXX if the indexer lists those feeds. Those extra kinds never become Hall works.

- **Movies:** Request queues SABnzbd in the Radarr-watched category (default `movies`), then tells Radarr to expect the title (`POST /api/v3/movie` with search off). When SAB finishes, Radarr gets `DownloadedMoviesScan`.
- **TV:** same with Sonarr (`series` add, then `DownloadedEpisodesScan`). SAB category default `tv`.
- **XXX:** SABnzbd default folder only. No *arr, no Hall card.

Without a Radarr/Sonarr key, a movie/TV Request still queues SAB and shows **Needs you** — Librarian does not pretend *arr was told.

Owners and ops can subscribe to a Newznab RSS (Find or Settings) for one Librarian kind. New items wait as **Asked** slips on Queue — confirm before SABnzbd. Librarian does not silently download a whole feed.

Optional Audiobookshelf URL and token in Settings match catalog audiobooks by ISBN, then author and title. That is a quiet **On the player** link, not a new admin skin, and it does not send audiobooks to the Plexamp music library. Plex remains the default audiobook target until you change it.

## The Hall

After sign-in you land on **The Hall**, not Settings. The hero is search (the stacks, not “then the world”). Rails below: **Continue** (volumes you opened), What’s New, Favorites, Books, Magazines, Comics, Audiobooks, Incoming Music. Owners and ops also see a **Gaps** rail. Opening a work leaves a bookmark on Continue; **Finished** means you have read it and clears that bookmark. Finished is not a download status.

Chrome stays Hall / Search / Favorites / You. Queue and Review are op links, not extra tabs.

## Search

One box, owned media only. Hits are what the house already has. Cover click opens a **peek**; Open full page goes to the work. Peek, Open, Favorite — no Request and no downloader chips on Search.

Advanced fields morph with the kind chip (artist/album for music, series/issue for comics, and so on). Author, title, series, artist, album, and year offer **suggestions while you type** — shelves first, then an optional owner-refreshed cache under Settings. You can always type freeform; picking a suggestion just keeps labels tidy. ISBN and issue stay plain boxes.

## Find

From Search, **Find beyond the shelves** is the next step. Find talks to NZBFinder, takes Request, and shows living job chips. With no query, **Discover** shows trending feeds for the kind chip. The boxes change with the kind chip: books and magazines take title, author, and ISBN; comics take series and issue; music takes artist, album, and year; audiobooks take author and title. The same typeahead as Search helps fill those fields. Request remembers what you sought and which result you picked — the downloader’s filename is not the library title.

- Owner / op: **Request** queues SABnzbd (Librarian kinds are identified as before). Movies/TV also tell Radarr/Sonarr to expect the grab. XXX stays in SAB’s default folder.
- Reader: **Request** files an “asked the house” slip. Nothing downloads until an owner or op confirms.

### Five job words

Find and Queue speak household English. The downloader’s raw line (Verifying, and so on) stays on the Queue card for ops. If retrieval or unpack failed, that muted line is the real reason — not an empty Arrived shelf.

| Word | Meaning |
| --- | --- |
| **Asked** | A reader asked; it is not on the way yet |
| **On the way** | Fetching and filing — you can wait |
| **Arrived** | It landed on the shelves |
| **Needs you** | Something unexpected; an owner or op should open Review |
| **Failed** | It did not land — missing files, a damaged archive, or unpack that never finished |

The title on the job is the title you asked for on Find. SABnzbd’s Usenet filename stays ops-only on Queue.

**Finished** is reading progress (you finished the book). **Promote** is for incoming music only: copy the album into the Plexamp library. Those two words are not job chips.

## Review

Unexpected identify results (unknown, extra files, convert fail, collision) go to the **bag**. Happy-path ISBN books do not. Apply writes the layout; Skip marks the work resolved.

## Gaps

Cards on The Hall are the *missing* set — honest holes between what you already own and what the catalog says belongs. Magazines stay local (`YYYY-MM` between the issues you have). Comics keep those integer holes and, with a Comic Vine key in Settings, fill the rest of the run. Books and audiobooks use Hardcover (token in Settings) then Open Library for series volumes. Music compares owned tracks to the MusicBrainz release and, when you already collect an artist, missing albums. **Confirm** before anything is queued lives on Find, not on a shelf browse. Clicking a gap opens Find with kind-appropriate fields already filled. Librarian never invents an ISBN, issue number, or MusicBrainz id.

## Music and audiobooks

Music organizes into Incoming, then **Promote** copies the album into the Plexamp library. Audiobooks never go there. Default publish target is a Plex Audiobooks library. Hide Finished on music — albums are not “read.” Shared Automat folder ownership and the Plex Music filename rule: [automat-media-contract.md](automat-media-contract.md).

## Covers, convert, indexer ping

Organized folders get a real cover when we can fetch one (indexer, Open Library ISBN, or the first comic page). CBR comics convert to CBZ with `unar` (in the image); PDF comics need `pdftoppm` on PATH or they stay in Review. On-demand extra formats use Calibre `ebook-convert` when installed — otherwise Download stays on the file we already have. Owners can **Ping NZBFinder** on Settings (opt-in live check; not CI). Extra Newznab hosts use the same v2 JSON shape. Audiobookshelf match is a Settings button plus a quiet work-page chip.

## Add to the shelves / Watch folder

Owners and ops can **Add to the shelves** from Settings (and a quiet Hall control). Browse `/data` or paste a path the container can see — this is not a browser upload of a whole library. If identify is sure, Librarian **moves and renames** into the proper Settings root. If not, the volume waits in Review (**Needs you**). Empty or unreadable dumps **Failed**.

**Scan the shelves** is different: it walks the library roots, updates the catalog, and never moves files.

Owners can **Refresh suggestions from shelves** on Settings to rebuild the typeahead seed from what’s already owned (optional MusicBrainz expansion from owned artists via `?external=1`). First boot stays light — suggestions work from the live catalog without a multi-GB dump. Full MusicBrainz / Open Library dumps remain later.

A **Watch folder** (Settings) is an optional drop directory. New top-level files and folders are identified the same way, on the same in-process poll as SAB. It cannot be a library root, SAB’s complete folder, or the Smart Map inbox (`YouTubeDownload` / `YouTubeLibrary`). After a confident organize, the source is moved out so Watch does not pick it up again.

## Enrich and Goodreads

Owners can **Enrich the shelves** on Settings, or **Enrich** on a book/audiobook page. Hardcover (token in Settings) fills description, series, year, and cover when a volume is thin; Open Library is the fallback. Enrich never invents an ISBN — title-only matches do not write one.

**Import Goodreads CSV** on Settings takes a Goodreads shelf export. Rows with an ISBN match an existing book (ISBN-10 or ISBN-13) and land on Favorites. Unmatched ISBNs create a thin work (no file yet — use Find). Rows without an ISBN are skipped. There is no Goodreads login.
