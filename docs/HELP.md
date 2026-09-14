# Help

Librarian is a private **reading room** for the books, magazines, comics, audiobooks, and incoming music the household already owns — and a quiet door to request what’s missing.

## The Hall

After sign-in you land on **The Hall**, not Settings. The hero is search. Rails below: What’s New, Favorites, Books, Magazines, Comics, Audiobooks, Incoming Music. Owners and ops also see a **Gaps** rail.

## Search

One box. Local FTS5 hits appear first (**In the stacks**). If you pause or press Enter, the same page can grow **Beyond the shelves** (NZBFinder). Cover click opens a **peek**; Open full page goes to `/works/:id`.

- Owner / op: **Request** queues SABnzbd at `downloader.sl`.
- Reader: **Request** files an “asked the house” slip. No SAB.

## Review

Unexpected identify results (unknown, extra files, convert fail, collision) go to the **bag**. Happy-path ISBN books do not. Apply writes the layout; Skip marks the work resolved.

## Gaps

Local v1: magazine `YYYY-MM` holes and comic issue-number holes between what you already own. Cards are the *missing* set. Confirm before anything is queued.

## Music and audiobooks

Music organizes into Incoming, then **Promote** copies the album layout to the Plexamp `music_root`. Audiobooks never go there. Default publish target is a Plex **Audiobooks** library (`audiobook_target=plex`).
