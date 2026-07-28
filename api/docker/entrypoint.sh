#!/bin/bash
# api/docker/entrypoint.sh
# First-boot bootstrap + supervisord handoff for Core and Full images.
# Shape is read from /etc/studio-shape (baked at image build time).
#
# Two paths:
#
#   A. Default CMD (supervisord) → full first-boot:
#      1. /workspace/.env exists → use as-is, generate nothing.
#      2. /workspace/.env absent → generate SHS_DEPLOYMENT_SHAPE, the three
#         secrets (JWT, worker shared, credential encryption), and the nginx
#         front-door vars (SHS_NGINX_PORT, SHS_CORS_ORIGINS=*,
#         SHS_PUBLIC_BASE_URL, SHS_WORKSPACE_ROOT) for BOTH shapes. Full
#         additionally gets POSTGRES_PASSWORD + matching SHS_DATABASE_URL
#         (bundled DB); core's DB URL is launcher-supplied. 0600 perms.
#      3. Symlink /app/api/.env and /app/.env → /workspace/.env.
#      4. Verify SHS_SUPERVISOR_USER and SHS_SUPERVISOR_PASSWORD are
#         present in process env. Exit non-zero if either is missing -
#         fail-closed per commit 4920b118. No auto-generation, no defaults.
#      5. Shape-specific work (Postgres init for Full, bootstrap for
#         both).
#      6. exec supervisord.
#
#   B. Override CMD (`docker run image studio-console …`, `bash`, `psql`,
#      etc.) → skip everything except the symlink, then exec the override.
#      One-off invocations must not block on Postgres or supervisord auth.
#      The symlink still runs because tools like studio-console need .env
#      to be where pydantic-settings expects it; we only skip if .env
#      hasn't been created yet (volume hasn't seen first boot, console
#      can still operate read-only on its own state).
#
# Image-baked ENV (set in the Dockerfiles, not the .env file): SHS_ENV,
# SHS_COMMUNITY_SOURCE, SHS_PLUS_SOURCE. Operator never tunes these at boot.
set -euo pipefail

# --- Constants -----------------------------------------------------------
SHAPE_FILE="/etc/studio-shape"
WORKSPACE_ENV="/workspace/.env"
SUPERVISORD_CONF="/etc/supervisor/supervisord.conf"
PG_BIN="/usr/lib/postgresql/18/bin"
PG_DATA="${SHS_PG_DATA:-/workspace/db}"
# Read-only bind mount the launcher drops a raw CF tunnel token at (contract:
# contracts-data/launch-manifest.json → consumed_secret_files). Must match console's
# CF_TOKEN_MOUNT constant exactly.
CF_TOKEN_MOUNT="/run/secrets/cf-token"

# --- Functions -----------------------------------------------------------
# Pump a .env file into process env. Splits on the first = only, preserving
# everything after it (incl. base64 padding). Process env wins over .env.
load_env_safe() {
    [ -f "$1" ] || return 0
    while IFS= read -r line || [ -n "$line" ]; do
        # Skip blank lines and comments
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
        # Split on the first = only, preserving everything after it (incl. trailing =)
        key="${line%%=*}"
        value="${line#*=}"
        # Trim whitespace from key
        key="${key#"${key%%[![:space:]]*}"}"
        key="${key%"${key##*[![:space:]]}"}"
        # Operator-supplied (process env) wins
        [ -n "${!key+x}" ] && continue
        # Strip surrounding quotes if present
        value="${value%\"}"; value="${value#\"}"
        value="${value%\'}"; value="${value#\'}"
        export "$key=$value"
    done < "$1"
}

# Consume a launcher-dropped Cloudflare tunnel token into /workspace/.env.
# The token is a high-value secret, so the launcher passes it via a read-only
# file mount (never `docker run -e`, which leaks via docker inspect and
# /proc/1/environ). Upsert semantics: strip any existing line, append the new
# value (append sidesteps sed escaping - CF tokens are base64 with / and +).
# Runs every boot; an absent mount leaves .env untouched (relaunch clobber-
# protection - the launcher drops the file only on first-provision/reconfigure).
consume_cf_token() {
    [ -f "$CF_TOKEN_MOUNT" ] || return 0
    token="$(tr -d '[:space:]' < "$CF_TOKEN_MOUNT")"
    [ -n "$token" ] || return 0
    if [ ! -f "$WORKSPACE_ENV" ]; then
        touch "$WORKSPACE_ENV"; chmod 0600 "$WORKSPACE_ENV"
    fi
    tmp="$(mktemp -p "$(dirname "$WORKSPACE_ENV")")"
    chmod 0600 "$tmp"
    grep -v '^CLOUDFLARE_TUNNEL_TOKEN=' "$WORKSPACE_ENV" > "$tmp" || true
    printf 'CLOUDFLARE_TUNNEL_TOKEN=%s\n' "$token" >> "$tmp"
    mv "$tmp" "$WORKSPACE_ENV"
    chmod 0600 "$WORKSPACE_ENV"
    echo "consumed $CF_TOKEN_MOUNT → .env"
}

# Write a literal numprocs=<count> into a supervisor conf fragment.
set_worker_numprocs() {
    conf="$1"; count="$2"
    [ -f "$conf" ] || return 0
    if ! [[ "$count" =~ ^[0-9]+$ ]]; then
        echo "WARNING: invalid worker count '$count' for $conf; numprocs unchanged" >&2
        return 0
    fi
    tmp="$(mktemp -p "$(dirname "$conf")")"
    sed "s/^numprocs=.*/numprocs=${count}/" "$conf" > "$tmp"
    # cat-in-place (not mv) keeps the fragment's mode/owner/inode.
    cat "$tmp" > "$conf"
    rm -f "$tmp"
}

# When sourced (e.g. by tests), expose functions and stop - skip all boot work.
(return 0 2>/dev/null) && return 0

# --- Read shape ----------------------------------------------------------
if [ ! -r "$SHAPE_FILE" ]; then
    echo "FATAL: $SHAPE_FILE missing or unreadable. Image build is broken." >&2
    exit 1
fi
SHAPE="$(tr -d '[:space:]' < "$SHAPE_FILE")"
if [ "$SHAPE" != "core" ] && [ "$SHAPE" != "full" ]; then
    echo "FATAL: $SHAPE_FILE contains '$SHAPE'; expected 'core' or 'full'." >&2
    exit 1
fi

# --- Helpers -------------------------------------------------------------
# Maintain the /app/.env and /app/api/.env symlinks if /workspace/.env
# already exists. Cheap and idempotent - needed for both the full first-
# boot path and any override-CMD path that might read .env (studio-console,
# psql, manual python invocations).
ensure_env_symlinks() {
    [ -f "$WORKSPACE_ENV" ] || return 0
    for link in /app/.env /app/api/.env; do
        if [ -L "$link" ] && [ "$(readlink "$link")" = "$WORKSPACE_ENV" ]; then
            continue
        fi
        rm -f "$link" 2>/dev/null || true
        ln -s "$WORKSPACE_ENV" "$link" 2>/dev/null || true
    done
}

# --- Branch: override CMD short-circuits first-boot ----------------------
# If the operator passed a CMD override (anything other than the default
# supervisord invocation), skip first-boot/bootstrap and exec the override
# directly. One-off invocations like `studio-console --version`,
# `psql ...`, or `bash` must not block on Postgres or supervisord auth.
DEFAULT_CMD_FIRST_ARG="supervisord"
if [ "$#" -gt 0 ] && [ "$1" != "$DEFAULT_CMD_FIRST_ARG" ]; then
    ensure_env_symlinks
    exec "$@"
fi

# --- Step 1/2: .env generation (only when fully absent) ------------------
mkdir -p /workspace

if [ ! -f "$WORKSPACE_ENV" ]; then
    echo "First boot: generating $WORKSPACE_ENV (shape=$SHAPE)"

    # Refuse to write a broken .env. SHS_STUDIO_VERSION is baked into the
    # image at build time (Dockerfile / Dockerfile.full ARG STUDIO_VERSION
    # → ENV SHS_STUDIO_VERSION). A missing or empty value here means the
    # build flow forgot to pass --build-arg STUDIO_VERSION. Failing cold-
    # boot is the right signal - silently writing SHS_STUDIO_VERSION= to
    # .env would leave operators unable to tell "correctly empty" from
    # "build broke and nobody noticed."
    if [ -z "${SHS_STUDIO_VERSION:-}" ]; then
        echo "FATAL: SHS_STUDIO_VERSION not baked into image (build defect)." >&2
        echo "       Pass --build-arg STUDIO_VERSION=... when building Core/Full." >&2
        exit 1
    fi

    umask 077

    # Generate secrets first so we can interpolate POSTGRES_PASSWORD into
    # SHS_DATABASE_URL for Full.
    #
    # SHS_CREDENTIAL_ENCRYPTION_KEY must be a Fernet key (urlsafe-base64-
    # encoded 32 bytes). bootstrap.py:_validate_fernet_key rejects hex.
    # Standard base64 swapped to urlsafe = Fernet-compatible.
    GEN_JWT="$(openssl rand -hex 32)"
    GEN_WORKER="$(openssl rand -hex 32)"
    GEN_ENCRYPTION="$(openssl rand -base64 32 | tr '+/' '-_')"
    GEN_PG_PASSWORD=""
    GEN_APP_PASSWORD=""
    if [ "$SHAPE" = "full" ]; then
        GEN_PG_PASSWORD="$(openssl rand -hex 32)"
        GEN_APP_PASSWORD="$(openssl rand -hex 32)"
    fi

    {
        echo "# Generated by studio entrypoint on first boot."
        echo "# Operator may edit. Subsequent boots leave this file alone."
        echo "SHS_DEPLOYMENT_SHAPE=$SHAPE"
        echo "SHS_STUDIO_VERSION=$SHS_STUDIO_VERSION"
        echo "SHS_JWT_SECRET_KEY=$GEN_JWT"
        echo "SHS_WORKER_SHARED_SECRET=$GEN_WORKER"
        echo "SHS_CREDENTIAL_ENCRYPTION_KEY=$GEN_ENCRYPTION"
        if [ "$SHAPE" = "full" ]; then
            # Full runs Postgres inside the container with this password,
            # and the API connects to it at localhost. Core has no bundled DB;
            # SHS_DATABASE_URL is supplied by the launcher (console/compose).
            echo "POSTGRES_PASSWORD=$GEN_PG_PASSWORD"
            echo "SHS_DATABASE_URL=postgresql+asyncpg://postgres:${GEN_PG_PASSWORD}@localhost:5432/selfhost_studio"
            # Greenfield Full serves requests as the restricted shs_app role (bootstrap provisions it from this URL).
            echo "SHS_DATABASE_APP_URL=postgresql+asyncpg://shs_app:${GEN_APP_PASSWORD}@localhost:5432/selfhost_studio"
        fi
        # nginx front-door vars: written for BOTH shapes so first boot self-seeds
        # them and later edits (e.g. the CF wizard writing a real domain) persist.
        # The launcher must NOT inject these via `docker run -e` on relaunch -
        # process env beats .env, so a re-injected localhost placeholder would
        # clobber an operator-configured domain every restart. nginx is the single
        # front door: browser, SSR, and the public URL share the nginx origin
        # (default :80); /api,/ws route to the API internally, so the placeholder
        # public URL is the nginx port, not :8000. CORS is permissive at first
        # boot - operators don't know their domain until the deploy is running;
        # tighten via the in-container console once it's known (same-origin via
        # nginx makes CORS moot once a real domain is set).
        NGINX_PORT="${SHS_NGINX_PORT:-80}"
        echo "SHS_NGINX_PORT=$NGINX_PORT"
        echo "SHS_CORS_ORIGINS=*"
        echo "SHS_PUBLIC_BASE_URL=http://localhost:${NGINX_PORT}"
        echo "SHS_WORKSPACE_ROOT=/workspace"
        # Browser-bundle origin vars: ui-start.sh reads these from .env to render
        # __env.js (NEXT_PUBLIC_*). Honor launcher-injected values so non-
        # interactive provisioning (CI/RunPod/GitOps) reaches the real domain;
        # else the nginx-origin placeholder. First-boot-only (block skipped once
        # .env exists) so a wizard-set domain on relaunch is never clobbered.
        # SHS_API_BASE_URL is deliberately NOT persisted - SSR must stay on the
        # in-container API (ui-start defaults it to localhost:$PORT), never
        # hairpin through the public origin.
        echo "SHS_PUBLIC_API_URL=${SHS_PUBLIC_API_URL:-http://localhost:${NGINX_PORT}}"
        echo "SHS_WS_URL=${SHS_WS_URL:-ws://localhost:${NGINX_PORT}}"
        echo "SHS_FRONTEND_URL=${SHS_FRONTEND_URL:-http://localhost:${NGINX_PORT}}"
    } > "$WORKSPACE_ENV"
    chmod 0600 "$WORKSPACE_ENV"
    umask 022
else
    echo "Found existing $WORKSPACE_ENV - using as-is, no keys generated."
fi

# --- Step 3: symlinks ----------------------------------------------------
# Two targets: /app/.env (per plan contract) and /app/api/.env (where
# pydantic-settings actually reads from, since CWD is /app/api). Both point
# at /workspace/.env. Cheap, satisfies both readings.
ensure_env_symlinks

# --- Step 4: fail-closed supervisord auth check --------------------------
# Must run before any DB or shape-specific work. If supervisord won't start,
# nothing else matters.
if [ -z "${SHS_SUPERVISOR_USER:-}" ] || [ -z "${SHS_SUPERVISOR_PASSWORD:-}" ]; then
    echo "FATAL: SHS_SUPERVISOR_USER and SHS_SUPERVISOR_PASSWORD must be set in" >&2
    echo "       the container environment. Pass them via 'docker run -e' or your" >&2
    echo "       RunPod template. The image fails closed by design - no auto-" >&2
    echo "       generation, no default password. See commit 4920b118." >&2
    exit 1
fi

# --- Step 5: shape-specific work -----------------------------------------
case "$SHAPE" in
    full)
        # Postgres lives inside the container. Initialize it on first boot,
        # then run bootstrap against it, then stop it so supervisord can own it.
        if [ ! -f "$PG_DATA/PG_VERSION" ]; then
            echo "Initializing PostgreSQL 18 data directory at $PG_DATA"
            mkdir -p "$PG_DATA"
            chown postgres:postgres "$PG_DATA"
            # Match Core's UTF8/en_US.utf8; default initdb falls back to SQL_ASCII.
            su - postgres -c "$PG_BIN/initdb -D $PG_DATA --encoding=UTF8 --locale=en_US.UTF-8"
            echo "host all all 0.0.0.0/0 md5" >> "$PG_DATA/pg_hba.conf"
            echo "listen_addresses='*'" >> "$PG_DATA/postgresql.conf"
        fi

        chown -R postgres:postgres "$PG_DATA"
        su - postgres -c "$PG_BIN/pg_ctl -D $PG_DATA -l /var/log/postgresql/postgresql.log start"
        until su - postgres -c "$PG_BIN/pg_isready" 2>/dev/null; do sleep 1; done

        # Sync the postgres-user password with SHS_DATABASE_URL on every boot.
        # md5 auth in pg_hba.conf requires it; idempotent ALTER USER is cheap.
        # Read the password fresh from .env so operator edits stay in sync.
        PG_PASS_FROM_ENV="$(grep -E '^POSTGRES_PASSWORD=' "$WORKSPACE_ENV" | head -1 | cut -d= -f2-)"
        if [ -n "$PG_PASS_FROM_ENV" ]; then
            su - postgres -c "psql -c \"ALTER USER postgres WITH PASSWORD '$PG_PASS_FROM_ENV';\"" >/dev/null
        fi

        su - postgres -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname = 'selfhost_studio'\" | grep -q 1" \
            || su - postgres -c "createdb selfhost_studio"
        su - postgres -c "psql -d selfhost_studio -c 'CREATE EXTENSION IF NOT EXISTS vector;'" 2>/dev/null || true

        # Embedded Postgres lives at localhost from the API's perspective,
        # not 'postgres' as the compose stack expects. Patch on first boot only.
        if grep -q '@postgres:' "$WORKSPACE_ENV"; then
            sed -i 's|@postgres:|@localhost:|g' "$WORKSPACE_ENV"
        fi
        if ! grep -q '^SHS_WORKSPACE_ROOT=' "$WORKSPACE_ENV"; then
            echo "SHS_WORKSPACE_ROOT=/workspace" >> "$WORKSPACE_ENV"
        fi

        echo "Running bootstrap..."
        cd /app/api
        export SHS_WORKSPACE_ROOT=/workspace
        PATH="/app/api/.venv/bin:$PATH" PYTHONPATH="/app/api:/app/worker" python3 scripts/bootstrap.py

        echo "Stopping temporary PostgreSQL (supervisord will manage it)..."
        su - postgres -c "$PG_BIN/pg_ctl -D $PG_DATA stop"

        export SHS_PG_DATA="$PG_DATA"
        ;;
    core)
        # External Postgres via compose. Bootstrap reads SHS_DATABASE_URL.
        # PYTHONPATH covers /app/api (bootstrap's deferred `from scripts.*` imports) and /app/worker (api code imports studio_workers.contracts).
        cd /app/api
        PATH="/app/api/.venv/bin:$PATH" PYTHONPATH="/app/api:/app/worker" python3 scripts/bootstrap.py
        ;;
esac

# --- Step 6: consume CF token, load .env, then hand off to CMD -----------
# Consume before load_env_safe so a freshly-dropped token lands in .env and
# then in process env for the autostart gate below.
consume_cf_token

# Supervisord doesn't read .env files. Child programs that don't ship their
# own load_dotenv() call (workers - pydantic env_file points at
# /app/worker/envs/, which doesn't exist in the image) need vars in process
# env. We pump /workspace/.env into our own env so supervisord and every
# spawned child inherit. Process env (docker run -e) wins over .env (matches
# pydantic-settings precedence and api/main.py:load_dotenv(override=False)).
load_env_safe "$WORKSPACE_ENV"

# Seed worker numprocs until first bootstrap; after that the console owns them.
export SHS_GENERAL_WORKERS="${SHS_GENERAL_WORKERS:-1}"
export SHS_TRANSFER_WORKERS="${SHS_TRANSFER_WORKERS:-1}"
if [ ! -f /workspace/.bootstrapped ]; then
    set_worker_numprocs /etc/supervisor/conf.d/worker-general.conf "$SHS_GENERAL_WORKERS"
    set_worker_numprocs /etc/supervisor/conf.d/worker-transfer.conf "$SHS_TRANSFER_WORKERS"
fi

# cloudflared autostarts only when a tunnel token is present (core/full parity
# with split's compose profile): token in .env → tunnel comes up on boot, no
# manual kick; absent → stays stopped, no crash-loop. cloudflared.conf reads
# autostart=%(ENV_CLOUDFLARED_AUTOSTART)s at conf-load, so this MUST be exported
# before exec, and always set (unset → supervisord conf-load fails).
if [ -n "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]; then
    export CLOUDFLARED_AUTOSTART=true
else
    export CLOUDFLARED_AUTOSTART=false
fi

echo "Starting supervisord (shape=$SHAPE)..."
exec "$@"
