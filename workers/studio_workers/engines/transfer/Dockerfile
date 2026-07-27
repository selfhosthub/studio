# Studio Transfer Worker
# Lightweight worker for streaming file transfers (upload/download)
# No GPU, no FFmpeg, no media processing - just HTTP streaming
#
# Build context should be workers/ directory:
#   docker build -f studio_workers/engines/transfer/Dockerfile .

FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy and install base requirements (httpx, psutil, etc.)
COPY studio_workers/requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy shared contracts package
COPY --from=contracts . /app/contracts/

# Copy worker runtime (engine dirs copied selectively below)
COPY studio_workers/*.py studio_workers/
COPY studio_workers/adapters/ studio_workers/adapters/
COPY studio_workers/utils/ studio_workers/utils/

# Copy engine code
COPY studio_workers/engines/__init__.py studio_workers/engines/__init__.py
COPY studio_workers/engines/transfer/ studio_workers/engines/transfer/

# Image carries Studio worker source, so the license notice ships with it.
LABEL org.opencontainers.image.title="Self-Host Studio worker (transfer)" \
      org.opencontainers.image.vendor="Self-Host Hub" \
      org.opencontainers.image.source="https://github.com/selfhosthub/studio" \
      org.opencontainers.image.licenses="LicenseRef-Studio-Use-License"
COPY LICENSE LEGAL.md /app/

# Create non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker && chown -R worker:worker /app && mkdir -p /workspace && chown -R worker:worker /workspace

# Environment variables
ENV WORKER_TYPE=transfer
ENV WORKSPACE_ROOT=/workspace

# Run the transfer worker
USER worker
CMD ["python", "-m", "studio_workers.worker"]
