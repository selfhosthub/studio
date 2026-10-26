#!/bin/bash
# api/scripts/docker-entrypoint.sh
set -e

WORKSPACE_ENV="/workspace/.env"
ENV_TEMPLATE="/app/envs/.env.prod"

# Copy the env template to the workspace owner-only when no .env exists yet.
seed_workspace_env() {
    [ -f "$WORKSPACE_ENV" ] && return 0
    (umask 077 && cp "$ENV_TEMPLATE" "$WORKSPACE_ENV")
    chmod 0600 "$WORKSPACE_ENV"
    echo "Created $WORKSPACE_ENV from template"
}

# Tighten an existing .env to 0600 when this uid owns it; a foreign-owned file is left as is.
secure_workspace_env() {
    { [ -f "$WORKSPACE_ENV" ] && [ -O "$WORKSPACE_ENV" ]; } || return 0
    chmod 0600 "$WORKSPACE_ENV" 2>/dev/null || echo "WARNING: could not chmod 0600 $WORKSPACE_ENV" >&2
}

# When sourced (e.g. by tests), expose functions and stop.
(return 0 2>/dev/null) && return 0

mkdir -p /workspace

# Auto-bootstrap: if no .env symlink, create one
if [ ! -L /app/.env ]; then
    seed_workspace_env
    # Symlink so pydantic-settings finds it
    ln -sf "$WORKSPACE_ENV" /app/.env
    echo "Symlinked /app/.env -> $WORKSPACE_ENV"
fi
secure_workspace_env

# Run bootstrap (creates super-org + super-admin on first boot)
python3 /app/scripts/bootstrap.py

# Worker scaling (defaults to 1 each, override via env)
export SHS_GENERAL_WORKERS=${SHS_GENERAL_WORKERS:-1}
export SHS_TRANSFER_WORKERS=${SHS_TRANSFER_WORKERS:-1}

exec "$@"
