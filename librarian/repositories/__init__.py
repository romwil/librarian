"""Repository mixins behind the ``librarian.db.Database`` facade.

| Module    | Owns                                                               |
|-----------|--------------------------------------------------------------------|
| catalog   | works, files, works_fts, Stacks browse/facets, search, suggestions |
| jobs      | download jobs and their timing history                             |
| wanted    | wanted requests, due/backoff ledger, tried release guids           |
| people    | users, invites, session epochs, per-user prefs                     |
| shelves   | Favorites, named shelves, reading progress                         |
| review    | bad releases, review audit, suggestions, cooldowns, app migrations |
"""

from librarian.repositories.catalog import CatalogRepository
from librarian.repositories.jobs import JobsRepository
from librarian.repositories.people import PeopleRepository
from librarian.repositories.review import ReviewRepository
from librarian.repositories.shelves import ShelvesRepository
from librarian.repositories.wanted import WantedRepository

__all__ = [
    "CatalogRepository",
    "JobsRepository",
    "PeopleRepository",
    "ReviewRepository",
    "ShelvesRepository",
    "WantedRepository",
]
