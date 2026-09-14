#!/bin/sh
set -e

if [ "$(id -u)" = "0" ]; then
    cfg_uid="$(stat -c '%u' /config 2>/dev/null || echo 0)"
    cfg_gid="$(stat -c '%g' /config 2>/dev/null || echo 0)"
    if [ "$cfg_uid" != "1000" ] || [ "$cfg_gid" != "1000" ]; then
        chown -R librarian:librarian /config
    fi
    exec gosu librarian "$@"
fi

exec "$@"
