# syntax=docker/dockerfile:1
# BuildKit required for --mount=type=cache.
#
# Cache boundaries (new deps vs app source):
#   frontend: package.json + lock → npm ci → frontend tree → npm run build
#   runtime:  apt → pyproject extras (stub pkg) → librarian/ + SPA dist
# docker-run.sh does not run host-side npm; the SPA is built in this frontend
# stage. librarian/ and frontend/src edits reuse npm ci and pip extras.
# BUILD_DATE / VCS_REF stay below apt/pip so a stamped rebuild does not
# reinstall wheels.

FROM node:20-alpine AS frontend
WORKDIR /frontend

# npm layer stays warm when only librarian/ or frontend/src changes.
# Adding foliate-js (or any other SPA dep) busts only this pair of layers.
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

# System packages (unar for CBR→CBZ / SAB rar; par2cmdline for Review repair).
# Independent of app source and extras.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates gosu unar par2 \
    && rm -rf /var/lib/apt/lists/*

# Python extras from pyproject only. Stub package + stub README so edits to
# librarian/, frontend/src, README, or LICENSE do not re-download wheels.
COPY pyproject.toml ./
RUN mkdir -p librarian \
    && printf 'Librarian\n' > README.md \
    && printf '# build stub\n' > librarian/__init__.py
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install ".[web]"

# Real sources; --no-deps keeps the extras layer when only Python/SPA changes.
COPY README.md LICENSE ./
COPY librarian ./librarian
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps --force-reinstall .

COPY --from=frontend /frontend/dist ./frontend/dist

RUN addgroup --system --gid 1000 librarian \
    && adduser --system --uid 1000 --ingroup librarian librarian \
    && mkdir -p /config && chown librarian:librarian /config

ENV DATA_DIR=/config
ENV PORT=8793

EXPOSE 8793
VOLUME ["/config", "/data"]

COPY scripts/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ARG BUILD_DATE=unknown
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="Librarian" \
      org.opencontainers.image.description="Household reading-room library" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="https://github.com/romwil/librarian" \
      org.opencontainers.image.licenses="MIT"

# Stamp from package version so What’s New / ops never drift from a hardcoded string.
RUN python -c "from librarian._version import __version__; open('/app/.build-info','w').write(f'{__version__} built ${BUILD_DATE} rev ${VCS_REF}\n')"

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8793/api/health')" || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "-m", "librarian.web"]
