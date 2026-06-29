# Studio Transfer Worker
# Lightweight worker for streaming file transfers (upload/download)
# No GPU, no FFmpeg, no media processing - just HTTP streaming
#
# Build context should be workers/ directory:
#   docker build -f engines/transfer/Dockerfile .

FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy and install base requirements (httpx, psutil, etc.)
COPY shared/requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy shared contracts package
COPY --from=contracts . /app/contracts/

# Copy shared code
COPY shared/ shared/

# Copy engine code
COPY engines/__init__.py engines/__init__.py
COPY engines/transfer/ engines/transfer/

# Create non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker && chown -R worker:worker /app && mkdir -p /workspace && chown -R worker:worker /workspace

# Environment variables
ENV WORKER_TYPE=transfer
ENV WORKSPACE_ROOT=/workspace

# Run the transfer worker
USER worker
CMD ["python", "-m", "shared.worker"]
