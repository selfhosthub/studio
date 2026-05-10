# Environment Variable Reference

> **Community & support:** [SelfHostHub Community](https://www.skool.com/selfhosthub) · [Innovators (Plus)](https://www.skool.com/selfhostinnovators)

All Studio environment variables use the `SHS_` prefix unless noted. Variables with no default are required - `docker-compose.yml` uses `${VAR:?error}` syntax and will fail to start if they are missing.

For how variables flow between env files and running processes, see [env-inheritance.md](../docs/development/env-inheritance.md) (architectural context; see here for the current variable list).

---

## Required Variables

Variables that have no defaults and must be present before startup.

| Variable | Used by | Description |
|----------|---------|-------------|
| `SHS_STUDIO_VERSION` | Compose | Docker image tag for all Studio containers. |
| `SHS_JWT_SECRET_KEY` | API | JWT signing secret. 32+ random chars. |
| `SHS_WORKER_SHARED_SECRET` | API, workers | Shared secret for worker authentication. 32+ random chars. |
| `SHS_CREDENTIAL_ENCRYPTION_KEY` | API | AES key for stored provider credentials. 32+ random chars. |
| `SHS_DATABASE_URL` | API | PostgreSQL connection URL. Format: `postgresql+asyncpg://user:pass@host:port/db`. |
| `POSTGRES_PASSWORD` | Postgres | Database superuser password. |
| `SHS_API_BASE_URL` | UI, non-Docker workers | API base URL (`http://host:port`). Docker workers use `http://api:8000` hardcoded in compose. Required for UI and for workers running outside Docker. |
| `SHS_PUBLIC_BASE_URL` | All workers | Publicly reachable URL for external API callbacks and file downloads. Must be accessible from the internet. |
| `SHS_WS_URL` | UI | WebSocket URL (`ws://host:port`). Injected into UI as `NEXT_PUBLIC_WS_URL`. |
| `SHS_CORS_ORIGINS` | API | Comma-separated allowed CORS origins. Must include the UI origin. |
| `SHS_WORKSPACE_HOST` | Compose | Host-side path mounted as `/workspace` in all containers (e.g. `~/.studio`). |
| `SHS_COMMUNITY_SOURCE` | API | Community catalog: local dir name (dev) or GitHub raw URL (prod). |
| `SHS_PLUS_SOURCE` | API | Plus catalog: local dir name or URL. |

---

## Deployment Variables

### Core Application

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_ENV` | `development` | Runtime environment: `development`, `production`, `test`. |
| `SHS_DEBUG` | `false` | Enables debug mode. Never `true` in production. |
| `SHS_STUDIO_VERSION` | - | Docker image tag for all Studio containers. Required. |
| `COMPOSE_PROJECT_NAME` | `studio` | Docker Compose project name. |
| `SHS_COMPONENTS` | - | Comma-separated enabled components, written by tooling that provisions the deploy. |
| `COMPOSE_PROFILES` | - | Comma-separated Docker Compose profile names. Controls which worker services start (e.g. `worker-general,worker-transfer`). One profile per worker - there is no aggregate `workers` profile. |

### Secrets

| Variable | Written to `.env` | Description |
|----------|-------------------|-------------|
| `SHS_JWT_SECRET_KEY` | Yes | JWT signing secret. 32+ chars. Required. |
| `SHS_WORKER_SHARED_SECRET` | Yes | Worker auth secret. 32+ chars. Required. |
| `SHS_CREDENTIAL_ENCRYPTION_KEY` | Yes | AES encryption key for stored provider credentials. Required. |
| `SHS_ADMIN_PASSWORD` | **No (shell only)** | Initial admin password. Used during first-boot bootstrap only; never persisted to `.env` for security. |
| `SHS_ENTITLEMENT_TOKEN` | Yes | Plus catalog access token. Leave blank to use community catalog only. |
| `SHS_SUPERVISOR_USER` | Yes | Core and Full images only. HTTP basic-auth username for the supervisord dashboard on port 9001. Supervisord refuses to start without it. |
| `SHS_SUPERVISOR_PASSWORD` | Yes | Core and Full images only. HTTP basic-auth password. Generate with `openssl rand -base64 24`. Supervisord refuses to start without it. |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_DATABASE_URL` | - | Full PostgreSQL URL (`postgresql+asyncpg://user:pass@host:port/db`). Required. |
| `POSTGRES_USER` | `postgres` | PostgreSQL superuser name. |
| `POSTGRES_PASSWORD` | - | PostgreSQL superuser password. Required. |
| `POSTGRES_PORT` | `5432` | Host port for postgres container. |

> `POSTGRES_DB` is hardcoded as `selfhost_studio` in `docker-compose.yml` and is not configurable.

### URLs & Networking

The URL vars are the single biggest source of botched deploys. There are five of them and they're easy to confuse - the same name (`SHS_API_BASE_URL`) means different things on the API host versus a worker host. See the [URL vars worked example](#url-vars-worked-example) below for a deploy you can copy.

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_API_BASE_URL` | - | On the API/UI host: the public URL where browsers and external callbacks reach Studio. On a worker host: the URL the worker uses to dial the API (Docker: `http://api:8000`, hardcoded in compose; non-Docker / cross-host: a real URL). Same name, different concept. |
| `SHS_PUBLIC_BASE_URL` | - | Publicly reachable URL for external API callbacks and file downloads. Required on all worker hosts. Set to the same value as the API's `SHS_API_BASE_URL`. |
| `SHS_FRONTEND_URL` | `""` | UI URL used in OAuth redirect-back flows. API-side only. |
| `SHS_WS_URL` | - | WebSocket URL injected into the UI container as `NEXT_PUBLIC_WS_URL`. Required. |
| `SHS_CORS_ORIGINS` | - | Comma-separated allowed origins. Must include the UI origin and any external embedders. Required. |
| `SHS_NGINX_PORT` | `80` | Host port the bundled nginx binds to. The `api` and `ui` services are not exposed to the host directly - nginx is the single entry point. |

#### URL vars worked example

Stack on a single VPS, domain `studio.example.com`, external Caddy terminating TLS on 443 and forwarding to nginx on host port 80, one general worker and one transfer worker on the same VPS:

```bash
# API host .env
SHS_NGINX_PORT=80
SHS_API_BASE_URL=https://studio.example.com           # public URL of this stack
SHS_PUBLIC_BASE_URL=https://studio.example.com        # workers and externals reach files here
SHS_FRONTEND_URL=https://studio.example.com           # OAuth redirect target
SHS_WS_URL=wss://studio.example.com                   # WebSocket origin (note wss://)
SHS_CORS_ORIGINS=https://studio.example.com           # add more origins comma-separated if needed
```

Workers running in the same compose project don't need their own `SHS_API_BASE_URL` - compose sets `http://api:8000` for them. Workers on a separate host get:

```bash
# Worker host .env
SHS_API_BASE_URL=https://studio.example.com           # *this* worker's API endpoint (note: same value as the API's public URL because workers reach API over the public domain)
SHS_PUBLIC_BASE_URL=https://studio.example.com        # used when workers tell the API where externals can fetch files
SHS_WORKER_SHARED_SECRET=...                          # byte-for-byte match with API host
```

Common traps:
- `SHS_API_BASE_URL` set on the API but pointing at `http://localhost:8000` - fine for the API container itself, but the value gets injected into the UI's `NEXT_PUBLIC_API_URL`, so browsers also try `localhost`. Use the public URL.
- `SHS_PUBLIC_BASE_URL` set in the API's env file - silent no-op (the API doesn't read it). Set it on workers.
- `SHS_WS_URL` left as `ws://` behind a TLS terminator - browsers refuse mixed content. Use `wss://` whenever the page is `https://`.
- `SHS_CORS_ORIGINS` missing the UI origin - every API request from the browser fails CORS preflight with a generic error. Include every origin that hosts the UI.

### Scaling / Replicas

Replica counts. Read from `.env` and used to render `docker-compose.override.yml`. studio-console manages the override file when used; otherwise edit `.env` and regenerate the override yourself.

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_API_REPLICAS` | `1` | API container replica count. |
| `SHS_UI_REPLICAS` | `1` | UI container replica count. |
| `SHS_GENERAL_WORKERS` | - | General worker instance count. |
| `SHS_TRANSFER_WORKERS` | - | Transfer worker instance count. |
| `SHS_AUDIO_WORKERS` | - | Audio worker instance count. |
| `SHS_VIDEO_WORKERS` | - | Video worker instance count. |
| `SHS_COMFYUI_IMAGE_WORKERS` | - | ComfyUI image worker count. |
| `SHS_COMFYUI_VIDEO_WORKERS` | - | ComfyUI video worker count. |

### Worker Infrastructure

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_WORKSPACE_ROOT` | `/workspace` | Container-side workspace path. Hardcoded to `/workspace` in Docker compose. Set to an absolute host path for native (non-Docker) workers. |
| `SHS_WORKSPACE_HOST` | `~/.studio` | Host-side directory mounted as `/workspace` in Docker. Required. |
| `SHS_STORAGE_BACKEND` | `local` | Storage backend. Currently only `local`. |
| `SHS_COMFYUI_URL` | `""` | ComfyUI server URL. Required when running ComfyUI workers. |
| `SHS_WHISPER_MODEL` | `base` | Whisper model for subtitle transcription: `tiny`, `base`, `small`, `medium`, `large`, `turbo`. |
| `HF_HOME` | - | HuggingFace model cache directory. Docker audio workers set this to `$WORKSPACE_HOST/models/huggingface`. |

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Studio-console sets `WARNING` in production. Used by API and all workers. |
| `SHS_LOG_FORMAT` | `rich` | `rich` (human-readable), `json` (structured/log collectors), `pretty` (tests). |
| `SHS_ENABLE_ACCESS_LOGS` | `false` | Enable per-request HTTP access logs. |
| `SHS_SUPPRESS_WORKER_POLLING_LOGS` | `true` | Suppresses verbose worker job-poll logs. |
| `SHS_SUPPRESS_ACCESS_LOG_SUCCESS` | `true` | Suppresses 2xx access logs (only 4xx/5xx are logged). |
| `SHS_SUPPRESS_WEBSOCKET_LOGS` | `true` | Suppresses WebSocket connection/heartbeat logs. |
| `SHS_UVICORN_LOG_LEVEL` | `INFO` | Uvicorn access-log level. |
| `SHS_UVICORN_ERROR_LOG_LEVEL` | `ERROR` | Uvicorn error-log level. |
| `SHS_API_SERVICE_NAME` | `api` | Service name attached to structured logs - useful when shipping logs from multiple Studio stacks to one log collector. |
| `PORT` | - | Shell-only. API HTTP port when running outside Docker (internal default 8000). Not written to `.env`. |
| `SHS_PORT` | `8000` | API HTTP port read by the API process. Override only if you're running outside the standard compose stack. |

### Catalog & Marketplace

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_COMMUNITY_SOURCE` | - | Community catalog: local dir name (e.g. `studio-community`) or full GitHub raw URL. Required. |
| `SHS_PLUS_SOURCE` | - | Plus catalog: dir name or URL. Required. |
| `SHS_CATALOG_CACHE_HOURS` | `24` | Hours to cache fetched catalog. Studio-console sets `168` (1 week) in production. |
| `SHS_ENTITLEMENT_TOKEN` | `""` | Plus catalog access token. Optional. |
| `SHS_DOCS_PATH` | `/app/docs` | In-container path where bundled docs are served from. |

#### Catalog subdirectories

These rarely need overriding - they map content types to subdirectories within whichever catalog source you've configured. Defaults match the layout of `studio-community` and `studio-plus`.

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_BLUEPRINTS_DIRECTORY` | `blueprints` | |
| `SHS_COMFYUI_DIRECTORY` | `comfyui` | |
| `SHS_PROMPTS_DIRECTORY` | `prompts` | |
| `SHS_PROVIDERS_DIRECTORY` | `providers` | |
| `SHS_WORKFLOWS_DIRECTORY` | `workflows` | |

### Admin Bootstrap

| Variable | Written to `.env` | Description |
|----------|-------------------|-------------|
| `SHS_ADMIN_EMAIL` | Yes (conditional) | Admin email. Written only during first-boot bootstrap. Default: `admin@example.com`. |
| `SHS_ADMIN_PASSWORD` | **No** | Admin password for bootstrap. Consumed and discarded; never persisted. |
| `SHS_SEED_DB` | **No** | Path to seed SQL file. Development / bootstrap only. |
| `SHS_SEED_ORGS` | **No** | Path to org seed directory. Development / bootstrap only. |
| `SHS_FORCE_PRODUCTION` | **No** | Forces production guards in reset-password flow. Shell only. |

### Cloudflare (optional)

Required only when using Cloudflare Tunnel (`COMPOSE_PROFILES=cloudflared`).

| Variable | Description |
|----------|-------------|
| `CLOUDFLARE_TUNNEL_TOKEN` | Cloudflare Tunnel auth token. Used by the `cloudflared` compose service. |
| `CLOUDFLARE_TUNNEL_ID` | Tunnel UUID. |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID. |
| `CLOUDFLARE_ZONE_ID` | DNS zone ID. |
| `CLOUDFLARE_ACCESS_APP_ID` | Zero Trust application ID. |
| `CLOUDFLARE_API_TOKEN` | API token for DNS automation. |

### Source Build (optional)

| Variable | Description |
|----------|-------------|
| `SHS_REPO_ROOT` | Path to a local `studio-app` checkout. Only needed when building images from source rather than pulling from GHCR. |

### Context Detection (shell-only, never written to `.env`)

| Variable | Description |
|----------|-------------|
| `RUNPOD_POD_ID` | Detected at boot to set deployment context to `runpod`. |

---

## API Tuning

All have sensible defaults - only override when needed. Loaded from `api/app/config/settings.py` via `pydantic-settings`.

### HTTP Client Timeouts

| Variable | Default | Unit | Description |
|----------|---------|------|-------------|
| `SHS_MARKETPLACE_CATALOG_TIMEOUT` | 10.0 | seconds | Catalog fetch timeout |
| `SHS_MARKETPLACE_DOWNLOAD_TIMEOUT` | 30.0 | seconds | Download / GitHub API timeout |
| `SHS_PACKAGE_DOWNLOAD_TIMEOUT` | 60.0 | seconds | Package zip download timeout |
| `SHS_WEBHOOK_TIMEOUT` | 30.0 | seconds | Outbound webhook timeout |

### Worker Heartbeat & Cleanup

| Variable | Default | Unit | Description |
|----------|---------|------|-------------|
| `SHS_WORKER_HEARTBEAT_TIMEOUT_MINUTES` | 3 | minutes | Mark worker dead after missing heartbeats. Must be > 2× worker heartbeat interval (default 60s). |
| `SHS_WORKER_CLEANUP_RETENTION_MINUTES` | 30 | minutes | Retain dead worker records before removal. |
| `SHS_STALE_STEP_TIMEOUT_MINUTES` | 15 | minutes | Fail steps stuck in QUEUED/RUNNING with no activity. Set higher for long video renders or model training. |
| `SHS_PERIODIC_CLEANUP_INTERVAL_SECONDS` | 60 | seconds | How often the in-process scheduler fires cleanup (worker deregister, stale step sweep, dead-letter replay). |
| `SHS_WARN_NO_WORKERS` | `true` | - | Emit a warning when no workers are registered. |

### Provider Adapter Timeouts

| Variable | Default | Unit | Description |
|----------|---------|------|-------------|
| `SHS_ADAPTER_CLIENT_TIMEOUT` | 60.0 | seconds | General adapter HTTP client timeout |
| `SHS_ADAPTER_POLL_REQUEST_TIMEOUT` | 30.0 | seconds | Individual poll request timeout |
| `SHS_ADAPTER_CREDENTIAL_VALIDATION_TIMEOUT` | 10.0 | seconds | Credential validation timeout |

### Provider Adapter Polling

| Variable | Default | Unit | Description |
|----------|---------|------|-------------|
| `SHS_ADAPTER_DEFAULT_POLL_INTERVAL` | 10.0 | seconds | Default interval between polls |
| `SHS_ADAPTER_DEFAULT_MAX_ATTEMPTS` | 60 | count | Max polling attempts |
| `SHS_ADAPTER_DEFAULT_TOTAL_TIMEOUT` | 600.0 | seconds | Total polling timeout |
| `SHS_BASE_ADAPTER_MAX_POLL_ATTEMPTS` | 15 | count | Max attempts for sync-style adapters |
| `SHS_BASE_ADAPTER_POLL_INTERVAL` | 2.0 | seconds | Poll interval for sync-style adapters |
| `SHS_BASE_ADAPTER_INITIAL_DELAY` | 2.0 | seconds | Initial delay before first poll |

### API Pagination

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_API_PAGE_LIMIT_DEFAULT` | 100 | Default page size for list endpoints |
| `SHS_API_PAGE_LIMIT_MEDIUM` | 50 | Default for audit logs, billing history |
| `SHS_API_PAGE_LIMIT_SMALL` | 25 | Default for instance lists, org users |
| `SHS_API_PAGE_LIMIT_RESOURCE` | 20 | Default for file/resource lists |
| `SHS_API_PAGE_MAX` | 100 | Maximum allowed page size |

### Billing & Organization

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_DEFAULT_TRIAL_DAYS` | 14 | Trial period for new users |
| `SHS_PENDING_ORG_MAX_USERS` | 1 | Max users in pending-approval orgs |
| `SHS_PENDING_ORG_MAX_EXECUTIONS` | 0 | Max workflow runs in pending-approval orgs |
| `SHS_PENDING_ORG_MAX_STORAGE_MB` | 50 | Max storage (MB) for pending-approval orgs |

### Grace Periods

| Variable | Default | Unit | Description |
|----------|---------|------|-------------|
| `SHS_GRACE_HOURS_STORAGE` | 168 | hours | Grace before blocking exceeded storage (7 days) |
| `SHS_GRACE_HOURS_WORKFLOWS` | 72 | hours | Grace for exceeded workflow count (3 days) |
| `SHS_GRACE_HOURS_BLUEPRINTS` | 72 | hours | Grace for exceeded blueprint count (3 days) |

### Limit Buffers

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_LIMIT_BUFFER_WORKFLOWS` | 10 | Extra workflows allowed above plan limit |
| `SHS_LIMIT_BUFFER_STORAGE_MB` | 1024 | Extra storage (MB) above plan limit |
| `SHS_LIMIT_BUFFER_USERS` | 3 | Extra users above plan limit |
| `SHS_LIMIT_BUFFER_BLUEPRINTS` | 5 | Extra blueprints above plan limit |
| `SHS_LIMIT_WARNING_THRESHOLD` | 0.80 | Fraction of limit that triggers a warning notification |
| `SHS_LIMIT_CRITICAL_THRESHOLD` | 0.95 | Fraction of limit that triggers a critical alert |

### Auth Token Expiry

| Variable | Default | Unit | Description |
|----------|---------|------|-------------|
| `SHS_ACCESS_TOKEN_EXPIRE_MINUTES` | 30 | minutes | User access token lifetime |
| `SHS_REFRESH_TOKEN_EXPIRE_DAYS` | 7 | days | User refresh token lifetime |
| `SHS_WEBHOOK_TOKEN_EXPIRE_HOURS` | 24 | hours | Webhook token lifetime |
| `SHS_WORKER_TOKEN_EXPIRE_MINUTES` | 5 | minutes | Worker JWT lifetime |

### Database Pool

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_DB_POOL_SIZE` | 20 | SQLAlchemy connection pool size |
| `SHS_DB_MAX_OVERFLOW` | 30 | Max connections above pool size |
| `SHS_DB_POOL_TIMEOUT` | 10 | Seconds to wait for a connection from the pool |
| `SHS_DB_POOL_RECYCLE` | 1800 | Seconds before recycling idle connections |

### Jobs & Queue

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_JOB_RETRY_LIMIT` | 3 | Max job-level retries |
| `SHS_RESULT_CONSUMER_RETRY_PAUSE` | 1 | Seconds between result consumer retries |
| `SHS_DEFAULT_FETCH_LIMIT` | 1000 | Default DB fetch limit for queue queries |
| `SHS_QUEUE_DEFAULT_MAX_CONCURRENCY` | 10 | Max concurrent jobs per queue |
| `SHS_QUEUE_DEFAULT_MAX_PENDING` | 1000 | Max pending jobs before queue rejects new work |
| `SHS_QUEUE_DEFAULT_TIMEOUT` | 3600 | Queue job timeout (seconds) |
| `SHS_DEFAULT_MAX_RETRIES` | 3 | Default step retry count |
| `SHS_DEFAULT_RETRY_DELAY_SECONDS` | 60 | Default step retry delay (seconds) |
| `SHS_STEP_DEFAULT_RETRY_COUNT` | 0 | Per-step retry count override |
| `SHS_STEP_DEFAULT_RETRY_DELAY` | 60 | Per-step retry delay override (seconds) |

### WebSocket (API-side)

| Variable | Default | Unit | Description |
|----------|---------|------|-------------|
| `SHS_WS_IDLE_TIMEOUT_SECONDS` | 300 | seconds | Disconnect idle WebSocket connections |
| `SHS_WS_MAX_CONNECTIONS_PER_IP` | 10 | count | Max concurrent WS connections per IP |
| `SHS_WS_MAX_TOTAL_CONNECTIONS` | 1000 | count | Total WS connection cap |
| `SHS_WS_MESSAGE_RATE_LIMIT` | 30 | count | Max messages per client per rate window |
| `SHS_WS_RATE_LIMIT_WINDOW_SECONDS` | 60 | seconds | Rate limit window duration |
| `SHS_WS_SEND_TIMEOUT_SECONDS` | 2.0 | seconds | Per-connection broadcast send timeout. Bounds half-open sockets (laptop sleep, dropped TCP without FIN) that would otherwise park indefinitely. |

### System Health

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_LOG_TAIL_DEFAULT` | 100 | Default log lines returned by `/system/logs` |
| `SHS_LOG_TAIL_MAX` | 1000 | Maximum log lines returned by `/system/logs` |
| `SHS_SYSTEM_HEALTH_DEFAULT_PAGE` | 10 | Default page size for system health endpoints |
| `SHS_SYSTEM_HEALTH_MAX_PAGE` | 100 | Max page size for system health endpoints |

### Thumbnails

| Variable | Default | Unit | Description |
|----------|---------|------|-------------|
| `SHS_THUMBNAIL_MAX_SIZE` | 256 | pixels | Thumbnail max dimension |
| `SHS_THUMBNAIL_QUALITY` | 85 | 1-100 | JPEG quality for thumbnails |

### OAuth

| Variable | Default | Unit | Description |
|----------|---------|------|-------------|
| `SHS_OAUTH_STATE_EXPIRY` | 600 | seconds | OAuth flow state validity |

### Limits & Webhooks

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_LICENSE_CACHE_TTL` | 86400 | LemonSqueezy license validation cache (seconds, 24h) |
| `SHS_AVATAR_MAX_FILE_SIZE` | 5242880 | Max avatar upload size (bytes, 5 MiB) |
| `SHS_WEBHOOK_SECRET_LENGTH` | 32 | Generated webhook secret length (chars) |
| `SHS_WEBHOOK_TOKEN_LENGTH` | 24 | Generated webhook token length (chars) |

### Maintenance

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_MAINTENANCE_MODE` | `false` | When `true`, returns 503 for all non-health requests. |

---

## Worker Variables

Workers use `pydantic-settings` split across `SharedSettings` (every worker) plus per-engine classes. `extra="ignore"` means each class silently drops `SHS_*` vars it doesn't own - a compose container that injects all worker vars won't crash.

Precedence: **process env > `workers/envs/.env.dev` > `workers/envs/.env.local` > field defaults**.

### Shared - Required (fail-fast if missing)

| Variable | Description |
|----------|-------------|
| `SHS_API_BASE_URL` | URL workers use to reach the API. Docker: `http://api:8000` (hardcoded in compose). Native host: `http://localhost:8100`. |
| `SHS_PUBLIC_BASE_URL` | Publicly reachable URL used by external APIs to download files from the workspace. Must be a tunnel URL or public address in dev. |
| `SHS_WORKER_SHARED_SECRET` | Shared secret for `POST /workers/register`. |
| `SHS_WORKSPACE_ROOT` | Workspace root. Docker: `/workspace`. Native host: absolute path. |

### Shared - Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_WORKER_TYPE` | `general` | Engine handler: `general`, `video`, `audio`, `comfyui-image`, `comfyui-image-edit`, `comfyui-video`, `comfyui-remote`, `transfer`. |
| `SHS_WORKER_NAME` | auto | Registered name. Auto-set as `worker-<type>-<8-hex>` when unset. |
| `SHS_LOG_LEVEL` | `INFO` | Log level. |
| `SHS_LOG_FORMAT` | `rich` | `rich`, `json`, or `pretty` (tests). |
| `SHS_LOG_COLORS` | `true` | Disable for CI or log collectors. |
| `SHS_LOG_PREFIX` | `""` | Prefix prepended to every log line. Useful to distinguish parallel workers. |
| `SHS_FILE_DOWNLOAD_MAX_MB` | 100 | Per-file download cap (MB). |
| `SHS_HTTP_CHUNK_SIZE` | 65536 | Streaming download chunk size (bytes). |
| `SHS_MAX_DOWNLOAD_SIZE_MB` | 500 | Total download cap per job (MB). |
| `SHS_HEARTBEAT_INTERVAL_S` | 60 | Seconds between `/workers/{id}/heartbeat` calls. |
| `SHS_HTTP_MAX_RETRIES` | 3 | API call retry count. |
| `SHS_HTTP_RETRY_BACKOFF_FACTOR` | 2.0 | Exponential backoff multiplier. |
| `SHS_HTTP_RETRY_BASE_DELAY` | 1.0 | First retry delay (seconds). |
| `SHS_HTTP_RETRY_MAX_DELAY` | 30.0 | Retry backoff cap (seconds). |
| `SHS_PUBLISH_MAX_RETRIES` | 3 | Retry count for `publish_step_result`. |
| `SHS_PUBLISH_RETRY_BASE_DELAY` | 1.0 | |
| `SHS_PUBLISH_RETRY_MAX_DELAY` | 10.0 | |
| `SHS_TRANSFER_RETRY_BASE_DELAY` | 2.0 | Transfer worker retry base delay. |
| `SHS_TRANSFER_RETRY_MAX_DELAY` | 60.0 | Transfer worker retry cap. |
| `SHS_THUMBNAIL_HEIGHT` | 300 | Thumbnail max height (pixels). |
| `SHS_THUMBNAIL_WIDTH` | 300 | Thumbnail max width (pixels). |
| `SHS_THUMBNAIL_JPEG_QUALITY` | 85 | JPEG quality 1–100. |
| `SHS_JOB_POLL_INTERVAL_S` | 5 | Seconds between `/internal/jobs/claim` calls when idle. |
| `SHS_JOB_POLL_BACKOFF_MAX_S` | 60 | Max poll interval after consecutive empty claims. |
| `SHS_JOB_CLAIM_TIMEOUT_S` | 1 | Job claim HTTP timeout (seconds). |
| `SHS_API_STARTUP_MAX_RETRIES` | 0 | `0` = retry forever before first registration. |
| `SHS_API_STARTUP_RETRY_INTERVAL_S` | 5 | Seconds between startup retries. |
| `SHS_FFPROBE_TIMEOUT_S` | 30 | ffprobe timeout. Also used by general worker for thumbnail generation. |
| `SHS_HEALTH_CHECK_TIMEOUT_S` | 5 | |
| `SHS_HTTP_DOWNLOAD_TIMEOUT_S` | 60 | |
| `SHS_HTTP_HANDLER_TIMEOUT_S` | 60 | |
| `SHS_HTTP_INTERNAL_TIMEOUT_S` | 30 | Worker → API internal endpoint timeout (seconds). |
| `SHS_HTTP_VIDEO_DOWNLOAD_TIMEOUT_S` | 120 | Large-media download timeout (seconds). |
| `SHS_HTTP_WEBHOOK_TIMEOUT_S` | 30 | Outbound webhook timeout (seconds). |
| `SHS_SUBPROCESS_TIMEOUT_S` | 10 | Generic subprocess timeout - encoder detection, etc. |
| `SHS_TRANSFER_CHUNK_SIZE` | 8388608 | Transfer worker chunk size (8 MiB). |
| `SHS_TRANSFER_TIMEOUT_S` | 3600 | Max transfer runtime (seconds). |
| `SHS_REGISTRATION_RETRY_INTERVAL` | 30 | Seconds between re-registration attempts after session loss. |
| `SHS_TOKEN_CACHE_MAX_SIZE` | 100 | |
| `SHS_TOKEN_CACHE_TTL` | 300 | Token cache TTL (seconds). |
| `SHS_WORKER_BUSY_TIMEOUT` | 3600 | Soft-warn when a single job runs longer than this (seconds). |

### Video Worker

Loaded only by `workers/engines/video/settings.py`.

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_FFMPEG_ENCODER` | `libx264` | H.264 encoder. Options: `libx264` (CPU, works everywhere), `h264_nvenc` (NVIDIA), `h264_videotoolbox` (Apple Silicon - not available inside Docker), `h264_vaapi` (Intel/AMD on Linux), `h264_qsv` (Intel Quick Sync). The worker verifies at startup; on failure it logs `WARNING` and keeps running - the configured value is never auto-substituted. |
| `SHS_FFMPEG_LOGGING_LEVEL` | `warning` | ffmpeg `-v` level. |
| `SHS_FFMPEG_TIMEOUT_SECONDS` | 1800 | Max runtime per ffmpeg command (seconds). |
| `SHS_WHISPER_MODEL` | `base` | Whisper model for subtitle transcription: `tiny`, `base`, `small`, `medium`, `large`, `turbo`. |
| `SHS_VIDEO_CACHE_DIR` | `None` | Cache dir for intermediate assets. Defaults to `$WORKSPACE_ROOT/data/video_cache`. |
| `SHS_VIDEO_CACHE_MAX_MB` | 1000 | Cache eviction threshold (MB). |
| `SHS_DEFAULT_SCENE_DURATION_S` | 5 | json2video scene duration when neither the scene nor its audio specifies one (seconds). |
| `SHS_DEFAULT_SMOOTHNESS` | 3 | json2video smoothness default. |

### Audio Worker

Loaded only by `workers/engines/audio/settings.py`.

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_AUDIO_TTS_CFG_WEIGHT` | 0.5 | Chatterbox TTS classifier-free guidance weight. Overridable per-job via `cfg_weight`. |
| `SHS_AUDIO_TTS_EXAGGERATION` | 0.5 | Chatterbox TTS exaggeration factor. Overridable per-job via `exaggeration`. |

### ComfyUI Worker

Loaded by both `engines/comfyui` (embedded) and `engines/comfyui_remote` (external server).

| Variable | Default | Description |
|----------|---------|-------------|
| `SHS_COMFYUI_URL` | `""` | ComfyUI server URL. Required for the remote variant. Dev default: `http://127.0.0.1:8188`. |
| `SHS_COMFYUI_EXTERNAL_URL` | `None` | Optional override for external mode. When set, the worker does not start embedded ComfyUI. |
| `SHS_COMFYUI_PATH` | `/app/ComfyUI` | Install path for embedded ComfyUI. |
| `SHS_COMFYUI_OUTPUT_DIR` | `/workspace/data/comfyui_output` | Where ComfyUI writes generated images before the worker uploads them. |
| `SHS_COMFYUI_CLIENT_TIMEOUT_S` | 300 | httpx client timeout for ComfyUI REST calls (seconds). |
| `SHS_COMFYUI_JOB_TIMEOUT_S` | 600 | Max runtime per ComfyUI workflow (seconds). |
| `SHS_COMFYUI_POLL_INTERVAL_S` | 5 | Seconds between `/history/{prompt_id}` polls. |
| `SHS_COMFYUI_HEALTH_POLL_INTERVAL_S` | 2 | Seconds between startup `/system_stats` probes. |
| `SHS_COMFYUI_STARTUP_TIMEOUT_S` | 120 | Max wait for embedded ComfyUI to come up (seconds). |
| `SHS_COMFYUI_STOP_TIMEOUT_S` | 10 | Graceful shutdown deadline (seconds). |
| `SHS_COMFYUI_RESTART_PAUSE_S` | 2 | Pause between stop and start during restart (seconds). |
| `SHS_COMFYUI_RETRY_INTERVAL_S` | 10 | Retry interval when ComfyUI is unreachable (seconds). |

---

## UI Build-Time Variables

> **Important:** `NEXT_PUBLIC_*` variables are inlined at build time by Next.js. Set them before `npm run build`. They are **not** runtime-configurable. In production Docker, the core ones are injected via the `ui` service's `environment:` block in `docker-compose.yml`.

### Core

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | - | API endpoint URL. Set from `SHS_API_BASE_URL` in Docker. Required. |
| `NEXT_PUBLIC_WS_URL` | - | WebSocket URL. Set from `SHS_WS_URL` in Docker. Required. |
| `NEXT_PUBLIC_API_ENV` | - | Environment: `development`, `production`, `e2e`. |

### Polling Intervals

| Variable | Default | Unit | Description |
|----------|---------|------|-------------|
| `NEXT_PUBLIC_POLL_DEFAULT_MS` | 5000 | ms | Default polling interval |
| `NEXT_PUBLIC_POLL_FAST_MS` | 2000 | ms | Fast polling for active operations |
| `NEXT_PUBLIC_POLL_SLOW_MS` | 30000 | ms | Slow polling for background checks |

### WebSocket

| Variable | Default | Unit | Description |
|----------|---------|------|-------------|
| `NEXT_PUBLIC_WS_RECONNECT_DELAY_MS` | 3000 | ms | Delay between reconnect attempts |
| `NEXT_PUBLIC_WS_MAX_RECONNECT` | 5 | count | Max reconnect attempts |
| `NEXT_PUBLIC_WS_PING_INTERVAL_MS` | 30000 | ms | Keep-alive ping interval |
| `NEXT_PUBLIC_WS_CONNECT_DELAY_MS` | 100 | ms | Startup delay (React Strict Mode double-invoke guard) |

### Pagination

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_PAGE_SIZE_DEFAULT` | 20 | Default items per page |
| `NEXT_PUBLIC_PAGE_SIZE_MAX` | 100 | Maximum items per page |

### API Status Monitoring

| Variable | Default | Unit | Description |
|----------|---------|------|-------------|
| `NEXT_PUBLIC_API_RECOVERY_POLL_MS` | 15000 | ms | Health check interval when API is down |
| `NEXT_PUBLIC_API_CHECK_TIMEOUT_MS` | 5000 | ms | Individual health check timeout |

### Dashboard Colors

Override the UI accent palette at build time. All are optional.

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_DASHBOARD_PRIMARY` | `#3B82F6` | Primary action color |
| `NEXT_PUBLIC_DASHBOARD_PRIMARY_HOVER` | `#2563EB` | Primary hover state |
| `NEXT_PUBLIC_DASHBOARD_SUCCESS` | `#10B981` | Success / positive indicator |
| `NEXT_PUBLIC_DASHBOARD_DANGER` | `#EF4444` | Danger / error indicator |
| `NEXT_PUBLIC_DASHBOARD_WARNING` | `#F59E0B` | Warning indicator |
| `NEXT_PUBLIC_DASHBOARD_ACCENT` | `#10B981` | Secondary accent |

### Other

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_ANALYTICS_ENABLED` | - | Analytics toggle. |
| `NEXT_TELEMETRY_DISABLED` | - | Set to `1` to disable Next.js telemetry. |

---

## Development & Test Only

Never set these in production.

| Variable | Used by | Description |
|----------|---------|-------------|
| `SHS_DISABLE_ENV_FILES` | Worker tests | When `1`/`true`/`yes`, each worker settings class skips reading `.env.dev` and `.env.local`. Set by `workers/tests/conftest.py` before any `shared.settings` import so tests see only what conftest and monkeypatches inject. |
| `SHS_TEST_DATABASE_URL` | API tests | Separate database URL for test runs. |
| `SHS_RUNNING_IN_DOCKER` | API | `true` when running inside a container. Set automatically. |
| `SHS_ALLOW_ENV_LOCAL` | API dev | Allows loading `.env.local` in development mode. |
| `SHS_FORCE_PRODUCTION` | Bootstrap | Forces production guards in reset-password flow. Shell only. |
