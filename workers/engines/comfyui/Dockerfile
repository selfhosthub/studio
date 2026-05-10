# workers/engines/comfyui/Dockerfile
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
#   docker build -f engines/comfyui/Dockerfile .

FROM python:3.12-slim

WORKDIR /app/worker

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy and install base requirements
COPY shared/requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy and install ComfyUI worker requirements
COPY engines/comfyui_remote/requirements.txt requirements.comfyui.txt
RUN uv pip install --system --no-cache -r requirements.comfyui.txt

# Copy shared contracts package
COPY --from=contracts . /app/worker/contracts/

# Copy shared code
COPY shared/ shared/

# Copy engine code
COPY engines/__init__.py engines/__init__.py
COPY engines/comfyui/ engines/comfyui/
# Swap __init__.py to exclude ComfyUIServer (no local ComfyUI in this image)
COPY engines/comfyui_remote/comfyui_init.py engines/comfyui/__init__.py
COPY engines/comfyui_remote/ engines/comfyui_remote/

# Create non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app/worker -s /sbin/nologin worker && chown -R worker:worker /app/worker && mkdir -p /workspace && chown -R worker:worker /workspace

# Default to image generation mode (override with WORKER_TYPE=comfyui-video)
ENV WORKER_TYPE=comfyui-image
ENV WORKSPACE_ROOT=/workspace

# COMFYUI_URL is REQUIRED - worker will fail to start without it
# Example: COMFYUI_URL=http://your-comfyui-host:8188

USER worker
CMD ["python", "-m", "shared.worker"]
