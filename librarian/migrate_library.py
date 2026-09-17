"""Blend Calibre / flat book trees into ``library/books`` as ``{Author}/{Title}/``.

Fail-closed: dry-run by default from the CLI. Prefer copy-then-cutover.
Collisions never overwrite — they are reported for Review.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from librarian.identify import safe_path_part
from librarian.metadata import read_folder_metadata

# Calibre title folders end with " (1234)".
_CALIBRE_ID_SUFFIX = re.compile(r"\s+\((\d+)\)\s*$")

BOOK_EXTENSIONS = (
    ".epub",
    ".azw3",
    ".azw",
    ".mobi",
    ".pdf",
    ".cbz",
    ".cbr",
    ".txt",
    ".fb2",
)
SIDECAR_NAMES = frozenset(
    {
        "cover.jpg",
        "cover.jpeg",
        "cover.png",
        "metadata.opf",
        "comicinfo.xml",
    }
)

# Skip Calibre container junk and non-shelf trees under a books dump.
SKIP_DIR_NAMES = frozenset(
    {
        ".xdg",
        ".config",
        ".calnotes",
        ".trash",
        ".ds_store",
        "ssl",
        "incoming",
        "__macosx",
    }
)

# Prefer EPUB as the Reading Room canonical; Kindle stays as secondary download.
CANONICAL_ORDER = (".epub", ".pdf", ".cbz", ".azw3", ".azw", ".mobi", ".fb2", ".txt")

DEFAULT_LIBRARY_SIBLINGS = (
    "books",
    "magazines",
    "comics",
    "audiobooks",
    "incoming-music",
)


@dataclass
class MigrateAction:
    action: str  # copy | skip | collision | junk | empty
    source: str
    dest: str = ""
    author: str = ""
    title: str = ""
    isbn: str = ""
    reason: str = ""
    files: List[str] = field(default_factory=list)


@dataclass
class MigrateReport:
    dry_run: bool
    source_root: str
    dest_root: str
    actions: List[MigrateAction] = field(default_factory=list)
    created_roots: List[str] = field(default_factory=list)

    def counts(self) -> Dict[str, int]:
        tallies: Dict[str, int] = {}
        for item in self.actions:
            tallies[item.action] = tallies.get(item.action, 0) + 1
        return tallies

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "source_root": self.source_root,
            "dest_root": self.dest_root,
            "counts": self.counts(),
            "created_roots": list(self.created_roots),
            "actions": [asdict(item) for item in self.actions],
        }


def strip_calibre_id(name: str) -> str:
    """Remove a trailing Calibre ``(id)`` from a folder or stem."""
    text = str(name or "").strip()
    return _CALIBRE_ID_SUFFIX.sub("", text).strip() or text


def is_junk_dir(path: Path) -> bool:
    name = path.name.strip().lower()
    if name in SKIP_DIR_NAMES or name.startswith("."):
        return True
    # Calibre library root noise
    if name in {"metadata.db", "metadata_db_prefs_backup.json"}:
        return True
    return False


def library_root_defaults(media_root: Path) -> Dict[str, Path]:
    base = Path(media_root) / "library"
    return {
        "books": base / "books",
        "magazines": base / "magazines",
        "comics": base / "comics",
        "audiobooks": base / "audiobooks",
        "incoming-music": base / "incoming-music",
    }


def create_library_roots(
    media_root: Path,
    *,
    dry_run: bool = True,
    siblings: Sequence[str] = DEFAULT_LIBRARY_SIBLINGS,
) -> List[str]:
    """Ensure ``media_root/library/{siblings}`` exist. Returns paths created or would-create."""
    created: List[str] = []
    root = Path(media_root) / "library"
    wanted = list(siblings) or list(DEFAULT_LIBRARY_SIBLINGS)
    for name in wanted:
        path = root / name
        if path.is_dir():
            continue
        created.append(str(path))
        if not dry_run:
            path.mkdir(parents=True, exist_ok=True)
    return created


def _book_files(folder: Path) -> List[Path]:
    files: List[Path] = []
    try:
        children = list(folder.iterdir())
    except OSError:
        return files
    for child in children:
        if not child.is_file():
            continue
        suffix = child.suffix.lower()
        if suffix in BOOK_EXTENSIONS or child.name.lower() in SIDECAR_NAMES:
            files.append(child)
    return files


def _pick_canonical(files: Sequence[Path]) -> Optional[Path]:
    by_suffix: Dict[str, Path] = {}
    for path in files:
        suffix = path.suffix.lower()
        if suffix in BOOK_EXTENSIONS and suffix not in by_suffix:
            by_suffix[suffix] = path
    for suffix in CANONICAL_ORDER:
        if suffix in by_suffix:
            return by_suffix[suffix]
    return None


def _identity_from_folder(
    folder: Path,
    *,
    author_hint: str,
    title_hint: str,
    read_opf: bool = True,
) -> Dict[str, str]:
    meta: Dict[str, Any] = {}
    if read_opf:
        # OPF is useful for ISBN / tidy titles, but expensive on network mounts.
        meta = read_folder_metadata(folder)
    author = str(meta.get("author") or author_hint or "").strip()
    title = strip_calibre_id(str(meta.get("title") or title_hint or "").strip())
    if not title:
        title = strip_calibre_id(title_hint) or "Untitled"
    if not author:
        author = author_hint or "Unknown Author"
    return {
        "author": safe_path_part(author, fallback="Unknown Author"),
        "title": safe_path_part(title, fallback="Untitled"),
        "isbn": str(meta.get("isbn") or "").strip(),
    }


def _dest_isbn(dest_dir: Path) -> str:
    if not dest_dir.is_dir():
        return ""
    meta = read_folder_metadata(dest_dir)
    return str(meta.get("isbn") or "").strip()


def _dest_has_books(dest_dir: Path) -> bool:
    if not dest_dir.is_dir():
        return False
    return any(p.suffix.lower() in BOOK_EXTENSIONS for p in _book_files(dest_dir))


def discover_calibre_book_folders(calibre_library: Path) -> Iterable[Tuple[Path, str, str]]:
    """Yield ``(folder, author_name, title_name)`` under a Calibre Library root."""
    root = Path(calibre_library)
    if not root.is_dir():
        return
    try:
        authors = sorted(p for p in root.iterdir() if p.is_dir() and not is_junk_dir(p))
    except OSError:
        return
    for author_dir in authors:
        try:
            titles = sorted(p for p in author_dir.iterdir() if p.is_dir() and not is_junk_dir(p))
        except OSError:
            continue
        for title_dir in titles:
            yield title_dir, author_dir.name, strip_calibre_id(title_dir.name)


def discover_flat_author_title(root: Path) -> Iterable[Tuple[Path, str, str]]:
    """Yield already-Librarian ``{Author}/{Title}/`` folders under *root*."""
    base = Path(root)
    if not base.is_dir():
        return
    try:
        authors = sorted(p for p in base.iterdir() if p.is_dir() and not is_junk_dir(p))
    except OSError:
        return
    for author_dir in authors:
        # Skip nested Calibre / Archive dumps when scanning a mixed books root.
        if author_dir.name in {"LonesomeLib", "Archive Historical", "newlib", "Calibre Library"}:
            continue
        try:
            titles = sorted(p for p in author_dir.iterdir() if p.is_dir() and not is_junk_dir(p))
        except OSError:
            continue
        for title_dir in titles:
            if _book_files(title_dir):
                yield title_dir, author_dir.name, strip_calibre_id(title_dir.name)


def find_calibre_library(source_root: Path) -> Optional[Path]:
    """Locate ``…/Calibre Library`` under a LonesomeLib-style tree."""
    base = Path(source_root)
    direct = base / "Calibre Library"
    if direct.is_dir():
        return direct
    nested = base / "LonesomeLib" / "Calibre Library"
    if nested.is_dir():
        return nested
    if base.name == "Calibre Library" and base.is_dir():
        return base
    # Walk one level for "*/Calibre Library"
    try:
        for child in base.iterdir():
            if not child.is_dir() or is_junk_dir(child):
                continue
            candidate = child / "Calibre Library"
            if candidate.is_dir():
                return candidate
    except OSError:
        pass
    return None


def plan_book_folder(
    source: Path,
    dest_root: Path,
    *,
    author_hint: str,
    title_hint: str,
) -> MigrateAction:
    files = _book_files(source)
    bookish = [p for p in files if p.suffix.lower() in BOOK_EXTENSIONS]
    if not bookish:
        return MigrateAction(
            action="empty",
            source=str(source),
            reason="no book files",
        )
    # Fast path: folder names are enough when the destination is empty.
    dest_probe = Path(dest_root) / safe_path_part(
        author_hint or "Unknown Author", fallback="Unknown Author"
    ) / safe_path_part(strip_calibre_id(title_hint) or "Untitled", fallback="Untitled")
    need_opf = _dest_has_books(dest_probe)
    identity = _identity_from_folder(
        source,
        author_hint=author_hint,
        title_hint=title_hint,
        read_opf=need_opf,
    )
    dest_dir = Path(dest_root) / identity["author"] / identity["title"]
    # If OPF renamed the path, re-check collision against the real dest.
    if not need_opf and dest_dir != dest_probe and _dest_has_books(dest_dir):
        identity = _identity_from_folder(
            source, author_hint=author_hint, title_hint=title_hint, read_opf=True
        )
        dest_dir = Path(dest_root) / identity["author"] / identity["title"]
        need_opf = True
    canonical = _pick_canonical(bookish)
    file_names = [p.name for p in files]
    if _dest_has_books(dest_dir):
        if not identity["isbn"]:
            identity = _identity_from_folder(
                source, author_hint=author_hint, title_hint=title_hint, read_opf=True
            )
        existing_isbn = _dest_isbn(dest_dir)
        incoming_isbn = identity["isbn"]
        if existing_isbn and incoming_isbn and existing_isbn == incoming_isbn:
            return MigrateAction(
                action="skip",
                source=str(source),
                dest=str(dest_dir),
                author=identity["author"],
                title=identity["title"],
                isbn=incoming_isbn,
                reason="same ISBN already on shelf",
                files=file_names,
            )
        return MigrateAction(
            action="collision",
            source=str(source),
            dest=str(dest_dir),
            author=identity["author"],
            title=identity["title"],
            isbn=incoming_isbn,
            reason=(
                "destination already has books"
                + (f"; shelf ISBN {existing_isbn}" if existing_isbn else "")
                + (f"; source ISBN {incoming_isbn}" if incoming_isbn else "")
            ),
            files=file_names,
        )
    return MigrateAction(
        action="copy",
        source=str(source),
        dest=str(dest_dir),
        author=identity["author"],
        title=identity["title"],
        isbn=identity["isbn"],
        reason=f"canonical={canonical.name if canonical else 'none'}",
        files=file_names,
    )


def _copy_folder_files(source: Path, dest_dir: Path, *, move: bool) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for src in _book_files(source):
        target = dest_dir / src.name
        if target.exists():
            # Prefer EPUB: if dest already has this name from a prior partial, skip same name.
            if target.resolve() == src.resolve():
                continue
            # Secondary formats with distinct names still copy; same basename → fail closed.
            raise FileExistsError(str(target))
        if move:
            shutil.move(str(src), str(target))
        else:
            shutil.copy2(src, target)


def apply_action(action: MigrateAction, *, dry_run: bool, move: bool = False) -> None:
    if action.action != "copy" or dry_run:
        return
    _copy_folder_files(Path(action.source), Path(action.dest), move=move)


def migrate_books(
    source_root: Path,
    dest_root: Path,
    *,
    dry_run: bool = True,
    move: bool = False,
    include_flat: bool = True,
    include_newlib: Optional[Path] = None,
    limit: Optional[int] = None,
) -> MigrateReport:
    """Plan (and optionally apply) a books blend into ``dest_root``.

    Default is copy (not move). ``move=True`` is for a later cutover after verify.
    """
    report = MigrateReport(
        dry_run=dry_run,
        source_root=str(source_root),
        dest_root=str(dest_root),
    )
    if not dry_run:
        Path(dest_root).mkdir(parents=True, exist_ok=True)

    calibre = find_calibre_library(source_root)
    folder_iter: List[Iterable[Tuple[Path, str, str]]] = []
    if calibre is not None:
        folder_iter.append(discover_calibre_book_folders(calibre))
    elif source_root.is_dir() and (source_root / "metadata.db").is_file():
        folder_iter.append(discover_calibre_book_folders(source_root))

    if include_flat:
        folder_iter.append(discover_flat_author_title(source_root))

    if include_newlib is not None:
        newlib = Path(include_newlib)
        if newlib.is_dir():
            folder_iter.append(discover_calibre_book_folders(newlib))

    seen_sources: set[str] = set()
    planned = 0
    # When sampling (--limit), skip the full-tree sort so network mounts stay usable.
    if limit is None:
        folders = sorted(
            (item for group in folder_iter for item in group),
            key=lambda item: (item[1].casefold(), item[2].casefold(), str(item[0])),
        )
        stream: Iterable[Tuple[Path, str, str]] = folders
    else:
        stream = (item for group in folder_iter for item in group)

    for folder, author_hint, title_hint in stream:
        if limit is not None and planned >= limit:
            break
        key = str(folder)
        if key in seen_sources:
            continue
        seen_sources.add(key)
        if is_junk_dir(folder):
            report.actions.append(
                MigrateAction(action="junk", source=str(folder), reason="junk dir")
            )
            continue
        action = plan_book_folder(
            folder,
            dest_root,
            author_hint=author_hint,
            title_hint=title_hint,
        )
        report.actions.append(action)
        planned += 1
        try:
            apply_action(action, dry_run=dry_run, move=move)
        except FileExistsError as error:
            action.action = "collision"
            action.reason = f"file exists during copy: {error}"
    return report


def archive_historical_guidance() -> str:
    return (
        "Archive Historical is flat PDFs (not {Author}/{Title}/). "
        "Park under library/magazines/Archive Historical/ or "
        "library/books/_archive/Archive Historical/ after books cutover; "
        "do not flatten into Author/Title without a human pass."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m librarian.migrate_library",
        description=(
            "Create library/* siblings and/or dry-run blend Calibre books into "
            "library/books. Default is dry-run (no writes)."
        ),
    )
    parser.add_argument(
        "--media-root",
        type=Path,
        default=Path("/data/media"),
        help="Host/container media root (default /data/media)",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Books dump to blend (default: MEDIA_ROOT/books)",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Destination books root (default: MEDIA_ROOT/library/books)",
    )
    parser.add_argument(
        "--create-roots",
        action="store_true",
        help="Ensure library/{books,magazines,comics,audiobooks,incoming-music} exist",
    )
    parser.add_argument(
        "--migrate-books",
        action="store_true",
        help="Plan/apply Calibre + flat books blend into --dest",
    )
    parser.add_argument(
        "--include-newlib",
        type=Path,
        default=None,
        nargs="?",
        const=Path("__default_newlib__"),
        help="Also blend MEDIA_ROOT/newlib (or a path). Dedupe via ISBN/collision.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform copies (still never overwrites). Without this, dry-run only.",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="With --apply, move instead of copy (not recommended for first cutover).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Plan at most N book folders (smoke / sampling)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full report as JSON",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    dry_run = not args.apply
    media_root = Path(args.media_root)
    source = Path(args.source) if args.source else media_root / "books"
    dest = Path(args.dest) if args.dest else media_root / "library" / "books"

    if not args.create_roots and not args.migrate_books:
        args.create_roots = True
        args.migrate_books = True

    report_bits: Dict[str, Any] = {
        "dry_run": dry_run,
        "media_root": str(media_root),
        "archive_historical": archive_historical_guidance(),
    }

    if args.create_roots:
        created = create_library_roots(media_root, dry_run=dry_run)
        report_bits["created_roots"] = created
        if not args.json:
            mode = "would create" if dry_run else "created"
            print(f"library roots ({mode}): {len(created)}")
            for path in created:
                print(f"  {path}")

    if args.migrate_books:
        newlib: Optional[Path] = None
        if args.include_newlib is not None:
            if args.include_newlib == Path("__default_newlib__"):
                newlib = media_root / "newlib"
            else:
                newlib = Path(args.include_newlib)
        report = migrate_books(
            source,
            dest,
            dry_run=dry_run,
            move=bool(args.move),
            include_newlib=newlib,
            limit=args.limit,
        )
        report_bits["migrate"] = report.to_dict()
        if not args.json:
            counts = report.counts()
            print(
                f"books migrate ({'dry-run' if dry_run else 'apply'}): "
                f"source={source} dest={dest}"
            )
            print("  " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "nothing")
            collisions = [a for a in report.actions if a.action == "collision"]
            for item in collisions[:20]:
                print(f"  collision: {item.source} -> {item.dest} ({item.reason})")
            if len(collisions) > 20:
                print(f"  … {len(collisions) - 20} more collisions")
            print(f"  note: {archive_historical_guidance()}")

    if args.json:
        json.dump(report_bits, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
