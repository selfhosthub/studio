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

Worker auth is two-stage: a worker secret authenticates registration, and nothing else. Every call after registration (claim, heartbeat, job status, step results, credential fetch, file upload and download, package sync, deregistration) carries the worker JWT issued at registration and refreshed on each heartbeat. The token expires in minutes, the heartbeat only refreshes it for the worker it names, and a credential or file is served only for the job the worker is running.

That worker secret is one of two things, and both are accepted at registration:

- **The fleet shared secret** (`SHS_WORKER_SHARED_SECRET`), which every instance generates on first boot. On its own it admits nobody: it files an enrollment request that a super admin approves (see below). A worker inside the deployment also presents the workspace bootstrap token and registers at once.
- **A per-worker enrollment credential** (`SHS_WORKER_CREDENTIAL`). A super admin mints a single-use join token under Infrastructure -> Workers, scoped to named queues; the worker exchanges it once with `studio-workers enroll --join-token <token>` and keeps the credential it gets back. Both the token and the credential are stored as a SHA-256 hash and shown exactly once.

An enrolled worker's JWT is bounded by its credential's recorded queue scope, and its self-declared `queue_labels` keep only the entries that are not queue names. A credential can narrow the operator's allowed queue set; it can never widen it.

Revoking an enrollment credential deregisters every worker registered with it in the same step, so its token stops working on the next call and it cannot register again.

### Approving a worker from outside the deployment

At every boot the API writes a fresh random token to `.worker-bootstrap` at the root of the workspace, readable only by the deployment's user. The bundled workers (the core and full in-container workers, and split's compose workers) mount the workspace, read the file each time they register, and register at once. The token rotates on every API boot, and both sides read the file at registration time, so a rotation needs no restart.

A worker that presents the shared secret without the bootstrap token gets `202` and a pending enrollment request. It waits, polling the request, until a super admin approves or rejects it under Infrastructure -> Workers. Approval can narrow the queues the worker asked for, and gives the worker its own enrollment credential, which it saves under `.studio-worker/` in its own workspace and uses from then on, so a restart needs no second approval. A rejected worker stops trying until it is restarted. At most 100 requests wait at once, and requests older than seven days are dropped.

A worker that mounts the deployment's workspace (for example a GPU box sharing it over the network) holds the bootstrap token and registers without approval. It can already read every organization's files through that mount, so the approval step would not change what it can reach.

Accepted risk, stated plainly. **Enrolling a worker closes the first two for that worker. They stand for every worker registered with the shared secret and the bootstrap token:**

- Any holder of the shared secret who can also read the workspace registers a worker without approval. That worker claims jobs on the allowed queues and receives the credentials and files those jobs name. The secret alone files a request and reaches nothing else.
- The shared secret is static per instance. There is no rotation mechanism: changing it means editing `.env`, restarting the API, and updating every worker at once.
- There is no per-worker revocation for shared-secret holders; you cannot cut off one machine without rotating the secret everywhere. Revoking one enrollment credential cuts off exactly one machine.
- There is no in-product rate limiting or throttling on the worker endpoints. This applies to both.

The shared secret cannot be removed yet: it is a self-generated secret in the console's launch manifest, every existing install already carries it in a `.env` the entrypoint never rewrites, and `docker-compose.yml` requires it on five worker services. Enrollment is additive.

The mitigation is edge gating, not in-product controls:

- Internal ports bind to `127.0.0.1` on the host by default; nothing is reachable from the LAN or internet unless you route it.
- `/internal/*` is unreachable through the default front door; only the dedicated API hostname routes it.
- Optionally, put a path-scoped Cloudflare Access application on `<api-hostname>/internal/*` and give workers a service token via `SHS_CF_ACCESS_CLIENT_ID` and `SHS_CF_ACCESS_CLIENT_SECRET`. The worker sends the token as `CF-Access-Client-Id`/`CF-Access-Client-Secret` headers on every API call; it is additive to the secret and JWT, and off by default. Do not gate the whole API hostname: OAuth callbacks and provider webhooks arrive from IPs you cannot allowlist.

Treat either secret as the key that admits a worker to the job system: both ride in worker env files, so scope those files 0600 and keep them off shared machines. An enrollment credential is the narrower of the two, since it is scoped and revocable.

## Migration: internal ports are now localhost-only

Older images and consoles published the API port (8000) and the supervisord port (9001, core/full) on all interfaces. Current consoles publish them on `127.0.0.1` only.

If you had a LAN worker pointed at `http://<host-ip>:8000`, it will stop connecting after upgrading. Pick one:

- Preferred: switch the worker to the API hostname path above.
- Preserve the old behavior: set `SHS_PUBLISH_INTERNAL_BIND=0.0.0.0` (or a specific LAN IP) in the launch environment. The console then publishes the internal ports on that bind instead of `127.0.0.1`. This exposes the API's worker endpoints (shared-secret auth only) and the supervisord dashboard (basic auth) to that network; only do it on a network you trust.
