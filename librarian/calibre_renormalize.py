"""One-button Calibre re-normalize — look first, then copy into library/books."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from librarian.migrate_library import find_calibre_library, migrate_books

PREVIEW_LIMIT = 120


def _text(value: Any) -> str:
    return str(value or "").strip()


def media_root_from_books(books_root: Path) -> Path:
    """``…/library/books`` → ``…/media`` when nested under library; else parent."""
    root = Path(books_root)
    if root.name == "books" and root.parent.name == "library":
        return root.parent.parent
    return root.parent


def resolve_calibre_source(settings: Mapping[str, Any] | Any) -> Optional[Path]:
    """Find a Calibre dump near the configured books root."""
    books = Path(_text(getattr(settings, "books_root", None) or (settings.get("books_root") if isinstance(settings, Mapping) else "")))
    if not books:
        return None
    media = media_root_from_books(books)
    candidates = [
        media / "books",
        media / "books" / "LonesomeLib" / "Calibre Library",
        media / "newlib",
        books.parent / "Calibre Library",
        books,
    ]
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        found = find_calibre_library(candidate)
        if found is not None:
            return found
        if (candidate / "metadata.db").is_file():
            return candidate
    return None


def renormalize_presence(report: Mapping[str, Any] | None, *, applying: bool = False) -> str:
    if not report:
        return "No Calibre dump is waiting near the books root."
    counts = dict(report.get("counts") or {})
    copies = int(counts.get("copy") or 0)
    skips = int(counts.get("skip") or 0)
    collisions = int(counts.get("collision") or 0)
    if applying and not report.get("dry_run", True):
        if copies < 1 and collisions < 1:
            return "Nothing new to shelve — the dump already matches the lamp."
        parts = []
        if copies:
            parts.append(f"Shelved {copies} volume{'s' if copies != 1 else ''}")
        if collisions:
            parts.append(f"{collisions} collision{'s' if collisions != 1 else ''} left for Review")
        return ". ".join(parts) + "."
    if copies < 1 and collisions < 1 and skips < 1:
        return "The lamp looked — nothing to re-normalize here."
    lead = f"{copies} ready to shelve" if copies else "Nothing new to copy"
    extras = []
    if skips:
        extras.append(f"{skips} already home")
    if collisions:
        extras.append(f"{collisions} need a human glance")
    if extras:
        return f"{lead} · " + " · ".join(extras) + "."
    return f"{lead}."


def assemble_calibre_renormalize(
    settings: Any,
    *,
    apply: bool = False,
    limit: Optional[int] = PREVIEW_LIMIT,
) -> Dict[str, Any]:
    """Dry-run (default) or copy Calibre dump into books_root. Never moves."""
    books_root = Path(_text(getattr(settings, "books_root", "") or ""))
    source = resolve_calibre_source(settings)
    if not books_root or not source:
        return {
            "available": False,
            "dry_run": not apply,
            "source_root": str(source or ""),
            "dest_root": str(books_root or ""),
            "counts": {},
            "actions": [],
            "presence": renormalize_presence(None),
        }
    capped = None if (apply and limit is None) else (limit if limit is not None else PREVIEW_LIMIT)
    report = migrate_books(
        source,
        books_root,
        dry_run=not apply,
        move=False,
        include_flat=False,
        limit=capped,
    )
    payload = report.to_dict()
    # Cap action rows returned to the SPA so Maintain stays a map, not a spreadsheet.
    actions = list(payload.get("actions") or [])[:80]
    return {
        "available": True,
        "dry_run": report.dry_run,
        "source_root": report.source_root,
        "dest_root": report.dest_root,
        "counts": report.counts(),
        "actions": actions,
        "action_total": len(report.actions),
        "presence": renormalize_presence(
            {"counts": report.counts(), "dry_run": report.dry_run},
            applying=apply,
        ),
    }
