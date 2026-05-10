#!/bin/bash
# api/docker/ui-start.sh
# Render /app/ui/public/__env.js from /workspace/.env, then exec node.
#
# Next.js inlines NEXT_PUBLIC_* into the client bundle at build time, which
# would tie the image to a single API URL. ui/shared/lib/config.ts reads
# window.__ENV first, falling back to the build-time bake - so we just need
# to write __env.js with runtime values before node starts.
#
# Re-rendered on every `supervisorctl restart ui`, so studio-console's
# CF wizard can write new domain values to .env and a UI restart picks
# them up without a container rebuild.
set -euo pipefail

WORKSPACE_ENV="/workspace/.env"
PUBLIC_DIR="/app/ui/public"

# Read a key from .env (strip surrounding quotes), or fall back to a default.
read_env_or() {
    local key="$1" fallback="$2" value=""
    if [ -f "$WORKSPACE_ENV" ]; then
        value="$(grep -E "^${key}=" "$WORKSPACE_ENV" | tail -1 | cut -d= -f2-)"
        value="${value%\"}"; value="${value#\"}"
        value="${value%\'}"; value="${value#\'}"
    fi
    echo "${value:-$fallback}"
}

API_URL="$(read_env_or SHS_API_BASE_URL "http://localhost:8000")"
WS_URL="$(read_env_or SHS_WS_URL "ws://localhost:8000")"
FRONTEND_URL="$(read_env_or SHS_FRONTEND_URL "http://localhost:3000")"

mkdir -p "$PUBLIC_DIR"
cat > "$PUBLIC_DIR/__env.js" <<EOF
window.__ENV = {
  NEXT_PUBLIC_API_URL: "$API_URL",
  NEXT_PUBLIC_WS_URL: "$WS_URL",
  NEXT_PUBLIC_FRONTEND_URL: "$FRONTEND_URL"
};
EOF

echo "ui: rendered __env.js (api=$API_URL ws=$WS_URL frontend=$FRONTEND_URL)"
exec node server.js
