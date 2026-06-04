# Docker Images

Studio images are published to GHCR. You can pull pre-built images or build from source.

> **Community & support:** [SelfHostHub Community](https://www.skool.com/selfhosthub) · [Innovators (Plus)](https://www.skool.com/selfhostinnovators)


## Image inventory

| Image | Dockerfile | Build context |
|-------|-----------|---------------|
| `ghcr.io/selfhosthub/studio-api` | `api/Dockerfile` | `api/` |
| `ghcr.io/selfhosthub/studio-ui` | `ui/Dockerfile` | `ui/` |
| `ghcr.io/selfhosthub/studio-worker-general` | `workers/engines/general/Dockerfile` | `workers/` |
| `ghcr.io/selfhosthub/studio-worker-transfer` | `workers/engines/transfer/Dockerfile` | `workers/` |
| `ghcr.io/selfhosthub/studio-worker-video` | `workers/engines/video/Dockerfile` | `workers/` |
| `ghcr.io/selfhosthub/studio-worker-audio` | `workers/engines/audio/Dockerfile` | `workers/` |
| `ghcr.io/selfhosthub/studio-worker-comfyui` | `workers/engines/comfyui/Dockerfile` | `workers/` |
| `ghcr.io/selfhosthub/studio-core` | `Dockerfile` | repo root |
| `ghcr.io/selfhosthub/studio-full` | `Dockerfile.full` | repo root |

### Image descriptions

- **`studio-api`** - API server only. Multi-stage build (no compiler in final image).
- **`studio-ui`** - Next.js standalone UI only.
- **`studio-worker-general`** - HTTP/API orchestrator. Handles provider integrations, polling, thumbnails.
- **`studio-worker-transfer`** - File streaming. Uploads generated content to external platforms.
- **`studio-worker-video`** - FFmpeg + Whisper STT (CPU-only). Video processing, subtitles, transcription.
- **`studio-worker-audio`** - Chatterbox TTS. Text-to-speech with voice cloning.
- **`studio-worker-comfyui`** - Lightweight proxy to operator-managed ComfyUI server. Deploy with `WORKER_TYPE=comfyui-image` or `WORKER_TYPE=comfyui-video`.
- **`studio-core`** - Core image. API + UI + general/transfer workers in one container under supervisord. Postgres runs as a separate container alongside it. Used by the [Core](deployment-matrix.md#core) deployment shape.
- **`studio-full`** - Full image. API + UI + general/transfer workers + embedded PostgreSQL all under supervisord in one container. For platforms that only allow one container (RunPod pods, Vast.ai). Postgres data lives at `/workspace/db` - mount a network volume or your data is lost on container destroy. Used by the [Full](deployment-matrix.md#full) deployment shape.

### Worker model policy

**Worker images never bundle LLMs, AI models, or third-party applications** (ComfyUI, Whisper models, HuggingFace models, etc.). The Core and Full images follow the same policy - they include only the general and transfer worker code, no model weights.

These are installed at container spin-up and stored on the operator's infrastructure - local directory or network volume (RunPod, etc.), mounted into the container. Storage paths: `/workspace/models/` (general), `HF_HOME` (HuggingFace cache).

## Pull pre-built images

```bash
docker compose pull
```

Or pull individually:

```bash
docker pull ghcr.io/selfhosthub/studio-api:latest
docker pull ghcr.io/selfhosthub/studio-ui:latest
```

## Build from source

```bash
# API
docker build -f api/Dockerfile -t ghcr.io/selfhosthub/studio-api:latest api/

# UI
docker build -f ui/Dockerfile -t ghcr.io/selfhosthub/studio-ui:latest ui/

# Workers (build context must be workers/ - shared code lives there)
docker build -f workers/engines/general/Dockerfile -t ghcr.io/selfhosthub/studio-worker-general:latest workers/
docker build -f workers/engines/transfer/Dockerfile -t ghcr.io/selfhosthub/studio-worker-transfer:latest workers/
docker build -f workers/engines/video/Dockerfile -t ghcr.io/selfhosthub/studio-worker-video:latest workers/
docker build -f workers/engines/audio/Dockerfile -t ghcr.io/selfhosthub/studio-worker-audio:latest workers/
docker build -f workers/engines/comfyui/Dockerfile -t ghcr.io/selfhosthub/studio-worker-comfyui:latest workers/

# Core image (API + UI + general/transfer worker, no Postgres)
docker build -f Dockerfile -t ghcr.io/selfhosthub/studio-core:latest .

# Full image (everything + embedded Postgres)
docker build -f Dockerfile.full -t ghcr.io/selfhosthub/studio-full:latest .
```

## Multi-platform builds

For ARM + AMD64:

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t ghcr.io/selfhosthub/studio-api:latest --push api/
```
