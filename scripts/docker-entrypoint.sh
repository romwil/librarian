#!/bin/sh
set -e

# Drop to PUID/PGID (Unraid nobody:users is 99:100). Defaults 1000:1000
# when the template does not set them. gosu accepts numeric UID:GID.
PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

if [ "$(id -u)" = "0" ]; then
    if [ -d /config ]; then
        cfg_uid="$(stat -c '%u' /config 2>/dev/null || echo 0)"
        cfg_gid="$(stat -c '%g' /config 2>/dev/null || echo 0)"
        if [ "$cfg_uid" != "$PUID" ] || [ "$cfg_gid" != "$PGID" ]; then
            chown -R "${PUID}:${PGID}" /config
        fi
    fi
    exec gosu "${PUID}:${PGID}" "$@"
fi

exec "$@"
