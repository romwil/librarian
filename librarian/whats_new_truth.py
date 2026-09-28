"""Deploy What’s New that never lies — version lockstep + honest notes tip."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from librarian import __version__ as RUNTIME_VERSION

_VERSION_HEADING = re.compile(
    r"^## \[(\d+\.\d+\.\d+)\]\s*[—–-]\s*\d{4}-\d{2}-\d{2}\s*$",
    re.MULTILINE,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def parse_pyproject_version(text: str) -> str:
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', text or "")
    return _text(match.group(1) if match else "")


def parse_package_json_version(text: str) -> str:
    try:
        payload = json.loads(text or "{}")
    except json.JSONDecodeError:
        return ""
    return _text(payload.get("version"))


def parse_version_py(text: str) -> str:
    match = re.search(r'(?m)^__version__\s*=\s*"([^"]+)"\s*$', text or "")
    return _text(match.group(1) if match else "")


def changelog_versions(text: str) -> List[str]:
    return [match.group(1) for match in _VERSION_HEADING.finditer(text or "")]


def release_notes_tip(payload: Any) -> str:
    """Newest version listed in release-notes.json (first entry after generate)."""
    if isinstance(payload, dict):
        releases = payload.get("releases")
    elif isinstance(payload, list):
        releases = payload
    else:
        releases = None
    if not isinstance(releases, list) or not releases:
        return ""
    first = releases[0] if isinstance(releases[0], dict) else {}
    return _text(first.get("version"))


def read_notes_tip_version(repo_or_public: Path) -> str:
    """Resolve tip version from dist or public release-notes.json (newer wins)."""
    root = Path(repo_or_public)
    candidates = [
        root / "frontend" / "dist" / "release-notes.json",
        root / "frontend" / "public" / "release-notes.json",
        root / "release-notes.json",
    ]
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        return ""
    newest = max(existing, key=lambda item: item.stat().st_mtime)
    try:
        payload = json.loads(newest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return release_notes_tip(payload)


def notes_match_runtime(*, runtime: str = "", notes_version: str = "") -> bool:
    left = _text(runtime) or _text(RUNTIME_VERSION)
    right = _text(notes_version)
    return bool(left) and left == right


def verify_version_lockstep(repo_root: Path) -> Dict[str, Any]:
    """Fail-closed checklist: package versions + CHANGELOG + notes tip agree."""
    root = Path(repo_root)
    sources: Dict[str, str] = {
        "runtime": _text(RUNTIME_VERSION),
        "pyproject": parse_pyproject_version((root / "pyproject.toml").read_text(encoding="utf-8")),
        "package_json": parse_package_json_version((root / "package.json").read_text(encoding="utf-8")),
        "frontend_package_json": parse_package_json_version(
            (root / "frontend" / "package.json").read_text(encoding="utf-8")
        ),
        "version_py": parse_version_py((root / "librarian" / "_version.py").read_text(encoding="utf-8")),
    }
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    versions = changelog_versions(changelog)
    tip = versions[0] if versions else ""
    sources["changelog_tip"] = tip
    sources["notes_tip"] = read_notes_tip_version(root)

    expected = sources["runtime"]
    mismatches = [name for name, value in sources.items() if value != expected]
    ok = not mismatches and bool(expected)
    return {
        "ok": ok,
        "version": expected,
        "sources": sources,
        "mismatches": mismatches,
        "presence": (
            f"What’s New tells the truth for {expected}."
            if ok
            else "Version story is split — What’s New would lie until lockstep is fixed."
        ),
    }


def truthful_release(releases: Sequence[Mapping[str, Any]], version: str) -> Optional[Dict[str, Any]]:
    """Exact version match only — never fall back to a newer/older story."""
    target = _text(version)
    if not target:
        return None
    for item in releases or ():
        if not isinstance(item, dict):
            continue
        if _text(item.get("version")) == target:
            return dict(item)
    return None
