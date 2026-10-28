"""List leftover movie and TV catalog rows for the Maintain report.

Read only. Files on disk are left where they are.
"""

from __future__ import annotations

from typing import Any, Dict, List

SCREEN_LEFTOVER_KINDS = ("movie", "tv")
_PAGE = 100
_CAP = 500


def screen_leftover_report(db: Any) -> Dict[str, Any]:
    """Catalog rows whose kind is movie or TV.

    Does not delete works, file rows, or files on disk.
    """
    items: List[Dict[str, Any]] = []
    truncated = False
    for kind in SCREEN_LEFTOVER_KINDS:
        offset = 0
        while True:
            if len(items) >= _CAP:
                truncated = True
                break
            batch = db.list_works(kind=kind, limit=_PAGE, offset=offset)
            if not batch:
                break
            for row in batch:
                if len(items) >= _CAP:
                    truncated = True
                    break
                items.append(
                    {
                        "id": str(row.get("id") or ""),
                        "title": str(row.get("title") or ""),
                        "author": str(row.get("author") or ""),
                        "kind": str(row.get("kind") or kind),
                    }
                )
            if truncated or len(batch) < _PAGE:
                break
            offset += len(batch)
        if truncated:
            break
    note = "These movie and TV rows are still in the catalog. Their files were left in place."
    if truncated:
        note = f"Showing the first {_CAP}. {note}"
    return {
        "count": len(items),
        "items": items,
        "truncated": truncated,
        "note": note,
    }
