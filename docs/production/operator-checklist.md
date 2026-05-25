# Operator Checklist

> **Community & support:** [SelfHostHub Community](https://www.skool.com/selfhosthub) · [Innovators (Plus)](https://www.skool.com/selfhostinnovators)

Get Studio from a fresh server to a working install. Walk top to bottom; each step has a verify command so you know it worked before moving on. If a step fails, stop and fix it before continuing - pushing through saves no time.

For deployment-shape decisions before you start, see [deployment-matrix.md](deployment-matrix.md).

## How to use this checklist

Each step has:

- **Do:** the action - command to run, file to edit, process to start
- **Verify:** how to confirm it worked
- **Expected:** what success looks like
- **If wrong:** brief troubleshooting where the failure mode isn't obvious

Don't skip optional steps without reading the **When** clause - some "optional" steps are required for specific topologies.

---

## Production deploy

**You are running:** the full stack on a production server, behind a real domain, configured by `studio-console`.

### Prerequisites

- [ ] **Step 1 - You're on the production server.**
  - **Do:** `hostname && docker --version`
  - **Expected:** prints the production hostname (not a laptop) and a Docker version.
  - **If wrong:** you're on the wrong machine.

- [ ] **Step 2 - Docker and Compose v2 are installed.**
  - **Do:** `docker --version && docker compose version`
  - **Expected:** both commands print versions; Compose is v2.x.
  - **If wrong:** install Docker Engine and the Compose v2 plugin per Docker's official docs for your OS.

- [ ] **Step 3 - Submodules are initialized.**
  - **Do:** `git submodule status`
  - **Expected:** all submodule lines start with a commit hash, not `-` (uninitialized).
  - **If wrong:** `git submodule update --init --recursive`.

### Network and DNS

- [ ] **Step 4 - DNS for your domain points at this server.**
  - **When:** required for any deployment reachable from the public internet.
  - **Do:** `dig +short your-domain.example.com` (replace with your real domain).
  - **Expected:** prints this server's public IP address.
  - **If wrong:** update the A/AAAA record at your DNS provider and wait for propagation.

- [ ] **Step 5 - Reverse proxy / TLS terminator is running.**
  - **When:** required for production. Studio does not terminate TLS itself.
  - **How Studio routes:** the production compose stack runs an internal nginx container that fronts API + UI on `SHS_NGINX_PORT` (default 80). The `api` and `ui` services are not bound to host ports - nginx is the only host-facing port. Send all external traffic to `SHS_NGINX_PORT`.
  - **Do:** start your external reverse proxy (Caddy, host nginx, Cloudflare Tunnel) configured to forward `your-domain.example.com` → `localhost:${SHS_NGINX_PORT}`. Cloudflare Tunnel via the bundled `cloudflared` profile talks to the internal nginx directly and skips the external proxy entirely.
  - **Verify:** `curl -sI https://your-domain.example.com/ | head -1`
  - **Expected:** the proxy returns a response (502 is fine - Studio isn't running yet, but the proxy is reachable). HTTP `530`, `523`, or DNS-resolution failure means the proxy isn't connected.

### Run the wizard

- [ ] **Step 6 - Install and run `studio-console`.**
  - **Do:** `curl -fsSL https://raw.githubusercontent.com/selfhosthub/studio-console/main/install.sh | bash && studio-console`
  - **Verify:** the wizard launches and prompts you interactively.
  - **Expected:** TUI walks through setup. Answer prompts honestly - domain, admin email, etc. The wizard auto-generates `SHS_JWT_SECRET_KEY`, `SHS_WORKER_SHARED_SECRET`, and `SHS_CREDENTIAL_ENCRYPTION_KEY` if not already set.

- [ ] **Step 7 - Verify `~/.studio/.env` was generated.**
  - **Do:** `ls -la ~/.studio/.env && wc -l ~/.studio/.env`
  - **Expected:** file exists, ~50+ lines, contains `SHS_*` variables with real values (not placeholders).
  - **If wrong:** wizard exited early or had errors. Re-run the wizard.

### Bring up the stack

- [ ] **Step 8 - Start the services.**
  - **Do:** `docker compose up -d`
  - **Verify:** `docker compose ps`
  - **Expected:** all services show `Up` or `healthy`. Postgres, API, UI (and workers, if you started those profiles) all running.
  - **If wrong:** `docker compose logs api` and `docker compose logs postgres` - look for env-var validation failures or DB connection errors.

- [ ] **Step 9 - Verify the public endpoint.**
  - **Do:** `curl -sf https://your-domain.example.com/health` (replace with your real domain).
  - **Expected:** HTTP 200 with health JSON.
  - **If wrong on connection error:** DNS not pointing at the server, or reverse proxy not configured. If 502: stack didn't come up - return to Step 8.

- [ ] **Step 10 - Log in.**
  - **Do:** open `https://your-domain.example.com/login` in a browser.
  - **Expected:** login page loads, the admin email and password from the wizard work, you land on the dashboard.

### Harden the public surface

- [ ] **Step 11 - Enforce rate limits on the auth endpoints at your edge.**
  - **When:** required for any production deployment reachable from the public internet. Studio does **not** rate-limit these endpoints in-process - that's an edge concern, configured at your CDN or reverse proxy.
  - **Why:** without this, `/auth/token` is exposed to brute-force and credential-stuffing attacks. Password hashing slows each attempt but doesn't stop a patient attacker.
  - **Endpoints to protect:**

    | Path | Method |
    |------|--------|
    | `/auth/token` | POST |
    | `/auth/refresh` | POST |
    | `/auth/register` | POST |

  - **Configure this at your edge layer** (CDN, reverse proxy, or WAF of your choice). The operator owns the edge; specific configs are out of scope for this checklist.
  - **If you skip this:** you are accepting the risk of brute-force login attempts against any exposed Studio instance. This is not appropriate for production deployments on the public internet.

**If this checklist disagrees with `studio-console`, trust the wizard.**

---

## Distributed workers

For workers running on a different host from the API (including RunPod GPU pods), see [deployment-matrix.md](deployment-matrix.md#distributed-workers).

You'll need the `SHS_WORKER_SHARED_SECRET` from the API host - copy it byte-for-byte into the worker host's `.env`. A mismatch produces silent 403s on every job poll with no clear error surface.

---

## URL var reference

The URL vars (`SHS_API_BASE_URL`, `SHS_PUBLIC_BASE_URL`, `SHS_FRONTEND_URL`, `SHS_WS_URL`, `SHS_CORS_ORIGINS`) are the single biggest source of botched deploys. Worked example with the gotchas: see [env-vars.md → URL vars worked example](env-vars.md#url-vars-worked-example).

---

## See also

- [deployment-matrix.md](deployment-matrix.md) - all deployment shapes (Standard, Core, Full, Split, Distributed workers)
- [env-vars.md](env-vars.md) - full env var reference
- [bootstrap.md](bootstrap.md) - what `api/scripts/bootstrap.py` does on first boot
- [vps-runpod.md](vps-runpod.md) - VPS + RunPod walkthrough
