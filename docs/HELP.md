# Help

Librarian is a private **reading room** for the books, magazines, comics, audiobooks, and incoming music the household already owns — and a quiet door to request what’s missing.

## Library vs Search vs Find

**Library** is the product: The Hall, work pages, Favorites, Continue, and the area rails. It is what is already on the shelves.

**Search** looks only at those local shelves. The hero on The Hall and `/search` never hunt the rest of the world.

**Find** is not a top-level tab. After Search results (including no hits), **Find beyond the shelves** opens Find with your query (and kind, plus the kind-appropriate fields — author/title/ISBN, series/issue, or artist/album) already filled in, then looks outside the house. With no query, Find shows **Discover**: trending indexer category feeds for the kind chip you picked — empty Find is Discover, and **What's trending** on The Hall or idle Search opens it without searching first. Owners and ops Request from Find; that is where queue chips and gap **confirm** live. Extra Newznab hosts join NZBFinder on Find only — Search stays on the local stacks.

## Find extras

Find can query more than NZBFinder. Extra Newznab v2 hosts live in Settings; results show a muted host name. If one host fails, the others still appear.

**Discover** reads each host’s capabilities category tree (comics `7030`, magazines `7010`, other books `70xx`, audiobooks `3030`, music `3010`/`3040`/`3999`, and real subcats the indexer lists). Latest-in-category uses category RSS (`/rss/category?id=` on NZBFinder, then classic `/rss?t=` or `/api?t=search&cat=`). NZBFinder v2 search needs a real query, so Discover does not call empty-query v2. It does not scrape HTML and does not auto-queue SAB. Each rail is a short latest slice — click the category title or **See all** to open that feed (`/find?discover=7030`) and browse many more results with the same Request / peek chips.

**Bestsellers / curated lists** is a Find preset (`/find?preset=nyt&list=hardcover-fiction`). Hall and idle Find link to it. With a BYO LLM in Settings (OpenAI Chat Completions, Anthropic Messages, or Google Gemini `generateContent` — native APIs, not OpenAI shims), Librarian asks the model once for the chosen category — most recent, or the list closest to a date you pick — then matches each title against the local shelves (ISBN when the model returns a check-digit-valid one; otherwise title+author). ISBN is never invented. List responses are briefly cached under `/config/lists-cache`. Without an LLM the panel stays honest and empty. If the provider rate-limits (HTTP 429), the panel shows a clear wait message — not a raw status code — and shelves / Find keep working. Shelved titles deep-link to the work; missing ones can be multi-selected. **Request missing** Finds beyond for the ebook and the audiobook together, ranks hits with the BYO LLM when configured (otherwise title/author heuristic), remembers alternates on the slip, then calls `/api/request` for each real hit (owners/ops queue SAB; readers file Asked slips). LLM calls are process-serialized with Retry-After / exponential backoff; after a rate-limit, remaining chase titles degrade to heuristic without failing the batch. Guids are never invented — only chase hits are requested. Each chased row has a collapsed **Chase details** disclosure with conversation, query steps, the full accepted/rejected result set, and remembered alternates. An optional `nyt_books_api_key` remains as a soft-deprecated fallback path only.

**Find beyond / re-grab** also rank the full indexer result set the same way (one LLM call per search, not per hit), surface a collapsed search-details trail, and store candidates on the job for dud-primary fallback. Confirm-before-SAB is unchanged.

Owners can turn on **Show categories** in Settings. Then Discover and fielded Find also offer Movies, TV, and XXX if the indexer lists those feeds — Discover chips group under Newznab parents (Movies, Audio, TV, XXX, Books, …). Those extra kinds never become Hall works.

- **Movies:** Request queues SABnzbd in the Radarr-watched category (default `movies`), then tells Radarr to expect the title (`POST /api/v3/movie` with search off). When SAB finishes, Radarr gets `DownloadedMoviesScan`.
- **TV:** same with Sonarr (`series` add, then `DownloadedEpisodesScan`). SAB category default `tv`.
- **XXX:** SABnzbd default folder only. No *arr, no Hall card.

Without a Radarr/Sonarr key, a movie/TV Request still queues SAB and shows **Needs you** — Librarian does not pretend *arr was told.

Owners and ops can subscribe to a Newznab RSS (Find or Settings) for one Librarian kind. New items wait as **Asked** slips on Queue — confirm before SABnzbd. Librarian does not silently download a whole feed.

Optional Audiobookshelf URL and token in Settings match catalog audiobooks by ISBN, then author and title. That is a quiet **On the player** link, not a new admin skin, and it does not send audiobooks to the Plexamp music library. Plex remains the default audiobook target until you change it.

## The Hall

After sign-in you land on **The Hall**, not Settings. The hero is search (the stacks, not “then the world”). Rails below: **Continue** (volumes you opened), What’s New, Favorites, Books, Magazines, Comics, Audiobooks, Incoming Music. Owners and ops also see a **Gaps** rail. Opening a work leaves a bookmark on Continue; **Finished** means you have read it and clears that bookmark. Finished is not a download status. Audiobook Listen writes the same Continue progress (file + seconds), so in-progress listens sit on the Continue rail beside books.

Chrome stays Hall / Search / Favorites / You. Queue and Review are op links, not extra tabs.

## Search

One box, owned media only. Hits are what the house already has. Cover click opens a **peek**; Open full page goes to the work. Peek, Open, Favorite — no Request and no downloader chips on Search. Typing or loading `/search?q=…` never talks to SABnzbd.

Advanced fields morph with the kind chip (artist/album for music, series/issue for comics, and so on). Author, title, series, artist, album, and year offer **suggestions while you type** — shelves first, then an optional owner-refreshed cache under Settings. You can always type freeform; picking a suggestion just keeps labels tidy. ISBN and issue stay plain boxes.

## Find

From Search, **Find beyond the shelves** is the next step after a local query. Empty Find is **Discover** (trending feeds for the kind chip) — open it from Hall or idle Search via **What's trending**, without typing a search first. Find talks to NZBFinder, takes Request, and shows living job chips. The boxes change with the kind chip: books and magazines take title, author, and ISBN; comics take series and issue; music takes artist, album, and year; audiobooks take author and title. The same typeahead as Search helps fill those fields. Request remembers what you sought and which result you picked — the downloader’s filename is not the library title.

When indexer hits look like parts of one release (`01of32`, `Part 2 of 10`, `CD1`, `[01/44]`), Find **groups** them into a multipart card with a part grid, completeness (`3/32 · incomplete`), and multiselect. **Request** on the set still creates one job per NZB — select all available, clear, or ask for a single part. Incomplete sets say so; the indexer may simply not list every part.

- Owner / op: **Request** queues SABnzbd (Librarian kinds are identified as before). Movies/TV also tell Radarr/Sonarr to expect the grab. XXX stays in SAB’s default folder.
- Reader: **Request** files an “asked the house” slip. Nothing downloads until an owner or op confirms.

Librarian downloads the NZB with the indexer API key, then pushes the file to SABnzbd (`addfile`). It does **not** ask SAB to fetch a `getnzb` / `download` URL — those links drop their token before they leave Find, so SAB would only see **Unauthorized** or **URL Fetching failed**. If Queue shows that kind of failure, delete the bad rows in SAB history and Request again after this build. Discover browse and typeahead never queue SAB; only an explicit Request (or Queue confirm of an Asked slip) does.

### Five job words

Find and Queue speak household English. The downloader’s raw line (Verifying, and so on) stays on the Queue card for ops. If retrieval or unpack failed, that muted line is the real reason — not an empty Arrived shelf.

| Word | Meaning |
| --- | --- |
| **Asked** | A reader asked; it is not on the way yet |
| **On the way** | Fetching and filing — you can wait |
| **Arrived** | It landed on the shelves |
| **Needs you** | Something unexpected; open **Review** (unknown identify, extra files, convert fail, collision, missing *arr*, and so on). The files are here — the house isn’t sure how to shelve them. Not a Failed download. |
| **Failed** | It did not land — missing files, a damaged archive, or unpack that never finished |

Queue cards for **Needs you** show a short reason and **Open Review** (deep-link when the job already has a work). The NZB id stays muted ops detail. The title on the job is the title you asked for on Find. SABnzbd’s Usenet filename stays ops-only on Queue.

**Finished** is reading progress (you finished the book). **Promote** is for incoming music only: move the album into the Plexamp library. Those two words are not job chips.

## Review / Bagging area

A **slip** is a download (or Add-to-shelves dump) that identify/organize could not finish filing. Happy-path ISBN books do not stop here. Each slip shows what Librarian tried, what’s wrong, and what to do next.

| What’s wrong | What to do |
| --- | --- |
| **Unpack stuck** | SABnzbd left rar/7z archives — extract or repair in SAB, then Apply once audio/book files appear, or **Skip** |
| **No payload** | Folder empty or only junk (par2/nfo) — point Complete folder at readable media, or Skip |
| **Missing folder** | Path not on disk for this container — fix **SAB complete root** in Settings so `/downloads` maps under `/data`, paste the real folder, or Skip |
| **Identity / kind / extras / convert** | Fill or confirm the fields, then Apply |
| **Collision** | Destination already taken — Skip keeps the shelf copy; Apply will not overwrite (change identity or folder first) |

**About `…/complete/downloads/…`:** that path is normal when SAB’s complete root is `…/complete` and the job used a **downloads** category. It is not a doubled map by itself.

**Apply** files a ticket once the folder has media Librarian can read. **Skip** dismisses the slip without shelving.

## Gaps

Cards on The Hall are the *missing* set — honest holes between what you already own and what the catalog says belongs. Magazines stay local (`YYYY-MM` between the issues you have). Comics keep those integer holes and, with a Comic Vine key in Settings, fill the rest of the run. Books and audiobooks use Hardcover (token in Settings) then Open Library for series volumes. Music compares owned tracks to the MusicBrainz release and, when you already collect an artist, missing albums. **Confirm** before anything is queued lives on Find, not on a shelf browse. Clicking a gap opens Find with kind-appropriate fields already filled. Librarian never invents an ISBN, issue number, or MusicBrainz id.

## Music and audiobooks

Music organizes into Incoming (`library/incoming-music`), then **Promote** moves the album into the Plexamp library at `/data/media/music`. Audiobooks never go there.

**Listen** opens the Listening room on an audiobook work (HTML5 audio + Media Session, chapter skip when tags exist, Continue bookmark). Peek and the work page use **Listen** as the primary CTA — never Promote to Plexamp. **Open in player** appears when Audiobookshelf has matched the title, or as a soft Plex handoff when that is the audiobook target. With Audiobookshelf configured but unmatched, the note stays honest.

On a **book** work page (and peek when the detail has loaded), Librarian surfaces a companion audiobook when the same ISBN, title+author, or series index is already on the shelves (**Audiobook on the shelves** → Listen), or offers **Find audiobook** with kind=audiobook and title/author/ISBN prefilled. Books, comics, and magazines use **Read** for the in-browser reader (not Open); audiobooks keep Listen.

Plex has **no** dedicated Audiobooks library type. Point a Plex **Music** library (named e.g. “Audiobooks”) at `audiobooks_root` (`/data/media/library/audiobooks`), enable store track progress / long-form, and use Plexamp speed + skip on that library. Folder layout is `{Author}/{Title}/`. Keep audiobooks out of the music library root. Optional Audiobookshelf remains a catalog match link when configured. Hide Finished on music — albums are not “read.” Shared Automat folder ownership and the Plex Music filename rule: [automat-media-contract.md](automat-media-contract.md). Library cutover from old flat `/data/media/books`: [ops/LIBRARY_MIGRATE.md](ops/LIBRARY_MIGRATE.md).

## Covers, convert, indexer ping

Organized folders get a real cover when we can fetch one (indexer, Open Library ISBN, or the first comic page). CBR comics convert to CBZ with `unar` (in the image); PDF comics need `pdftoppm` on PATH or they stay in Review. On-demand extra formats use Calibre `ebook-convert` when installed — otherwise Download stays on the file we already have. Owners can **Ping NZBFinder** on Settings (opt-in live check; not CI). Extra Newznab hosts use the same v2 JSON shape. Audiobookshelf match is a Settings button plus a quiet work-page chip.

## Add to the shelves / Watch folder

Owners and ops can **Add to the shelves** from Settings (and a quiet Hall control). Browse `/data` or paste a path the container can see — this is not a browser upload of a whole library. Point at a **dump** (or a single file), not a Settings library root. If identify is sure, Librarian **moves and renames** into the proper Settings root. If not, the volume waits in Review (**Needs you**). Empty or unreadable dumps **Failed** with a reason (not just the folder name). A configured library root is refused — use **Scan the shelves** instead.

**Scan the shelves** is different: it walks the library roots, updates the catalog, and never moves files.

Owners can **Refresh suggestions from shelves** on Settings to rebuild the typeahead seed from what’s already owned (optional MusicBrainz expansion from owned artists via `?external=1`). First boot stays light — suggestions work from the live catalog without a multi-GB dump. Full MusicBrainz / Open Library dumps remain later.

A **Watch folder** (Settings) is an optional drop directory. New top-level files and folders are identified the same way, on the same in-process poll as SAB. It cannot be a library root, SAB’s complete folder, or the Smart Map inbox (`YouTubeDownload` / `YouTubeLibrary`). After a confident organize, the source is moved out so Watch does not pick it up again.

## Enrich and Goodreads

Owners can **Enrich the shelves** on Settings, or **Enrich** on a book/audiobook page. Hardcover (token in Settings) fills description, series, year, and cover when a volume is thin; Open Library is the fallback. Enrich never invents an ISBN — title-only matches do not write one.

**Import Goodreads CSV** on Settings takes a Goodreads shelf export. Rows with an ISBN match an existing book (ISBN-10 or ISBN-13) and land on Favorites. Unmatched ISBNs create a thin work (no file yet — use Find). Rows without an ISBN are skipped. There is no Goodreads login.
