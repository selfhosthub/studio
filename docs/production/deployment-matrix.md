# Deployment Matrix

How to choose the right deployment for your environment.

> **Community & support:** [SelfHostHub Community](https://www.skool.com/selfhosthub) · [Innovators (Plus)](https://www.skool.com/selfhostinnovators)

## Picking a shape

**Default:** [Standard](#standard) - separate containers for `nginx`, `api`, `ui`, `postgres`, plus any workers you enable. This is what the README, the docker-compose file, and every other doc assume unless they say otherwise. Use it unless you have a reason not to.

**Alternatives:**

- Want fewer containers? → [Core](#core). API + UI + general/transfer workers fuse into one container under supervisord; Postgres still runs separately.
- Stuck with one container only (RunPod pod, Vast.ai, single-container hosting)? → [Full](#full). Everything plus Postgres lives in a single container with data on `/workspace/db`.
- Scaling beyond one host, or using a managed DB? → [Split](#split). Same container shape as Standard, but services land on different hosts and Postgres can be Cloud SQL / RDS / Azure.
- Workers on a different machine from the API (cloud GPU, dedicated GPU box)? → [Distributed workers](#distributed-workers). Workers poll the API over HTTP; no shared filesystem.
- GPU workers on the same machine? → start the GPU-needing profiles with the [GPU override](#gpu-workers).
- Managed Kubernetes? → [not available yet](#kubernetes).

## Scenarios

### Standard

The default. A solo creator on a VPS or home server, or anyone bringing up Studio without a constraint that forces another shape.

| | |
|---|---|
| **Target user** | Solo operator, single machine |
| **Entry point** | `studio-console` |
| **Compose file** | `docker-compose.yml` |
| **Containers** | 3–8 (postgres + api + ui + optional workers) |
| **Postgres** | Separate `postgres` container - data on `${SHS_WORKSPACE_HOST}/postgres` bind mount |
| **Min hardware** | 2 CPU / 4 GB RAM |
| **GPU** | Optional - enable per-worker with `workers/docker-compose.gpu.yml` |
| **Storage** | `~/.studio` bind mount + `postgres_data` Docker volume |
| **Networking** | Single host, Docker bridge network |

```bash
docker compose up -d                                          # start core stack (postgres + api + ui + nginx)
COMPOSE_PROFILES=worker-general docker compose up -d          # add one worker
COMPOSE_PROFILES=worker-general,worker-transfer,worker-video docker compose up -d   # add several
```

Each worker is its own compose profile (`worker-general`, `worker-transfer`, `worker-video`, `worker-audio`, `worker-comfyui-image`). There is no aggregate `workers` profile - list the ones you want explicitly.

### Core

Same as Standard but fewer containers. The `ghcr.io/selfhosthub/studio-core` image fuses API + UI + general/transfer workers into one container under supervisord; Postgres still runs separately.

| | |
|---|---|
| **Target user** | Solo operator who wants minimal container management |
| **Entry point** | `docker-compose.yml` with `studio-core` image |
| **Containers** | 2 (postgres + studio-core) |
| **Postgres** | Separate `postgres` container - `studio-core` connects to it over the docker network |
| **Min hardware** | 2 CPU / 4 GB RAM |
| **GPU** | No - image includes general + transfer workers only (CPU work) |
| **Storage** | Same as Standard |
| **Trade-off** | Simpler ops, but no video/audio/comfyui workers |

### Full

Everything in a single container - PostgreSQL, API, UI, and general/transfer workers. For platforms that only allow one container (RunPod pods, Vast.ai, single-container hosting).

| | |
|---|---|
| **Target user** | GPU cloud renters (RunPod, Vast.ai) |
| **Entry point** | `docker run -p 8000:8000 -p 3000:3000 -p 9001:9001 -v ~/.studio:/workspace -e SHS_SUPERVISOR_USER=admin -e SHS_SUPERVISOR_PASSWORD=... ghcr.io/selfhosthub/studio-full` |
| **Dockerfile** | `Dockerfile.full` |
| **Containers** | 1 |
| **Postgres** | Embedded - runs inside the same container under supervisord, data at `/workspace/db` |
| **Min hardware** | 2 CPU / 4 GB RAM |
| **GPU** | No (general + transfer workers only) |
| **Storage** | `/workspace` - RunPod network volume or local bind mount. Required for Postgres durability |
| **Networking** | Three ports exposed by the image: `8000` (API), `3000` (UI), `9001` (supervisord dashboard, basic-auth required) |
| **Required env** | `SHS_SUPERVISOR_USER` + `SHS_SUPERVISOR_PASSWORD` - supervisord dashboard on `:9001` is exposed by the image; both vars must be set or the container exits on boot |
| **Trade-off** | Zero orchestration, but Postgres is embedded - back up `/workspace/db` to preserve data, and lose the volume = lose the database |

### Split

Same container shape as Standard, but services run on different hosts (or against a managed Postgres). For teams or operators who want to scale services independently.

| | |
|---|---|
| **Target user** | Teams, higher-traffic deployments |
| **Entry point** | `docker-compose.yml` with individual images |
| **Containers** | 4–8 (postgres, api, ui, workers) |
| **Postgres** | Separate container, or external managed DB (Cloud SQL / RDS / Azure Database) - point `SHS_DATABASE_URL` at it |
| **Min hardware** | 4+ CPU / 8+ GB RAM |
| **GPU** | Optional per-worker |
| **Storage** | Same as Standard, or managed DB (Cloud SQL / RDS) for Postgres |
| **Networking** | Docker bridge or overlay network |
| **Trade-off** | More containers to manage, but each service can be scaled or restarted independently |

### Distributed workers

Workers on a separate machine from the API (or the same machine, running independently). Workers poll the API over HTTP - no shared Docker network or filesystem required.

| | |
|---|---|
| **Target user** | Operators with a dedicated GPU box, cloud GPU instances, or anyone wanting workers decoupled from the core stack |
| **Entry point** | `docker compose -f workers/docker-compose.yml ...` (or studio-console on the worker host, if that's how you provision split-services elsewhere) |
| **Compose file** | `workers/docker-compose.yml` |
| **Containers** | Workers only (1–5) |
| **Min hardware** | GPU host: depends on worker type. API host: same as Standard |
| **GPU** | Add the GPU override: `-f workers/docker-compose.yml -f workers/docker-compose.gpu.yml` |
| **Storage** | `/workspace` on each host (models cached locally) |
| **Networking** | Workers connect to API via `SHS_API_BASE_URL` - public URL, localhost, or Tailscale. Authenticate with `SHS_WORKER_SHARED_SECRET` (must match the API). |

```bash
docker compose -f workers/docker-compose.yml up -d worker-audio       # one worker type
docker compose -f workers/docker-compose.yml \
               -f workers/docker-compose.gpu.yml up -d worker-audio   # with GPU
```

The worker host needs its own `.env` with at least `SHS_API_BASE_URL`, `SHS_WORKER_SHARED_SECRET`, and `SHS_WORKSPACE_HOST`. Copy `SHS_WORKER_SHARED_SECRET` byte-for-byte from the API host.

Workers can also run on the same machine as the core stack without conflict - they use a separate Docker Compose project and connect to the API over HTTP, not a shared network. Multiple workers of the same type share load via atomic job claiming.

### GPU workers

Not a separate scenario - a modifier on Standard or Split. Adds GPU device reservations for workers that need them (audio, comfyui).

```bash
# Both Core and Full (from repo root)
docker compose -f docker-compose.yml -f workers/docker-compose.gpu.yml up -d worker-audio

# Worker-only host
docker compose -f workers/docker-compose.yml \
               -f workers/docker-compose.gpu.yml up -d worker-audio
```

### Kubernetes

Managed Kubernetes (GKE, EKS, AKS). **Not yet implemented.**

| | |
|---|---|
| **Target user** | Cloud-native teams, managed infrastructure |
| **What's needed** | Helm chart or manifests for: Deployments (api, ui, workers), Services + Ingress, ConfigMaps/Secrets, PVCs for workspace, GPU node pool for workers |
| **Database** | Managed PostgreSQL (Cloud SQL, RDS, Azure Database) - not a container |
| **Images** | Published to GHCR (`ghcr.io/selfhosthub/`) |
| **Status** | Planned - images are container-runtime agnostic and ready for k8s |

### RunPod Serverless

Stateless GPU workers that spin up on demand. **Planned, not implemented.**

| | |
|---|---|
| **Target user** | Operators who want GPU burst capacity without persistent pods |
| **Architecture** | Workers push files to API over HTTPS, Cloudflare Tunnel for networking |
| **Status** | Planned |

## Resource summary

| Scenario | Containers | Min CPU | Min RAM | GPU | Postgres |
|----------|-----------|---------|---------|-----|----------|
| Standard | 3–8 | 2 | 4 GB | Optional | Container |
| Core | 2 | 2 | 4 GB | No | Container |
| Full | 1 | 2 | 4 GB | No | Embedded |
| Split | 4–8 | 4+ | 8+ GB | Optional | Container or managed |
| Distributed workers | 1–5 (workers only) | Varies | Varies | Yes | N/A (on API host) |
| Kubernetes | Pods per service | Varies | Varies | GPU node pool | Managed (Cloud SQL / RDS) |

## Key concepts

- **Workspace** - persistent storage at `~/.studio` (host) or `/workspace` (container). Holds generated files, model caches, and runtime config.
- **Secrets** - three required: `SHS_JWT_SECRET_KEY`, `SHS_WORKER_SHARED_SECRET`, `SHS_CREDENTIAL_ENCRYPTION_KEY`. Generate each with `openssl rand -hex 32` and store in `.env`. studio-console auto-generates them when used.
- **Bootstrap** - `api/scripts/bootstrap.py` runs on every container start. On first boot, creates the super-org and super-admin account, then writes a `.bootstrapped` marker.
- **Supervisord** - manages multiple processes inside the Core and Full images (API, UI, worker, and optionally PostgreSQL). Its web dashboard on port `9001` is protected by HTTP basic-auth from `SHS_SUPERVISOR_USER` / `SHS_SUPERVISOR_PASSWORD` - both required, no fallback.
- **Worker model policy** - worker images never bundle AI models or third-party applications. Models are downloaded at first run and cached on the operator's storage.

## Files reference

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Production compose - Standard, Core, and Split shapes all use this file (different image choices and host layout) |
| `workers/docker-compose.yml` | Worker-only hosts (pre-built GHCR images) |
| `workers/docker-compose.gpu.yml` | GPU device reservation override for workers |
| `deploy/.env.example` | Production env template |
| `Dockerfile` | Core image (API + UI + general/transfer workers) |
| `Dockerfile.full` | Full image (everything + PostgreSQL) |
| `api/Dockerfile` | API-only image |
| `ui/Dockerfile` | UI-only image |
| `workers/engines/*/Dockerfile` | Per-worker images |
