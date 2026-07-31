# workers/studio_workers/engines/comfyui/Dockerfile
# ComfyUI worker: lightweight proxy to operator-managed ComfyUI server
# No GPU, no CUDA, no bundled ComfyUI - just HTTP client + workflow templates
#
# Deployment modes (via WORKER_TYPE env var):
#   WORKER_TYPE=comfyui-image  - image generation queue (standard GPU)
#   WORKER_TYPE=comfyui-video  - video generation queue (high-memory GPU)
#
# Requires:
#   COMFYUI_URL - URL of the operator's ComfyUI server
#
# Build context should be workers/ directory:
#   docker build -f studio_workers/engines/comfyui/Dockerfile .

FROM python:3.12-slim

WORKDIR /app/worker

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && apt-get install -y --only-upgrade libexpat1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy and install base requirements
COPY studio_workers/requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy and install ComfyUI worker requirements
COPY studio_workers/engines/comfyui/requirements.txt requirements.comfyui.txt
RUN uv pip install --system --no-cache -r requirements.comfyui.txt

# Copy shared contracts package
COPY studio_workers/contracts/ studio_workers/contracts/

# Copy worker runtime (engine dirs copied selectively below)
COPY studio_workers/*.py studio_workers/
COPY studio_workers/adapters/ studio_workers/adapters/
COPY studio_workers/utils/ studio_workers/utils/

# Copy engine code
COPY studio_workers/engines/__init__.py studio_workers/engines/__init__.py
COPY studio_workers/engines/comfyui/ studio_workers/engines/comfyui/

# Image carries Studio worker source, so the license notice ships with it.
LABEL org.opencontainers.image.title="Self-Host Studio worker (comfyui)" \
      org.opencontainers.image.vendor="Self-Host Hub" \
      org.opencontainers.image.source="https://github.com/selfhosthub/studio" \
      org.opencontainers.image.licenses="LicenseRef-Studio-Use-License"
COPY LICENSE LEGAL.md /app/

# Create non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app/worker -s /sbin/nologin worker && chown -R worker:worker /app/worker && mkdir -p /workspace && chown -R worker:worker /workspace

# Default to image generation mode (override with WORKER_TYPE=comfyui-video)
ENV WORKER_TYPE=comfyui-image
ENV WORKSPACE_ROOT=/workspace

# COMFYUI_URL is REQUIRED - worker will fail to start without it
# Example: COMFYUI_URL=http://your-comfyui-host:8188

USER worker
CMD ["python", "-m", "studio_workers.worker"]
