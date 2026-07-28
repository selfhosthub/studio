# Dockerfile
# Core image: API + UI + general/transfer workers under supervisord.
# BYO Postgres via compose. Build context: repo root.
#
# Build: docker build --build-arg STUDIO_CONSOLE_VERSION=<ver> -t selfhosthub/studio-core .
# Run:   docker compose up -d

# --- Stage 1: Build UI ---
FROM node:24-alpine AS ui-builder
WORKDIR /app
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ .

# Next.js inlines NEXT_PUBLIC_* into the client bundle at build time.
# Defaults work when browser and container share the host (localhost).
# Override via --build-arg for cross-origin deploys.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_WS_URL=ws://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_PUBLIC_WS_URL=${NEXT_PUBLIC_WS_URL}

RUN npm run build

# --- Stage 2: Build API + worker Python deps (shared venv) ---
FROM python:3.12-slim AS python-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    libpng-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app/api
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-cache --no-install-project
COPY api/ .
RUN uv sync --frozen --no-dev --no-cache

COPY workers/studio_workers/requirements.txt /tmp/worker-requirements.txt
RUN uv pip install --python /app/api/.venv/bin/python --no-cache -r /tmp/worker-requirements.txt

# --- Stage 3: Final image (no compiler) ---
FROM python:3.12-slim

# Required at build time. No default - a missing arg fails the build.
ARG STUDIO_CONSOLE_VERSION
ARG STUDIO_VERSION

# Refuse to build without STUDIO_VERSION. Without this check the build
# silently produces an image with SHS_STUDIO_VERSION="", which then ships
# to GHCR before anyone notices. Matches the late STUDIO_CONSOLE_VERSION
# check chained into `uv tool install` below; this one runs early so a
# missing arg fails before any apt/curl layer work.
RUN test -n "${STUDIO_VERSION}" \
    || (echo "STUDIO_VERSION build arg required (pass --build-arg STUDIO_VERSION=X.Y.Z)" >&2 && exit 1)

# Optional. CI passes --build-arg GIT_SHA=$(git rev-parse HEAD); local builds
# leave it empty. Surfaced via /api/v1/system/version for restore preflight.
ARG GIT_SHA=""
LABEL org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.title="Self-Host Studio" \
      org.opencontainers.image.description="Self-hosted media workflow orchestration and automation" \
      org.opencontainers.image.vendor="Self-Host Hub" \
      org.opencontainers.image.source="https://github.com/selfhosthub/studio" \
      org.opencontainers.image.licenses="LicenseRef-Studio-Use-License" \
      org.opencontainers.image.version="${STUDIO_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENV=production \
    PORT=8000 \
    HOST=0.0.0.0 \
    SHS_ENV=production \
    SHS_STUDIO_VERSION=${STUDIO_VERSION} \
    SHS_GIT_SHA=${GIT_SHA} \
    SHS_COMMUNITY_SOURCE=https://raw.githubusercontent.com/selfhosthub/studio-community/main \
    SHS_PLUS_SOURCE=https://raw.githubusercontent.com/selfhosthub/studio-plus/main

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    openssl \
    postgresql-client \
    supervisor \
    nginx \
    gettext-base \
    libjpeg62-turbo \
    zlib1g \
    libpng16-16t64 \
    && rm -rf /var/lib/apt/lists/*

# cloudflared from upstream binary release. Cloudflare's apt repo doesn't
# carry trixie (Debian 13) yet; binary works on both amd64 and arm64.
ARG CLOUDFLARED_VERSION=2026.7.3
RUN ARCH="$(dpkg --print-architecture)" \
    && curl -fsSL "https://github.com/cloudflare/cloudflared/releases/download/${CLOUDFLARED_VERSION}/cloudflared-linux-${ARCH}" \
        -o /usr/local/bin/cloudflared \
    && chmod 0755 /usr/local/bin/cloudflared

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/* \
    # SSR runs node directly; drop the npm/corepack CLIs from the runtime image
    && rm -rf /usr/lib/node_modules /usr/bin/npm /usr/bin/npx /usr/bin/corepack

# --- studio-console (in-container operator tool) ---
# Installed into /opt/uv-tools with the shim on /usr/local/bin so the binary
# is on PATH for every process in the image. Always rebuilds: the ADD of the
# GitHub release metadata changes whenever the release does, busting the cache.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_TOOL_DIR=/opt/uv-tools \
    UV_TOOL_BIN_DIR=/usr/local/bin
RUN test -n "${STUDIO_CONSOLE_VERSION}" || (echo "STUDIO_CONSOLE_VERSION build arg required" >&2 && exit 1)
ADD "https://api.github.com/repos/selfhosthub/studio-console/releases/tags/v${STUDIO_CONSOLE_VERSION}" /tmp/.console-release.json
RUN uv tool install \
        "https://github.com/selfhosthub/studio-console/releases/download/v${STUDIO_CONSOLE_VERSION}/studio_console-${STUDIO_CONSOLE_VERSION}-py3-none-any.whl" \
    && chmod -R a+rX /opt/uv-tools

# --- API ---
WORKDIR /app/api
COPY --from=python-builder /app/api/.venv .venv
COPY --from=python-builder /app/api .
ENV PATH="/app/api/.venv/bin:$PATH" \
    PYTHONPATH="/app:/app/worker"

# Launch manifest at its frozen path - studio-console and the entrypoint read it here.
COPY contracts-data/launch-manifest.json /app/contracts/launch-manifest.json

# The image carries the full Studio source, so the license notice ships with it.
COPY LICENSE LEGAL.md /app/

# Deployment shape - read by entrypoint and by studio-console for shape-aware behavior.
RUN echo -n "core" > /etc/studio-shape && chmod 0644 /etc/studio-shape

COPY api/docker/entrypoint.sh /docker-entrypoint.sh
RUN chmod 755 /docker-entrypoint.sh

# --- UI ---
WORKDIR /app/ui
COPY --from=ui-builder /app/public ./public
COPY --from=ui-builder /app/.next/standalone ./
COPY --from=ui-builder /app/.next/static ./.next/static

# --- Workers ---
WORKDIR /app/worker
COPY workers/studio_workers/*.py studio_workers/
COPY workers/studio_workers/adapters/ studio_workers/adapters/
COPY workers/studio_workers/contracts/ studio_workers/contracts/
COPY workers/studio_workers/utils/ studio_workers/utils/
COPY workers/studio_workers/engines/__init__.py studio_workers/engines/__init__.py
COPY workers/studio_workers/engines/general/ studio_workers/engines/general/
COPY workers/studio_workers/engines/transfer/ studio_workers/engines/transfer/

# --- Supervisord ---
RUN mkdir -p /etc/supervisor/conf.d /var/log/supervisor
COPY api/docker/supervisord.conf /etc/supervisor/supervisord.conf
COPY api/docker/app.conf /etc/supervisor/conf.d/
COPY api/docker/ui.conf /etc/supervisor/conf.d/
COPY api/docker/nginx-program.conf /etc/supervisor/conf.d/nginx.conf
COPY api/docker/worker-general.conf /etc/supervisor/conf.d/
COPY api/docker/worker-transfer.conf /etc/supervisor/conf.d/
COPY api/docker/cloudflared.conf /etc/supervisor/conf.d/

# --- nginx front door ---
# Single listen port routes /api,/ws → 8000 and / → 3000, so the browser,
# SSR, and cloudflared all use one origin. nginx-start.sh renders the
# listen port from SHS_NGINX_PORT at boot.
COPY api/docker/nginx.conf.template /etc/nginx/nginx.conf.template
COPY api/docker/nginx-start.sh /usr/local/bin/nginx-start.sh
RUN chmod +x /usr/local/bin/nginx-start.sh && mkdir -p /var/run/nginx

# --- Cloudflare tunnel ---
# cloudflared starts disabled (autostart=false). studio-console's CF wizard
# writes CLOUDFLARE_TUNNEL_TOKEN to .env then runs `supervisorctl start
# cloudflared`. The wrapper reads .env fresh each start so the token works
# without a supervisord restart.
COPY api/docker/cloudflared-start.sh /usr/local/bin/cloudflared-start.sh
RUN chmod +x /usr/local/bin/cloudflared-start.sh

# --- UI runtime env injection ---
# ui-start.sh renders /app/ui/public/__env.js from /workspace/.env at every
# `supervisorctl restart ui`, so the browser picks up runtime values (CF
# tunnel domain etc.) without rebuilding the image.
COPY api/docker/ui-start.sh /usr/local/bin/ui-start.sh
RUN chmod +x /usr/local/bin/ui-start.sh

# Image runs as root: supervisord.conf has user=root and can't drop privilege
# from a non-root user. Per-service images (studio-api, studio-ui, workers)
# run as a dedicated non-root user; only the multi-process images need root.
RUN mkdir -p /workspace

WORKDIR /app/api

ENTRYPOINT ["/docker-entrypoint.sh"]
# Default CMD runs full first-boot + supervisord. Override (e.g.
# `docker run image studio-console version`) skips first-boot and execs
# the override directly - see api/docker/entrypoint.sh.
CMD ["supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]

EXPOSE 80 8000 3000 9001

# Health-check through nginx (the front door), not the API directly, so a
# dead proxy fails the container even when the API is up.
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${SHS_NGINX_PORT:-80}/health || exit 1
