"""One name parser for releases, shelf layouts, and scanned files.

- ``release``: Usenet / SAB folder and file names (``parse_usenet_name``).
- ``library``: ``Author/Title (id)`` and Calibre volumes (``parse_library_volume``).
- ``comic`` / ``audiobook`` / ``magazine``: kind-specific token rules.
- ``tokens`` / ``isbn`` / ``extensions``: shared building blocks.
"""

from __future__ import annotations

from librarian.naming.audiobook import (
    AudiobookTokens,
    extract_asin,
    normalize_audiobook_name,
    tokens_for_identity,
)
from librarian.naming.book import parse_book_scene, strip_calibre_suffix
from librarian.naming.comic import (
    ComicTokens,
    comic_identity_fields,
    normalize_comic_name,
    parse_comic,
    scrub_comic_stem,
)
from librarian.naming.extensions import (
    ARCHIVE_EXTENSIONS,
    BOOK_FORMAT_EXTENSIONS,
    COMIC_ARCHIVE_EXTENSIONS,
    EBOOK_FORMAT_EXTENSIONS,
    JUNK_EXTENSIONS,
    JUNK_NAMES,
    MEDIA_EXTENSIONS,
    SIDECAR_NAMES,
    STEM_EXTENSIONS,
)
from librarian.naming.identity import Identity
from librarian.naming.isbn import (
    extract_isbn,
    isbn10_to_isbn13,
    isbn13_to_isbn10,
    isbn_match_keys,
    validated_isbn,
)
from librarian.naming.library import (
    library_file_fields,
    parse_library_volume,
    path_author_title,
    restore_path_punctuation,
    title_and_series,
)
from librarian.naming.magazine import parse_magazine
from librarian.naming.release import parse_usenet_name, release_file_fields
from librarian.naming.tokens import (
    filename_stem,
    looks_like_dump_title,
    tidy_title,
    usenet_basename,
)

__all__ = [
    "ARCHIVE_EXTENSIONS",
    "AudiobookTokens",
    "BOOK_FORMAT_EXTENSIONS",
    "COMIC_ARCHIVE_EXTENSIONS",
    "ComicTokens",
    "EBOOK_FORMAT_EXTENSIONS",
    "Identity",
    "JUNK_EXTENSIONS",
    "JUNK_NAMES",
    "MEDIA_EXTENSIONS",
    "SIDECAR_NAMES",
    "STEM_EXTENSIONS",
    "comic_identity_fields",
    "extract_asin",
    "extract_isbn",
    "filename_stem",
    "isbn10_to_isbn13",
    "isbn13_to_isbn10",
    "isbn_match_keys",
    "library_file_fields",
    "looks_like_dump_title",
    "normalize_audiobook_name",
    "normalize_comic_name",
    "parse_comic",
    "parse_library_volume",
    "parse_magazine",
    "parse_book_scene",
    "parse_usenet_name",
    "path_author_title",
    "release_file_fields",
    "restore_path_punctuation",
    "scrub_comic_stem",
    "strip_calibre_suffix",
    "tidy_title",
    "title_and_series",
    "tokens_for_identity",
    "usenet_basename",
    "validated_isbn",
]
