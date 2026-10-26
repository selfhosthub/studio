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
RUN pip install --no-cache-dir --upgrade pip==26.2.2

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libgomp1 \
    libsndfile1 \
    && apt-get install -y --only-upgrade libexpat1 \
    bsdutils libblkid1 liblastlog2-2 libmount1 libsmartcols1 libuuid1 login mount util-linux \
    libssl3t64 openssl openssl-provider-legacy \
    perl-base gzip libpcre2-8-0 libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv

# Copy and install base requirements first (for caching)
# Pin every dependency to the versions in workers/uv.lock
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --all-extras --no-emit-project --no-hashes -q -o constraints.txt

COPY studio_workers/requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt -c constraints.txt

# Copy and install audio-specific requirements without gradio (declared by chatterbox-tts, never imported)
COPY studio_workers/engines/audio/requirements.txt requirements.audio.txt
RUN echo gradio > excludes.txt && \
    uv pip install --system --no-cache -r requirements.audio.txt -c constraints.txt --excludes excludes.txt

# Remove pre-commit with its virtualenv (s3tokenizer declares pre-commit as a runtime dep)
RUN pip uninstall -y pre-commit virtualenv 2>/dev/null || true

# resemble-perth needs pkg_resources (removed in setuptools 82, deprecation-warns in 81); >=78.1.1 has
# the trivy-flagged CVE fixes. Without pkg_resources, PerthImplicitWatermarker
# silently becomes None and TTS crashes at model init.
RUN uv pip install --system --no-cache "setuptools>=78.1.1,<81" -c constraints.txt

# Fail the build if the watermarker or either model class the handler loads cannot be imported.
RUN python -c "from perth.perth_net.perth_net_implicit.perth_watermarker import PerthImplicitWatermarker; from chatterbox.tts import ChatterboxTTS; from chatterbox.tts_turbo import ChatterboxTurboTTS"

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
RUN groupadd -g 1000 worker && useradd -u 1000 -g worker -d /app -s /sbin/nologin worker && chown -R worker:worker /app && mkdir -p /workspace/models/huggingface && chown -R worker:worker /workspace

# Environment variables
ENV WORKER_TYPE=audio
# HOME on a 1777 path so caches (~/.cache, whisper) work at any runtime uid,
# including compose user: overrides that have no passwd entry
ENV HOME=/var/tmp/studio-workers/home
ENV HF_HOME=/workspace/models/huggingface
ENV WORKSPACE_ROOT=/workspace
# Scratch stays off the /workspace bind mount so writes never depend on host dir ownership
ENV SHS_AUDIO_OUTPUT_DIR=/var/tmp/studio-workers/audio_output

# Run the audio worker
# Remove pip from the runtime image
RUN /usr/local/bin/python -m pip uninstall -y pip

USER worker
CMD ["python", "-m", "studio_workers.worker"]
