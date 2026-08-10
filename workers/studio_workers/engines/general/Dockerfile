# Studio Orchestrator Worker
# Lightweight worker for HTTP-based provider integrations
# No GPU required - handles API calls, polling, file downloads, thumbnail generation
#
# Build context should be workers/ directory:
#   docker build -f studio_workers/engines/general/Dockerfile .

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    libpng-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy and install base requirements
COPY studio_workers/requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy shared contracts package
COPY studio_workers/contracts/ studio_workers/contracts/

# Copy worker runtime (engine dirs copied selectively below)
COPY studio_workers/*.py studio_workers/
COPY studio_workers/adapters/ studio_workers/adapters/
COPY studio_workers/utils/ studio_workers/utils/

# Copy engine code
COPY studio_workers/engines/__init__.py studio_workers/engines/__init__.py
COPY studio_workers/engines/general/ studio_workers/engines/general/

# Image carries Studio worker source, so the license notice ships with it.
LABEL org.opencontainers.image.title="Self-Host Studio worker (general)" \
      org.opencontainers.image.vendor="Self-Host Hub" \
      org.opencontainers.image.source="https://github.com/selfhosthub/studio" \
      org.opencontainers.image.licenses="LicenseRef-Studio-Use-License"
COPY LICENSE LEGAL.md /app/

# Pull the patched kernel headers package
RUN apt-get update && apt-get install -y --only-upgrade linux-libc-dev && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g 1000 worker && useradd -u 1000 -g worker -d /app -s /sbin/nologin worker && chown -R worker:worker /app

# Run the orchestrator worker
ENV WORKER_TYPE=general
# HOME on a 1777 path so caches (~/.cache, whisper) work at any runtime uid,
# including compose user: overrides that have no passwd entry
ENV HOME=/var/tmp/studio-workers/home
USER worker
CMD ["python", "-m", "studio_workers.worker"]
