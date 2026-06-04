#!/bin/bash
# api/docker/entrypoint.sh
# First-boot bootstrap + supervisord handoff for Core and Full images.
# Shape is read from /etc/studio-shape (baked at image build time).
#
# Two paths:
#
#   A. Default CMD (supervisord) → full first-boot:
#      1. /workspace/.env exists → use as-is, generate nothing.
#      2. /workspace/.env absent → generate SHS_DEPLOYMENT_SHAPE and the
#         three secrets (JWT, worker shared, credential encryption). For
#         Full also POSTGRES_PASSWORD, matching SHS_DATABASE_URL,
#         permissive SHS_CORS_ORIGINS=*, SHS_WORKSPACE_ROOT. 0600 perms.
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
    if [ "$SHAPE" = "full" ]; then
        GEN_PG_PASSWORD="$(openssl rand -hex 32)"
    fi

    {
        echo "# Generated by studio-app entrypoint on first boot."
        echo "# Operator may edit. Subsequent boots leave this file alone."
        echo "SHS_DEPLOYMENT_SHAPE=$SHAPE"
        echo "SHS_STUDIO_VERSION=$SHS_STUDIO_VERSION"
        echo "SHS_JWT_SECRET_KEY=$GEN_JWT"
        echo "SHS_WORKER_SHARED_SECRET=$GEN_WORKER"
        echo "SHS_CREDENTIAL_ENCRYPTION_KEY=$GEN_ENCRYPTION"
        if [ "$SHAPE" = "full" ]; then
            # Full runs Postgres inside the container with this password,
            # and the API connects to it at localhost.
            echo "POSTGRES_PASSWORD=$GEN_PG_PASSWORD"
            echo "SHS_DATABASE_URL=postgresql+asyncpg://postgres:${GEN_PG_PASSWORD}@localhost:5432/selfhost_studio"
            # Permissive CORS + placeholder public URL at first boot - RunPod
            # operators don't know their public URL until the pod is running.
            # Tighten via the in-container console once the domain is known.
            echo "SHS_CORS_ORIGINS=*"
            echo "SHS_PUBLIC_BASE_URL=http://localhost:8000"
            echo "SHS_WORKSPACE_ROOT=/workspace"
        fi
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
        PATH="/app/api/.venv/bin:$PATH" PYTHONPATH="/app/api" python3 scripts/bootstrap.py

        echo "Stopping temporary PostgreSQL (supervisord will manage it)..."
        su - postgres -c "$PG_BIN/pg_ctl -D $PG_DATA stop"

        export SHS_PG_DATA="$PG_DATA"
        export SHS_GENERAL_WORKERS="${SHS_GENERAL_WORKERS:-1}"
        export SHS_TRANSFER_WORKERS="${SHS_TRANSFER_WORKERS:-1}"
        ;;
    core)
        # External Postgres via compose. Bootstrap reads SHS_DATABASE_URL.
        cd /app/api
        python3 scripts/bootstrap.py
        export SHS_GENERAL_WORKERS="${SHS_GENERAL_WORKERS:-1}"
        export SHS_TRANSFER_WORKERS="${SHS_TRANSFER_WORKERS:-1}"
        ;;
esac

# --- Step 6: load .env into process env, then hand off to CMD ------------
# Supervisord doesn't read .env files. Child programs that don't ship their
# own load_dotenv() call (workers - pydantic env_file points at
# /app/worker/envs/, which doesn't exist in the image) need vars in process
# env. We pump /workspace/.env into our own env so supervisord and every
# spawned child inherit. Process env (docker run -e) wins over .env (matches
# pydantic-settings precedence and api/main.py:load_dotenv(override=False)).
load_env_safe() {
    [ -f "$1" ] || return 0
    while IFS='=' read -r key value || [ -n "$key" ]; do
        # Skip blank lines and comments
        [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
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
load_env_safe "$WORKSPACE_ENV"

echo "Starting supervisord (shape=$SHAPE)..."
exec "$@"
