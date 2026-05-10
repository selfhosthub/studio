# Studio Bootstrap Guide

> **Community & support:** [SelfHostHub Community](https://www.skool.com/selfhosthub) · [Innovators (Plus)](https://www.skool.com/selfhostinnovators)

> **Scope:** Production deployment contexts (single host, distributed workers, RunPod).

---

## Overview

Studio ships with a bootstrap script (`api/scripts/bootstrap.py`) that handles first-run configuration. It runs automatically on container start via `docker-entrypoint.sh`.

**What it does on every start:**
- Validates required secrets (`SHS_JWT_SECRET_KEY`, `SHS_WORKER_SHARED_SECRET`, `SHS_CREDENTIAL_ENCRYPTION_KEY`)
- Recovers missing secrets from environment variables (RunPod vault, shell env) and writes them to `.env`

**What it does on first boot only:**
- Waits for the database to be available
- Creates database tables
- Creates the super organization and super-admin account (username: `super_admin`)
- Creates the protected `ENTITLEMENT_TOKEN` secret on the system org (blank placeholder, or pre-populated if `SHS_ENTITLEMENT_TOKEN` is in the environment)
- Creates workspace directories for the super organization
- Writes a `.bootstrapped` marker file

**What it does not do:**
- Overwrite an existing `.env` - edit `/workspace/.env` directly (or `~/.studio/.env` on the host) for post-boot changes
- Re-bootstrap when the `.bootstrapped` marker exists (protects shared storage)
- Seed provider credentials - operators add these through the UI after first boot

---

## Environment Variable Flow

Env vars are set explicitly at each layer. **No fallbacks.** If a required var is missing, the code fails with a `RuntimeError`.

### API

```
Host                            docker-compose.yml              Container
────                            ──────────────────              ─────────
~/.studio/.env                  env_file: ${HOME}/.studio/.env  /workspace/.env
                                                                (bind-mounted from ~/.studio/.env)

                                volume: ~/.studio:/workspace    SHS_WORKSPACE_ROOT=/workspace
                                env:    SHS_WORKSPACE_ROOT=/workspace
```

**Key variables:**

| Variable | Set by | Value in container | Read by |
|----------|--------|--------------------|---------|
| `SHS_WORKSPACE_ROOT` | docker-compose.yml | `/workspace` | workspace.py, main.py, users.py, organizations.py, system_health_service.py |
| `SHS_ENV` | `~/.studio/.env` | `production` | bootstrap.py, settings.py |
| `SHS_DATABASE_URL` | `~/.studio/.env` | postgres connection string | database.py |

### Workers

```
Host                            docker-compose.yml              Container
────                            ──────────────────              ─────────
~/.studio/.env                  env_file: ${HOME}/.studio/.env  /workspace/.env
                                volume: ~/.studio:/workspace    SHS_WORKSPACE_ROOT=/workspace
```

For distributed workers (different host from the API), the workers host has its own `.env` with `SHS_API_BASE_URL` pointing at the public URL of the API host and a matching `SHS_WORKER_SHARED_SECRET`.

**Key variables:**

| Variable | Same-host value | Distributed value | Read by |
|----------|----------------|-------------------|---------|
| `SHS_WORKSPACE_ROOT` | `/workspace` | `/workspace` | constants.py, storage.py, handler.py |
| `SHS_API_BASE_URL` | `http://api:8000` (Docker bridge) | `https://your-domain.example.com` | worker.py, worker_base.py, result_publisher.py |
| `SHS_WORKER_SHARED_SECRET` | from `.env` | from `.env` (must match API host) | worker_base.py, http_job_client.py |

### Workspace location

The host directory that backs `/workspace` inside the containers is configurable via `SHS_WORKSPACE_HOST`:

| Deployment | `SHS_WORKSPACE_HOST` | Result |
|-----------|----------------------|--------|
| VPS / bare metal (default) | unset | `~/.studio` on the host |
| RunPod | `/workspace` | RunPod network volume |
| Kubernetes | your PV mount path | the PV |
| Custom | any absolute path | wherever you point it |

Set the value before running `studio-console`, and it will honor it. After setup it lives in `.env` and is read by `docker compose` for the bind mounts. The container side (`SHS_WORKSPACE_ROOT=/workspace`) does not change - only the host side moves.

### Rules

1. **No fallbacks for filesystem paths.** `SHS_WORKSPACE_ROOT` must be explicitly set. Code raises `RuntimeError` if missing.
2. **No fallbacks for service URLs.** `SHS_API_BASE_URL` and `SHS_WORKER_SHARED_SECRET` must be explicitly set. Code raises `RuntimeError` if missing.
3. **Tuning knobs may have defaults.** Retry counts, timeouts, cache sizes - these have sensible defaults in code. See [env-vars.md](env-vars.md).
4. **One name per variable.** No aliases. One canonical name, used everywhere.

---

## Deployment Contexts

### Local / VPS

On first container start, `docker-entrypoint.sh` copies `api/envs/.env.prod` to `/workspace/.env` if the file doesn't already exist. The bind mount maps `~/.studio` on the host to `/workspace` in the container, so the file persists at `~/.studio/.env`.

Bootstrap runs once and writes the `.bootstrapped` marker. Subsequent starts skip bootstrap.

To change a value after first run, edit `~/.studio/.env` directly and restart:

```bash
docker compose restart api
```

### RunPod (network volume)

On first boot, the entrypoint copies `api/envs/.env.prod` to `/workspace/.env` and creates a symlink (`/app/.env` → `/workspace/.env`). The network volume ensures the file survives pod restarts and rebuilds.

The `.bootstrapped` marker on the network volume prevents re-bootstrap when new instances scale up or pods restart. This is critical for shared storage - re-initializing the filesystem would destroy data for all instances.

Required secrets must be set in the RunPod dashboard **before** starting the pod. See [RunPod Secrets](#runpod-secrets) below.

### Workers on a separate host

When workers run on a different machine from the API:

- Only `workers/envs/.env.prod` (or `~/.studio/.env` from the wizard) is used on that host
- `SHS_API_BASE_URL` must point to the API host's public URL
- `SHS_WORKER_SHARED_SECRET` must match the value on the API host exactly

See [Split Deployment](#split-deployment) below.

---

## Required Values

These must be set before first boot. `studio-console` auto-generates secrets; bootstrap validates them on every start.

| Key | Where | Auto-generated | Notes |
|-----|-------|----------------|-------|
| `SHS_JWT_SECRET_KEY` | API | Yes (always) | Signs auth tokens. Changing it invalidates all sessions. |
| `SHS_WORKER_SHARED_SECRET` | API + Workers | Yes (if not pre-set) | Must match on both sides. Pre-set via env var for split deployments. |
| `SHS_CREDENTIAL_ENCRYPTION_KEY` | API | Yes (if not pre-set) | Encrypts provider credentials at rest. **Losing this key makes stored credentials unrecoverable.** Back up `.env` or store in an external vault. |
| `SHS_DATABASE_URL` | API | No | Full postgres connection string |
| `SHS_PUBLIC_BASE_URL` | Workers | No | Public URL for external API callbacks and file downloads. Must be reachable from outside your network. |
| `SHS_FRONTEND_URL` | API | No | Frontend URL used by the API for OAuth redirect callbacks. |

**Secret recovery:** if a secret is missing from `.env` but present as an environment variable (RunPod vault, shell env), bootstrap writes it to `.env` automatically and continues. If missing everywhere, the API will not start.

---

## RunPod Secrets

Create these secrets in the RunPod dashboard before starting your pod:

| Secret Name | Example Value | Notes |
|-------------|---------------|-------|
| `postgres_password` | `openssl rand -hex 32` | Database password |
| `jwt_secret_key` | `openssl rand -hex 32` | Auth token signing |
| `worker_shared_secret` | `openssl rand -hex 32` | API ↔ worker auth |
| `credential_encryption_key` | `openssl rand -hex 32` | Encrypts provider credentials at rest |
| `admin_password` | your chosen password | Super admin login |

Then in your pod environment variables:

```
POSTGRES_PASSWORD={{ RUNPOD_SECRET_postgres_password }}
SHS_JWT_SECRET_KEY={{ RUNPOD_SECRET_jwt_secret_key }}
SHS_WORKER_SHARED_SECRET={{ RUNPOD_SECRET_worker_shared_secret }}
SHS_CREDENTIAL_ENCRYPTION_KEY={{ RUNPOD_SECRET_credential_encryption_key }}
SHS_ADMIN_PASSWORD={{ RUNPOD_SECRET_admin_password }}
```

Storing `SHS_CREDENTIAL_ENCRYPTION_KEY` in the RunPod vault protects against accidental `.env` deletion - bootstrap will recover it from the environment variable on next start.

If any required secrets are missing, the bootstrap script aborts with a clear error listing exactly what needs to be added.

---

## First Boot Sequence

```
docker-entrypoint.sh
    ↓
mkdir -p /workspace
symlink: /app/.env → /workspace/.env  (app reads from persisted file)
    ↓
python3 bootstrap.py
    ↓
Check SHS_ENV (from .env file)
    ↓
validate_secrets() - runs on EVERY start
    ├── secret in .env → use it
    ├── secret in env var (vault) but not .env → write to .env, continue
    └── secret missing everywhere → fail with context-aware error
    ↓
    ├── .bootstrapped exists → skip to API start
    └── no marker → continue to first-boot setup
    ↓
wait_for_database() - retry loop until postgres responds
    ↓
ensure_tables_exist() - create all tables from SQLAlchemy models
    ↓
bootstrap_database.py:
    ├── create_super_organization() - System org + workspace dirs
    │     └── ensure_org_workspace(org_id) - reads SHS_WORKSPACE_ROOT, creates /workspace/orgs/{id}/
    ├── create_super_admin() - username: super_admin, with configured email + password
    └── create_entitlement_token_secret() - protected, undeletable ENTITLEMENT_TOKEN
          └── if SHS_ENTITLEMENT_TOKEN in env → active with token; else → blank placeholder
    ↓
Write /workspace/.bootstrapped marker
    ↓
exec python main.py - start the API server
```

---

## Post-Boot Configuration

To change a value after first boot, edit the `.env` file directly:

- **Docker**: edit `~/.studio/.env` on the host (bind-mounted as `/workspace/.env` in the container)
- **RunPod**: edit `/workspace/.env` on the network volume

Restart the API container after changes:

```bash
docker compose restart api
```

---

## Split Deployment

When the API/UI and workers run on separate machines:

**API + UI host** - run bootstrap normally. The `SHS_WORKER_SHARED_SECRET` in `/workspace/.env` must be copied to the workers host.

**Workers-only host** - put a minimal `~/.studio/.env` in place before bringing the worker compose up:

```
SHS_API_BASE_URL          # URL of the API host (must be reachable from this machine)
SHS_WORKER_SHARED_SECRET  # must match the API host value exactly
SHS_WORKSPACE_HOST        # host directory mounted as /workspace inside the worker
```

Then start whichever worker(s) this host runs:

```bash
docker compose -f workers/docker-compose.yml up -d worker-audio
```

---

## Troubleshooting

### Missing secrets
Bootstrap validates secrets on every start. If a secret is missing from `.env`, it checks environment variables (RunPod vault, shell env) and writes any found values to `.env`. If a secret is missing everywhere, the API will not start.

For previously bootstrapped systems, a missing `SHS_CREDENTIAL_ENCRYPTION_KEY` means existing encrypted credentials are unreadable. Restore the original key from your backup or external vault.

### `.env` exists but values are wrong
Do not delete `.env` and re-run bootstrap - edit `~/.studio/.env` directly (or `/workspace/.env` on RunPod).

### Database already initialized
The `.bootstrapped` marker causes bootstrap to skip entirely. If you need to re-run bootstrap, remove the marker file first: `rm /workspace/.bootstrapped` (or `rm ~/.studio/.bootstrapped` on a single-host install).

### Workers can't reach the API
Check `SHS_API_BASE_URL` in the workers' `.env`. It must be reachable from the workers host - not `localhost` unless they're on the same machine.

### Lost CREDENTIAL_ENCRYPTION_KEY
If the key is lost and there is no backup, encrypted provider credentials in the database cannot be recovered. Delete the affected credential records and re-enter them through the UI with a new key.

---

## Related Docs

- [`super_admin.md`](super_admin.md) - super admin role, capabilities, and first-login guide
- [`env-vars.md`](env-vars.md) - operator-tunable environment variables (timeouts, limits, polling)
- [`docker-images.md`](docker-images.md) - image build details
- [`deployment-matrix.md`](deployment-matrix.md) - deployment shapes and decision tree
- [`README.md`](../README.md) - quick start and operator entry points
