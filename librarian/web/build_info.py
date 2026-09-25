"""Build stamp + Vite public asset resolution."""

from __future__ import annotations

from pathlib import Path

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def read_build_info() -> str:
    """Docker image stamp from /app/.build-info, or empty when unset (local venv)."""
    for candidate in (Path("/app/.build-info"), _REPO_ROOT / ".build-info"):
        try:
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return ""


def frontend_public_file(*parts: str) -> Path | None:
    """Resolve a Vite public asset from dist (prod) or public/ (local pre-build).

    When both exist (common after generate-release-notes without a rebuild),
    prefer the newer file so Settings stays current during local development.
    """
    candidates = [
        FRONTEND_DIST.joinpath(*parts),
        FRONTEND_DIST.parent.joinpath("public", *parts),
    ]
    existing = [candidate for candidate in candidates if candidate.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda item: item.stat().st_mtime)
