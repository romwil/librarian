"""PRD-001: nothing reaches SABnzbd without an owner/op confirm."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "librarian"

# Automated acquisition and poller paths. Owner/op Get and Confirm live in jobs.py.
_FORBIDDEN = (
    ROOT / "wanted_search.py",
    ROOT / "wanted_sweep.py",
    ROOT / "wanted.py",
    ROOT / "rss.py",
    ROOT / "poller.py",
    ROOT / "noted.py",
    ROOT / "ingest.py",
    ROOT / "sorting_autopilot.py",
    ROOT / "sorting_undo.py",
    ROOT / "review_diagnosis.py",
)


def _attribute_calls(path: Path, names: set[str]) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in names:
            hits.append((func.attr, node.lineno))
        elif isinstance(func, ast.Name) and func.id in names:
            hits.append((func.id, node.lineno))
    return hits


def test_poller_and_wanted_paths_never_call_sab_add():
    for path in _FORBIDDEN:
        assert path.is_file(), path
        hits = _attribute_calls(path, {"addfile", "addurl"})
        assert hits == [], f"{path.name} must not call SAB add ({hits})"


def test_wanted_search_does_not_import_sab():
    tree = ast.parse((ROOT / "wanted_search.py").read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert all("sabnzbd" not in name and name != "librarian.jobs" for name in imported)


def test_addfile_only_runs_from_jobs_submit():
    """The only client.addfile call is jobs._submit_nzb_to_sab (confirm / owner Get)."""
    files = []
    for path in ROOT.rglob("*.py"):
        if path.name == "sabnzbd.py":
            continue
        if _attribute_calls(path, {"addfile"}):
            files.append(str(path.relative_to(ROOT)))
    assert files == ["jobs.py"]
