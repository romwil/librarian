"""Tell Komga / Audiobookshelf to rescan after a comic or audiobook lands on the shelf."""

from __future__ import annotations

from typing import Any, Dict, Optional

from librarian.kinds import KIND_AUDIOBOOK, KIND_COMIC


def notify_shelf_scanners(settings: Any, kind: str) -> Dict[str, Optional[Dict[str, Any]]]:
    """Best-effort library rescans. A scanner failure never fails the organize."""
    komga_scan = None
    if kind == KIND_COMIC:
        try:
            from librarian.komga import notify_komga_scan

            komga_scan = notify_komga_scan(settings)
        except Exception:
            komga_scan = {"ok": False, "skipped": False, "error": "unexpected"}
    abs_scan = None
    if kind == KIND_AUDIOBOOK:
        try:
            from librarian.audiobookshelf import notify_abs_scan

            abs_scan = notify_abs_scan(settings)
        except Exception:
            abs_scan = {"ok": False, "skipped": False, "error": "unexpected"}
    return {"komga_scan": komga_scan, "abs_scan": abs_scan}
