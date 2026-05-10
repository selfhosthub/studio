# VPS + RunPod Deployment Guide

> **Community & support:** [SelfHostHub Community](https://www.skool.com/selfhosthub) · [Innovators (Plus)](https://www.skool.com/selfhostinnovators)

The recommended setup for self-hosted GPU workflows: a cheap always-on VPS for the core stack, with RunPod GPU pods spun up only when you need them.

---

## Overview

Most Studio workloads (API, UI, general orchestration, file transfers) are CPU-bound and need to be always-on. GPU workloads (TTS, image generation, video generation) are bursty - you need a lot of power for minutes at a time, then nothing for hours.

Splitting these across a VPS and RunPod gives you:

- **Low fixed cost** - a $20/month VPS handles the always-on stack
- **Pay-per-use GPU** - spin up a 3090 for $0.50/hr only when jobs are queued
- **No wasted GPU idle time** - stop the pod when the queue is empty
- **Scale by worker type** - different GPU tiers for different workloads

---

## What runs on the VPS

The VPS runs the core Studio stack via Docker Compose:

| Service | Image | Purpose |
|---------|-------|---------|
| PostgreSQL | `pgvector/pgvector:pg18` | Database (Postgres 18 with the pgvector extension preinstalled) |
| API | `ghcr.io/selfhosthub/studio-api` | Backend server |
| UI | `ghcr.io/selfhosthub/studio-ui` | Next.js frontend |
| General worker | `ghcr.io/selfhosthub/studio-worker-general` | HTTP/API orchestration, provider integrations |
| Transfer worker | `ghcr.io/selfhosthub/studio-worker-transfer` | File uploads to external platforms |

**Minimum VPS specs:** 2 CPU / 4 GB RAM / 40 GB disk. A Hetzner CX32 or equivalent handles this comfortably.

### Setup

Provision the stack on the VPS via `studio-console` (the supported entry point for split-services), or directly via `docker compose up -d` against [docker-compose.yml](../../docker-compose.yml) if you'd rather drive compose yourself. See [bootstrap.md](bootstrap.md) for the first-boot sequence either way.

---

## What runs on RunPod

GPU workers run as separate RunPod pods, each polling the VPS API for jobs:

| Worker | Image | Queue (`SHS_WORKER_TYPE`) |
|--------|-------|-------|
| Video | `ghcr.io/selfhosthub/studio-worker-video` | `video` |
| Audio (TTS) | `ghcr.io/selfhosthub/studio-worker-audio` | `audio` |
| ComfyUI image | `ghcr.io/selfhosthub/studio-worker-comfyui` | `comfyui-image` |
| ComfyUI video | `ghcr.io/selfhosthub/studio-worker-comfyui` | `comfyui-video` |

The two ComfyUI rows share one image - set `SHS_WORKER_TYPE` to pick the queue.

Workers are stateless pollers. They connect to the API via `SHS_API_BASE_URL`, authenticate with `SHS_WORKER_SHARED_SECRET`, pick up jobs, process them, and push results back. No shared filesystem between VPS and RunPod is required.

---

## GPU requirements per worker type

| Worker | GPU needed | Recommended | Minimum | Notes |
|--------|-----------|-------------|---------|-------|
| `shs-video` | None (CPU-only) | Any instance | 2 CPU / 4 GB RAM | FFmpeg + Whisper STT. CPU-bound. Any cheap pod works. |
| `shs-audio` (Chatterbox TTS) | Light GPU | RTX 3060 / 3080 | 8 GB VRAM | MPS (Apple Silicon) works for local dev. Inference is fast on consumer GPUs. |
| `shs-comfyui` (image gen) | VRAM-hungry | RTX 3090 / 4090 | RTX 3080 (10 GB VRAM) | SDXL and Flux models need 10+ GB VRAM. 24 GB recommended. |
| `shs-comfyui` (video gen) | Heavy | RTX 4090 / A100 | RTX 3090 (24 GB VRAM) | Video generation models are the most VRAM-hungry. 24 GB minimum, 40+ GB ideal. |

**Cost-performance sweet spot:** An RTX 3090 pod on RunPod (~$0.40–0.50/hr community cloud) handles audio + image generation well. Only video generation benefits from stepping up to a 4090 or A100.

---

## RunPod network volume setup

Network volumes persist model downloads across pod restarts. Without one, every pod start re-downloads multi-GB models.

### Create a network volume

1. Go to **RunPod Console → Storage → Network Volumes**
2. Click **Create Network Volume**
3. Choose the **same region** as your pods (volumes are region-locked)
4. Size: **50 GB minimum** (100 GB recommended for ComfyUI models)
5. Name it something identifiable (e.g., `studio-workspace`)

### Why it's required

- Worker images never bundle AI models (see [docker-images.md](docker-images.md#worker-model-and-application-policy))
- Models download to `/workspace/models/` on first run and are cached
- HuggingFace cache lives at `/workspace/models/huggingface` (`HF_HOME`)
- Without a network volume, you pay for model downloads on every pod start

---

## Worker pod template

Create a pod template on RunPod for each worker type you need.

### Image

Use the GHCR image for the worker type:

- `ghcr.io/selfhosthub/studio-worker-video:latest`
- `ghcr.io/selfhosthub/studio-worker-audio:latest`
- `ghcr.io/selfhosthub/studio-worker-comfyui:latest`

### Required environment variables

| Variable | Value | Notes |
|----------|-------|-------|
| `SHS_API_BASE_URL` | `https://studio.example.com` | Public URL of your VPS API. Must be reachable from RunPod. |
| `SHS_WORKER_SHARED_SECRET` | *(copy from VPS `.env`)* | Must match the API exactly. |
| `SHS_WORKSPACE_ROOT` | `/workspace` | Mount point for the network volume. |
| `SHS_WORKER_TYPE` | `video`, `audio`, `comfyui-image`, or `comfyui-video` | Which job queue this worker polls. |

### Optional environment variables

| Variable | Default | Notes |
|----------|---------|-------|
| `SHS_WHISPER_MODEL` | `base` | Video worker only. Whisper model size (`tiny`, `base`, `small`, `medium`, `large`). |
| `HF_HOME` | `/workspace/models/huggingface` | Audio worker. HuggingFace cache directory (no `SHS_` prefix - this is HuggingFace's own var). |
| `SHS_COMFYUI_URL` | `http://127.0.0.1:8188` | ComfyUI worker. URL of the ComfyUI server (typically localhost if running in the same pod). |

### Volume mount

Attach your network volume to `/workspace`.

### Pod configuration

- **Container disk:** 20 GB (enough for the runtime; models go to the network volume)
- **Volume mount path:** `/workspace`
- **Expose HTTP ports:** Not required (workers are outbound-only pollers)

### Full image: lock down the supervisord dashboard

The `studio-full` (Full) and `studio-core` (Core) images run API + UI + worker(s) under supervisord, whose web dashboard is exposed on port `9001`. RunPod auto-publishes that port via its public TCP proxy, so anyone with the proxy URL could otherwise restart the API, kill workers, or stop Postgres.

Before starting the pod, set both:

| Variable | Value |
|----------|-------|
| `SHS_SUPERVISOR_USER` | Username for the dashboard (e.g. `admin`). |
| `SHS_SUPERVISOR_PASSWORD` | Password - generate with `openssl rand -base64 24`. |

Supervisord refuses to start if either env var is unset. The dashboard is reachable at the RunPod TCP proxy URL for port 9001 and prompts for HTTP basic-auth on every request. In-container `supervisorctl status` keeps working without auth (it talks to the unix socket, not HTTP).

### Single-pod Full with on-demand workers (planned)

The `studio-full` image today ships with general + transfer workers only - no audio, video, or ComfyUI. A planned extension lets a single RunPod pod host all worker types by deferring their install until the operator asks for them, instead of bundling multi-GB dependencies into the base image.

Shape of the design (not yet implemented):

- **Network volume at `/workspace` is required.** All installed components - Python deps, ComfyUI, custom nodes, model weights, Whisper, Chatterbox TTS - live under `/workspace` so they survive pod restarts and serverless cold-starts. Ephemeral volumes lose everything; network volume is the only supported choice.
- **Workers default to `autostart=false`.** Supervisord conf for `worker-audio`, `worker-video`, `worker-comfyui` ships in the image but does not launch on boot. No crash-loop, no resource consumption, until the operator opts in.
- **CLI-only management.** No UI surface. An in-container manager script handles install, errors, and the `supervisorctl start <worker>` flip once a marker file at `/workspace/installed/<worker>.marker` is written.
- **RunPod templates handle the heavy lifting.** Pre-built templates that pre-install requirements onto the network volume are the expected path; manual install inside the running container is supported but not the recommended flow.
- **Models live in `/workspace/models/`** - same layout the multi-pod topology already uses (`/workspace/models/huggingface`, `/workspace/models/comfyui`, etc.).

Until this lands, GPU workloads on RunPod follow the multi-pod topology in the rest of this doc: Full or VPS for the core stack, separate GPU pods for audio/video/comfyui workers.

---

## Networking

The VPS API must be reachable from RunPod workers over HTTPS. Three options:

### Option 1: Domain + Caddy (recommended)

Point a domain at your VPS IP and let Caddy handle TLS automatically. The compose stack's internal nginx (on `SHS_NGINX_PORT`, default 80) is the only port to forward to - it routes API and UI internally.

```
studio.example.com → VPS IP (ports 80/443)
  Caddy reverse-proxies → localhost:${SHS_NGINX_PORT}
```

Workers set `SHS_API_BASE_URL=https://studio.example.com`.

### Option 2: Cloudflare Tunnel

If you can't open ports or don't want to expose the VPS IP, use the bundled `cloudflared` compose profile (`COMPOSE_PROFILES=cloudflared`). It joins the `prod-network` and points at the internal nginx - no host port exposure needed.

Good for: VPS behind NAT, operators who want zero open ports.

### Option 3: Raw IP

Use `http://<VPS_IP>:${SHS_NGINX_PORT}` directly. No TLS, no domain. Acceptable for testing only - RunPod workers communicate over the public internet, use TLS in production.

Workers set `SHS_API_BASE_URL=http://<VPS_IP>:${SHS_NGINX_PORT}`.

---

## Cost breakdown

Example monthly cost for a solo creator producing video content:

| Component | Provider | Spec | Cost |
|-----------|----------|------|------|
| VPS | Hetzner CX32 | 4 CPU / 8 GB RAM / 80 GB | ~$8/month |
| Network volume | RunPod | 100 GB | ~$10/month |
| GPU (audio) | RunPod 3090 | ~2 hrs/month | ~$1/month |
| GPU (image) | RunPod 3090 | ~5 hrs/month | ~$2.50/month |
| GPU (video) | RunPod 4090 | ~3 hrs/month | ~$2.50/month |
| Domain | Any registrar | Optional | ~$1/month |
| **Total** | | | **~$25/month** |

Compare to: a dedicated GPU server ($150–300/month) or cloud GPU instances billed 24/7.

The key savings come from GPU workers being idle most of the time. You only pay for active generation time.

---

## Day-to-day operations

### Starting a worker pod

1. Go to **RunPod Console → Pods**
2. Create a pod from your saved template (or start a stopped pod)
3. The worker registers with the API automatically on startup
4. Check **Studio UI → Settings → Workers** to confirm it appears

### Stopping a worker pod

Stop the pod when you're done generating. Queued jobs will wait until a worker comes back online - nothing is lost.

### Monitoring

- **RunPod Console** - pod status, GPU utilization, logs
- **Studio UI → Settings → Workers** - registered workers, last heartbeat, job counts
- **VPS Docker logs** - `docker compose logs -f api` for API-side worker communication

### Common operations

```bash
# On the VPS - check worker registrations
docker compose logs api | grep "worker"

# On the VPS - restart API after config change
docker compose restart api

# On the VPS - view all running services
docker compose ps
```

---

## GPU availability tips

RunPod GPU availability varies by region and time of day. Tips for getting pods:

1. **Check multiple regions** - availability differs between US, EU, and APAC datacenters
2. **Use community cloud** - cheaper and more available than secure cloud. Fine for async batch jobs where you don't need guaranteed uptime
3. **Try off-peak hours** - GPU availability is better during US nighttime / weekday mornings
4. **Use on-demand, not spot** - spot instances are cheaper but get preempted. For short generation jobs, on-demand is more reliable
5. **Consider Vast.ai as an alternative** - similar GPU rental marketplace, sometimes has better availability or pricing for specific GPU types. Workers connect the same way (Docker image + env vars)
6. **Pre-download models** - start a cheap CPU pod with your network volume attached, run the worker once to download models, then stop it. This way your GPU pod starts fast with cached models

---

## Related docs

- [deployment-matrix.md](deployment-matrix.md) - all deployment scenarios
- [docker-images.md](docker-images.md) - image inventory and build instructions
- [bootstrap.md](bootstrap.md) - first-run setup and secrets
- [env-vars.md](env-vars.md) - full environment variable reference

For GPU availability tips, cost optimization, and community support, visit the [SelfHostHub Community](https://www.skool.com/selfhostinnovators).
