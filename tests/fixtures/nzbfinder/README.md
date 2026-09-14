# NZBFinder v2 fixtures (secret-stripped)

Captured from `https://nzbfinder.ws/api/v2` with User-Agent
`Librarian/0.1 (Automat; +https://github.com/romwil/librarian)`.

**Do not commit API tokens. Do not re-fetch these live.** Auth belongs in env / local settings only.

| File | Request |
| --- | --- |
| `capabilities.json` | `GET /api/v2/capabilities` (public) |
| `books-linux.json` | `GET /api/v2/books?title=linux&limit=2` |
| `search-magazine.json` | `GET /api/v2/search?query=linux&cat=7010&limit=1` |
| `details-linux.json` | `GET /api/v2/details?id=<guid>` (first books hit) |

Download links keep only `id=…nzb`. Category → kind lives in `librarian/indexers/kind_map.py`.
