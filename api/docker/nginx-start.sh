#!/bin/bash
# api/docker/nginx-start.sh
# Render the listen port into nginx.conf from SHS_NGINX_PORT, then exec nginx
# in the foreground for supervisord. Re-rendered on every restart so a port
# change in .env takes effect after `supervisorctl restart nginx`.
#
# nginx does no env interpolation of its own; envsubst fills the
# ${SHS_NGINX_PORT} and ${SHS_API_HOSTNAME} placeholders. Only those vars are
# substituted so other nginx $variables (e.g. $host) survive untouched.
set -euo pipefail

WORKSPACE_ENV="/workspace/.env"
SRC="/etc/nginx/nginx.conf.template"
DST="/etc/nginx/nginx.conf"

# Default 80, matching the split-stack convention (SHS_NGINX_PORT).
PORT="${SHS_NGINX_PORT:-}"
if [ -z "$PORT" ] && [ -f "$WORKSPACE_ENV" ]; then
    PORT="$(grep -E '^SHS_NGINX_PORT=' "$WORKSPACE_ENV" | tail -1 | cut -d= -f2- || true)"
    PORT="${PORT%\"}"; PORT="${PORT#\"}"
fi
export SHS_NGINX_PORT="${PORT:-80}"

# API hostname for the dedicated api server block. The placeholder default
# starts with an underscore so it never matches a real Host header.
API_HOSTNAME="${SHS_API_HOSTNAME:-}"
if [ -z "$API_HOSTNAME" ] && [ -f "$WORKSPACE_ENV" ]; then
    API_HOSTNAME="$(grep -E '^SHS_API_HOSTNAME=' "$WORKSPACE_ENV" | tail -1 | cut -d= -f2- || true)"
    API_HOSTNAME="${API_HOSTNAME%\"}"; API_HOSTNAME="${API_HOSTNAME#\"}"
fi
export SHS_API_HOSTNAME="${API_HOSTNAME:-_api_hostname_unset}"

mkdir -p /var/run/nginx /var/log/supervisor
envsubst '${SHS_NGINX_PORT} ${SHS_API_HOSTNAME}' < "$SRC" > "$DST"

echo "nginx: listening on ${SHS_NGINX_PORT}"
exec nginx -c "$DST" -g 'daemon off;'
