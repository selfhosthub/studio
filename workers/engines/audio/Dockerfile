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
#   docker build -f engines/audio/Dockerfile .

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libgomp1 \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy and install base requirements first (for caching)
COPY shared/requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy and install audio-specific requirements
# Then remove gradio (transitive dep from chatterbox-tts - worker has no web UI)
COPY engines/audio/requirements.txt requirements.audio.txt
RUN uv pip install --system --no-cache -r requirements.audio.txt && \
    pip uninstall -y gradio gradio-client 2>/dev/null || true

# resemble-perth uses pkg_resources (removed in setuptools>=70) and distutils
# (removed from stdlib in 3.12, vendored by setuptools). Without this pin,
# PerthImplicitWatermarker silently becomes None and crashes at runtime.
RUN uv pip install --system --no-cache "setuptools<70"

# Copy shared contracts package
COPY --from=contracts . /app/contracts/

# Copy shared code
COPY shared/ shared/

# Copy engine code
COPY engines/__init__.py engines/__init__.py
COPY engines/audio/ engines/audio/

# Create non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker && chown -R worker:worker /app && mkdir -p /workspace/models/huggingface && chown -R worker:worker /workspace

# Environment variables
ENV WORKER_TYPE=audio
ENV HF_HOME=/workspace/models/huggingface
ENV WORKSPACE_ROOT=/workspace

# Run the audio worker
USER worker
CMD ["python", "-m", "shared.worker"]
