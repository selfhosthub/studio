# Worker Access: Paths, Security Model, Migration

How workers reach the API in each deployment shape, what the auth model does and does not protect against, and what changed for operators when internal ports went localhost-only.

## Sanctioned access paths

Workers talk to the API on the `/internal/*` and `/api/v1/internal/*` routes. There are exactly four supported ways to reach them:

| Path | Who uses it | How it works |
|------|-------------|--------------|
| Compose network | Split-shape workers in the same compose project | `SHS_API_BASE_URL=http://api:8000`, hardcoded in compose. Never leaves the Docker network. |
| Localhost API port | Native (non-Docker) workers on the same host | Core and full publish the API on `127.0.0.1:8000` (console 1.4.1+). Split gains this with the next console release; until then split's native same-host path is the API hostname. |
| API hostname | Docker workers on the same host, and all remote workers | The bundled nginx serves a dedicated server block for the API hostname (the host part of the split API URL, or `SHS_PUBLIC_API_URL` on core/full) and routes everything on it to the API. Remote workers reach it through your tunnel or reverse proxy; a same-host Docker worker reaches it with `--add-host <api-hostname>:host-gateway`. |
| Worker-only host compose | A dedicated GPU/worker box | `workers/docker-compose.yml` with a real `SHS_API_BASE_URL` URL. This is the API-hostname path from another machine. |

The default front door never routes worker traffic: nginx returns 404 for `/internal/*` on every hostname except the dedicated API hostname. A worker pointed at the UI hostname does not work by design.

Cloudflare tunnel caveat: worker result upload is a single multipart request, so Cloudflare's 100MB body limit caps tunnel-routed uploads. Audio and images fit; long video renders need direct routing or a shared workspace.

## Security model and accepted risk

Worker auth is two-stage: the shared secret (`SHS_WORKER_SHARED_SECRET`) authenticates claim, status, cleanup, credential fetch, and file download; step results, per-job tokens, and upload use a worker JWT issued against it.

Accepted risk, stated plainly:

- The shared secret is static per instance. There is no rotation mechanism: changing it means editing `.env`, restarting the API, and updating every worker at once.
- There is no per-worker revocation. Any holder of the secret is a worker; you cannot cut off one machine without rotating the secret everywhere.
- There is no in-product rate limiting or throttling on the worker endpoints.

The mitigation is edge gating, not in-product controls:

- Internal ports bind to `127.0.0.1` on the host by default; nothing is reachable from the LAN or internet unless you route it.
- `/internal/*` is unreachable through the default front door; only the dedicated API hostname routes it.
- Optionally, put a path-scoped Cloudflare Access application on `<api-hostname>/internal/*` and give workers a service token via `SHS_CF_ACCESS_CLIENT_ID` and `SHS_CF_ACCESS_CLIENT_SECRET`. The worker sends the token as `CF-Access-Client-Id`/`CF-Access-Client-Secret` headers on every API call; it is additive to the secret and JWT, and off by default. Do not gate the whole API hostname: OAuth callbacks and provider webhooks arrive from IPs you cannot allowlist.

Treat the shared secret like a root credential for the job system: it rides in worker env files, so scope those files 0600 and keep them off shared machines.

## Migration: internal ports are now localhost-only

Older images and consoles published the API port (8000) and the supervisord port (9001, core/full) on all interfaces. Current consoles publish them on `127.0.0.1` only.

If you had a LAN worker pointed at `http://<host-ip>:8000`, it will stop connecting after upgrading. Pick one:

- Preferred: switch the worker to the API hostname path above.
- Preserve the old behavior: set `SHS_PUBLISH_INTERNAL_BIND=0.0.0.0` (or a specific LAN IP) in the launch environment. The console then publishes the internal ports on that bind instead of `127.0.0.1`. This exposes the API's worker endpoints (shared-secret auth only) and the supervisord dashboard (basic auth) to that network; only do it on a network you trust.
