# Studio Orchestrator Worker
# Lightweight worker for HTTP-based provider integrations
# No GPU required - handles API calls, polling, file downloads, thumbnail generation
#
# Build context should be workers/ directory:
#   docker build -f engines/general/Dockerfile .

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
COPY shared/requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy shared contracts package
COPY --from=contracts . /app/contracts/

# Copy shared code
COPY shared/ shared/

# Copy engine code
COPY engines/__init__.py engines/__init__.py
COPY engines/general/ engines/general/

# Create non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker && chown -R worker:worker /app

# Run the orchestrator worker
ENV WORKER_TYPE=general
USER worker
CMD ["python", "-m", "shared.worker"]
