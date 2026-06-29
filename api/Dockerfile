# api/Dockerfile
# Multi-stage build: compile native extensions in builder, copy to slim runner

# --- Stage 1: Builder (has gcc for compiling native extensions) ---
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install deps first (cached unless pyproject.toml or uv.lock change)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache --no-install-project

# Copy source and install project
COPY . .
COPY --from=contracts . /app/contracts/
RUN uv sync --frozen --no-dev --no-cache

# --- Stage 2: Runner (no compiler, no build tools) ---
FROM python:3.12-slim

ARG GIT_SHA=""
LABEL org.opencontainers.image.revision="${GIT_SHA}"

ENV PYTHONUNBUFFERED=1 \
    PORT=8000 \
    SHS_GIT_SHA=${GIT_SHA}

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy compiled venv and app code from builder, setting ownership inline
# (avoids a slow recursive chown over the venv on Ubuntu/overlay2)
COPY --from=builder --chown=appuser:appgroup /app/.venv .venv
COPY --from=builder --chown=appuser:appgroup /app .
ENV PATH="/app/.venv/bin:$PATH"

# Copy entrypoint to root and make executable
COPY --chown=appuser:appgroup scripts/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod 755 /docker-entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Create workspace and ensure /app dir itself is writable by appuser
RUN mkdir -p /workspace && chown appuser:appgroup /workspace /app
USER appuser

ENTRYPOINT ["/docker-entrypoint.sh"]

CMD ["python", "main.py"]
