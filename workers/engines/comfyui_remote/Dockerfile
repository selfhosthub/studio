# Studio ComfyUI Remote Worker (shs-comfyui provider)
# Lightweight worker that calls an external ComfyUI server (no GPU required).
#
# Use Cases:
# - Call RunPod ComfyUI endpoints
# - Call cloud GPU services (Replicate, etc.)
# - Call self-hosted ComfyUI on a GPU server
#
# This worker does NOT embed ComfyUI. It only contains:
# - ComfyUI API client (REST + WebSocket for progress)
# - Workflow templates
# - Thumbnail generation (PIL)
#
# Requires:
# - COMFYUI_URL env var pointing to external ComfyUI server
# - No GPU needed (runs on CPU-only machines)
#
# Image size: ~200MB (vs ~10GB+ for embedded ComfyUI worker)
#
# Build context should be workers/ directory:
#   docker build -f engines/comfyui_remote/Dockerfile .

FROM python:3.12-slim

WORKDIR /app/worker

# Install minimal system dependencies
# Note: libgl1 replaces libgl1-mesa-glx in newer Debian (trixie+)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy and install base requirements
COPY shared/requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy and install remote-specific requirements (lighter than full comfyui)
COPY engines/comfyui_remote/requirements.txt requirements.remote.txt
RUN uv pip install --system --no-cache -r requirements.remote.txt

# Copy shared contracts package
COPY --from=contracts . /app/worker/contracts/

# Copy shared code
COPY shared/ shared/

# Copy engine code
COPY engines/__init__.py engines/__init__.py
COPY engines/comfyui/ engines/comfyui/
COPY engines/comfyui_remote/comfyui_init.py engines/comfyui/__init__.py
COPY engines/comfyui_remote/ engines/comfyui_remote/

# Create non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app/worker -s /sbin/nologin worker && chown -R worker:worker /app/worker && mkdir -p /workspace && chown -R worker:worker /workspace

# Environment variables
ENV WORKER_TYPE=comfyui-remote
ENV WORKSPACE_ROOT=/workspace

# COMFYUI_URL is REQUIRED - worker will fail to start without it
# Example: COMFYUI_URL=https://your-runpod-instance.runpod.io

USER worker
CMD ["python", "-m", "shared.worker"]
