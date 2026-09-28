#!/usr/bin/env bash
# Fail closed when package versions / CHANGELOG / What’s New tip disagree.
#
# Usage:
#   ./scripts/verify-release-truth.sh
#   ./scripts/verify-release-truth.sh --require-version 0.5.13
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REQUIRE_VERSION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --require-version)
      REQUIRE_VERSION="${2:-}"
      if [[ -z "$REQUIRE_VERSION" ]]; then
        echo "Usage: $0 [--require-version X.Y.Z]" >&2
        exit 1
      fi
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [--require-version X.Y.Z]"
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

cd "$ROOT"
# Prefer venv python when present so imports resolve to the editable package.
PYTHON="python3"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

"$PYTHON" - "$REQUIRE_VERSION" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

from librarian.whats_new_truth import verify_version_lockstep

require = (sys.argv[1] or "").strip()
root = Path.cwd()
report = verify_version_lockstep(root)
print(json.dumps(report, indent=2, sort_keys=True))
if require and report.get("version") != require:
    print(f"Expected version {require}, got {report.get('version')}", file=sys.stderr)
    sys.exit(1)
if not report.get("ok"):
    print(report.get("presence") or "What’s New lockstep failed", file=sys.stderr)
    sys.exit(1)
print(report.get("presence") or "ok")
PY
