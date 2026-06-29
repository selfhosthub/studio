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

# nginx is the single front door: the browser reaches /api and /ws on the
# same nginx origin, so the browser bundle's API/WS/frontend defaults all
# collapse to that origin (default :80). /api,/ws route to the API internally.
NGINX_PORT="$(read_env_or SHS_NGINX_PORT "80")"
NGINX_ORIGIN="http://localhost:${NGINX_PORT}"
NGINX_WS_ORIGIN="ws://localhost:${NGINX_PORT}"

# Browser bundle gets the PUBLIC URL; SSR (process env SHS_API_BASE_URL) gets the
# internal one. Bridge: fall back to SHS_API_BASE_URL for one release so images
# pulled ahead of a console upgrade still boot. Next release will exit 1 instead.
API_URL="$(read_env_or SHS_PUBLIC_API_URL "")"
if [ -z "$API_URL" ]; then
    echo "DEPRECATION: SHS_PUBLIC_API_URL is not set, falling back to SHS_API_BASE_URL. This fallback will be removed in the next release. Upgrade studio-console and re-run the wizard."
    API_URL="$(read_env_or SHS_API_BASE_URL "$NGINX_ORIGIN")"
fi
WS_URL="$(read_env_or SHS_WS_URL "$NGINX_WS_ORIGIN")"
FRONTEND_URL="$(read_env_or SHS_FRONTEND_URL "$NGINX_ORIGIN")"

mkdir -p "$PUBLIC_DIR"
cat > "$PUBLIC_DIR/__env.js" <<EOF
window.__ENV = {
  NEXT_PUBLIC_API_URL: "$API_URL",
  NEXT_PUBLIC_WS_URL: "$WS_URL",
  NEXT_PUBLIC_FRONTEND_URL: "$FRONTEND_URL"
};
EOF

# SSR (ui/shared/api/server.ts:getServerApiUrl) reads SHS_API_BASE_URL from
# process env per request and throws if unset - no public fallback by design
# (that would hairpin SSR out of the container). In the full image api and ui
# share the container, so SSR reaches the API at localhost:$PORT. Honor an
# operator .env override; otherwise default to the in-container API.
SSR_API_URL="$(read_env_or SHS_API_BASE_URL "http://localhost:${PORT:-8000}")"
export SHS_API_BASE_URL="$SSR_API_URL"

echo "ui: rendered __env.js (api=$API_URL ws=$WS_URL frontend=$FRONTEND_URL ssr=$SSR_API_URL)"
exec node server.js
