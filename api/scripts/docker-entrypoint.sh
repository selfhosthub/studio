#!/bin/bash
set -e

mkdir -p /workspace

# Auto-bootstrap: if no .env symlink, create one
if [ ! -L /app/.env ]; then
    # First boot: copy template to workspace if not exists
    if [ ! -f /workspace/.env ]; then
        cp /app/envs/.env.prod /workspace/.env
        echo "Created /workspace/.env from template"
    fi
    # Symlink so pydantic-settings finds it
    ln -sf /workspace/.env /app/.env
    echo "Symlinked /app/.env -> /workspace/.env"
fi

# Run bootstrap (creates super-org + super-admin on first boot)
python3 /app/scripts/bootstrap.py

# Worker scaling (defaults to 1 each, override via env)
export SHS_GENERAL_WORKERS=${SHS_GENERAL_WORKERS:-1}
export SHS_TRANSFER_WORKERS=${SHS_TRANSFER_WORKERS:-1}

exec "$@"
