# Studio Audio Worker (shs-audio provider)
# GPU worker for text-to-speech with Chatterbox TTS
#
# Features:
# - Text-to-speech (standard + turbo variants)
# - Voice cloning from ~10s reference audio
# - Paralinguistic tags [laugh], [chuckle], [cough] (turbo)
#
# Device auto-detection: CUDA > MPS > CPU
# PyTorch CUDA wheels include CUDA runtime - no nvidia/cuda base needed.
#
# Models auto-download from HuggingFace Hub on first run.
# Mount HF_HOME volume to persist across restarts.
#
# Build context should be workers/ directory:
#   docker build -f studio_workers/engines/audio/Dockerfile .

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libgomp1 \
    libsndfile1 \
    && apt-get install -y --only-upgrade libexpat1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy and install base requirements first (for caching)
COPY studio_workers/requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy and install audio-specific requirements
# Then remove gradio (transitive dep from chatterbox-tts - worker has no web UI)
COPY studio_workers/engines/audio/requirements.txt requirements.audio.txt
RUN uv pip install --system --no-cache -r requirements.audio.txt && \
    pip uninstall -y gradio gradio-client 2>/dev/null || true

# resemble-perth needs pkg_resources (removed in setuptools 82, deprecation-warns in 81); >=78.1.1 has
# the trivy-flagged CVE fixes. Without pkg_resources, PerthImplicitWatermarker
# silently becomes None and TTS crashes at model init.
RUN uv pip install --system --no-cache "setuptools>=78.1.1,<81"

# Fail the build if the watermarker import chain breaks (no silent None).
RUN python -c "from perth.perth_net.perth_net_implicit.perth_watermarker import PerthImplicitWatermarker"

# Copy shared contracts package
COPY studio_workers/contracts/ studio_workers/contracts/

# Copy worker runtime (engine dirs copied selectively below)
COPY studio_workers/*.py studio_workers/
COPY studio_workers/adapters/ studio_workers/adapters/
COPY studio_workers/utils/ studio_workers/utils/

# Copy engine code
COPY studio_workers/engines/__init__.py studio_workers/engines/__init__.py
COPY studio_workers/engines/audio/ studio_workers/engines/audio/

# Image carries Studio worker source, so the license notice ships with it.
LABEL org.opencontainers.image.title="Self-Host Studio worker (audio)" \
      org.opencontainers.image.vendor="Self-Host Hub" \
      org.opencontainers.image.source="https://github.com/selfhosthub/studio" \
      org.opencontainers.image.licenses="LicenseRef-Studio-Use-License"
COPY LICENSE LEGAL.md /app/

# Create non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker && chown -R worker:worker /app && mkdir -p /workspace/models/huggingface && chown -R worker:worker /workspace

# Environment variables
ENV WORKER_TYPE=audio
ENV HF_HOME=/workspace/models/huggingface
ENV WORKSPACE_ROOT=/workspace

# Run the audio worker
USER worker
CMD ["python", "-m", "studio_workers.worker"]
