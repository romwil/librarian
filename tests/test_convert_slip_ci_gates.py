"""Sprint 0.2 gates: hashed Python lockfile and a CI workflow that runs the suite."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_requirements_lock_has_hashes():
    lock = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    assert "fastapi" in lock
    assert "--hash=sha256:" in lock
    dev = (ROOT / "requirements-dev.lock").read_text(encoding="utf-8")
    assert "pytest" in dev
    assert "--hash=sha256:" in dev


def test_dockerfile_installs_from_hashed_lockfile():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "pip install --require-hashes -r requirements.lock" in text
    assert "pip install --no-deps" in text
    assert 'pip install ".[web]"' not in text


def test_e2e_launcher_rebuilds_dist_unless_skipped():
    script = (ROOT / "scripts" / "start-e2e-server.mjs").read_text(encoding="utf-8")
    assert "E2E_SKIP_BUILD" in script
    assert 'npm(["run", "build"]' in script
    assert 'npm(["install"]' not in script
    assert "Building frontend for E2E" in script
    assert "delete env.LIBRARIAN_SKIP_APP_BOOT" in script


def test_ci_workflow_runs_required_gates():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pytest" in workflow
    assert "npm test" in workflow
    assert "test:e2e" in workflow
    assert "8794" in workflow
    assert "LIBRARIAN_SKIP_APP_BOOT" in workflow
