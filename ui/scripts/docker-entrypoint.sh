#!/bin/bash
set -e

# Ensure workspace directory exists
mkdir -p /workspace

# Initialize /workspace/.env from environment if it doesn't exist
if [ ! -f /workspace/.env ]; then
    cat > /workspace/.env << ENVEOF
SHS_ENV=${SHS_ENV:?SHS_ENV is required}
NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL:?NEXT_PUBLIC_API_URL is required - set in .env}
NEXT_PUBLIC_WS_URL=${NEXT_PUBLIC_WS_URL:?NEXT_PUBLIC_WS_URL is required - set in .env}
NEXT_PUBLIC_API_ENV=${NEXT_PUBLIC_API_ENV:-production}
ENVEOF
    echo "Created /workspace/.env from environment"
else
    echo "Found existing /workspace/.env"
fi

# Create symlink from /app/.env to /workspace/.env
if [ -L /app/.env ]; then
    rm /app/.env
fi
ln -sf /workspace/.env /app/.env
echo "✅ Created symlink /app/.env → /workspace/.env"

# Execute the main command (passed as arguments to this script)
exec "$@"
