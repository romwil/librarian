"""File extension families shared by naming, identify, and organize."""

from __future__ import annotations

MEDIA_EXTENSIONS = {
    ".epub",
    ".pdf",
    ".mobi",
    ".azw3",
    ".kepub",
    ".cbz",
    ".cbr",
    ".cbt",
    ".m4b",
    ".mp3",
    ".flac",
    ".m4a",
    ".ogg",
    ".opus",
}
# Alternate ebook encodings of one title (SAB multi-format / Calibre).
BOOK_FORMAT_EXTENSIONS = {".epub", ".pdf", ".mobi", ".azw3", ".kepub"}
# Clear ebook encodings (not PDF — PDF is comic-or-book depending on siblings).
EBOOK_FORMAT_EXTENSIONS = {".epub", ".mobi", ".azw3", ".kepub"}
COMIC_ARCHIVE_EXTENSIONS = {".cbz", ".cbr", ".cbt"}
SIDECAR_NAMES = {"metadata.opf", "comicinfo.xml", "cover.jpg", "cover.png", "nfo"}
JUNK_EXTENSIONS = {".par2", ".nzb", ".nfo", ".sfv", ".srr", ".url"}
JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
ARCHIVE_EXTENSIONS = {".rar", ".7z"}
STEM_EXTENSIONS = MEDIA_EXTENSIONS | JUNK_EXTENSIONS | ARCHIVE_EXTENSIONS | {
    ".zip",
    ".gz",
    ".txt",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}
