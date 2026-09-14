#!/bin/sh
# Build and run Librarian without Compose (Unraid-friendly).
# Canonical host kit: /mnt/user/appdata/librarian
#   On-host build (current, until Hub exists):  ./docker-run.sh
# Does NOT wipe ./config. Stock Unraid has no Compose.
# Port 8793 — never 8788 / 8790 / 8791 / 8792.
set -eu

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

CONFIG_PATH="${CONFIG_PATH:-$ROOT_DIR/config}"
DATA_HOST="${DATA_HOST:-/mnt/user/data}"
HOST_PORT="${HOST_PORT:-8793}"
IMAGE="${IMAGE:-librarian:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-librarian}"
WAIT_SECS="${WAIT_SECS:-90}"
SKIP_BUILD="${SKIP_BUILD:-0}"

if [ "$HOST_PORT" = "8788" ] || [ "$HOST_PORT" = "8790" ] || [ "$HOST_PORT" = "8791" ] || [ "$HOST_PORT" = "8792" ]; then
  echo "ERROR: Librarian must not bind $HOST_PORT (Projectionist / Smart Map / Lobby)." >&2
  exit 1
fi

mkdir -p "$CONFIG_PATH"

read_env() {
  _key="$1"
  if [ ! -f .env ]; then
    return 0
  fi
  _line=$(grep -E "^[[:space:]]*${_key}=" .env | tail -n 1 || true)
  if [ -z "$_line" ]; then
    return 0
  fi
  _val=${_line#*=}
  case "$_val" in
    \"*\") _val=${_val#\"}; _val=${_val%\"} ;;
    \'*\') _val=${_val#\'}; _val=${_val%\'} ;;
  esac
  export "$_key=$_val"
}

for _env_key in \
  TZ \
  LIBRARIAN_OWNER_USERNAME LIBRARIAN_OWNER_PASSWORD LIBRARIAN_SESSION_SECRET \
  SABNZBD_URL SABNZBD_API_KEY NZBFINDER_URL NZBFINDER_API_TOKEN \
  LLM_BASE_URL LLM_API_KEY LLM_MODEL DATA_HOST
do
  read_env "$_env_key"
done

if [ -n "${DATA_HOST:-}" ]; then
  DATA_HOST="${DATA_HOST}"
fi

if [ -z "${VCS_REF:-}" ]; then
  if [ -f "$ROOT_DIR/.source-rev" ]; then
    VCS_REF=$(tr -d '[:space:]' < "$ROOT_DIR/.source-rev")
  elif [ -d "$ROOT_DIR/.git" ] && [ ! -e /mnt/user/appdata ]; then
    VCS_REF=$(git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || echo local)
  else
    VCS_REF=local
  fi
fi

export DOCKER_BUILDKIT=1

if [ "$SKIP_BUILD" = "1" ]; then
  echo "Using image ${IMAGE} (no local build)..."
  if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "ERROR: image ${IMAGE} is not present locally." >&2
    exit 1
  fi
else
  echo "Building image ${IMAGE} (rev ${VCS_REF})..."
  docker build \
    --build-arg BUILDKIT_INLINE_CACHE=1 \
    --build-arg "BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --build-arg "VCS_REF=${VCS_REF}" \
    -t "$IMAGE" .
fi

echo "Stopping existing container (if any)..."
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

echo "Starting ${CONTAINER_NAME} on port ${HOST_PORT}..."
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  --add-host=host.docker.internal:host-gateway \
  -p "${HOST_PORT}:8793" \
  -e DATA_DIR=/config \
  -e PORT=8793 \
  -e TZ="${TZ:-America/New_York}" \
  -e LIBRARIAN_OWNER_USERNAME="${LIBRARIAN_OWNER_USERNAME:-owner}" \
  -e LIBRARIAN_OWNER_PASSWORD="${LIBRARIAN_OWNER_PASSWORD:-}" \
  -e LIBRARIAN_SESSION_SECRET="${LIBRARIAN_SESSION_SECRET:-}" \
  -e SABNZBD_URL="${SABNZBD_URL:-http://downloader.sl}" \
  -e SABNZBD_API_KEY="${SABNZBD_API_KEY:-}" \
  -e NZBFINDER_URL="${NZBFINDER_URL:-https://nzbfinder.ws}" \
  -e NZBFINDER_API_TOKEN="${NZBFINDER_API_TOKEN:-}" \
  -e LLM_BASE_URL="${LLM_BASE_URL:-}" \
  -e LLM_API_KEY="${LLM_API_KEY:-}" \
  -e LLM_MODEL="${LLM_MODEL:-gpt-4o-mini}" \
  -v "${CONFIG_PATH}:/config" \
  -v "${DATA_HOST}:/data" \
  "$IMAGE"

echo "Waiting for health..."
_deadline=$(( $(date +%s) + WAIT_SECS ))
while [ "$(date +%s)" -lt "$_deadline" ]; do
  if docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null | grep -qx true; then
    _body=$(docker exec "$CONTAINER_NAME" python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8793/api/health', timeout=5).read().decode())" 2>/dev/null || true)
    if printf '%s' "$_body" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"'; then
      echo "Health: $_body"
      echo "Librarian is running on http://127.0.0.1:${HOST_PORT}/"
      exit 0
    fi
  else
    _status=$(docker inspect -f '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || true)
    if [ "$_status" = "exited" ] || [ "$_status" = "dead" ]; then
      docker logs --tail 80 "$CONTAINER_NAME" 2>&1 || true
      echo "ERROR: container exited during startup (status=$_status)" >&2
      exit 1
    fi
  fi
  sleep 2
done

docker logs --tail 80 "$CONTAINER_NAME" 2>&1 || true
echo "ERROR: timed out after ${WAIT_SECS}s waiting for /api/health" >&2
exit 1
