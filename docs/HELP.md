# Help

Librarian is a private **reading room** for the books, magazines, comics, audiobooks, and incoming music the household already owns — and a quiet door to request what’s missing.

## The Hall

After sign-in you land on **The Hall**, not Settings. The hero is search. Rails below: **Continue** (volumes you opened), What’s New, Favorites, Books, Magazines, Comics, Audiobooks, Incoming Music. Owners and ops also see a **Gaps** rail. Opening a work leaves a bookmark on Continue; **Finished** clears it.

## Search

One box. Local FTS5 hits appear first (**In the stacks**). If you pause or press Enter, the same page can grow **Beyond the shelves** (NZBFinder). Cover click opens a **peek**; Open full page goes to `/works/:id`.

- Owner / op: **Request** queues SABnzbd at `downloader.sl`.
- Reader: **Request** files an “asked the house” slip. No SAB.

## Review

Unexpected identify results (unknown, extra files, convert fail, collision) go to the **bag**. Happy-path ISBN books do not. Apply writes the layout; Skip marks the work resolved.

## Gaps

Local v1: magazine `YYYY-MM` holes, comic issue-number holes, audiobook part/cd/disc holes, and music track-number holes between what you already own. Cards are the *missing* set. Confirm before anything is queued. Book series / MusicBrainz discography catalogs are later.

## Music and audiobooks

Music organizes into Incoming, then **Promote** copies the album layout to the Plexamp `music_root`. Audiobooks never go there. Default publish target is a Plex **Audiobooks** library (`audiobook_target=plex`).

## Covers, convert, indexer ping

Organized folders get a real `cover.jpg` when we can fetch one (indexer URL, Open Library ISBN, or CBZ page 1). CBR comics convert to CBZ with `unar` (in the image); PDF comics need `pdftoppm` on PATH or they stay in Review. On-demand EPUB/PDF/MOBI/AZW3/KEPUB uses Calibre `ebook-convert` when installed — otherwise Download stays on the canonical file. Owners can **Ping NZBFinder** on Settings (opt-in live caps; not CI).
