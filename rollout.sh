#!/bin/sh
# Pull romwil/librarian from Docker Hub and recreate the Automat container.
# Canonical host kit: /mnt/user/appdata/librarian
#   ssh automat 'cd /mnt/user/appdata/librarian && ./rollout.sh'
# Same volume/env contract as docker-run.sh (never wipes ./config).
# Until a Hub image exists, pull fails — use ./docker-run.sh to build on-host.
set -eu

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

IMAGE_TAG="${1:-${IMAGE_TAG:-latest}}"
HUB_IMAGE="${HUB_IMAGE:-romwil/librarian:${IMAGE_TAG}}"

echo "=== Librarian Hub rollout ==="
echo "Dir:   $ROOT_DIR"
echo "Image: $HUB_IMAGE"
echo "Config bind: ${CONFIG_PATH:-$ROOT_DIR/config} → /config (preserved)"

if ! docker pull "$HUB_IMAGE"; then
  echo "ERROR: could not pull ${HUB_IMAGE}." >&2
  echo "No Hub image is published yet (or Docker Hub is unreachable)." >&2
  echo "Build on this host instead:" >&2
  echo "  ./docker-run.sh" >&2
  echo "Publish later from a real git checkout (not this kit):" >&2
  echo "  ./scripts/docker-release.sh" >&2
  exit 1
fi

IMAGE="$HUB_IMAGE" SKIP_BUILD=1 exec "$ROOT_DIR/docker-run.sh"
