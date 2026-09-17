#!/usr/bin/env bash
# Create Librarian library/* siblings under a media root (default /data/media).
# Safe to re-run. Does not touch /data/media/music.
set -euo pipefail

MEDIA_ROOT="${1:-/data/media}"
LIBRARY="${MEDIA_ROOT}/library"

mkdir -p \
  "${LIBRARY}/books" \
  "${LIBRARY}/magazines" \
  "${LIBRARY}/comics" \
  "${LIBRARY}/audiobooks" \
  "${LIBRARY}/incoming-music"

echo "library roots ready under ${LIBRARY}:"
ls -la "${LIBRARY}"

cat <<'EOF'

Archive Historical (flat Hacker Digest PDFs under old books/):
  Park at library/magazines/Archive Historical/ or library/books/_archive/
  after the books blend — do not auto-flatten into {Author}/{Title}/.

music_root stays ${MEDIA_ROOT}/music (Smart Map + Plexamp). Never put audiobooks there.

Next: dry-run migrate, then Settings rebind + Scan — see docs/ops/LIBRARY_MIGRATE.md
EOF
