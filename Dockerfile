# syntax=docker/dockerfile:1
# BuildKit required for --mount=type=cache.

FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates gosu \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
RUN mkdir -p librarian && printf '# build stub\n' > librarian/__init__.py
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install ".[web]"

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

RUN echo "0.1.0 built ${BUILD_DATE} rev ${VCS_REF}" > /app/.build-info

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8793/api/health')" || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "-m", "librarian.web"]
