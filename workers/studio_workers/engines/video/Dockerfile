# workers/studio_workers/engines/video/Dockerfile
# Video worker: FFmpeg + Whisper STT (CPU-only, no GPU)
#
# Features:
# - Image-to-video with zoom/pan effects (Ken Burns)
# - Video + audio merging with optional subtitles
# - Whisper STT for transcription (CPU - GPU not needed for subtitle generation)
# - Karaoke-style ASS subtitles
#
# Build context should be workers/ directory:
#   docker build -f studio_workers/engines/video/Dockerfile .

FROM python:3.12-slim

WORKDIR /app

# Install FFmpeg, fontconfig, and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    libpng-dev \
    git \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy and install base requirements first (for caching)
COPY studio_workers/requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Install CPU-only PyTorch BEFORE Whisper (prevents Whisper pulling CUDA wheels)
RUN uv pip install --system --no-cache \
    torch --index-url https://download.pytorch.org/whl/cpu

# Copy and install video-specific requirements (Whisper will use existing CPU torch)
COPY studio_workers/engines/video/requirements.txt requirements.video.txt
RUN uv pip install --system --no-cache -r requirements.video.txt

# Copy shared contracts package
COPY studio_workers/contracts/ studio_workers/contracts/

# Copy worker runtime (engine dirs copied selectively below)
COPY studio_workers/*.py studio_workers/
COPY studio_workers/adapters/ studio_workers/adapters/
COPY studio_workers/utils/ studio_workers/utils/

# Copy engine code. Subtitle fonts ride along in studio_workers/engines/video/fonts/ and are
# passed to libass via the ass filter's fontsdir, so no system font install.
COPY studio_workers/engines/__init__.py studio_workers/engines/__init__.py
COPY studio_workers/engines/video/ studio_workers/engines/video/

# Image carries Studio worker source, so the license notice ships with it.
LABEL org.opencontainers.image.title="Self-Host Studio worker (video)" \
      org.opencontainers.image.vendor="Self-Host Hub" \
      org.opencontainers.image.source="https://github.com/selfhosthub/studio" \
      org.opencontainers.image.licenses="LicenseRef-Studio-Use-License"
COPY LICENSE LEGAL.md /app/

# Pull the patched libtiff and setuptools (vendored jaraco.context rides along)
RUN apt-get update && apt-get install -y --only-upgrade libtiff6 linux-libc-dev libexpat1 libssh-4 && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir "setuptools>=78.1.1"

# Create non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker && chown -R worker:worker /app

# Default Whisper model (can be overridden via env)
ENV WHISPER_MODEL=base

# Run the video worker
ENV WORKER_TYPE=video
USER worker
CMD ["python", "-m", "studio_workers.worker"]
