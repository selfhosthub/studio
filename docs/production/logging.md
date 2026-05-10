# Logging

> **Community & support:** [SelfHostHub Community](https://www.skool.com/selfhosthub) · [Innovators (Plus)](https://www.skool.com/selfhostinnovators)

Operator reference for log configuration across all three Studio components: API, Workers, and UI.

## Environment variables

Every env var that affects logging output. Variables not present in `.env` files rely on code defaults.

| Variable | Component | Default | Valid values | Description |
|----------|-----------|---------|--------------|-------------|
| `SHS_LOG_LEVEL` | API, Workers | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | Minimum severity threshold for root logger |
| `SHS_LOG_FORMAT` | API, Workers | `rich` | `rich`, `json`, `pretty` | Output format (see [Log formats](#log-formats)) |
| `SHS_LOG_VERBOSITY` | API, Workers | `full` (json) / `standard` (other) | `minimal`, `standard`, `full` | Context fields in output (see [Verbosity levels](#verbosity-levels)) |
| `SHS_ENABLE_ACCESS_LOGS` | API | `false` | `true`, `false` | Enable uvicorn HTTP access logs |
| `SHS_SUPPRESS_WEBSOCKET_LOGS` | API | `true` | `true`, `false` | Suppress WebSocket connection open/close messages |
| `SHS_SUPPRESS_WORKER_POLLING_LOGS` | API | `true` | `true`, `false` | Suppress heartbeat, empty job claims, and "claiming job" INFO logs |
| `SHS_LOG_COLORS` | API, Workers | `true` | `true`, `false` | Enable colors in `pretty`/`rich` format output |
| `SHS_LOG_PREFIX` | Workers | auto-detect | Any string | Override log line prefix; auto-detects hostname+IP in non-Docker, empty in Docker |
| `COLUMNS` | API, Workers | `120` | Integer | Terminal width for Rich output; required in Docker to prevent line wrapping |
| `SHS_UVICORN_LOG_LEVEL` | API | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | Separate log level for `uvicorn` logger |
| `SHS_UVICORN_ERROR_LOG_LEVEL` | API | `ERROR` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | Log level for `uvicorn.error`; defaults to ERROR to suppress WebSocket exception spam |
| `SHS_API_SERVICE_NAME` | API | `api` | Any string | Service name in JSON logs; matches `WORKER_TYPE` semantics for unified dashboards |
| `SHS_FFMPEG_LOGGING_LEVEL` | Workers (video) | `warning` | FFmpeg log levels (`quiet`, `panic`, `fatal`, `error`, `warning`, `info`, `verbose`, `debug`) | Controls FFmpeg subprocess verbosity |
| `SHS_DEBUG` | API | `false` | `true`, `false` | Enables uvicorn reload and FastAPI debug mode; not a logging var per se but affects log output |

### Where variables are set

| File | Key settings |
|------|-------------|
| `api/envs/.env.dev` | `SHS_LOG_LEVEL=INFO`, `SHS_LOG_FORMAT=rich`, `SHS_LOG_VERBOSITY=standard`, `SHS_ENABLE_ACCESS_LOGS=true`, `SHS_SUPPRESS_WEBSOCKET_LOGS=false`, `SHS_SUPPRESS_WORKER_POLLING_LOGS=true`, `COLUMNS=120` |
| `api/envs/.env.prod` | `SHS_LOG_LEVEL=INFO`, `SHS_LOG_FORMAT=json`, `SHS_LOG_VERBOSITY=full`, `SHS_ENABLE_ACCESS_LOGS=false`, `SHS_SUPPRESS_WORKER_POLLING_LOGS=true` |
| `workers/envs/.env.dev` | `SHS_LOG_LEVEL=INFO`, `SHS_LOG_FORMAT=rich`, `SHS_LOG_VERBOSITY=minimal`, `COLUMNS=120` |
| `workers/envs/.env.prod` | `SHS_LOG_LEVEL=INFO`, `SHS_LOG_FORMAT=json`, `SHS_LOG_VERBOSITY=full` |
| `ui/envs/.env.dev` | No logging variables |
| `ui/envs/.env.prod` | No logging variables |

Variables **only in code** (no `.env` file entry): `SHS_LOG_PREFIX`, `SHS_LOG_COLORS`, `SHS_UVICORN_LOG_LEVEL`, `SHS_UVICORN_ERROR_LOG_LEVEL`, `SHS_FFMPEG_LOGGING_LEVEL`.

## Log formats

### `rich` (default for development)

Uses the `rich` Python library for colored, highlighted output with a custom theme. Falls back to `pretty` if `rich` is not installed.

```
[2025-11-30 17:29:34] INFO     uvicorn.error - Started server process [12]
[2025-11-30 17:29:34] INFO     app.service   - Processing user request
```

Theme: `info=green`, `warning=yellow`, `error=bold red`, `debug=dim cyan`.

Configuration: `show_time=True`, `show_level=True`, `show_path=False`, `rich_tracebacks=False`.

### `pretty` (fallback)

Basic ANSI color codes without the `rich` library. Log levels are colorized by severity.

```
2025-11-30 17:29:34 INFO     uvicorn.error - Started server process [12]
```

Level colors: DEBUG=cyan, INFO=green, WARNING=yellow, ERROR=red, CRITICAL=bold red.

Controlled by `SHS_LOG_COLORS` (both API and Workers).

### `json` (production)

Single-line JSON objects. Both API and workers conform to the canonical log schema defined in `contracts/log_schema.py`. Fields vary by `SHS_LOG_VERBOSITY`.

```json
{"timestamp":"2026-03-04T10:30:45.123Z","level":"INFO","service":"api","message":"Processing user request","host":"172.17.0.5","logger":"app.service","username":"john_doe","org_slug":"acme","user_id":"a4d88592-...","org_id":"33b39bc6-...","correlation_id":"550e8400-..."}
```

Both components emit the same top-level fields (`timestamp`, `level`, `service`, `message`) at minimal verbosity, plus `host` and `logger` at standard+. Component-specific context fields (API: `username`/`org_slug`/`user_id`/`org_id`; Workers: `job_id`/`instance_id`/`step_id`) appear at full verbosity. The `correlation_id` field is shared - API sets it from the request, workers receive it via the job payload.

## Verbosity levels

Controls which context fields appear in log output. Primarily affects JSON format; rich/pretty formats always use a fixed layout. The canonical field names are defined in `contracts/log_schema.py`.

| Level | Shared fields | + API-specific | + Worker-specific | Use case |
|-------|--------------|----------------|-------------------|----------|
| `minimal` | `timestamp`, `level`, `service`, `message` | - | - | Low-overhead environments |
| `standard` | + `host`, `logger` | + `username`, `org_slug` | - | Moderate verbosity, useful for tracing issues |
| `full` | + `correlation_id` | + `user_id`, `org_id` | + `job_id`, `instance_id`, `step_id`, `operation`, `prompt_id`, `duration_ms` | Production audit trails / SOC 2 |

Default is `full` when `SHS_LOG_FORMAT=json`, otherwise `standard`.

Exception field name is `exception` in both components (unified). Developer-provided structured fields appear under `extra` when passed via `logger.info("msg", extra={...})`.

## Filters

### API filters

Filter classes are in `api/app/infrastructure/logging/filters.py`. Configuration functions are in `config.py`, formatters in `formatters.py`. The old `access_log_filter.py` is a backward-compatibility shim that re-exports from these modules.

| Filter class | Suppresses | Env var | Default | Attached to |
|-------------|-----------|---------|---------|-------------|
| `TokenRedactionFilter` | JWT tokens in query params (`?token=...`), Authorization headers, standalone JWT patterns (`eyJ...`) | None (always active) | Always on | All handlers |
| `HealthCheckFilter` | `GET /health` access log entries (exact match only; does not suppress `/infrastructure/health`) | None (always active) | Always on | Access handler |
| `WebSocketFilter` | Messages containing "WebSocket", "connection open", "connection close" | `SHS_SUPPRESS_WEBSOCKET_LOGS` | Suppressed (`true`) | Default handler |
| `WorkerPollingFilter` | Heartbeat requests (`/heartbeat`), empty job claims (`/jobs/claim` with 204), "claiming job from queue" INFO logs | `SHS_SUPPRESS_WORKER_POLLING_LOGS` | Suppressed (`true`) | All handlers |
| `AccessLogBlocker` | All access log messages unconditionally | `SHS_ENABLE_ACCESS_LOGS` (blocks when `false`) | Blocked (`false`) | Access handler |
| `SuppressASGITracebackFilter` | Duplicate ASGI exception tracebacks from `uvicorn.error` | None (always active) | Always on | `uvicorn.error` handler |

`TokenRedactionFilter` modifies records in-place (replaces tokens with `[REDACTED]` or `[REDACTED_JWT]`) and always returns `True`. All other filters return `False` to suppress matching records.

### Worker filters

Workers have no custom filter classes. Library noise is controlled by setting third-party logger levels to WARNING at init time (see [Logger levels](#logger-levels-by-logger)).

Workers redact sensitive URLs (S3 signed tokens) at the call site using `redact_url()` from `workers/shared/utils/redaction.py`, not via a log filter.

## Logger levels by logger

### API

| Logger | Default level | Override via | Notes |
|--------|--------------|-------------|-------|
| root | `INFO` | `SHS_LOG_LEVEL` | All application loggers inherit from root |
| `uvicorn` | `INFO` | `SHS_UVICORN_LOG_LEVEL` | `propagate=False` |
| `uvicorn.error` | `ERROR` | `SHS_UVICORN_ERROR_LOG_LEVEL` | `propagate=False`; has `SuppressASGITracebackFilter` |
| `uvicorn.access` | `INFO` or disabled (level 100) | `SHS_ENABLE_ACCESS_LOGS` | `propagate=False`; when disabled, handlers cleared and level set to 100 |
| `httpx` | `WARNING` | - | Always suppressed via `suppress_third_party_loggers()` |
| `httpcore` | `WARNING` | - | Always suppressed via `suppress_third_party_loggers()` |
| `asyncio` | `WARNING` | - | Always suppressed via `suppress_third_party_loggers()` |

### Workers

| Logger | Default level | Override via | Notes |
|--------|--------------|-------------|-------|
| root | `INFO` | `SHS_LOG_LEVEL` | |
| `httpx` | `WARNING` | - | Always suppressed |
| `httpcore` | `WARNING` | - | Always suppressed |
| `urllib3` | `WARNING` | - | Always suppressed |
| `asyncio` | `WARNING` | - | Always suppressed |
| `hpack` | `WARNING` | - | Always suppressed (HTTP/2 header compression) |

All engine handlers use `logging.getLogger(__name__)` and inherit root level. No per-handler level override.

### UI

No Python logging. Next.js uses native `console.*` calls. No log levels, no structured logging.

## Configuration flow

### API startup

Location: `api/main.py`, calling functions in `api/app/infrastructure/logging/config.py`.

```
1. Load env vars: SHS_ENABLE_ACCESS_LOGS, SHS_LOG_LEVEL, SHS_LOG_FORMAT, SHS_LOG_VERBOSITY,
   SHS_UVICORN_LOG_LEVEL, SHS_UVICORN_ERROR_LOG_LEVEL

2. Select config based on SHS_LOG_FORMAT:
   ├─ "json"  → get_json_log_config()     → dictConfig with JSONFormatter
   ├─ "rich"  → setup_rich_logging()       → programmatic RichHandler setup
   ├─ (access logs enabled) → get_log_config() → dictConfig with ColoredFormatter + AccessFormatter
   └─ (else)  → get_base_log_config()     → dictConfig with ColoredFormatter, access logs disabled

3. Call suppress_third_party_loggers() (httpx, httpcore, asyncio → WARNING)

4. Add SuppressASGITracebackFilter to uvicorn.error

5. In lifespan startup: re-disable access logs if SHS_ENABLE_ACCESS_LOGS=false
   (belt-and-suspenders, catches uvicorn re-enabling them)

6. Pass log_config=None to uvicorn.run() so pre-configured logging is used
```

### Worker startup

Location: `workers/shared/worker.py` line 37–40, calling `workers/shared/utils/logging_config.py`.

```
1. Import setup_logging FIRST (before any handler imports)
2. Call setup_logging() at module load time
   ├─ Read SHS_LOG_LEVEL, SHS_LOG_FORMAT, SHS_LOG_VERBOSITY, SHS_LOG_PREFIX, SHS_LOG_COLORS, COLUMNS
   ├─ "json"  → JsonFormatter on stdout
   ├─ "rich"  → RichHandler on stdout (if rich installed, else PrettyFormatter)
   └─ "pretty" → PrettyFormatter on stdout
   └─ Suppress httpx, httpcore, urllib3, asyncio, hpack to WARNING
3. All subsequent imports get consistent logging config
4. Engine handlers use logging.getLogger(__name__) - never call basicConfig
```

Exception: `comfyui-remote` handler calls `logging.basicConfig()` at import time to log a clear error if `SHS_COMFYUI_URL` is unset, before shared config takes over.

### UI

No logging initialization. Next.js default behavior:
- Server-side: `console.*` calls go to Node.js stdout/stderr of the Next.js process
- Client-side: `console.*` calls go to the browser developer console
- Error boundaries catch React rendering errors and log via `console.error()`

## Middleware

### LoggingContextMiddleware

Location: `api/app/infrastructure/logging/context_middleware.py`.

Runs early in the middleware stack (after CORS, before MaintenanceMiddleware). On each request:

1. Generates or reads `X-Correlation-ID` header
2. Extracts JWT from `Authorization: Bearer <token>` header
3. Parses JWT payload for `user_id` (from `sub`), `username`, `org_id`, `org_slug`
4. Sets `RequestContext` via contextvars (`api/app/infrastructure/logging/request_context.py`)
5. Adds `X-Correlation-ID` to response headers
6. Clears context in `finally` block

The `JSONFormatter` reads `RequestContext` to populate user/org/correlation fields in JSON log entries.

## Per-component summary

| Component | Log destination | Default format | Configurable vars | Logging library |
|-----------|----------------|----------------|-------------------|----------------|
| API | stdout (all handlers) | `rich` | `SHS_LOG_LEVEL`, `SHS_LOG_FORMAT`, `SHS_LOG_VERBOSITY`, `SHS_ENABLE_ACCESS_LOGS`, `SHS_SUPPRESS_WEBSOCKET_LOGS`, `SHS_SUPPRESS_WORKER_POLLING_LOGS`, `SHS_LOG_COLORS`, `COLUMNS`, `SHS_UVICORN_LOG_LEVEL`, `SHS_UVICORN_ERROR_LOG_LEVEL` | Python `logging` + `rich` |
| Workers | stdout (all output) | `rich` | `SHS_LOG_LEVEL`, `SHS_LOG_FORMAT`, `SHS_LOG_VERBOSITY`, `SHS_LOG_PREFIX`, `SHS_LOG_COLORS`, `COLUMNS`, `SHS_FFMPEG_LOGGING_LEVEL` | Python `logging` + `rich` |
| UI | Node.js stdout/stderr (server), browser console (client) | Unstructured `console.*` | None | None (native console) |

## Security

- **Token redaction** (API): `TokenRedactionFilter` strips JWTs from all log output - query params, Authorization headers, and standalone JWT patterns. Always active, cannot be disabled.
- **URL redaction** (Workers): `redact_url()` strips S3 signed URL query parameters before logging. Applied at call sites, not as a filter.
- **WebSocket auth**: UI sends auth tokens via `Sec-WebSocket-Protocol` header instead of query params to prevent tokens from appearing in access logs.
- **Sensitive key redaction** (Workers): Result publisher redacts keys matching `secret`, `password`, `api_key`, `token`, `authorization`, `credential_id`, `access_token`, `refresh_token`, `private_key`, `client_secret`, `aws_secret`, `signing_key` before storing results. This is storage redaction, not log redaction.

## Gaps

What is **not** configurable today:

- **No per-path access log filtering.** You can enable or disable all access logs (`SHS_ENABLE_ACCESS_LOGS`), but cannot suppress specific endpoints (e.g., suppress `/api/v1/health` but keep `/api/v1/workflows`). The `HealthCheckFilter` is hardcoded to `/health` only.
- **No per-endpoint suppression without turning off all access logs.** Worker polling and WebSocket filters are the only targeted suppressions available.
- **No file logging.** All output goes to stdout/stderr. Log aggregation depends on the container orchestrator or external tooling (ELK, Loki, etc.).
- **No UI structured logging.** The frontend has no logging library, no log levels, no structured output, and no remote error tracking (Sentry, DataDog, etc.). All logging is bare `console.*` calls.
- **No per-logger level override via env vars** (except root, uvicorn, uvicorn.error). You cannot set `httpx` to DEBUG via env var - it requires a code change.
- **No log rotation.** Stdout-only output means rotation is the container orchestrator's responsibility.
- **No request/response body logging.** Access logs include method, path, and status code but not request/response payloads.
- **No client-side error aggregation.** UI errors in the browser console are not collected or forwarded anywhere.
- **Workers have no log filters.** Unlike the API, workers cannot suppress specific log patterns via env vars - library suppression is hardcoded at init time.

---

For log aggregation setups (ELK, Loki, Datadog) and advanced configuration questions, visit the [SelfHostHub Community](https://www.skool.com/selfhostinnovators).
