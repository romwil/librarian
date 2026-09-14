#!/bin/sh
# Build and run Librarian without Compose (Unraid-friendly).
# Canonical host kit: /mnt/user/appdata/librarian
#   On-host build (current, until Hub exists):  ./docker-run.sh
#   Hub pull + recreate (later):                ./rollout.sh
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
  TZ PUID PGID EXTRA_HOSTS \
  LIBRARIAN_OWNER_USERNAME LIBRARIAN_OWNER_PASSWORD LIBRARIAN_SESSION_SECRET \
  LIBRARIAN_TRUST_PROXY_HEADERS \
  SABNZBD_URL SABNZBD_API_KEY NZBFINDER_URL NZBFINDER_API_TOKEN \
  LLM_BASE_URL LLM_API_KEY LLM_MODEL DATA_HOST
do
  read_env "$_env_key"
done

if [ -n "${DATA_HOST:-}" ]; then
  DATA_HOST="${DATA_HOST}"
fi

# Prefer an explicit stamp. The Automat kit often has a stale or
# dubious-ownership .git (rsync excludes .git) which previously baked
# the wrong rev into .build-info. When syncing the kit:
#   git rev-parse --short HEAD > .source-rev
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
    echo "Pull it with ./rollout.sh, or drop SKIP_BUILD to build on this host." >&2
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

# host.docker.internal plus optional EXTRA_HOSTS="name:ip,name:ip".
# If the Unraid host can resolve downloader.sl, pin it so the container
# does not depend on Docker DNS for the SAB hostname.
ADD_HOSTS="--add-host=host.docker.internal:host-gateway"
if command -v getent >/dev/null 2>&1; then
  _sab_ip=$(getent hosts downloader.sl 2>/dev/null | awk '{print $1}' | head -1 || true)
  if [ -n "${_sab_ip:-}" ]; then
    ADD_HOSTS="${ADD_HOSTS} --add-host=downloader.sl:${_sab_ip}"
  fi
fi
if [ -n "${EXTRA_HOSTS:-}" ]; then
  _old_ifs=$IFS
  IFS=,
  for _pair in $EXTRA_HOSTS; do
    _pair=$(printf '%s' "$_pair" | tr -d ' ')
    if [ -n "$_pair" ]; then
      ADD_HOSTS="${ADD_HOSTS} --add-host=${_pair}"
    fi
  done
  IFS=$_old_ifs
fi

echo "Starting ${CONTAINER_NAME} on port ${HOST_PORT}..."
# shellcheck disable=SC2086
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  $ADD_HOSTS \
  -p "${HOST_PORT}:8793" \
  -e DATA_DIR=/config \
  -e PORT=8793 \
  -e TZ="${TZ:-America/New_York}" \
  -e PUID="${PUID:-99}" \
  -e PGID="${PGID:-100}" \
  -e LIBRARIAN_OWNER_USERNAME="${LIBRARIAN_OWNER_USERNAME:-owner}" \
  -e LIBRARIAN_OWNER_PASSWORD="${LIBRARIAN_OWNER_PASSWORD:-}" \
  -e LIBRARIAN_SESSION_SECRET="${LIBRARIAN_SESSION_SECRET:-}" \
  -e LIBRARIAN_TRUST_PROXY_HEADERS="${LIBRARIAN_TRUST_PROXY_HEADERS:-}" \
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
      if docker exec "$CONTAINER_NAME" cat /app/.build-info >/dev/null 2>&1; then
        echo "Build info:"
        docker exec "$CONTAINER_NAME" cat /app/.build-info || true
        echo
      fi
      echo "Librarian is running."
      echo "  Web UI:  http://$(hostname -I 2>/dev/null | awk '{print $1}'):${HOST_PORT}/"
      echo "  Logs:    docker logs -f ${CONTAINER_NAME}"
      echo "  Stop:    docker stop ${CONTAINER_NAME} && docker rm ${CONTAINER_NAME}"
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
