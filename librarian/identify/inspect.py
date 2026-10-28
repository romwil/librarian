"""Complete-folder checks: what payload, archives, and junk a download folder holds."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from librarian.identify.paths import (
    _unique_paths,
    path_layout_note,
    resolve_storage_path,
    usable_folder,
)
from librarian.kinds import KIND_AUDIOBOOK, KIND_BOOK, KIND_COMIC, KIND_MUSIC
from librarian.naming.extensions import (
    ARCHIVE_EXTENSIONS,
    BOOK_FORMAT_EXTENSIONS,
    COMIC_ARCHIVE_EXTENSIONS,
    EBOOK_FORMAT_EXTENSIONS,
    JUNK_EXTENSIONS,
    JUNK_NAMES,
    MEDIA_EXTENSIONS,
    SIDECAR_NAMES,
)
from librarian.naming.isbn import extract_isbn
from librarian.naming.tokens import AUDIO_PART, AUDIOBOOK_HINT, tidy_title
from librarian.review_reasons import (
    REVIEW_CONVERT,
    REVIEW_MISSING_FOLDER,
    REVIEW_NO_PAYLOAD,
    REVIEW_UNPACK_STUCK,
)


def _is_junk_file(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    if "__macosx" in parts:
        return True
    name = path.name.lower()
    if name in JUNK_NAMES or name in SIDECAR_NAMES:
        return True
    suffix = path.suffix.lower()
    if suffix in JUNK_EXTENSIONS:
        return True
    if name.endswith(".par2"):
        return True
    return False


def _is_archive_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in ARCHIVE_EXTENSIONS:
        return True
    if re.match(r"^\.r\d{2}$", suffix):
        return True
    return False


# Parent dirs with this many sibling volumes look like library/ingest roots,
# not a SAB release folder — never rglob them while suggesting a better path.
_LIBRARY_ROOT_CHILD_DIRS = 32
# Cap suggestion scans so a mistaken broad candidate cannot hang Review.
_SUGGEST_PAYLOAD_MAX_FILES = 400


def list_payload_files(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    if folder.is_file():
        if _is_junk_file(folder) or _is_archive_file(folder):
            return []
        return [folder] if folder.suffix.lower() in MEDIA_EXTENSIONS else []
    found: List[Path] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        if _is_junk_file(path) or _is_archive_file(path):
            continue
        if path.suffix.lower() in MEDIA_EXTENSIONS:
            found.append(path)
    return found


def _looks_like_library_root(folder: Path) -> bool:
    """True when a folder holds many volume dirs (ingest dump / library root)."""
    if not folder.is_dir():
        return False
    try:
        child_dirs = 0
        for child in folder.iterdir():
            if not child.is_dir():
                continue
            child_dirs += 1
            if child_dirs >= _LIBRARY_ROOT_CHILD_DIRS:
                return True
    except OSError:
        return False
    return False


def _folder_has_payload_quick(folder: Path, *, max_files: int = _SUGGEST_PAYLOAD_MAX_FILES) -> bool:
    """True if readable media exists; stops early and never sorts the whole tree."""
    if not folder.exists():
        return False
    if folder.is_file():
        if _is_junk_file(folder) or _is_archive_file(folder):
            return False
        return folder.suffix.lower() in MEDIA_EXTENSIONS
    scanned = 0
    try:
        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            scanned += 1
            if scanned > max_files:
                return False
            if _is_junk_file(path) or _is_archive_file(path):
                continue
            if path.suffix.lower() in MEDIA_EXTENSIONS:
                return True
    except OSError:
        return False
    return False


def inspect_complete_folder(folder: Path) -> Dict[str, Any]:
    """Classify a SAB complete folder: payload vs leftover archives vs junk."""
    if not usable_folder(folder) or not Path(folder).exists():
        return {
            "payload": [],
            "archives": [],
            "junk": [],
            "problem": REVIEW_MISSING_FOLDER,
        }
    root = Path(folder)
    if root.is_file():
        files = [root]
    else:
        files = [path for path in sorted(root.rglob("*")) if path.is_file()]
    payload: List[Path] = []
    archives: List[Path] = []
    junk: List[Path] = []
    for path in files:
        if _is_junk_file(path):
            junk.append(path)
        elif _is_archive_file(path):
            archives.append(path)
        elif path.suffix.lower() in MEDIA_EXTENSIONS:
            payload.append(path)
        else:
            junk.append(path)
    problem: Optional[str] = None
    if payload:
        problem = None
    elif archives:
        problem = REVIEW_UNPACK_STUCK
    else:
        problem = REVIEW_NO_PAYLOAD
    return {
        "payload": payload,
        "archives": archives,
        "junk": junk,
        "problem": problem,
    }


def suggest_payload_folder(folder: Path) -> Optional[Path]:
    """Nearby folder that already has readable media (parent or nested child only)."""
    if not usable_folder(folder):
        return None
    root = Path(folder)
    candidates: List[Path] = []
    parent = root.parent if root.is_absolute() or str(root.parent) not in {"", "."} else None
    if parent is not None and parent.is_dir() and parent.name not in {"", ".", "/"}:
        # Prefer a same-named child under parent, then parent itself if it has media.
        same = parent / root.name
        if same.is_dir() and same != root:
            candidates.append(same)
        candidates.append(parent)
    if root.is_dir():
        try:
            for child in sorted(root.iterdir()):
                if child.is_dir():
                    candidates.append(child)
        except OSError:
            pass
    for candidate in _unique_paths(candidates):
        try:
            if root.exists() and candidate.resolve() == root.resolve():
                continue
        except OSError:
            pass
        # Do not suggest a broad complete/downloads root that happens to contain other albums.
        if candidate.name in {"complete", "downloads", "usenet", "data", "media"}:
            continue
        # Ingest dumps (e.g. /data/media/newlib with 1000+ volumes) must not be rglob'd.
        if _looks_like_library_root(candidate):
            continue
        if _folder_has_payload_quick(candidate):
            return candidate
    return None


def _diagnosis_path_clear(folder: Path) -> bool:
    try:
        from librarian.slip_gate import folder_is_path_clear
    except Exception:
        return False
    try:
        return bool(folder_is_path_clear(Path(folder)))
    except OSError:
        return False


def diagnose_review_folder(folder: Path, complete_root: str = "") -> Dict[str, Any]:
    """Live diagnosis for a Review slip: what we checked, what’s wrong, optional better path."""
    raw = Path(folder) if usable_folder(folder) else Path()
    resolved = resolve_storage_path(raw, complete_root) if usable_folder(raw) else raw
    inspection = inspect_complete_folder(resolved)
    problem = inspection.get("problem")
    # Only hunt for a better path when this folder itself has no usable media.
    # Always-on suggest used to rglob library parents (e.g. newlib) and hang GET /api/review.
    suggested: Optional[Path] = None
    if problem:
        suggested = suggest_payload_folder(resolved)
        if suggested is None and usable_folder(raw) and resolved != raw:
            suggested = suggest_payload_folder(raw)
    payload = inspection.get("payload") or []
    archives = inspection.get("archives") or []
    junk = inspection.get("junk") or []
    par2_count = sum(1 for path in junk if Path(path).name.lower().endswith(".par2"))
    looked_for = "book (epub/pdf), comic (cbz/cbr), or audio (flac/mp3/m4a/m4b) files"
    empty_dir = False
    if problem == REVIEW_NO_PAYLOAD and resolved.exists() and resolved.is_dir():
        try:
            empty_dir = not any(resolved.iterdir())
        except OSError:
            empty_dir = False
    if problem == REVIEW_MISSING_FOLDER:
        tried = f"Looked for a complete folder at {resolved or raw or '(empty)'}."
    elif problem == REVIEW_UNPACK_STUCK:
        sidecar = f"(also {len(junk)} junk/sidecar file(s)"
        if par2_count:
            sidecar += f", including {par2_count} PAR2 recovery file(s)"
        sidecar += ")"
        tried = (
            f"Opened {resolved}. Found {len(archives)} archive file(s) and no readable media "
            f"{sidecar}."
        )
        if par2_count:
            tried += (
                " Archives may be incomplete or checksum-damaged — "
                "Repair runs par2 then unpack; Retry shelves if media appears."
            )
        else:
            tried += (
                " No PAR2 recovery files here — extract manually, fix in SABnzbd, "
                "or Request a new version."
            )
    elif problem == REVIEW_NO_PAYLOAD and empty_dir:
        tried = f"Opened {resolved}. The folder is empty."
    elif problem == REVIEW_NO_PAYLOAD:
        tried = f"Opened {resolved}. Found {len(junk)} non-media file(s) and no {looked_for}."
    else:
        tried = f"Opened {resolved}. Found {len(payload)} readable file(s) this Librarian can shelve."
    dump_meta = collection_dump_meta([Path(path) for path in payload])
    if dump_meta.get("collection_dump") and not problem:
        n = int(dump_meta.get("distinct_title_count") or 0)
        tried = (
            f"Opened {resolved}. Found {len(payload)} readable file(s) across "
            f"{n} different title name(s) — this looks like a multi-title collection dump, "
            f"not one book with leftover junk."
        )
    return {
        "path": str(resolved) if usable_folder(resolved) else str(raw or ""),
        "resolved_path": str(resolved) if usable_folder(resolved) else "",
        "problem": problem,
        "payload_count": len(payload),
        "archive_count": len(archives),
        "junk_count": len(junk),
        "par2_count": par2_count,
        "looked_for": looked_for,
        "tried": tried,
        "path_note": path_layout_note(resolved if usable_folder(resolved) else raw),
        "suggested_folder": str(suggested) if suggested is not None else None,
        "collection_dump": bool(dump_meta.get("collection_dump")),
        "distinct_title_count": int(dump_meta.get("distinct_title_count") or 0),
        "path_clear": _diagnosis_path_clear(resolved if usable_folder(resolved) else raw),
    }


def _kind_from_payload(files: Sequence[Path], folder: Path) -> str:
    suffixes = {path.suffix.lower() for path in files}
    names = " ".join([folder.name, *(path.name for path in files)]).lower()
    # Comic archives win only when no clear ebook encodings share the payload.
    # Mixed comic+ebook is handled by partition/split — never blend as comic.
    if suffixes & COMIC_ARCHIVE_EXTENSIONS and not (suffixes & EBOOK_FORMAT_EXTENSIONS):
        return KIND_COMIC
    if suffixes & {".m4b"} or AUDIOBOOK_HINT.search(names):
        return KIND_AUDIOBOOK
    if suffixes & {".flac", ".mp3", ".m4a", ".ogg", ".opus"} and ".epub" not in suffixes:
        return KIND_MUSIC
    if suffixes & EBOOK_FORMAT_EXTENSIONS:
        return KIND_BOOK
    if suffixes == {".pdf"}:
        return KIND_BOOK
    if suffixes & COMIC_ARCHIVE_EXTENSIONS:
        return KIND_COMIC
    return ""


def is_mixed_comic_ebook_payload(files: Sequence[Path]) -> bool:
    """True when a volume holds both comic archives and clear ebook encodings.

    Those are separate works (comic adaptation vs prose book), never alternate
    formats of one title. PDF alone does not trigger this — PDF+cbz stays comic.
    """
    suffixes = {path.suffix.lower() for path in files}
    return bool(suffixes & COMIC_ARCHIVE_EXTENSIONS) and bool(suffixes & EBOOK_FORMAT_EXTENSIONS)


def partition_comic_ebook_files(files: Sequence[Path]) -> Dict[str, List[Path]]:
    """Split media into comic archives vs ebook encodings (PDF follows ebooks when mixed)."""
    comics: List[Path] = []
    ebooks: List[Path] = []
    pdfs: List[Path] = []
    other: List[Path] = []
    for path in files:
        suffix = path.suffix.lower()
        if suffix in COMIC_ARCHIVE_EXTENSIONS:
            comics.append(path)
        elif suffix in EBOOK_FORMAT_EXTENSIONS:
            ebooks.append(path)
        elif suffix == ".pdf":
            pdfs.append(path)
        else:
            other.append(path)
    if comics and ebooks:
        return {"comic": comics, "book": ebooks + pdfs, "other": other}
    if comics:
        return {"comic": comics + pdfs, "book": [], "other": other + ebooks}
    return {"comic": [], "book": ebooks + pdfs, "other": other}


def ingest_targets_for_mixed_payload(files: Sequence[Path]) -> List[Path]:
    """Paths to enqueue when a leaf folder mixed comics with ebooks.

    Each comic archive is its own volume. Ebook encodings that share a
    normalized stem stay one volume (representative file; siblings expand later).
    """
    parts = partition_comic_ebook_files(files)
    targets: List[Path] = list(parts.get("comic") or [])
    book_groups: Dict[str, List[Path]] = {}
    for path in parts.get("book") or []:
        key = _normalized_payload_stem(path) or path.stem.lower()
        book_groups.setdefault(key, []).append(path)
    for group in book_groups.values():
        ordered = sorted(group, key=lambda item: item.name.lower())
        targets.append(ordered[0])
    targets.extend(parts.get("other") or [])
    return targets


def ingest_targets_for_multi_title_payload(files: Sequence[Path]) -> List[Path]:
    """One ingest target per distinct title stem in a flat multi-book dump.

    NYT / Usenet Fiction folders often hold dozens of ``Title - Author.epub``
    siblings. Clear-extra and ingest must not treat that as one volume — pick a
    representative file per stem; ``expand_organize_payload`` pulls same-stem
    multi-format siblings later.
    """
    groups: Dict[str, List[Path]] = {}
    for path in files:
        key = _normalized_payload_stem(path) or path.stem.lower()
        groups.setdefault(key, []).append(path)
    targets: List[Path] = []
    for key in sorted(groups.keys()):
        ordered = sorted(
            groups[key],
            key=lambda item: (
                0 if item.suffix.lower() == ".epub" else 1,
                item.name.lower(),
            ),
        )
        targets.append(ordered[0])
    return targets


def match_payload_files_to_identity(
    files: Sequence[Path],
    identity: Mapping[str, Any],
) -> List[Path]:
    """Return media files in ``files`` that belong to the confirmed Review identity.

    Used when Apply peels one volume out of a multi-title dump (extra_files).
    Matches ISBN-in-name, normalized title stem, or title substring in the stem;
    then expands to same-stem multi-format siblings.
    """
    title = tidy_title(str(identity.get("title") or ""))
    isbn = extract_isbn(str(identity.get("isbn") or "")) or ""
    title_norm = _normalized_payload_stem(Path(f"{title}.epub")) if title else ""
    title_l = title.lower()
    hits: List[Path] = []
    for path in files:
        stem_norm = _normalized_payload_stem(path)
        name_digits = re.sub(r"[^0-9]", "", path.name)
        if isbn and isbn in name_digits:
            hits.append(path)
            continue
        if title_norm and stem_norm == title_norm:
            hits.append(path)
            continue
        if title_l and title_l in path.stem.lower():
            hits.append(path)
    if not hits:
        return []
    stems = {_normalized_payload_stem(path) for path in hits}
    stems.discard("")
    return sorted(
        [path for path in files if _normalized_payload_stem(path) in stems],
        key=lambda item: item.name.lower(),
    )


def unexpected_extra_files(files: Sequence[Path]) -> bool:
    """Public: folder looks like multiple distinct works (not one multi-format book)."""
    return _unexpected_extra_files(files)


def collection_dump_meta(files: Sequence[Path]) -> Dict[str, Any]:
    """Household signal: flat/multi-stem dump vs one book with alternate formats.

    NYT Fiction / Usenet collection folders have many distinct title stems. That is
    not "extra junk beside one download" — Clear / ingest should expand per title.
    Mixed comic+ebook is a different repair path and is not flagged here.
    """
    payload = [Path(path) for path in files]
    if is_mixed_comic_ebook_payload(payload):
        return {"collection_dump": False, "distinct_title_count": 0}
    if not _unexpected_extra_files(payload):
        return {"collection_dump": False, "distinct_title_count": 0}
    stems = {_normalized_payload_stem(path) for path in payload}
    stems.discard("")
    count = len(stems)
    return {"collection_dump": count >= 2, "distinct_title_count": count}


def expand_organize_payload(target: Path) -> List[Path]:
    """Media files for identify/organize.

    When the target is a single ebook file, include same-stem ebook siblings in
    the same folder (Calibre multi-format) but never comic archives — so a mass
    import that split a mixed folder still shelves epub+azw3 as one book.
    """
    if target.is_file():
        if _is_junk_file(target) or _is_archive_file(target):
            return []
        suffix = target.suffix.lower()
        if suffix not in MEDIA_EXTENSIONS:
            return []
        if suffix in EBOOK_FORMAT_EXTENSIONS or suffix == ".pdf":
            stem = _normalized_payload_stem(target)
            siblings: List[Path] = []
            try:
                for child in target.parent.iterdir():
                    if not child.is_file():
                        continue
                    child_suffix = child.suffix.lower()
                    if child_suffix not in EBOOK_FORMAT_EXTENSIONS and child_suffix != ".pdf":
                        continue
                    if _normalized_payload_stem(child) != stem:
                        continue
                    siblings.append(child)
            except OSError:
                return [target]
            return sorted(siblings or [target], key=lambda item: item.name.lower())
        return [target]
    return list_payload_files(target)


def _normalized_payload_stem(path: Path) -> str:
    """Collapse Calibre/Usenet name noise so epub+mobi of one title match."""
    stem = path.stem
    # Calibre: "Title - Author"
    if " - " in stem:
        stem = stem.split(" - ", 1)[0]
    text = stem.lower().replace(".", " ").replace("_", " ")
    text = re.sub(r"[^a-z0-9\s]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _compatible_alternate_formats(files: Sequence[Path]) -> bool:
    """True when every media file is an alternate ebook encoding of one title."""
    if len(files) <= 1:
        return True
    suffixes = {path.suffix.lower() for path in files}
    if not suffixes or not suffixes <= BOOK_FORMAT_EXTENSIONS:
        return False
    stems = {_normalized_payload_stem(path) for path in files}
    stems.discard("")
    return len(stems) == 1


def _unexpected_extra_files(files: Sequence[Path]) -> bool:
    """True when the folder looks like multiple distinct works (not one multi-format book)."""
    if len(files) <= 1:
        return False
    if all(
        AUDIO_PART.search(path.name) or path.suffix.lower() in {".mp3", ".m4b", ".flac"} for path in files
    ):
        return False
    if _compatible_alternate_formats(files):
        return False
    return True


def expected_payload_ok(kind: str, files: Sequence[Path]) -> Optional[str]:
    if not files:
        return REVIEW_NO_PAYLOAD
    suffixes = {path.suffix.lower() for path in files}
    if kind == KIND_COMIC and ".cbr" in suffixes and ".cbz" not in suffixes:
        return REVIEW_CONVERT
    if kind == KIND_BOOK and suffixes == {".pdf"}:
        return REVIEW_CONVERT
    return None

