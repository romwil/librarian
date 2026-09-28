"""What’s New that never lies — version lockstep + exact tip match."""

from pathlib import Path

from librarian.whats_new_truth import (
    changelog_versions,
    notes_match_runtime,
    parse_package_json_version,
    parse_pyproject_version,
    release_notes_tip,
    truthful_release,
    verify_version_lockstep,
)


def test_parsers_and_tip():
    assert parse_pyproject_version('name = "x"\nversion = "0.5.12"\n') == "0.5.12"
    assert parse_package_json_version('{"version":"0.5.12"}') == "0.5.12"
    assert release_notes_tip({"releases": [{"version": "0.5.12"}, {"version": "0.5.11"}]}) == "0.5.12"
    assert notes_match_runtime(runtime="0.5.12", notes_version="0.5.12") is True
    assert notes_match_runtime(runtime="0.5.12", notes_version="0.5.11") is False


def test_truthful_release_never_falls_back():
    releases = [
        {"version": "0.5.12", "highlights": ["a"]},
        {"version": "0.5.11", "highlights": ["b"]},
    ]
    assert truthful_release(releases, "0.5.12")["version"] == "0.5.12"
    assert truthful_release(releases, "0.5.13") is None


def test_verify_lockstep_on_repo():
    root = Path(__file__).resolve().parents[1]
    report = verify_version_lockstep(root)
    assert report["version"]
    assert "sources" in report
    # CHANGELOG must list the runtime tip among headings.
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert report["version"] in changelog_versions(changelog) or not report["ok"]
