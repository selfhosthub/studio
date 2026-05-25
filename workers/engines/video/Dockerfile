# workers/engines/video/Dockerfile
# Video worker: FFmpeg + Whisper STT (CPU-only, no GPU)
#
# Features:
# - Image-to-video with zoom/pan effects (Ken Burns)
# - Video + audio merging with optional subtitles
# - Whisper STT for transcription (CPU - GPU not needed for subtitle generation)
# - Karaoke-style ASS subtitles
#
# Build context should be workers/ directory:
#   docker build -f engines/video/Dockerfile .

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
COPY shared/requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Install CPU-only PyTorch BEFORE Whisper (prevents Whisper pulling CUDA wheels)
RUN uv pip install --system --no-cache \
    torch --index-url https://download.pytorch.org/whl/cpu

# Copy and install video-specific requirements (Whisper will use existing CPU torch)
COPY engines/video/requirements.txt requirements.video.txt
RUN uv pip install --system --no-cache -r requirements.video.txt

# Copy shared contracts package
COPY --from=contracts . /app/contracts/

# Copy shared code
COPY shared/ shared/

# Copy engine code
COPY engines/__init__.py engines/__init__.py
COPY engines/video/ engines/video/

# Install custom fonts for subtitles
COPY engines/video/fonts/ /tmp/fonts/
RUN mkdir -p /usr/share/fonts/truetype/custom && \
    cp -r /tmp/fonts/*/*.ttf /usr/share/fonts/truetype/custom/ 2>/dev/null || true && \
    fc-cache -f -v && \
    rm -rf /tmp/fonts

# Create non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker && chown -R worker:worker /app

# Default Whisper model (can be overridden via env)
ENV WHISPER_MODEL=base

# Run the video worker
ENV WORKER_TYPE=video
USER worker
CMD ["python", "-m", "shared.worker"]
